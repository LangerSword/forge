from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from forge.graph import GraphSpec, NodeSpec
from forge.ledger import Ledger
from forge.scheduler import GraphScheduler


def _specialist(node_id: str) -> NodeSpec:
    return NodeSpec(
        node_id=node_id,
        node_type="specialist",
        title=f"work {node_id}",
        goal=f"do {node_id}",
        acceptance=["done"],
    )


def _passed(req):
    return SimpleNamespace(
        status="passed",
        session_id=f"session-{req.worker_name}",
        worktree=None,
        artifact_exists=True,
        verification_passed=True,
        classification=SimpleNamespace(value="passed"),
        reason="completed",
    )


def test_graph_nodes_persist_across_connections(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    ledger.ensure_graph_node("g-persist", "n1", attempt=1)
    assert ledger.update_graph_node(
        "g-persist", "n1", expected_status="pending", status="passed", attempt=1,
        evidence_ref="run:g-persist:work:1",
    )
    fresh = Ledger(tmp_path)
    row = fresh.get_graph_node("g-persist", "n1")
    assert row is not None
    assert row["status"] == "passed"
    assert row["attempt"] == 1
    assert row["evidence_ref"] == "run:g-persist:work:1"


def test_graph_node_compare_and_set_rejects_stale_write(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    ledger.ensure_graph_node("g-cas", "n1", attempt=1)
    assert ledger.update_graph_node("g-cas", "n1", expected_status="pending", status="failed")
    # a stale writer still thinks the node is pending
    assert not ledger.update_graph_node("g-cas", "n1", expected_status="pending", status="passed")
    assert ledger.get_graph_node("g-cas", "n1")["status"] == "failed"


def test_scheduler_records_graph_nodes_after_run(tmp_path: Path) -> None:
    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: SimpleNamespace(run=lambda req: _passed(req)),
    )
    scheduler.run(GraphSpec(nodes=[_specialist("s1")]), graph_id="g-record")

    rows = {row["node_id"]: row for row in scheduler.ledger.list_graph_nodes("g-record")}
    assert rows["s1"]["status"] == "passed"
    assert rows["s1"]["attempt"] == 1
    assert rows["s1"]["evidence_ref"].startswith("run:")


def test_scheduler_resume_skips_passed_nodes(tmp_path: Path) -> None:
    calls: list[str] = []
    fail_second = {"on": True}

    def runner_factory(request):
        def run(req):
            calls.append(req.run_id)
            if req.run_id.endswith(":s2") and fail_second["on"]:
                raise RuntimeError("worker crashed")
            return _passed(req)
        return SimpleNamespace(run=run)

    graph = GraphSpec(nodes=[_specialist("s1"), _specialist("s2")], rationale="resume test")
    scheduler = GraphScheduler(tmp_path, runner_factory=runner_factory)

    first = scheduler.run(graph, graph_id="g-resume")
    assert first.status == "failed"
    assert len([call for call in calls if call.endswith(":s1")]) == 1
    assert len([call for call in calls if call.endswith(":s2")]) == 1

    fail_second["on"] = False
    second = scheduler.run(graph, graph_id="g-resume", resume=True)

    assert second.status == "passed"
    # s1 was already passed — it must not execute a second time
    assert len([call for call in calls if call.endswith(":s1")]) == 1
    # s2 failed before — it must be retried on resume
    assert len([call for call in calls if call.endswith(":s2")]) == 2

    events = [event["kind"] for event in scheduler.ledger.events_for_run("g-resume")]
    assert "node_resumed" in events

    rows = {row["node_id"]: row for row in scheduler.ledger.list_graph_nodes("g-resume")}
    assert rows["s1"]["status"] == "passed"
    assert rows["s2"]["status"] == "passed"


def test_scheduler_without_resume_reruns_everything(tmp_path: Path) -> None:
    calls: list[str] = []

    def runner_factory(request):
        def run(req):
            calls.append(req.run_id)
            return _passed(req)
        return SimpleNamespace(run=run)

    graph = GraphSpec(nodes=[_specialist("s1")], rationale="control")
    scheduler = GraphScheduler(tmp_path, runner_factory=runner_factory)

    scheduler.run(graph, graph_id="g-no-resume")
    scheduler.run(graph, graph_id="g-no-resume")

    # without resume, the node executes on both runs
    assert len([call for call in calls if call.endswith(":s1")]) == 2
