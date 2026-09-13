"""Tests for the typed execution graph: node types, edge types, validation, compilation."""
from __future__ import annotations

import pytest

from forge.graph import (
    EdgeType,
    GraphSpec,
    NodeResult,
    NodeSpec,
    NodeType,
    RoutingDecision,
    compile_goal_graph,
    to_taskgraph,
)
from forge.schema import GoalSpec


def _node(node_id: str = "a", node_type: str = "specialist", **overrides) -> NodeSpec:
    base = dict(
        node_id=node_id,
        node_type=node_type,
        title=f"node {node_id}",
        goal=f"do {node_id}",
        acceptance=["done"],
    )
    base.update(overrides)
    return NodeSpec(**base)


def test_node_result_records_observations_and_evidence() -> None:
    result = NodeResult(
        node_id="research-1",
        status="passed",
        observations=("card-based layout with frosted glass",),
        evidence_refs=("run:research-1",),
    )
    assert result.status == "passed"
    assert result.observations == ("card-based layout with frosted glass",)
    assert result.evidence_refs == ("run:research-1",)
    assert result.subgraph is None


def test_node_result_rejects_invalid_status() -> None:
    with pytest.raises(Exception):
        NodeResult(node_id="x", status="succeeded", observations=(), evidence_refs=())


def test_routing_decision_vocabulary_is_bounded() -> None:
    for decision in ("continue", "retry", "reroute", "escalate", "stop"):
        assert RoutingDecision(decision=decision, reason="ok").decision == decision
    with pytest.raises(Exception):
        RoutingDecision(decision="maybe", reason="ok")


def test_graph_rejects_invalid_node_type() -> None:
    with pytest.raises(Exception):
        NodeSpec(
            node_id="a",
            node_type="wizard",
            title="x",
            goal="x",
            acceptance=["x"],
        )


def test_graph_rejects_duplicate_node_ids() -> None:
    with pytest.raises(ValueError, match="duplicate node_id"):
        GraphSpec(nodes=[_node("a"), _node("a")])


def test_graph_rejects_unknown_dependencies() -> None:
    with pytest.raises(ValueError, match="unknown dependency"):
        GraphSpec(nodes=[_node("a", deps=["ghost"])])


def test_graph_rejects_cycles() -> None:
    with pytest.raises(ValueError, match="cycle"):
        GraphSpec(nodes=[_node("a", deps=["b"]), _node("b", deps=["a"])])


def test_graph_rejects_exceeding_max_parallel() -> None:
    with pytest.raises(ValueError, match="max_parallel"):
        GraphSpec(nodes=[_node("a")], max_parallel=9)


def test_graph_rejects_exceeding_max_depth() -> None:
    with pytest.raises(ValueError, match="max_depth"):
        GraphSpec(nodes=[_node("a")], max_depth=99)


def test_compile_goal_graph_produces_typed_nodes() -> None:
    goal = GoalSpec(
        goal="build a feature",
        repo="/tmp/repo",
        acceptance=["feature exists"],
        tools=["echo"],
        harness="local",
        artifact_path="out.json",
    )
    graph = compile_goal_graph(goal)
    assert isinstance(graph, GraphSpec)
    types = {node.node_type for node in graph.nodes}
    assert types == {"specialist", "verifier"}
    specialist = next(n for n in graph.nodes if n.node_type == "specialist")
    verifier = next(n for n in graph.nodes if n.node_type == "verifier")
    assert specialist.artifact_path == "out.json"
    assert verifier.deps == [specialist.node_id]
    assert verifier.edge_type == "gate"
    assert graph.max_parallel == goal.max_parallel


def test_compile_goal_graph_is_deterministic() -> None:
    goal = GoalSpec(goal="g", repo="/tmp/r", acceptance=["a"], tools=[], harness="local")
    first = compile_goal_graph(goal)
    second = compile_goal_graph(goal)
    assert first.model_dump() == second.model_dump()


def test_edge_types_are_bounded() -> None:
    for edge in ("sequence", "dependency", "gate", "parallel", "judge"):
        spec = _node("a", edge_type=edge)
        assert spec.edge_type == edge
    with pytest.raises(Exception):
        _node("a", edge_type="teleport")


def test_to_taskgraph_bridge_preserves_ids_and_deps() -> None:
    graph = GraphSpec(
        nodes=[
            _node("build", acceptance=["built"], artifact_path="a.json"),
            _node("check", node_type="verifier", deps=["build"], edge_type="gate"),
        ],
        max_parallel=2,
        rationale="test",
    )
    taskgraph = to_taskgraph(graph)
    assert [t.task_id for t in taskgraph.tasks] == ["build", "check"]
    assert taskgraph.tasks[1].deps == ["build"]
    assert taskgraph.tasks[0].artifact_path == "a.json"
    assert taskgraph.max_parallel == 2


def test_to_taskgraph_rejects_depth_beyond_one_level() -> None:
    """The current executor is single-level; deeper graphs must fail loudly, not silently drop."""
    deep = GraphSpec(nodes=[_node("a")], max_depth=3, rationale="deep")
    with pytest.raises(ValueError, match="max_depth"):
        to_taskgraph(deep)


def test_cli_graph_command_prints_compiled_graph(tmp_path, capsys) -> None:
    import json

    from forge.cli import main_from_args_for_test

    goal_file = tmp_path / "goal.json"
    goal_file.write_text(
        GoalSpec(goal="build it", repo="/tmp/r", acceptance=["works"], tools=[], harness="local").model_dump_json()
    )
    code = main_from_args_for_test(["graph", str(goal_file)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["ok"] is True
    assert out["counts"]["by_type"] == {"specialist": 1, "verifier": 1}
    assert out["counts"]["node_count"] == 2


def test_cli_graph_command_fails_loudly_on_bad_goal(tmp_path, capsys) -> None:
    import json

    from forge.cli import main_from_args_for_test

    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    code = main_from_args_for_test(["graph", str(bad)])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["ok"] is False
