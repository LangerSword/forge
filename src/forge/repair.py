"""Bounded local repair loop for deterministic C0 tasks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import neatlogs

from .c0_fixture import run_fixture_verification
from .tracing import TraceSink, emit_trace


class RepairAdapter(Protocol):
    def repair(self, candidate: Path, failure: dict) -> bool: ...


@dataclass(frozen=True)
class RepairResult:
    passed: bool
    attempts: int
    negative_lesson: str | None
    last_result: dict


@neatlogs.span(kind="CHAIN", name="repair_until_pass")
def repair_until_pass(
    candidate: Path,
    *,
    adapter: RepairAdapter,
    sink: TraceSink,
    run_id: str,
    max_attempts: int = 2,
) -> RepairResult:
    result = run_fixture_verification(candidate)
    emit_trace(sink, run_id, "verification", "verifier", result)
    for attempt in range(1, max_attempts + 1):
        if result["passed"]:
            return RepairResult(True, attempt - 1, None, result)
        emit_trace(sink, run_id, "repair_attempt", "repair-agent", {"attempt": attempt, "failure": result.get("stderr", "")[-1000:]})
        if not adapter.repair(candidate, result):
            lesson = f"repair_failed:attempt={attempt}:task={result.get('task_id')}"
            emit_trace(sink, run_id, "negative_lesson", "repair-agent", {"lesson": lesson})
            return RepairResult(False, attempt, lesson, result)
        result = run_fixture_verification(candidate)
        emit_trace(sink, run_id, "verification", "verifier", result)
    lesson = f"repair_budget_exhausted:attempts={max_attempts}:task={result.get('task_id')}"
    emit_trace(sink, run_id, "negative_lesson", "repair-agent", {"lesson": lesson})
    return RepairResult(False, max_attempts, lesson, result)
