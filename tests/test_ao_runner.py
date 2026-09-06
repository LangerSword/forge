from __future__ import annotations

import json
from pathlib import Path

from forge.ao_cli import AOCommandResult, parse_spawn_output
from forge.ao_runner import AORunRequest, AORunner
from forge.watchdog import WorkerClassification


class FakeCLI:
    def __init__(self, worktree: Path):
        self.worktree = worktree
        self.spawn_calls: list[dict[str, str]] = []

    def spawn_command(self, *, project: str, name: str, prompt: str, harness: str, mode: str):
        return ("ao", "spawn", "--project", project, "--name", name, "--prompt", "<redacted>")

    def spawn(self, *, project: str, name: str, prompt: str, harness: str, mode: str):
        self.spawn_calls.append({"project": project, "name": name, "prompt": prompt, "harness": harness, "mode": mode})
        return AOCommandResult(
            ("ao", "spawn"),
            0,
            json.dumps({"session_id": "session-1", "worktree_path": str(self.worktree)}),
            "",
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
    assert client.killed == []
    assert {event.kind for event in result.events} >= {"spawn", "poll", "verdict"}


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
