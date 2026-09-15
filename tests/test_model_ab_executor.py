"""Tests for the AO-backed model-variant A/B executor (task 2).

Each trial runs through the real AORunner under the declared harness policy;
the model comes from the experiment condition, never from the worker.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge.ao_cli import AOCommandResult
from forge.ledger import Ledger
from forge.model_ab import ModelABExecutor


class FakeCLI:
    def __init__(self):
        self.spawn_calls: list[dict] = []

    def spawn_command(self, **kwargs):
        return ("ao", "spawn")

    def spawn(self, **kwargs):
        self.spawn_calls.append(kwargs)
        # parse_spawn_output is fail-loud by design: the fake must emit a
        # parseable session id (the live CLI prints a spawn line).
        return AOCommandResult(
            ("ao", "spawn"), 0,
            'spawned session ab-test-1 "trial" (idle)\n', "",
        )


class OneShotClient:
    """Session goes working -> exited with a fresh artifact."""

    def __init__(self, artifact: Path):
        self.artifact = artifact
        self.polls = 0

    def session(self, session_id: str) -> dict:
        self.polls += 1
        if self.polls >= 2 and not self.artifact.exists():
            self.artifact.write_text("trial artifact\n")
        if self.polls >= 2:
            return {"id": session_id, "status": "exited", "isTerminated": True}
        return {"id": session_id, "status": "working", "activity_state": "active"}

    def send(self, session_id: str, message: str) -> dict:
        return {"ok": True}

    def kill(self, session_id: str) -> dict:
        return {"ok": True}


def _executor(tmp_path: Path, run_id: str = "ab-exec-1") -> tuple[ModelABExecutor, FakeCLI, Path]:
    worktree = tmp_path / "wt"
    worktree.mkdir()
    artifact = worktree / "out.json"
    cli = FakeCLI()
    executor = ModelABExecutor(
        ao_cli=cli,
        ao_client=OneShotClient(artifact),
        ledger=Ledger(tmp_path),
        project="forge",
        worktree=worktree,
        artifact_path=artifact,
        run_prefix=run_id,
        # verifier authority: artifact content check (the trial artifact)
        independent_verifier=lambda _root, path: path.is_file() and path.stat().st_size > 0,
    )
    return executor, cli, artifact


def test_executor_passes_model_to_spawn_and_returns_runresult(tmp_path: Path) -> None:
    from forge.evaluation import EvaluationCase

    executor, cli, artifact = _executor(tmp_path)
    case = EvaluationCase("case-a", "ref-a")
    result = executor.execute(case, candidate_id=None, model="nvidia/abacusai/dracarys-llama-3.1-70b-instruct")

    assert cli.spawn_calls, "runner never spawned"
    assert cli.spawn_calls[0]["model"] == "nvidia/abacusai/dracarys-llama-3.1-70b-instruct"
    assert result.status == "passed"
    assert result.harness == "opencode"


def test_executor_records_policy_check_in_ledger(tmp_path: Path) -> None:
    from forge.evaluation import EvaluationCase
    from forge.harness_policy import HarnessPolicy, policy_hash

    policy = HarnessPolicy(harness="opencode", allowed_models=("nvidia/", None), max_runtime_s=900.0)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    cli = FakeCLI()
    executor = ModelABExecutor(
        ao_cli=cli,
        ao_client=OneShotClient(worktree / "out.json"),
        ledger=Ledger(tmp_path),
        project="forge",
        worktree=worktree,
        artifact_path=worktree / "out.json",
        run_prefix="ab-exec-policy",
        policy=policy,
    )
    executor.execute(EvaluationCase("case-a", "ref-a"), model="nvidia/x/y")

    events = Ledger(tmp_path).events_for_run(
        [e for e in [ev["run_id"] for ev in Ledger(tmp_path).list_runs()] if e.startswith("ab-exec-policy")][0]
    ) if any(ev["run_id"].startswith("ab-exec-policy") for ev in Ledger(tmp_path).list_runs()) else []
    assert any(e["kind"] == "policy_check" and e["payload"].get("policy_hash") == policy_hash(policy) for e in events)


def test_executor_rejects_nonallowlisted_model_before_spawn(tmp_path: Path) -> None:
    from forge.evaluation import EvaluationCase
    from forge.harness_policy import HarnessPolicy, HarnessPolicyError

    policy = HarnessPolicy(harness="opencode", allowed_models=("nvidia/", None), max_runtime_s=900.0)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    cli = FakeCLI()
    executor = ModelABExecutor(
        ao_cli=cli,
        ao_client=OneShotClient(worktree / "out.json"),
        ledger=Ledger(tmp_path),
        project="forge",
        worktree=worktree,
        artifact_path=worktree / "out.json",
        run_prefix="ab-exec-reject",
        policy=policy,
    )
    with pytest.raises(HarnessPolicyError, match="model"):
        executor.execute(EvaluationCase("case-a", "ref-a"), model="sketchy-model")
    assert not cli.spawn_calls, "violating model reached spawn"


def test_executor_run_ids_are_unique_per_case(tmp_path: Path) -> None:
    from forge.evaluation import EvaluationCase

    executor, cli, _ = _executor(tmp_path)
    r1 = executor.execute(EvaluationCase("case-a", "ref-a"), model=None)
    r2 = executor.execute(EvaluationCase("case-b", "ref-b"), model=None)
    assert r1.run_id != r2.run_id
