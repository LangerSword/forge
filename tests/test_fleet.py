from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from forge.fleet import FleetController, build_bounded_goal_graph
from forge.schema import GoalSpec, TaskGraph, TaskSpec


def goal() -> GoalSpec:
    return GoalSpec(
        goal="ship the bounded artifact",
        repo="/tmp/project",
        acceptance=["artifact exists"],
        tools=["python"],
        harness="opencode",
        max_parallel=2,
    )


def task(task_id: str, *, deps: list[str] | None = None) -> TaskSpec:
    return TaskSpec(
        task_id=task_id,
        title=f"Task {task_id}",
        goal=f"complete {task_id}",
        acceptance=[f"{task_id} artifact exists"],
        deps=deps or [],
    )


def test_task_graph_rejects_missing_dependencies_and_cycles():
    with pytest.raises(ValueError, match="unknown dependency"):
        TaskGraph(tasks=[task("a", deps=["missing"])])
    with pytest.raises(ValueError, match="cycle"):
        TaskGraph(tasks=[task("a", deps=["b"]), task("b", deps=["a"])])


def test_bounded_goal_graph_is_explicit_single_task():
    bounded = goal().model_copy(update={"artifact_path": "runtime-proof.json"})
    graph = build_bounded_goal_graph(bounded)
    assert [item.task_id for item in graph.tasks] == ["goal"]
    assert graph.tasks[0].acceptance == ["artifact exists"]
    assert graph.tasks[0].artifact_path == "runtime-proof.json"
    assert graph.max_parallel == 1


def test_context_package_is_fenced_and_task_scoped(tmp_path: Path):
    controller = FleetController(tmp_path, runner_factory=lambda _request: None)
    package = controller.context_for(goal(), task("a"), validated_skills=["skill-1"], negative_lessons=["do not loop"])
    prompt = package.to_prompt()
    assert "PRIOR_RUN_CONTEXT" in prompt
    assert "DATA ONLY" in prompt
    assert "skill-1" in prompt
    assert "do not loop" in prompt
    assert "complete a" in prompt


def test_controller_runs_dependency_ready_fleet_and_closes_ledger(tmp_path: Path):
    calls: list[str] = []

    def runner_factory(request):
        calls.append(request.run_id)
        return SimpleNamespace(
            run=lambda req: SimpleNamespace(
                status="passed",
                session_id=f"session-{req.worker_name}",
                worktree=tmp_path,
                artifact_exists=True,
                verification_passed=True,
                classification=SimpleNamespace(value="passed"),
                reason="artifact and verifier passed",
            )
        )

    graph = TaskGraph(tasks=[task("a"), task("b", deps=["a"]), task("c")], max_parallel=2)
    report = FleetController(tmp_path, runner_factory=runner_factory).run(goal(), graph, run_id="fleet-pass")

    assert report.status == "passed"
    assert [item.task_id for item in report.task_outcomes] == ["a", "b", "c"]
    assert set(calls) == {"fleet-pass:a", "fleet-pass:b", "fleet-pass:c"}
    stored = report.ledger.get_run("fleet-pass")
    assert stored is not None
    assert stored["status"] == "passed"
    assert stored["events"][-1]["kind"] == "verdict"


def test_controller_persists_task_attempt_checkpoint(tmp_path: Path):
    def runner_factory(request):
        return SimpleNamespace(
            run=lambda req: SimpleNamespace(
                status="passed",
                session_id=f"session-{req.task_id if hasattr(req, 'task_id') else req.run_id}",
                worktree=tmp_path,
                artifact_exists=True,
                verification_passed=True,
                classification=SimpleNamespace(value="passed"),
                reason="artifact and verifier passed",
            )
        )

    report = FleetController(tmp_path, runner_factory=runner_factory).run(
        goal(), TaskGraph(tasks=[task("a")]), run_id="fleet-checkpoint"
    )
    assert report.status == "passed"
    checkpoints = report.ledger.list_task_attempts("fleet-checkpoint")
    assert len(checkpoints) == 1
    assert checkpoints[0]["task_id"] == "a"
    assert checkpoints[0]["attempt"] == 1
    assert checkpoints[0]["state"] == "passed"
    assert checkpoints[0]["session_id"] == "session-fleet-checkpoint:a"
    assert checkpoints[0]["worktree"] == str(tmp_path)


