"""Deterministic playbook contract: applicability selection, ordered tool steps,
and trial recording with nullable cost/token fields.

This is the bridge between learning evaluation and execution: a validated
playbook gets selected by task-family fingerprint, drives tool traces, and
produces an immutable Trial record that the evaluator uses for A/B comparison.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .ledger import Ledger
from .tooling import ToolCall, ToolContext, ToolRegistry


@dataclass(frozen=True)
class Playbook:
    playbook_id: str
    task_family: str
    ordered_steps: tuple[str, ...]
    source_candidate_id: str = ""
    verification_steps: tuple[str, ...] = ()
    content_sha256: str = ""


@dataclass(frozen=True)
class PlaybookTrial:
    trial_id: str
    run_id: str
    task_id: str
    condition: str  # baseline | learned
    playbook_id: str
    passed: bool
    tool_calls: tuple[str, ...]
    interventions: int = 0
    wall_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items()}


class PlaybookRegistry:
    """Lookup playbooks by task-family fingerprint, with an on-disk index."""

    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self._by_family: dict[str, Playbook] = {}

    def save(self, playbook: Playbook) -> None:
        self._by_family[playbook.task_family] = playbook
        self.ledger.event(
            "playbook-index",
            "playbook_saved",
            "playbook-registry",
            {
                "playbook_id": playbook.playbook_id,
                "task_family": playbook.task_family,
                "source_candidate_id": playbook.source_candidate_id,
            },
        )

    def select(self, *, task_family: str) -> str | None:
        """Return the playbook_id for a matching task family, or None."""
        match = self._by_family.get(task_family)
        if match is not None:
            self.ledger.event(
                "playbook-index",
                "playbook_selected",
                "playbook-registry",
                {
                    "playbook_id": match.playbook_id,
                    "task_family": task_family,
                },
            )
            return match.playbook_id
        return None

    def get(self, playbook_id: str) -> Playbook | None:
        for pb in self._by_family.values():
            if pb.playbook_id == playbook_id:
                return pb
        return None


def run_playbook_trial(
    *,
    ledger: Ledger,
    run_id: str,
    task_id: str,
    goal: Any,
    worktree: Path,
    playbook: Playbook,
    tool_registry: ToolRegistry | None = None,
) -> PlaybookTrial:
    """Execute a playbook's ordered steps and return a trial record.

    Each step is a tool name; the registry validates allowlist bounds and
    records every call/result/error as evidence events.
    """
    tool_registry = tool_registry or ToolRegistry(ledger)
    context = ToolContext(
        run_id=run_id,
        task_id=task_id,
        worktree=worktree,
        allowed_tools=playbook.ordered_steps,
        remaining_steps=len(playbook.ordered_steps) + 5,
    )
    calls: list[str] = []
    all_passed = True
    i = 0
    for step_name in playbook.ordered_steps:
        i += 1
        call = ToolCall(
            call_id=f"{run_id}:{task_id}:{i}",
            name=step_name,
            arguments={"step": step_name, "token": "discovered-abc"},
        )
        result = tool_registry.invoke(context, call)
        calls.append(step_name)
        if not result.ok:
            all_passed = False
            break

    # Nullable cost/token fields — never fabricate zero.
    trial = PlaybookTrial(
        trial_id=f"{run_id}:{task_id}",
        run_id=run_id,
        task_id=task_id,
        condition="learned",
        playbook_id=playbook.playbook_id,
        passed=all_passed,
        tool_calls=tuple(calls),
        interventions=0,
        wall_ms=None,
        tokens_in=None,
        tokens_out=None,
        cost_usd=None,
        evidence_refs=(
            f"run:{run_id}",
            f"task:{task_id}",
            f"playbook:{playbook.playbook_id}",
        ),
    )
    ledger.event(
        run_id,
        "trial_recorded",
        "playbook",
        trial.to_dict(),
    )
    return trial