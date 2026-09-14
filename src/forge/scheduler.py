"""Recursive graph scheduler: executes a typed GraphSpec, level by level.

The scheduler is the commander's dispatch layer above `FleetController`:

- Non-planner nodes (specialist/verifier/judge/...) execute through the
  existing bounded `FleetController` — verification authority is unchanged.
- Planner nodes expand: the injected `planner` callable receives the node and
  returns a `GraphSpec`, which is executed recursively, bounded by `max_depth`.

Determinism rules:
- Ledger events record graph_started / planner_expanded / graph_completed.
- Runner exceptions are never swallowed: they surface to the caller.
- A graph passes only when every node result passes.
"""
from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any, Callable

from .fleet import FleetController
from .graph import GraphRunResult, GraphSpec, NodeResult, NodeSpec, to_taskgraph
from .ledger import Ledger
from .schema import GoalSpec

_TERMINAL_STATUSES = ("passed", "failed", "blocked", "stopped")


class GraphScheduler:
    """Execute a GraphSpec with planner-node subgraph expansion."""

    def __init__(
        self,
        root: Path,
        *,
        runner_factory: Callable[[Any], Any],
        planner: Callable[[NodeSpec], GraphSpec] | None = None,
        memory: Any | None = None,
        clock: Callable[[], float] = monotonic,
        max_depth: int = 3,
    ) -> None:
        self.root = root
        self.runner_factory = runner_factory
        self.planner = planner
        self.memory = memory
        self.clock = clock
        self.max_depth = max_depth
        self.ledger = Ledger(root)

    def run(
        self,
        graph: GraphSpec,
        *,
        graph_id: str,
        goal: GoalSpec | None = None,
        depth: int = 0,
    ) -> GraphRunResult:
        if depth > self.max_depth:
            raise ValueError(f"max_depth {self.max_depth} exceeded at depth {depth}")

        self.ledger.run(graph_id, graph.rationale, "C0", "forge-scheduler", "running")
        self.ledger.event(graph_id, "graph_started", "scheduler", {
            "node_count": len(graph.nodes),
            "depth": depth,
        })

        planner_nodes = [node for node in graph.nodes if node.node_type == "planner"]
        work_nodes = [node for node in graph.nodes if node.node_type != "planner"]

        if planner_nodes and self.planner is None:
            raise ValueError("planner nodes require a planner callable")

        planner_ids = {node.node_id for node in planner_nodes}
        work_ids = {node.node_id for node in work_nodes}
        for node in planner_nodes:
            if any(dep in work_ids for dep in node.deps):
                raise ValueError(
                    f"planner node '{node.node_id}' cannot depend on work nodes in this version"
                )

        results: list[NodeResult] = []

        for node in planner_nodes:
            subgraph = self.planner(node) if self.planner is not None else None
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
            results.append(
                NodeResult(
                    node_id=node.node_id,
                    status=sub_result.status,
                    observations=(),
                    evidence_refs=(f"graph:{graph_id}:{node.node_id}",),
                    subgraph=sub_result,
                )
            )

        if work_nodes:
            # Dependencies on planner nodes are already satisfied: the planner's
            # subgraph ran to completion above. Strip those deps so the bounded
            # executor (which only knows this level) validates cleanly.
            adjusted: list[NodeSpec] = []
            for node in work_nodes:
                if any(dep in planner_ids for dep in node.deps):
                    node = node.model_copy(
                        update={"deps": [dep for dep in node.deps if dep not in planner_ids]}
                    )
                adjusted.append(node)

            work_spec = GraphSpec(
                nodes=adjusted,
                max_parallel=graph.max_parallel,
                max_depth=1,
                rationale=graph.rationale,
            )
            controller = FleetController(
                self.root,
                runner_factory=self.runner_factory,
                memory=self.memory,
                clock=self.clock,
            )
            report = controller.run(
                goal or self._synthetic_goal(graph),
                to_taskgraph(work_spec),
                run_id=f"{graph_id}:work",
            )
            for outcome in report.task_outcomes:
                status = outcome.status if outcome.status in _TERMINAL_STATUSES else "failed"
                observations: tuple[str, ...] = ()
                if status != "passed" and outcome.reason:
                    observations = (outcome.reason,)
                results.append(
                    NodeResult(
                        node_id=outcome.task_id,
                        status=status,
                        observations=observations,
                        evidence_refs=(f"run:{outcome.run_id}",),
                    )
                )

        status = "passed" if results and all(r.status == "passed" for r in results) else "failed"
        self.ledger.event(graph_id, "graph_completed", "scheduler", {
            "status": status,
            "node_count": len(results),
            "depth": depth,
        })
        self.ledger.update_run_status(graph_id, status)
        return GraphRunResult(graph_id=graph_id, status=status, node_results=tuple(results))

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
