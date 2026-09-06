"""Validated data contracts shared by Forge harnesses."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class GoalSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(min_length=1)
    repo: str = Field(min_length=1)
    acceptance: list[str] = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    budget_usd: float | None = Field(default=None, ge=0)
    max_minutes: int = Field(default=15, gt=0)
    harness: str = Field(min_length=1)
    deployment: dict[str, Any] | None = None


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
