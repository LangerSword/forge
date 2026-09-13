from __future__ import annotations

import json
from pathlib import Path

from forge.ledger import Ledger
from forge.playbook import (
    Playbook,
    PlaybookRegistry,
    PlaybookTrial,
    run_playbook_trial,
)
from forge.schema import GoalSpec
from forge.tooling import Tool, ToolCall, ToolContext, ToolRegistry, ToolResult


class WrongOrderTool(Tool):
    """Deterministic tool where the correct sequence matters (baseline fails).

    Requires a token that only the validate_token step produces. Baseline
    skips validation and fails; the learned playbook runs validate_token first
    then passes the discovered token to this tool.
    """

    name = "target_api"

    def invoke(self, call: ToolCall, context: ToolContext) -> ToolResult:
        args = call.arguments
        token = args.get("token") if args.get("token") is not None else args.get("value")
        ok = bool(token) and token not in ("", "invalid")
        return ToolResult(
            call.call_id,
            ok,
            "ok" if ok else "missing_token",
            evidence_refs=(f"tool:{context.task_id}",),
            error_code=None if ok else "missing_token",
        )


class LearnStepTool(Tool):
    name = "validate_token"

    def invoke(self, call: ToolCall, context: ToolContext) -> ToolResult:
        return ToolResult(call.call_id, True, "valid", evidence_refs=(f"tool:{context.task_id}",))


def _make_goal(repo: str, artifact: str) -> GoalSpec:
    return GoalSpec(
        goal="set up third-party API auth then create an artifact",
        repo=repo,
        acceptance=["artifact exists"],
        tools=["target_api", "validate_token"],
        harness="local",
        artifact_path=artifact,
    )


def test_playbook_selection_applies_only_when_fingerprint_matches(tmp_path: Path) -> None:
    registry = PlaybookRegistry(Ledger(tmp_path))
    playbook = Playbook(
        playbook_id="auth-setup-v1",
        task_family="third-party-auth",
        ordered_steps=("validate_token", "target_api"),
        source_candidate_id="candidate-auth-1",
    )
    registry.save(playbook)

    assert registry.select(task_family="third-party-auth") == "auth-setup-v1"
    assert registry.select(task_family="different-family") is None


def test_learned_trial_that_would_fail_baseline_passes_and_records_trace(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    playbook = Playbook(
        playbook_id="auth-setup-learned",
        task_family="third-party-auth",
        ordered_steps=("validate_token", "target_api"),
        source_candidate_id="candidate-auth-1",
    )
    registry = PlaybookRegistry(ledger)
    registry.save(playbook)

    tooling = ToolRegistry(ledger)
    tooling.register(LearnStepTool())
    tooling.register(WrongOrderTool())

    trial = run_playbook_trial(
                ledger=ledger,
                run_id="trial-learned-1",
                task_id="auth",
                goal=_make_goal("forge", "proof.json"),
                worktree=tmp_path,
                playbook=playbook,
                tool_registry=tooling,
            )

    assert trial.condition == "learned"
    assert trial.playbook_id == "auth-setup-learned"
    assert trial.passed is True
    assert trial.tool_calls == ("validate_token", "target_api")
    # Cost/token fields stay null when the tool does not report them.
    assert json.dumps(trial.to_dict()).find("null") != -1
    assert json.dumps(trial.to_dict()) is not None
