from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from forge.graph import GraphSpec, NodeSpec
from forge.scheduler import GraphScheduler


def _specialist(node_id: str = "s1") -> NodeSpec:
    return NodeSpec(
        node_id=node_id,
        node_type="specialist",
        title=f"work {node_id}",
        goal=f"do {node_id}",
        acceptance=["done"],
    )


def _planner(node_id: str = "p1") -> NodeSpec:
    return NodeSpec(
        node_id=node_id,
        node_type="planner",
        title=f"plan {node_id}",
        goal=f"plan {node_id}",
        acceptance=["plan exists"],
    )


def _passing_runner():
    return SimpleNamespace(
        run=lambda req: SimpleNamespace(
            status="passed",
            session_id=f"session-{req.worker_name}",
            worktree=None,
            artifact_exists=True,
            verification_passed=True,
            classification=SimpleNamespace(value="passed"),
            reason="completed",
        )
    )


def test_scheduler_runs_leaf_graph(tmp_path: Path) -> None:
    scheduler = GraphScheduler(tmp_path, runner_factory=lambda req: _passing_runner())
    result = scheduler.run(GraphSpec(nodes=[_specialist()]), graph_id="g-leaf")
    assert result.status == "passed"
    assert [item.node_id for item in result.node_results] == ["s1"]


def test_scheduler_expands_planner_node_into_subgraph(tmp_path: Path) -> None:
    def planner(node: NodeSpec) -> GraphSpec:
        return GraphSpec(nodes=[_specialist("child")], rationale="planner output")

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda req: _passing_runner(),
        planner=planner,
    )
    result = scheduler.run(GraphSpec(nodes=[_planner()]), graph_id="g-expand")
    assert result.status == "passed"
    planner_result = result.node_results[0]
    assert planner_result.subgraph is not None
    assert planner_result.subgraph.status == "passed"
    assert planner_result.subgraph.node_results[0].node_id == "child"


def test_scheduler_enforces_max_depth(tmp_path: Path) -> None:
    def planner(node: NodeSpec) -> GraphSpec:
        return GraphSpec(nodes=[_planner(node_id="p2")], rationale="nested planner")

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda req: _passing_runner(),
        planner=planner,
        max_depth=1,
    )
    with pytest.raises(ValueError, match="max_depth"):
        scheduler.run(GraphSpec(nodes=[_planner()]), graph_id="g-depth")


def test_scheduler_requires_planner_callable_for_planner_nodes(tmp_path: Path) -> None:
    scheduler = GraphScheduler(tmp_path, runner_factory=lambda req: _passing_runner())
    with pytest.raises(ValueError, match="planner"):
        scheduler.run(GraphSpec(nodes=[_planner()]), graph_id="g-no-planner")
