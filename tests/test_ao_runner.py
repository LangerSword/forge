from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from forge.ao_cli import AOCommandResult, parse_spawn_output
from forge.ao_runner import AORunRequest, AORunner, session_snapshot
from forge.harness_policy import policy_hash
from forge.ledger import Ledger
from forge.watchdog import WorkerClassification


class FakeCLI:
    def __init__(self, worktree: Path):
        self.worktree = worktree
        self.spawn_calls: list[dict[str, str | None]] = []

    def spawn_command(self, *, project: str, name: str, prompt: str, harness: str, mode: str, model: str | None = None):
        return ("ao", "spawn", "--project", project, "--name", name, "--prompt", "<redacted>")

    def spawn(self, *, project: str, name: str, prompt: str, harness: str, mode: str, model: str | None = None):
        self.spawn_calls.append({"project": project, "name": name, "prompt": prompt, "harness": harness, "mode": mode, "model": model})
        return AOCommandResult(
            ("ao", "spawn"),
            0,
            json.dumps({"session_id": "session-1", "worktree_path": str(self.worktree)}),
            "",
        )


class NonzeroSpawnCLI(FakeCLI):
    def spawn(self, *, project: str, name: str, prompt: str, harness: str, mode: str, model: str | None = None):
        self.spawn_calls.append({"project": project, "name": name, "prompt": prompt, "harness": harness, "mode": mode, "model": model})
        return AOCommandResult(
            ("ao", "spawn"),
            1,
            json.dumps({"session_id": "session-recovered", "worktree_path": str(self.worktree)}),
            "AO reported an error after creating the worker",
        )


class FakeClient:
    def __init__(self, snapshots: list[dict[str, object]], artifact: Path | None = None):
        self.snapshots = snapshots
        self.artifact = artifact
        self.polls = 0
        self.sent: list[tuple[str, str]] = []
        self.killed: list[str] = []

    def session(self, session_id: str) -> dict[str, object]:
        snapshot = self.snapshots[min(self.polls, len(self.snapshots) - 1)]
        self.polls += 1
        if self.artifact is not None and self.polls == 2:
            self.artifact.write_text("artifact\n")
        return snapshot

    def send(self, session_id: str, message: str) -> dict[str, object]:
        self.sent.append((session_id, message))
        return {"ok": True}

    def kill(self, session_id: str) -> dict[str, object]:
        self.killed.append(session_id)
        return {"ok": True}


def test_parse_spawn_output_accepts_documented_json_result(tmp_path: Path):
    result = parse_spawn_output(
        AOCommandResult(
            ("ao", "spawn"),
            0,
            json.dumps({"sessionId": "s-1", "workspace": str(tmp_path)}),
            "",
        )
    )
    assert result.session_id == "s-1"
    assert result.worktree == tmp_path


def test_parse_spawn_output_accepts_human_readable_result(tmp_path: Path):
    result = parse_spawn_output(f"Spawned session: s-2\nWorktree: {tmp_path}\n")
    assert result.session_id == "s-2"
    assert result.worktree == tmp_path


def test_session_snapshot_normalizes_real_nested_ao_activity():
    snapshot = session_snapshot(
        {
            "session": {
                "id": "forge-11",
                "status": "working",
                "createdAt": "2026-09-07T21:36:06.107342854Z",
                "activity": {
                    "state": "active",
                    "lastActivityAt": "2026-09-07T21:36:13.662777385Z",
                },
            }
        },
        session_id="forge-11",
        now=datetime(2026, 9, 7, 21, 36, 43, tzinfo=timezone.utc),
    )
    assert snapshot.status == "working"
    assert snapshot.activity_state == "active"
    assert snapshot.elapsed_s > 36
    assert snapshot.last_activity_s > 29


