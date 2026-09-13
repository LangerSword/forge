"""Typed execution graph: the canonical input model for the Forge commander.

A goal compiles into a `GraphSpec` — typed nodes (planner, specialist, judge,
verifier, reflector, evaluator, memory, aggregator) connected by typed edges
(sequence, dependency, gate, parallel, judge). The graph is the unit of work
the scheduler dispatches; `to_taskgraph` bridges the single-level subset onto
the existing executor so the working core stays untouched.

This module is intentionally deterministic and LLM-free: it validates and
compiles structure. Node runtimes (agent calls, tools, memory) plug in later.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schema import GoalSpec, TaskGraph, TaskSpec

NodeType = Literal[
    "planner",
    "specialist",
    "judge",
    "verifier",
    "reflector",
    "evaluator",
    "memory",
    "aggregator",
]

EdgeType = Literal["sequence", "dependency", "gate", "parallel", "judge"]

NODE_TYPES: tuple[str, ...] = (
    "planner",
    "specialist",
    "judge",
    "verifier",
    "reflector",
    "evaluator",
    "memory",
    "aggregator",
)

EDGE_TYPES: tuple[str, ...] = ("sequence", "dependency", "gate", "parallel", "judge")


class NodeSpec(BaseModel):
    """One unit of graph work with an explicit type and edge semantics."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,79}$")
    node_type: NodeType
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=4000)
    acceptance: list[str] = Field(min_length=1, max_length=32)
    deps: list[str] = Field(default_factory=list, max_length=16)
    edge_type: EdgeType = "sequence"
    artifact_path: str | None = Field(default=None, min_length=1)
    tools: list[str] = Field(default_factory=list, max_length=32)


class GraphSpec(BaseModel):
    """A validated, bounded execution graph."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[NodeSpec] = Field(min_length=1, max_length=12)
    max_parallel: int = Field(default=1, ge=1, le=3)
    max_depth: int = Field(default=1, ge=1, le=3)
    rationale: str = Field(default="bounded typed graph", max_length=2000)

    @model_validator(mode="after")
    def _validate_graph(self) -> "GraphSpec":
        ids = [node.node_id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate node_id")
        known = set(ids)
        for node in self.nodes:
            for dep in node.deps:
                if dep not in known:
                    raise ValueError(f"unknown dependency: {node.node_id}->{dep}")
        remaining = {node.node_id: set(node.deps) for node in self.nodes}
        resolved: set[str] = set()
        while remaining:
            ready = {node_id for node_id, deps in remaining.items() if deps <= resolved}
            if not ready:
                raise ValueError("cycle in graph")
            resolved.update(ready)
            for node_id in ready:
                remaining.pop(node_id)
        return self


class GraphRunResult(BaseModel):
    """Terminal summary of a graph execution (used for subgraph results)."""

    model_config = ConfigDict(extra="forbid")

    graph_id: str = Field(min_length=1)
    status: Literal["passed", "failed", "blocked", "stopped"]
    node_results: tuple["NodeResult", ...] = ()


class NodeResult(BaseModel):
    """Universal node output: status, structured observations, evidence refs.

    `observations` are the memory entries a node contributes to the context
    fabric; `evidence_refs` point back to ledger runs and artifacts.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(min_length=1)
    status: Literal["passed", "failed", "blocked", "stopped"]
    observations: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    subgraph: GraphRunResult | None = None


class RoutingDecision(BaseModel):
    """What a judge node tells the scheduler to do next."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["continue", "retry", "reroute", "escalate", "stop"]
    reason: str = Field(min_length=1, max_length=500)
    reroute_to: str | None = Field(default=None, min_length=1)


def compile_goal_graph(goal: GoalSpec, *, graph_id: str = "goal") -> GraphSpec:
    """Compile a goal into the smallest typed graph: specialist + verifier gate.

    Deterministic: the same goal always compiles to the same graph. Deeper
    graphs are created by planner nodes at runtime, not by this function.
    """
    specialist = NodeSpec(
        node_id=graph_id,
        node_type="specialist",
        title="Execute the goal",
        goal=goal.goal,
        acceptance=list(goal.acceptance),
        artifact_path=goal.artifact_path,
        tools=list(goal.tools),
    )
    verifier = NodeSpec(
        node_id=f"{graph_id}-verify",
        node_type="verifier",
        title="Independent verification",
        goal=f"Independently verify acceptance for: {goal.goal}",
        acceptance=list(goal.acceptance),
        deps=[specialist.node_id],
        edge_type="gate",
        artifact_path=goal.artifact_path,
    )
    return GraphSpec(
        nodes=[specialist, verifier],
        max_parallel=goal.max_parallel,
        max_depth=1,
        rationale="bounded goal graph: one specialist task behind an independent verifier gate",
    )


def to_taskgraph(graph: GraphSpec) -> TaskGraph:
    """Bridge a single-level GraphSpec onto the current bounded executor.

    The executor dispatches one-level task graphs; deeper graphs must be
    executed by the recursive scheduler, so reject them loudly instead of
    silently flattening the structure.
    """
    if graph.max_depth > 1:
        raise ValueError(f"max_depth {graph.max_depth} exceeds executor support (single-level)")
    return TaskGraph(
        tasks=[
            TaskSpec(
                task_id=node.node_id,
                title=node.title,
                goal=node.goal,
                acceptance=list(node.acceptance),
                deps=list(node.deps),
                artifact_path=node.artifact_path,
            )
            for node in graph.nodes
        ],
        max_parallel=graph.max_parallel,
        rationale=graph.rationale,
    )


def graph_counts(graph: GraphSpec) -> dict[str, Any]:
    """Compact summary for CLI readbacks."""
    by_type: dict[str, int] = {}
    for node in graph.nodes:
        by_type[node.node_type] = by_type.get(node.node_type, 0) + 1
    return {
        "node_count": len(graph.nodes),
        "by_type": by_type,
        "max_parallel": graph.max_parallel,
        "max_depth": graph.max_depth,
    }


NodeResult.model_rebuild()
GraphRunResult.model_rebuild()
