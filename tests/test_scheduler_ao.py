from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from forge.graph import GraphSpec, NodeSpec, to_taskgraph
from forge.scheduler import GraphScheduler


def _ao_node(node_id: str = "s1") -> NodeSpec:
    return NodeSpec(
        node_id=node_id,
        node_type="specialist",
        title="run through AO",
        goal="produce the verified artifact",
        acceptance=["artifact exists"],
        tools=["ao"],
        artifact_path="out.json",
    )


def test_to_taskgraph_carries_node_tools() -> None:
    graph = GraphSpec(nodes=[_ao_node()])
    taskgraph = to_taskgraph(graph)
    assert taskgraph.tasks[0].tools == ["ao"]


def test_scheduler_rejects_unverified_ao_pass(tmp_path: Path) -> None:
    """An AO-style worker claiming 'passed' with no artifact/verifier stays failed.

    The scheduler inherits FleetController's rule; it must not relax it.
    """

    def ao_like_runner(request):
        return SimpleNamespace(
            run=lambda req: SimpleNamespace(
                status="passed",
                session_id="ao-session-1",
                worktree=None,
                artifact_exists=False,
                verification_passed=False,
                classification=SimpleNamespace(value="terminated"),
                reason="worker claims it is done",
            )
        )

    scheduler = GraphScheduler(tmp_path, runner_factory=ao_like_runner)
    report = scheduler.run(GraphSpec(nodes=[_ao_node()]), graph_id="g-ao-unverified")

    assert report.status == "failed"
    assert report.node_results[0].status == "failed"
    assert "unverified_worker_pass" in " ".join(report.node_results[0].observations)


def test_scheduler_passes_verified_ao_node(tmp_path: Path) -> None:
    """A worker with a fresh artifact AND independent verification passes."""

    def ao_like_runner(request):
        return SimpleNamespace(
            run=lambda req: SimpleNamespace(
                status="passed",
                session_id="ao-session-2",
                worktree=None,
                artifact_exists=True,
                verification_passed=True,
                classification=SimpleNamespace(value="passed"),
                reason="artifact and independent verification passed",
            )
        )

    scheduler = GraphScheduler(tmp_path, runner_factory=ao_like_runner)
    report = scheduler.run(GraphSpec(nodes=[_ao_node()]), graph_id="g-ao-verified")

    assert report.status == "passed"
    assert report.node_results[0].status == "passed"


def test_scheduler_ao_node_dispatches_with_node_goal(tmp_path: Path) -> None:
    seen: list[str] = []

    def ao_like_runner(request):
        seen.append(request.goal)
        return SimpleNamespace(
            run=lambda req: SimpleNamespace(
                status="passed",
                session_id="ao-session-3",
                worktree=None,
                artifact_exists=True,
                verification_passed=True,
                classification=SimpleNamespace(value="passed"),
                reason="ok",
            )
        )

    scheduler = GraphScheduler(tmp_path, runner_factory=ao_like_runner)
    scheduler.run(GraphSpec(nodes=[_ao_node()]), graph_id="g-ao-goal")

    assert seen == ["produce the verified artifact"]
