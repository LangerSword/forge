from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from forge.graph import GraphSpec, NodeSpec
from forge.memory import LocalMemoryStub, Observation
from forge.scheduler import GraphScheduler


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


def _specialist(node_id: str = "s1") -> NodeSpec:
    return NodeSpec(node_id=node_id, node_type="specialist", title="work", goal="do work", acceptance=["done"])


def _judge(node_id: str = "j1", deps: list[str] | None = None) -> NodeSpec:
    return NodeSpec(node_id=node_id, node_type="judge", title="judge", goal="judge", acceptance=["decision"], deps=deps or ["s1"])


def _planner(node_id: str = "p1") -> NodeSpec:
    return NodeSpec(node_id=node_id, node_type="planner", title="plan", goal="plan the work", acceptance=["plan"])


def test_scheduler_injects_recall_into_two_arg_planner(tmp_path: Path) -> None:
    memory = LocalMemoryStub()
    memory.write(Observation(
        node_id="prior-run",
        kind="design_pattern",
        description="use frosted glass cards for the settings panel",
        task_family="p1",
    ))
    seen: dict[str, str] = {}

    def planner(node: NodeSpec, memory_context: str) -> GraphSpec:
        seen["context"] = memory_context
        return GraphSpec(nodes=[_specialist("child")], rationale="expanded")

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: _passing_runner(),
        planner=planner,
        memory=memory,
    )
    result = scheduler.run(GraphSpec(nodes=[_planner()]), graph_id="g-mem-planner")

    assert result.status == "passed"
    assert "frosted glass cards" in seen["context"]

    events = scheduler.ledger.events_for_run("g-mem-planner")
    recalls = [event for event in events if event["kind"] == "memory_recall"]
    assert len(recalls) == 1
    assert recalls[0]["payload"]["node_id"] == "p1"
    assert recalls[0]["payload"]["count"] == 1

    # planner outcome observation is written under the planner node's family
    assert memory.profile(tag="p1")["kinds"].get("outcome") == 1


def test_scheduler_still_supports_one_arg_planner(tmp_path: Path) -> None:
    memory = LocalMemoryStub()

    def planner(node: NodeSpec) -> GraphSpec:
        return GraphSpec(nodes=[_specialist("child")], rationale="expanded")

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: _passing_runner(),
        planner=planner,
        memory=memory,
    )
    result = scheduler.run(GraphSpec(nodes=[_planner()]), graph_id="g-mem-one-arg")

    assert result.status == "passed"
    # recall still recorded even though the planner ignores the context
    events = scheduler.ledger.events_for_run("g-mem-one-arg")
    assert any(event["kind"] == "memory_recall" for event in events)


def test_scheduler_writes_judge_decisions_as_observations(tmp_path: Path) -> None:
    memory = LocalMemoryStub()

    def judge(node, result):
        return {"decision": "continue", "reason": "looks good"}

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: _passing_runner(),
        judge=judge,
        memory=memory,
    )
    report = scheduler.run(GraphSpec(nodes=[_specialist(), _judge()]), graph_id="g-mem-judge")

    assert report.status == "passed"
    profile = memory.profile(tag="s1")
    assert profile["kinds"].get("decision") == 1

    events = scheduler.ledger.events_for_run("g-mem-judge")
    writes = [
        event
        for event in events
        if event["kind"] == "memory_write" and event["payload"].get("kind") == "decision"
    ]
    assert len(writes) == 1
    assert writes[0]["payload"]["decision"] == "continue"


def test_scheduler_writes_graph_level_outcome(tmp_path: Path) -> None:
    memory = LocalMemoryStub()
    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: _passing_runner(),
        memory=memory,
    )
    scheduler.run(GraphSpec(nodes=[_specialist()]), graph_id="g-mem-graph")

    graph_profile = memory.profile(tag="g-mem-graph")
    assert graph_profile["kinds"].get("outcome") == 1


def test_scheduler_without_memory_stays_clean(tmp_path: Path) -> None:
    scheduler = GraphScheduler(tmp_path, runner_factory=lambda request: _passing_runner())
    result = scheduler.run(GraphSpec(nodes=[_specialist()]), graph_id="g-no-mem")
    assert result.status == "passed"
    kinds = {event["kind"] for event in scheduler.ledger.events_for_run("g-no-mem")}
    assert "memory_recall" not in kinds
    assert "memory_write" not in kinds


def test_scheduler_recall_crosses_run_boundaries(tmp_path: Path) -> None:
    """Regression: a later run's planner must recall observations from earlier runs.

    The bug: recall was filtered by the node's own id as a 'task family', so a
    planner could only ever recall its own past attempts — never the context
    other nodes wrote. Recall is semantic; the family filter must not be
    applied at injection time.
    """
    memory = LocalMemoryStub()
    memory.write(Observation(
        node_id="run-1:settings-ui",
        kind="outcome",
        description="task settings-ui passed: built the settings panel",
        task_family="settings-ui",
    ))
    captured: dict[str, str] = {}

    def planner(node: NodeSpec, memory_context: str) -> GraphSpec:
        captured["context"] = memory_context
        return GraphSpec(nodes=[_specialist("child")], rationale="planned")

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: _passing_runner(),
        planner=planner,
        memory=memory,
    )
    scheduler.run(GraphSpec(nodes=[_planner()]), graph_id="run-2")

    assert captured["context"], "planner recalled nothing across the run boundary"
    assert "settings panel" in captured["context"]


def test_scheduler_graph_observation_recalls_by_goal(tmp_path: Path) -> None:
    """Regression: the graph-level observation must carry the graph's rationale.

    The bug: the description was 'graph <id> passed: N nodes' — recallable only
    by the run id, never by what the run was about.
    """
    memory = LocalMemoryStub()
    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: _passing_runner(),
        memory=memory,
    )
    scheduler.run(
        GraphSpec(nodes=[_specialist()], rationale="ship the widget settings panel"),
        graph_id="g-goal-text",
    )

    recalled = memory.recall(query="ship the widget settings panel", limit=5)
    assert recalled, "no observations written"
    assert any("widget settings panel" in observation.description for observation in recalled)