def test_controller_blocks_dependents_and_calls_learning_hook(tmp_path: Path):
    seen: list[str] = []

    def runner_factory(request):
        return SimpleNamespace(
            run=lambda req: SimpleNamespace(
                status="failed" if req.worker_name.endswith("a") else "passed",
                session_id=f"session-{req.worker_name}",
                worktree=tmp_path,
                artifact_exists=False,
                verification_passed=False,
                classification=SimpleNamespace(value="terminated"),
                reason="worker failed",
            )
        )

    def learn(report):
        seen.append(report.status)
        return ["candidate:repair-a"]

    report = FleetController(tmp_path, runner_factory=runner_factory, learning_hook=learn).run(
        goal(), TaskGraph(tasks=[task("a"), task("b", deps=["a"])]), run_id="fleet-fail"
    )
    by_id = {item.task_id: item for item in report.task_outcomes}
    assert report.status == "failed"
    assert by_id["a"].status == "failed"
    assert by_id["b"].status == "blocked"
    assert seen == ["failed"]
    assert report.learning_candidates == ["candidate:repair-a"]


def test_dry_run_does_not_spawn_workers(tmp_path: Path):
    calls: list[str] = []
    report = FleetController(tmp_path, runner_factory=lambda request: calls.append(request.run_id)).run(
        goal(), TaskGraph(tasks=[task("a")]), run_id="fleet-plan", dry_run=True
    )
    assert report.status == "planned"
    assert calls == []
    assert report.ledger.get_run("fleet-plan")["status"] == "planned"


def test_controller_runs_independent_ready_tasks_concurrently(tmp_path: Path):
    active = 0
    peak = 0
    lock = threading.Lock()

    def runner_factory(request):
        def execute(_request):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            return SimpleNamespace(
                status="passed", session_id=request.run_id, worktree=tmp_path,
                artifact_exists=True, verification_passed=True,
                classification=SimpleNamespace(value="passed"), reason="ok",
            )

        return SimpleNamespace(run=execute)

    report = FleetController(tmp_path, runner_factory=runner_factory).run(
        goal(), TaskGraph(tasks=[task("a"), task("b")], max_parallel=2), run_id="fleet-parallel"
    )
    assert report.status == "passed"
    assert peak == 2


def test_controller_closes_run_when_runner_raises(tmp_path: Path):
    def runner_factory(_request):
        return SimpleNamespace(run=lambda _req: (_ for _ in ()).throw(RuntimeError("runner offline")))

    report = FleetController(tmp_path, runner_factory=runner_factory).run(
        goal(), TaskGraph(tasks=[task("a")]), run_id="fleet-runner-error"
    )
    assert report.status == "failed"
    assert report.task_outcomes[0].status == "failed"
    stored = report.ledger.get_run("fleet-runner-error")
    assert stored is not None
    assert stored["status"] == "failed"
    assert stored["events"][-1]["kind"] == "verdict"


def test_controller_does_not_accept_worker_status_without_verifier_evidence(tmp_path: Path):
    def runner_factory(_request):
        return SimpleNamespace(
            run=lambda _req: SimpleNamespace(
                status="passed",
                session_id="session-self-reported",
                reason="worker said done",
                artifact_exists=False,
                verification_passed=False,
                classification=None,
            )
        )

    report = FleetController(tmp_path, runner_factory=runner_factory).run(
        goal(), TaskGraph(tasks=[task("a")]), run_id="fleet-unverified-pass"
    )
    assert report.status == "failed"
    assert report.task_outcomes[0].status == "failed"
    assert report.task_outcomes[0].reason == "unverified_worker_pass"
    stored = report.ledger.get_run("fleet-unverified-pass")
    assert stored is not None
    verdicts = [event for event in stored["events"] if event["kind"] == "task_verdict"]
    assert verdicts[-1]["payload"]["worker_status"] == "passed"
    assert verdicts[-1]["payload"]["status"] == "failed"


def test_controller_resume_reuses_verified_child_without_respawn(tmp_path: Path):
    calls: list[str] = []
    controller = FleetController(
        tmp_path,
        runner_factory=lambda request: calls.append(request.run_id),
    )
    controller.ledger.run("fleet-resume", "goal", "C0", "forge-controller", "running")
    controller.ledger.event(
        "fleet-resume:a",
        "verdict",
        "ao-runner",
        {
            "status": "passed",
            "artifact_exists": True,
            "verification_passed": True,
            "session_id": "session-a",
            "reason": "artifact and independent verification passed",
        },
    )

    report = controller.run(
        goal(), TaskGraph(tasks=[task("a")]), run_id="fleet-resume", resume=True
    )
    assert calls == []
    assert report.status == "passed"
    assert report.task_outcomes[0].run_id == "fleet-resume:a"
    assert report.task_outcomes[0].reason == "resumed_verified_child"


