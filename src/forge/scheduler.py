"""Recursive graph scheduler: executes a typed GraphSpec, level by level.

The scheduler is the commander's dispatch layer above `FleetController`:

- Non-planner nodes (specialist/verifier/...) execute through the existing
  bounded `FleetController` — verification authority is unchanged.
- Planner nodes expand: the injected `planner` callable receives the node and
  returns a `GraphSpec`, which is executed recursively, bounded by `max_depth`.
- Judge nodes route: the injected `judge` callable evaluates the judged node's
  result and returns a decision (continue / retry / reroute / escalate / stop).
  `retry` re-runs the judged node within a bounded budget; `escalate`/`stop`
  mark the judged node blocked with the judge's reason preserved.

Determinism rules:
- Ledger events record graph_started / planner_expanded / routing_decision /
  graph_completed per level.
- Runner exceptions are never swallowed: they surface to the caller.
- A graph passes only when every node result passes.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from time import monotonic
from typing import Any, Callable

from .fleet import FleetController
from .graph import GraphRunResult, GraphSpec, NodeResult, NodeSpec, to_taskgraph
from .ledger import Ledger
from .memory import Observation, render_recall
from .schema import GoalSpec

_TERMINAL_STATUSES = ("passed", "failed", "blocked", "stopped")
_DECISIONS = ("continue", "retry", "reroute", "escalate", "stop")


class GraphScheduler:
    """Execute a GraphSpec with planner subgraph expansion and judge routing."""

    def __init__(
        self,
        root: Path,
        *,
        runner_factory: Callable[[Any], Any],
        planner: Callable[..., GraphSpec] | None = None,
        judge: Callable[[NodeSpec, NodeResult], Any] | None = None,
        memory: Any | None = None,
        clock: Callable[[], float] = monotonic,
        max_depth: int = 3,
        max_retries: int = 1,
    ) -> None:
        self.root = root
        self.runner_factory = runner_factory
        self.planner = planner
        self.judge = judge
        self.memory = memory
        self.clock = clock
        self.max_depth = max_depth
        self.max_retries = max_retries
        self.ledger = Ledger(root)

    def run(
        self,
        graph: GraphSpec,
        *,
        graph_id: str,
        goal: GoalSpec | None = None,
        depth: int = 0,
        resume: bool = False,
    ) -> GraphRunResult:
        """Execute a graph. With ``resume=True``, nodes already checkpointed as
        ``passed`` are reused instead of re-executed (work nodes only; planner
        re-expansion is not yet checkpointed)."""
        if depth > self.max_depth:
            raise ValueError(f"max_depth {self.max_depth} exceeded at depth {depth}")

        self.ledger.run(graph_id, graph.rationale, "C0", "forge-scheduler", "running")
        self.ledger.event(graph_id, "graph_started", "scheduler", {
            "node_count": len(graph.nodes),
            "depth": depth,
        })

        planner_nodes = [node for node in graph.nodes if node.node_type == "planner"]
        judge_nodes = [node for node in graph.nodes if node.node_type == "judge"]
        if self.judge is None:
            work_nodes = [node for node in graph.nodes if node.node_type != "planner"]
        else:
            work_nodes = [
                node for node in graph.nodes if node.node_type not in ("planner", "judge")
            ]

        if planner_nodes and self.planner is None:
            raise ValueError("planner nodes require a planner callable")

        planner_ids = {node.node_id for node in planner_nodes}
        work_ids = {node.node_id for node in work_nodes}
        for node in planner_nodes:
            if any(dep in work_ids for dep in node.deps):
                raise ValueError(
                    f"planner node '{node.node_id}' cannot depend on work nodes in this version"
                )

        results_by_id: dict[str, NodeResult] = {}
        effective_goal = goal or self._synthetic_goal(graph)

        for node in planner_nodes:
            memory_context = ""
            if self.memory is not None:
                # Recall is semantic across the whole fabric. Do NOT filter by
                # node_id: an instance id is not a task family, and filtering by
                # it would stop a run from ever recalling prior runs' context.
                recalled = self.memory.recall(query=node.goal, limit=5)
                memory_context = render_recall(recalled)
                self.ledger.event(graph_id, "memory_recall", "scheduler", {
                    "node_id": node.node_id,
                    "count": len(recalled),
                    "rendered_chars": len(memory_context),
                })
            subgraph = self._expand_planner(node, memory_context)
            if subgraph is None:
                raise ValueError(f"planner produced no subgraph for node '{node.node_id}'")
            self.ledger.event(graph_id, "planner_expanded", "scheduler", {
                "node_id": node.node_id,
                "subgraph_node_count": len(subgraph.nodes),
                "depth": depth,
            })
            sub_result = self.run(
                subgraph,
                graph_id=f"{graph_id}:{node.node_id}",
                goal=goal,
                depth=depth + 1,
            )
            results_by_id[node.node_id] = NodeResult(
                node_id=node.node_id,
                status=sub_result.status,
                observations=(),
                evidence_refs=(f"graph:{graph_id}:{node.node_id}",),
                subgraph=sub_result,
            )
            if self.memory is not None:
                self.memory.write(Observation(
                    node_id=f"{graph_id}:{node.node_id}",
                    kind="outcome",
                    description=(
                        f"planner {node.node_id} {sub_result.status} for goal "
                        f"'{node.goal[:160]}': expanded into {len(subgraph.nodes)} nodes"
                    ),
                    task_family=node.node_id,
                    evidence_refs=(f"graph:{graph_id}:{node.node_id}",),
                    activation="high",
                ))
                self.ledger.event(graph_id, "memory_write", "scheduler", {
                    "node_id": node.node_id,
                    "kind": "outcome",
                    "status": sub_result.status,
                })

        node_priors: dict[str, str] = {}
        work_attempt: int | None = None
        if work_nodes:
            dispatch = self._strip_satisfied_deps(work_nodes, planner_ids)
            skipped_ids: set[str] = set()
            if resume:
                for node in dispatch:
                    row = self.ledger.get_graph_node(graph_id, node.node_id)
                    if row is not None and row["status"] == "passed":
                        results_by_id[node.node_id] = NodeResult(
                            node_id=node.node_id,
                            status="passed",
                            evidence_refs=(row.get("evidence_ref") or f"graph:{graph_id}",),
                        )
                        skipped_ids.add(node.node_id)
                        self.ledger.event(graph_id, "node_resumed", "scheduler", {
                            "node_id": node.node_id,
                            "status": "passed",
                        })
            remaining = [node for node in dispatch if node.node_id not in skipped_ids]
            if remaining:
                work_attempt = self._next_attempt(graph_id)
                for node in remaining:
                    row = self.ledger.get_graph_node(graph_id, node.node_id)
                    if row is None:
                        self.ledger.ensure_graph_node(
                            graph_id, node.node_id, attempt=work_attempt
                        )
                        node_priors[node.node_id] = "pending"
                    else:
                        node_priors[node.node_id] = row["status"]
                results_by_id.update(
                    self._run_work(
                        remaining,
                        effective_goal,
                        f"{graph_id}:work:{work_attempt}",
                        graph.max_parallel,
                    )
                )

        if judge_nodes and self.judge is not None:
            self._apply_routing(
                graph_id=graph_id,
                judge_nodes=judge_nodes,
                results_by_id=results_by_id,
                effective_goal=effective_goal,
                nodes_by_id={node.node_id: node for node in graph.nodes},
            )

        # Persist each node's FINAL status (after any judge retry/escalation) so a
        # later resume can trust the checkpoint. Compare-and-set on the status we
        # observed at dispatch time; a miss means a stale/unexpected writer.
        for node_id, prior in node_priors.items():
            final = results_by_id.get(node_id)
            if final is None:
                continue
            recorded = self.ledger.update_graph_node(
                graph_id,
                node_id,
                expected_status=prior,
                status=final.status,
                attempt=work_attempt,
                evidence_ref=final.evidence_refs[0] if final.evidence_refs else None,
            )
            if not recorded:
                self.ledger.event(graph_id, "graph_node_cas_miss", "scheduler", {
                    "node_id": node_id,
                    "expected_status": prior,
                })

        results = [
            results_by_id[node.node_id]
            for node in graph.nodes
            if node.node_id in results_by_id
        ]
        status = "passed" if results and all(r.status == "passed" for r in results) else "failed"
        self.ledger.event(graph_id, "graph_completed", "scheduler", {
            "status": status,
            "node_count": len(results),
            "depth": depth,
        })
        self.ledger.update_run_status(graph_id, status)
        if self.memory is not None:
            self.memory.write(Observation(
                node_id=graph_id,
                kind="outcome",
                description=(
                    f"graph {graph_id} {status} for goal '{graph.rationale[:160]}': "
                    f"{len(results)} nodes at depth {depth}"
                ),
                task_family=graph_id,
                evidence_refs=(f"graph:{graph_id}",),
                activation="high",
            ))
            self.ledger.event(graph_id, "memory_write", "scheduler", {
                "node_id": graph_id,
                "kind": "outcome",
                "status": status,
            })
        return GraphRunResult(graph_id=graph_id, status=status, node_results=tuple(results))

    def _apply_routing(
        self,
        *,
        graph_id: str,
        judge_nodes: list[NodeSpec],
        results_by_id: dict[str, NodeResult],
        effective_goal: GoalSpec,
        nodes_by_id: dict[str, NodeSpec],
    ) -> None:
        retries_used: dict[str, int] = {}
        for judge_node in judge_nodes:
            judged_id = next(
                (dep for dep in judge_node.deps if dep in results_by_id), None
            )
            if judged_id is None:
                raise ValueError(
                    f"judge node '{judge_node.node_id}' has no completed dependency to judge"
                )
            judged = results_by_id[judged_id]
            raw = self.judge(judge_node, judged) if self.judge is not None else None
            if isinstance(raw, dict):
                decision = raw.get("decision")
                reason = str(raw.get("reason", ""))
            else:
                decision = getattr(raw, "decision", None)
                reason = str(getattr(raw, "reason", ""))
            if decision not in _DECISIONS:
                raise ValueError(f"invalid routing decision: {decision!r}")

            self.ledger.event(graph_id, "routing_decision", "scheduler", {
                "judge_node_id": judge_node.node_id,
                "judged_node_id": judged_id,
                "decision": decision,
                "reason": reason,
            })

            if decision == "retry":
                used = retries_used.get(judged_id, 0)
                if used < self.max_retries:
                    retries_used[judged_id] = used + 1
                    node_spec = nodes_by_id.get(judged_id)
                    if node_spec is None:
                        raise ValueError(
                            f"cannot retry '{judged_id}': node spec not available to the scheduler"
                        )
                    retry_spec = node_spec.model_copy(update={"deps": []})
                    retried = self._run_work(
                        [retry_spec],
                        effective_goal,
                        f"{graph_id}:retry{retries_used[judged_id]}",
                        1,
                    )
                    results_by_id.update(retried)
            elif decision in ("escalate", "stop"):
                results_by_id[judged_id] = judged.model_copy(update={
                    "status": "blocked",
                    "observations": ((reason or f"judge_{decision}"),),
                })

            judge_status = "blocked" if decision in ("escalate", "stop") else "passed"
            results_by_id[judge_node.node_id] = NodeResult(
                node_id=judge_node.node_id,
                status=judge_status,
                observations=(reason,) if reason else (),
                evidence_refs=(f"graph:{graph_id}:{judge_node.node_id}",),
            )
            if self.memory is not None:
                self.memory.write(Observation(
                    node_id=f"{graph_id}:{judge_node.node_id}",
                    kind="decision",
                    description=(
                        f"judge {judge_node.node_id} on {judged_id}: {decision} ({reason})"
                    ),
                    task_family=judged_id,
                    evidence_refs=(f"graph:{graph_id}:{judge_node.node_id}",),
                    activation="high",
                ))
                self.ledger.event(graph_id, "memory_write", "scheduler", {
                    "node_id": judge_node.node_id,
                    "kind": "decision",
                    "decision": decision,
                })

    def _expand_planner(self, node: NodeSpec, memory_context: str) -> GraphSpec | None:
        """Call the planner with recalled context when it accepts a second argument.

        Signature detection is deterministic (inspect.signature), so a one-arg
        planner keeps working unchanged and a two-arg planner receives the
        rendered recall block.
        """
        if self.planner is None:
            return None
        if not self._planner_accepts_context():
            return self.planner(node)
        return self.planner(node, memory_context)

    def _planner_accepts_context(self) -> bool:
        if self.planner is None:
            return False
        try:
            parameters = list(inspect.signature(self.planner).parameters.values())
        except (TypeError, ValueError):
            return False
        positional = [
            parameter
            for parameter in parameters
            if parameter.kind
            in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
        ]
        return len(positional) >= 2

    def _next_attempt(self, graph_id: str) -> int:
        """Next attempt number for this graph: one past the highest on record."""
        rows = self.ledger.list_graph_nodes(graph_id)
        if not rows:
            return 1
        return max(int(row["attempt"]) for row in rows) + 1

    def _strip_satisfied_deps(
        self, nodes: list[NodeSpec], planner_ids: set[str]
    ) -> list[NodeSpec]:
        adjusted: list[NodeSpec] = []
        for node in nodes:
            if any(dep in planner_ids for dep in node.deps):
                node = node.model_copy(
                    update={"deps": [dep for dep in node.deps if dep not in planner_ids]}
                )
            adjusted.append(node)
        return adjusted

    def _run_work(
        self,
        nodes: list[NodeSpec],
        goal: GoalSpec,
        run_id: str,
        max_parallel: int,
    ) -> dict[str, NodeResult]:
        work_spec = GraphSpec(
            nodes=nodes,
            max_parallel=max_parallel,
            max_depth=1,
            rationale=goal.goal,
        )
        controller = FleetController(
            self.root,
            runner_factory=self.runner_factory,
            memory=self.memory,
            clock=self.clock,
        )
        report = controller.run(goal, to_taskgraph(work_spec), run_id=run_id)
        collected: dict[str, NodeResult] = {}
        for outcome in report.task_outcomes:
            status = outcome.status if outcome.status in _TERMINAL_STATUSES else "failed"
            observations: tuple[str, ...] = ()
            if status != "passed" and outcome.reason:
                observations = (outcome.reason,)
            collected[outcome.task_id] = NodeResult(
                node_id=outcome.task_id,
                status=status,
                observations=observations,
                evidence_refs=(f"run:{outcome.run_id}",),
            )
        return collected

    def _synthetic_goal(self, graph: GraphSpec) -> GoalSpec:
        """Minimal goal for executor-level invariants when the caller gives none."""
        acceptance = ["graph completed"]
        for node in graph.nodes:
            if node.acceptance:
                acceptance = list(node.acceptance)
                break
        return GoalSpec(
            goal=graph.rationale,
            repo=str(self.root),
            acceptance=acceptance,
            harness="local",
            max_parallel=graph.max_parallel,
        )