def test_runner_stops_on_runtime_budget_and_kills_worker(tmp_path: Path):
    cli = FakeCLI(tmp_path)
    client = FakeClient([{"id": "session-budget", "status": "working", "elapsed_s": 0, "last_activity_s": 0}])
    result = AORunner(
        ao_cli=cli,
        ao_client=client,
        sleep_fn=lambda _: None,
    ).run(
        AORunRequest(
            run_id="runner-budget",
            goal="bounded worker",
            project="forge",
            worker_name="worker-budget",
            prompt="Wait.",
            max_polls=5,
            max_runtime_s=0.000001,
        )
    )
    assert result.status == "stopped"
    assert result.reason == "runtime_budget_exceeded"
    assert client.killed == ["session-1"]


def test_runner_passes_only_after_artifact_and_verifier(tmp_path: Path):
    artifact = tmp_path / "result.json"
    cli = FakeCLI(tmp_path)
    client = FakeClient(
        [
            {"id": "session-1", "status": "working", "elapsed_s": 1, "last_activity_s": 0},
            {"id": "session-1", "status": "completed", "elapsed_s": 2, "last_activity_s": 0},
        ],
        artifact,
    )
    verified: list[Path] = []

    result = AORunner(
        ao_cli=cli,
        ao_client=client,
        sleep_fn=lambda _: None,
        changed_files_probe=lambda _: ("result.json",),
        independent_verifier=lambda worktree, path: verified.append(path) or path.exists(),
    ).run(
        AORunRequest(
            run_id="runner-success",
            goal="make an artifact",
            project="forge",
            worker_name="worker-1",
            prompt="Create the artifact.",
            artifact_path=Path("result.json"),
            max_polls=3,
        )
    )

    assert result.status == "passed"
    assert result.passed
    assert result.session_id == "session-1"
    assert verified == [artifact]
    assert client.sent == []
    assert client.killed == ["session-1"]
    assert {event.kind for event in result.events} >= {"spawn", "poll", "verdict"}


def test_runner_reconciles_nonzero_spawn_with_session_output(tmp_path: Path):
    artifact = tmp_path / "result.json"
    cli = NonzeroSpawnCLI(tmp_path)
    client = FakeClient(
        [
            {"id": "session-recovered", "status": "working", "elapsed_s": 1, "last_activity_s": 0},
            {"id": "session-recovered", "status": "completed", "elapsed_s": 2, "last_activity_s": 0},
        ],
        artifact,
    )
    result = AORunner(
        ao_cli=cli,
        ao_client=client,
        sleep_fn=lambda _: None,
        independent_verifier=lambda _root, path: path.exists(),
    ).run(
        AORunRequest(
            run_id="runner-recovered-spawn",
            goal="recover side-effecting spawn",
            project="forge",
            worker_name="worker-recovered",
            prompt="Create the artifact.",
            artifact_path=Path("result.json"),
            max_polls=3,
        )
    )
    assert result.status == "passed"
    assert result.session_id == "session-recovered"
    assert any(event.kind == "spawn_result" for event in result.events)


def test_runner_blocks_artifact_when_independent_verifier_is_missing(tmp_path: Path):
    artifact = tmp_path / "result.json"
    cli = FakeCLI(tmp_path)
    client = FakeClient(
        [
            {"id": "session-1", "status": "working", "elapsed_s": 1, "last_activity_s": 0},
            {"id": "session-1", "status": "completed", "elapsed_s": 2, "last_activity_s": 0},
        ],
        artifact,
    )
    result = AORunner(
        ao_cli=cli,
        ao_client=client,
        sleep_fn=lambda _: None,
    ).run(
        AORunRequest(
            run_id="runner-no-verifier",
            goal="make an artifact",
            project="forge",
            worker_name="worker-no-verifier",
            prompt="Create the artifact.",
            artifact_path=Path("result.json"),
            max_polls=2,
        )
    )

    assert result.status == "blocked"
    assert result.artifact_exists is True
    assert result.verification_passed is False
    assert result.reason == "independent_verifier_required"
    assert any(event.kind == "verification_unavailable" for event in result.events)


