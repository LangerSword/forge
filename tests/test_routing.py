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
        title="work",
        goal="do work",
        acceptance=["done"],
    )


def _judge(node_id: str = "j1", deps: list[str] | None = None) -> NodeSpec:
    return NodeSpec(
        node_id=node_id,
        node_type="judge",
        title="judge",
        goal="judge the work",
        acceptance=["decision"],
        deps=deps or ["s1"],
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


def test_judge_continue_keeps_scheduler_flow(tmp_path: Path) -> None:
    calls: list[str] = []

    def runner_factory(request):
        calls.append(request.run_id)
        return _runner("passed")

    def judge(node, result):
        return {"decision": "continue", "reason": "looks good"}

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=runner_factory,
        judge=judge,
    )
    report = scheduler.run(GraphSpec(nodes=[_specialist(), _judge()]), graph_id="g-judge-ok")

    assert report.status == "passed"
    assert [item.node_id for item in report.node_results] == ["s1", "j1"]
    events = scheduler.ledger.events_for_run("g-judge-ok")
    routing = [event for event in events if event["kind"] == "routing_decision"]
    assert len(routing) == 1
    assert routing[0]["payload"]["decision"] == "continue"
    assert routing[0]["payload"]["judged_node_id"] == "s1"


def test_judge_retry_reruns_node_once_then_stops(tmp_path: Path) -> None:
    calls: list[str] = []

    def runner_factory(request):
        calls.append(request.run_id)
        return _runner("failed")

    def judge(node, result):
        return {"decision": "retry", "reason": "flaky"}

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=runner_factory,
        judge=judge,
        max_retries=1,
    )
    report = scheduler.run(GraphSpec(nodes=[_specialist(), _judge()]), graph_id="g-judge-retry")

    assert report.status == "failed"
    specialist_runs = [call for call in calls if call.endswith(":s1")]
    assert len(specialist_runs) == 2
    events = scheduler.ledger.events_for_run("g-judge-retry")
    decisions = [e["payload"]["decision"] for e in events if e["kind"] == "routing_decision"]
    assert decisions == ["retry"]


def test_judge_unknown_decision_raises(tmp_path: Path) -> None:
    def judge(node, result):
        return {"decision": "teleport", "reason": "not a real decision"}

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: _runner("passed"),
        judge=judge,
    )
    with pytest.raises(ValueError, match="decision"):
        scheduler.run(GraphSpec(nodes=[_specialist(), _judge()]), graph_id="g-judge-bad")


def test_judge_escalate_blocks_judged_node(tmp_path: Path) -> None:
    def judge(node, result):
        return {"decision": "escalate", "reason": "needs a human"}

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=lambda request: _runner("passed"),
        judge=judge,
    )
    report = scheduler.run(GraphSpec(nodes=[_specialist(), _judge()]), graph_id="g-judge-esc")

    assert report.status == "failed"
    judged = next(item for item in report.node_results if item.node_id == "s1")
    assert judged.status == "blocked"
    assert "needs a human" in judged.observations


def test_judge_retry_budget_is_bounded(tmp_path: Path) -> None:
    calls: list[str] = []

    def runner_factory(request):
        calls.append(request.run_id)
        return _runner("failed")

    def judge(node, result):
        return {"decision": "retry", "reason": "still flaky"}

    scheduler = GraphScheduler(
        tmp_path,
        runner_factory=runner_factory,
        judge=judge,
        max_retries=0,
    )
    report = scheduler.run(GraphSpec(nodes=[_specialist(), _judge()]), graph_id="g-judge-noretry")

    assert report.status == "failed"
    specialist_runs = [call for call in calls if call.endswith(":s1")]
    assert len(specialist_runs) == 1