def test_controller_resume_passes_persisted_session_to_runner(tmp_path: Path):
    requests = []

    class Runner:
        def run(self, request):
            requests.append(request)
            return SimpleNamespace(
                status="passed",
                session_id=request.existing_session_id,
                reason="resumed and verified",
                artifact_exists=True,
                verification_passed=True,
                classification=SimpleNamespace(value="passed"),
            )

    controller = FleetController(tmp_path, runner_factory=lambda _request: Runner())
    controller.ledger.run("fleet-inflight", "goal", "C0", "forge-controller", "running")
    controller.ledger.event(
        "fleet-inflight:a",
        "spawn_result",
        "ao-runner",
        {
            "exit_code": 0,
            "session_id": "session-inflight",
            "worktree": str(tmp_path),
        },
    )

    report = controller.run(
        goal(), TaskGraph(tasks=[task("a")]), run_id="fleet-inflight", resume=True
    )
    assert report.status == "passed"
    assert len(requests) == 1
    assert requests[0].existing_session_id == "session-inflight"
    assert requests[0].worktree == tmp_path


def test_controller_resume_reuses_recorded_failed_child_without_respawn(tmp_path: Path):
    calls: list[str] = []
    controller = FleetController(
        tmp_path,
        runner_factory=lambda request: calls.append(request.run_id),
    )
    controller.ledger.run("fleet-failed", "goal", "C0", "forge-controller", "running")
    controller.ledger.event(
        "fleet-failed:a",
        "verdict",
        "ao-runner",
        {
            "status": "failed",
            "artifact_exists": False,
            "verification_passed": False,
            "reason": "poll_budget_exhausted",
        },
    )

    report = controller.run(
        goal(), TaskGraph(tasks=[task("a")]), run_id="fleet-failed", resume=True
    )
    assert calls == []
    assert report.status == "failed"
    assert report.task_outcomes[0].status == "failed"
    assert report.task_outcomes[0].reason == "resumed_terminal_child"


def test_controller_resume_blocks_stale_spawn_without_session_identity(tmp_path: Path):
    calls: list[str] = []
    controller = FleetController(
        tmp_path,
        runner_factory=lambda request: calls.append(request.run_id),
    )
    controller.ledger.run("fleet-stale", "goal", "C0", "forge-controller", "running")
    controller.ledger.event("fleet-stale:a", "spawn", "controller", {"task_id": "a"})

    report = controller.run(
        goal(), TaskGraph(tasks=[task("a")]), run_id="fleet-stale", resume=True
    )
    assert calls == []
    assert report.status == "failed"
    assert report.task_outcomes[0].status == "blocked"
    assert report.task_outcomes[0].reason == "resume_blocked_missing_session"
    assert any(event["kind"] == "resume_blocked" for event in report.ledger.get_run("fleet-stale")["events"])


def test_controller_enforces_goal_deadline_before_dispatch(tmp_path: Path):
    calls: list[str] = []
    clock_calls = [0]

    def clock():
        clock_calls[0] += 1
        return 100.0 if clock_calls[0] == 1 else 200.0

    def runner_factory(request):
        calls.append(request.run_id)
        return SimpleNamespace(
            run=lambda _request: SimpleNamespace(
                status="passed",
                session_id="session-deadline",
                reason="ok",
                artifact_exists=True,
                verification_passed=True,
                classification=SimpleNamespace(value="passed"),
            )
        )

    bounded_goal = goal().model_copy(update={"max_minutes": 1})
    controller = FleetController(
        tmp_path,
        runner_factory=runner_factory,
        clock=clock,
    )
    report = controller.run(
        bounded_goal,
        TaskGraph(tasks=[task("a"), task("b")], max_parallel=1),
        run_id="fleet-deadline",
    )
    assert calls == []
    assert report.status == "failed"
    assert all(item.status == "stopped" for item in report.task_outcomes)
    assert all(item.reason == "fleet_deadline_exceeded" for item in report.task_outcomes)