def test_runner_resumes_existing_session_without_spawning_duplicate(tmp_path: Path):
    artifact = tmp_path / "result.json"
    cli = FakeCLI(tmp_path)
    client = FakeClient(
        [
            {"id": "session-resume", "status": "working", "elapsed_s": 1, "last_activity_s": 0},
            {"id": "session-resume", "status": "completed", "elapsed_s": 2, "last_activity_s": 0},
        ],
        artifact,
    )
    result = AORunner(
        ao_cli=cli,
        ao_client=client,
        sleep_fn=lambda _: None,
        independent_verifier=lambda _root, path: path.exists(),
    ).run(
        AORunRequest(
            run_id="runner-resume",
            goal="resume the existing worker",
            project="forge",
            worker_name="worker-resume",
            prompt="Continue the existing task.",
            artifact_path=Path("result.json"),
            existing_session_id="session-resume",
            worktree=tmp_path,
            max_polls=3,
        )
    )

    assert result.status == "passed"
    assert result.session_id == "session-resume"
    assert cli.spawn_calls == []
    assert any(event.kind == "resume" for event in result.events)


def test_runner_rejects_preexisting_unchanged_artifact(tmp_path: Path):
    artifact = tmp_path / "result.json"
    artifact.write_text("stale\n")
    cli = FakeCLI(tmp_path)

    class CompletedClient:
        def session(self, session_id: str):
            return {"id": session_id, "status": "completed", "elapsed_s": 1, "last_activity_s": 0}

        def send(self, session_id: str, message: str):
            return {"ok": True}

        def kill(self, session_id: str):
            return {"ok": True}

    result = AORunner(
        ao_cli=cli,
        ao_client=CompletedClient(),
        sleep_fn=lambda _: None,
        independent_verifier=lambda _root, path: path.exists(),
    ).run(
        AORunRequest(
            run_id="runner-stale-artifact",
            goal="produce a fresh artifact",
            project="forge",
            worker_name="worker-stale-artifact",
            prompt="Replace the stale artifact.",
            artifact_path=Path("result.json"),
            max_polls=2,
        )
    )

    assert result.status == "blocked"
    assert result.reason == "stale_artifact"
    assert result.verification_passed is False


def test_runner_closes_verified_session_and_records_cleanup(tmp_path: Path):
    artifact = tmp_path / "result.json"
    cli = FakeCLI(tmp_path)
    client = FakeClient(
        [
            {"id": "session-close", "status": "working", "elapsed_s": 1, "last_activity_s": 0},
            {"id": "session-close", "status": "completed", "elapsed_s": 2, "last_activity_s": 0},
        ],
        artifact,
    )
    result = AORunner(
        ao_cli=cli,
        ao_client=client,
        sleep_fn=lambda _: None,
        independent_verifier=lambda _root, path: path.exists(),
    ).run(
        AORunRequest(
            run_id="runner-close",
            goal="make and close",
            project="forge",
            worker_name="worker-close",
            prompt="Create the artifact.",
            artifact_path=Path("result.json"),
            max_polls=3,
        )
    )
    assert result.status == "passed"
    assert client.killed == ["session-1"]
    assert any(event.kind == "cleanup" for event in result.events)


def test_runner_nudges_hidden_block_then_kills(tmp_path: Path):
    cli = FakeCLI(tmp_path)
    client = FakeClient(
        [
            {"id": "session-1", "status": "needs_input", "activity_state": "waiting_input", "elapsed_s": 1, "last_activity_s": 1},
            {"id": "session-1", "status": "needs_input", "activity_state": "waiting_input", "elapsed_s": 2, "last_activity_s": 2},
        ]
    )

    result = AORunner(ao_cli=cli, ao_client=client, sleep_fn=lambda _: None).run(
        AORunRequest(
            run_id="runner-blocked",
            goal="blocked task",
            project="forge",
            worker_name="worker-2",
            prompt="Wait for no one.",
            max_polls=3,
        )
    )

    assert result.status == "blocked"
    assert result.classification == WorkerClassification.BLOCKED_HIDDEN
    assert client.sent == [("session-1", "Continue the scoped task; report blockers.")]
    assert client.killed == ["session-1"]
    assert [event.kind for event in result.events].count("send") == 1
    assert [event.kind for event in result.events].count("kill") == 1


