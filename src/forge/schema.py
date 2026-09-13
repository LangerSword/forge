"""Validated data contracts shared by Forge harnesses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class GoalSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(min_length=1)
    repo: str = Field(min_length=1)
    acceptance: list[str] = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    budget_usd: float | None = Field(default=None, ge=0)
    max_minutes: int = Field(default=15, gt=0)
    harness: str = Field(min_length=1)
    max_parallel: int = Field(default=1, ge=1, le=3)
    deployment: dict[str, Any] | None = None
    artifact_path: str | None = Field(default=None, min_length=1)
    verifier_commands: list[list[str]] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def _validate_verifier_commands(self) -> "GoalSpec":
        for command in self.verifier_commands:
            if not command or any(not isinstance(token, str) or not token.strip() for token in command):
                raise ValueError("verifier_commands must contain non-empty string-token commands")
            if len(command) > 32:
                raise ValueError("verifier command exceeds 32 tokens")
        return self


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,79}$")
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=4000)
    acceptance: list[str] = Field(min_length=1, max_length=32)
    deps: list[str] = Field(default_factory=list, max_length=16)
    harness: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    max_steps: int = Field(default=30, ge=1, le=200)
    artifact_path: str | None = Field(default=None, min_length=1)
    mode: str = Field(default="chat", min_length=1)
    context_refs: list[str] = Field(default_factory=list, max_length=32)


class TaskGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tasks: list[TaskSpec] = Field(min_length=1, max_length=12)
    max_parallel: int = Field(default=1, ge=1, le=3)
    rationale: str = Field(default="bounded dependency graph", max_length=2000)

    @model_validator(mode="after")
    def _validate_graph(self) -> "TaskGraph":
        tasks = self.tasks
        ids = [task.task_id for task in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate task_id")
        known = set(ids)
        for task in tasks:
            for dep in task.deps:
                if dep not in known:
                    raise ValueError(f"unknown dependency: {task.task_id}->{dep}")
        remaining = {task.task_id: set(task.deps) for task in tasks}
        resolved: set[str] = set()
        while remaining:
            ready = {task_id for task_id, deps in remaining.items() if deps <= resolved}
            if not ready:
                raise ValueError("cycle in task graph")
            resolved.update(ready)
            for task_id in ready:
                remaining.pop(task_id)
        return self


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    check: str
    passed: bool
    evidence: list[str] = Field(default_factory=list)
    detail: str | None = None


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    run_id: str
    actor: str
    kind: str
    timestamp: str
    payload: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int | None = Field(default=None, ge=0)


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    goal: str
    condition: Literal["C0", "C1", "C2"]
    harness: str
    status: Literal["passed", "failed", "blocked", "stopped"]
    checks: list[CheckResult]
    tools_called: int = Field(default=0, ge=0)
    tokens_in: int | None = Field(default=None, ge=0)
    tokens_out: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    wall_s: float = Field(default=0, ge=0)
    skills_used: list[str] = Field(default_factory=list)
    interventions: int = Field(default=0, ge=0)
    evidence_refs: list[str] = Field(default_factory=list)

    def compare(self, other: RunResult, *, metrics: tuple[str, ...] | None = None) -> ComparisonResult:
        """Compare this (baseline) result against a learned result.

        Pass status is the primary signal: failed→passed = improvement,
        passed→failed = regression. Secondary metrics (tools_called,
        interventions, wall_s) are compared directionally when not equal.
        Cost/token fields are compared only if both sides report non-null.
        """
        if metrics is None:
            metrics = ("tools_called", "interventions", "wall_s")
        deltas: dict[str, float | None] = {}

        # Pass status
        baseline_passed = self.status == "passed"
        learned_passed = other.status == "passed"
        deltas["passed"] = (1 if learned_passed else 0) - (1 if baseline_passed else 0)

        # Nullable metric fields
        nullable = ("cost_usd", "tokens_in", "tokens_out")
        for key in (m for m in nullable if m not in metrics):
            v1 = getattr(self, key, None)
            v2 = getattr(other, key, None)
            if v1 is not None and v2 is not None:
                deltas[key] = float(v2 - v1)
            else:
                deltas[key] = None

        # Numeric metrics
        for key in metrics:
            v1 = getattr(self, key, 0)
            v2 = getattr(other, key, 0)
            deltas[key] = float(v2 - v1)

        reasons: list[str] = []

        # Check regression: learned failed when baseline passed
        if baseline_passed and not learned_passed:
            reasons.append("regression: learned failed after baseline passed")

        # Check regression: tool calls increased
        tc_delta = deltas.get("tools_called", 0)
        if tc_delta is not None and tc_delta > 0:
            reasons.append(f"regression: tool_calls increased by {tc_delta}")

        # Check regression: interventions increased
        iv_delta = deltas.get("interventions", 0)
        if iv_delta is not None and iv_delta > 0:
            reasons.append(f"regression: interventions increased by {iv_delta}")

        # Check improvement
        improved = False
        if not baseline_passed and learned_passed:
            improved = True
            reasons.append("improved: learned passed after baseline failed")
        elif baseline_passed and learned_passed:
            # Both passed — check secondary metrics
            if any(
                d is not None and d < 0
                for d in (deltas.get(k) for k in ("tools_called", "interventions"))
            ):
                improved = True
                reasons.append("improved: fewer tool_calls or interventions while maintaining pass")

        if not reasons:
            reasons.append("no_detectable_change")

        regression = any(r.startswith("regression") for r in reasons)

        return ComparisonResult(
            improved=improved,
            regression=regression,
            deltas=deltas,
            reasons=tuple(reasons),
        )


@dataclass(frozen=True)
class ComparisonResult:
    """Deterministic comparison of a baseline and learned run."""

    improved: bool
    regression: bool
    deltas: dict[str, float | None]
    reasons: tuple[str, ...] = ()


class CapturePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_url: str
    no_source_clone: bool = True
    allowed_observations: set[str] = Field(default_factory=lambda: {
        "rendered_dom", "screenshot", "accessibility_tree", "public_asset_urls",
        "interaction_outcomes", "computed_style",
    })
    forbidden_actions: set[str] = Field(default_factory=lambda: {
        "clone_repository", "read_target_source", "download_target_source",
    })

    def assert_safe(self) -> None:
        if not self.no_source_clone:
            raise ValueError("rendered benchmark requires no_source_clone=true")
        if self.forbidden_actions & {"clone_repository", "read_target_source"} == set():
            raise ValueError("source access must remain explicitly forbidden")