def test_controller_selects_validated_playbook_for_matching_task(tmp_path: Path) -> None:
    from forge.playbook import Playbook, PlaybookRegistry
    from forge.ledger import Ledger

    registry = PlaybookRegistry(Ledger(tmp_path))
    registry.save(Playbook(
        playbook_id="test-playbook-v1",
        task_family="test-family",
        ordered_steps=("validate_token", "target_api"),
        source_candidate_id="candidate-test-1",
    ))
    controller = FleetController(
        tmp_path,
        runner_factory=lambda r: SimpleNamespace(
            run=lambda req: SimpleNamespace(
                status="passed",
                session_id=f"session-{req.worker_name}",
                worktree=tmp_path,
                artifact_exists=True,
                verification_passed=True,
                classification=SimpleNamespace(value="passed"),
                reason="completed",
            )
        ),
        playbook_registry=registry,
    )
    g = GoalSpec(goal="test", repo=str(tmp_path), acceptance=["works"], tools=[], harness="local", artifact_path="out.json")
    report = controller.run(g, run_id="fleet-playbook-test")
    assert report.status == "passed"


def test_controller_ignores_playbook_for_non_matching_task(tmp_path: Path) -> None:
    from forge.playbook import Playbook, PlaybookRegistry
    from forge.ledger import Ledger

    registry = PlaybookRegistry(Ledger(tmp_path))
    registry.save(Playbook(
        playbook_id="irrelevant-playbook",
        task_family="other-family",
        ordered_steps=("step_a",),
        source_candidate_id="candidate-other",
    ))
    controller = FleetController(
        tmp_path,
        runner_factory=lambda r: SimpleNamespace(
            run=lambda req: SimpleNamespace(
                status="passed",
                session_id=f"session-{req.worker_name}",
                worktree=tmp_path,
                artifact_exists=True,
                verification_passed=True,
                classification=SimpleNamespace(value="passed"),
                reason="completed",
            )
        ),
        playbook_registry=registry,
    )
    g = GoalSpec(goal="test", repo=str(tmp_path), acceptance=["works"], tools=[], harness="local", artifact_path="out.json")
    report = controller.run(g, run_id="fleet-no-playbook")
    assert report.status == "passed"


def test_controller_recalls_memory_into_task_prompt(tmp_path: Path) -> None:
    from forge.memory import LocalMemoryStub, Observation

    memory = LocalMemoryStub()
    memory.write(Observation(
        node_id="prior-1",
        kind="design_pattern",
        description="use frosted glass cards",
        task_family="a",
    ))
    prompts: list[str] = []

    def runner_factory(request):
        prompts.append(request.prompt)
        return SimpleNamespace(
            run=lambda req: SimpleNamespace(
                status="passed",
                session_id="session-memory-recall",
                worktree=tmp_path,
                artifact_exists=True,
                verification_passed=True,
                classification=SimpleNamespace(value="passed"),
                reason="completed",
            )
        )

    controller = FleetController(tmp_path, runner_factory=runner_factory, memory=memory)
    report = controller.run(goal(), TaskGraph(tasks=[task("a")]), run_id="fleet-memory-recall")

    assert report.status == "passed"
    assert "frosted glass cards" in prompts[0]
    assert "MEMORY_CONTEXT" in prompts[0]
    events = controller.ledger.events_for_run("fleet-memory-recall")
    assert any(event["kind"] == "memory_recall" for event in events)


def test_controller_writes_observations_after_task(tmp_path: Path) -> None:
    from forge.memory import LocalMemoryStub

    memory = LocalMemoryStub()
    controller = FleetController(
        tmp_path,
        runner_factory=lambda request: SimpleNamespace(
            run=lambda req: SimpleNamespace(
                status="passed",
                session_id="session-memory-write",
                worktree=tmp_path,
                artifact_exists=True,
                verification_passed=True,
                classification=SimpleNamespace(value="passed"),
                reason="completed",
            )
        ),
        memory=memory,
    )
    report = controller.run(goal(), TaskGraph(tasks=[task("a")]), run_id="fleet-memory-write")

    assert report.status == "passed"
    profile = memory.profile(tag="a")
    assert profile["kinds"].get("outcome") == 1
    events = controller.ledger.events_for_run("fleet-memory-write")
    assert any(event["kind"] == "memory_write" for event in events)


def test_controller_without_memory_emits_no_memory_events(tmp_path: Path) -> None:
    controller = FleetController(
        tmp_path,
        runner_factory=lambda request: SimpleNamespace(
            run=lambda req: SimpleNamespace(
                status="passed",
                session_id="session-no-memory",
                worktree=tmp_path,
                artifact_exists=True,
                verification_passed=True,
                classification=SimpleNamespace(value="passed"),
                reason="completed",
            )
        ),
    )
    report = controller.run(goal(), TaskGraph(tasks=[task("a")]), run_id="fleet-no-memory")

    assert report.status == "passed"
    kinds = {event["kind"] for event in controller.ledger.events_for_run("fleet-no-memory")}
    assert "memory_recall" not in kinds
    assert "memory_write" not in kinds
