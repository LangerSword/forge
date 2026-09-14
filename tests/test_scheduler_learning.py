from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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


def _runner(status: str):
    return SimpleNamespace(
        run=lambda req: SimpleNamespace(
            status=status,
            session_id="s",
            worktree=None,
            artifact_exists=True,
            verification_passed=True,
            classification=SimpleNamespace(value=status),
            reason="scripted",
        )
    )


def test_learning_hook_called_once_on_failed_graph(tmp_path: Path) -> None:
    seen: list[object] = []

    def hook(result):
        seen.append(result)
        return ["candidate:fix-s1"]

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: _runner("failed"),
        learning_hook=hook,
    )
    report = scheduler.run(GraphSpec(nodes=[_specialist("s1")]), graph_id="g-learn")

    assert report.status == "failed"
    assert len(seen) == 1
    assert seen[0].status == "failed"

    events = scheduler.ledger.events_for_run("g-learn")
    reflections = [event for event in events if event["kind"] == "reflection"]
    assert len(reflections) == 1
    assert reflections[0]["payload"]["candidate_count"] == 1
    assert reflections[0]["payload"]["status"] == "candidate_only"


def test_learning_hook_not_called_on_passed_graph(tmp_path: Path) -> None:
    calls: list[object] = []

    def hook(result):
        calls.append(result)
        return ["candidate:should-not-happen"]

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: _runner("passed"),
        learning_hook=hook,
    )
    report = scheduler.run(GraphSpec(nodes=[_specialist("s1")]), graph_id="g-learn-clean")

    assert report.status == "passed"
    assert calls == []
    kinds = [event["kind"] for event in scheduler.ledger.events_for_run("g-learn-clean")]
    assert "reflection" not in kinds


def test_learning_hook_cannot_change_node_status(tmp_path: Path) -> None:
    """The hook returns candidate ids only; it must never mark a node passed."""

    def hook(result):
        return ["candidate:pretend-it-worked"]

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: _runner("failed"),
        learning_hook=hook,
    )
    report = scheduler.run(GraphSpec(nodes=[_specialist("s1")]), graph_id="g-learn-noop")

    assert report.status == "failed"
    assert all(item.status == "failed" for item in report.node_results)


def test_learning_hook_exception_is_recorded_and_run_completes(tmp_path: Path) -> None:
    """A broken reflector must not corrupt the run: record it, finish normally."""

    def hook(result):
        raise RuntimeError("reflector offline")

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: _runner("failed"),
        learning_hook=hook,
    )
    report = scheduler.run(GraphSpec(nodes=[_specialist("s1")]), graph_id="g-learn-broken")

    assert report.status == "failed"
    events = scheduler.ledger.events_for_run("g-learn-broken")
    kinds = [event["kind"] for event in events]
    assert "reflection_error" in kinds
    assert "graph_completed" in kinds
    stored = scheduler.ledger.get_run("g-learn-broken")
    assert stored["status"] == "failed"