def test_runner_classifies_no_op_and_kills_after_bounded_nudge(tmp_path: Path):
    cli = FakeCLI(tmp_path)
    client = FakeClient(
        [
            {"id": "session-1", "status": "working", "elapsed_s": 100, "last_activity_s": 100},
            {"id": "session-1", "status": "working", "elapsed_s": 101, "last_activity_s": 101},
        ]
    )

    result = AORunner(
        ao_cli=cli,
        ao_client=client,
        sleep_fn=lambda _: None,
        changed_files_probe=lambda _: (),
    ).run(
        AORunRequest(
            run_id="runner-no-op",
            goal="no-op task",
            project="forge",
            worker_name="worker-3",
            prompt="Do nothing.",
            max_idle_s=10,
            max_polls=3,
        )
    )

    assert result.status == "failed"
    assert result.classification == WorkerClassification.NO_OP
    assert client.sent
    assert client.killed == ["session-1"]
    assert result.to_dict()["schema_version"] == "forge.ao-runner.v1"


# --------------------------------------------------------------------------
# HarnessPolicy wiring: validate before spawn, model knob, ledger policy hash
# --------------------------------------------------------------------------


def _policy_test_request(**overrides):
    from forge.ao_runner import AORunRequest

    defaults = {
        "run_id": "policy-runner-test",
        "goal": "policy wiring test",
        "project": "forge",
        "worker_name": "policy-w",
        "prompt": "do the thing",
        "harness": "opencode",
        "mode": "chat",
        "max_polls": 5,
        "poll_interval_s": 0.0,
        "max_runtime_s": 60.0,
    }
    defaults.update(overrides)
    return AORunRequest(**defaults)


def _policy():
    from forge.harness_policy import HarnessPolicy

    return HarnessPolicy(
        harness="opencode",
        allowed_models=("nvidia/", None),
        max_polls=120,
        max_runtime_s=900.0,
    )


def test_runner_rejects_nonallowlisted_model_before_spawn():
    runner = AORunner(ao_cli=FakeCLI(Path("/tmp/wt")), ao_client=FakeClient([{}]))
    with pytest.raises(Exception) as excinfo:
        runner.run(_policy_test_request(model="sketchy-model"), policy=_policy())
    assert "model" in str(excinfo.value)


def test_runner_rejects_bounds_outside_policy_before_spawn():
    runner = AORunner(ao_cli=FakeCLI(Path("/tmp/wt")), ao_client=FakeClient([{}]))
    with pytest.raises(Exception, match="runtime"):
        runner.run(_policy_test_request(max_runtime_s=9999.0), policy=_policy())


def test_runner_passes_model_flag_to_spawn_command():
    cli = FakeCLI(Path("/tmp/wt"))
    client = FakeClient([{"id": "session-1", "status": "exited", "isTerminated": True}])
    runner = AORunner(ao_cli=cli, ao_client=client)
    result = runner.run(_policy_test_request(model="nvidia/abacusai/dracarys-llama-3.1-70b-instruct"))
    assert result.status in {"passed", "blocked", "failed"}
    assert cli.spawn_calls, "spawn never executed"
    assert cli.spawn_calls[0]["model"] == "nvidia/abacusai/dracarys-llama-3.1-70b-instruct"


def test_runner_records_policy_hash_in_ledger(tmp_path):
    ledger = Ledger(tmp_path)
    cli = FakeCLI(Path("/tmp/wt"))
    client = FakeClient([{"id": "session-1", "status": "exited", "isTerminated": True}])
    runner = AORunner(ao_cli=cli, ao_client=client, ledger=ledger)
    policy = _policy()
    runner.run(_policy_test_request(), policy=policy)
    events = ledger.events_for_run("policy-runner-test")
    hashes = [e["payload"].get("policy_hash") for e in events if e["kind"] == "policy_check"]
    assert hashes and hashes[0] == policy_hash(policy)


def test_runner_without_policy_still_runs():
    """Back-compat: policy=None keeps the old behavior."""
    cli = FakeCLI(Path("/tmp/wt"))
    client = FakeClient([{"id": "session-1", "status": "exited", "isTerminated": True}])
    runner = AORunner(ao_cli=cli, ao_client=client)
    result = runner.run(_policy_test_request())
    assert result.status in {"passed", "blocked", "failed"}
