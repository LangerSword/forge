"""Allowlisted tool registry with ledger-backed call/result evidence.

This is the execution edge of the Forge learning loop: every tool invocation
is validated against a per-task allowlist and every call/result/error is recorded
in the ledger so later learning evaluation can compare tool traces (ordering,
parameters, outcome) rather than just a boolean pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .ledger import Ledger


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolContext:
    run_id: str
    task_id: str
    worktree: Path
    allowed_tools: tuple[str, ...] = ()
    remaining_steps: int = 30


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    ok: bool
    output: str
    evidence_refs: tuple[str, ...] = ()
    error_code: str | None = None


class Tool(Protocol):
    name: str

    def invoke(self, call: ToolCall, context: ToolContext) -> ToolResult: ...


class ToolRegistry:
    """Resolve allowlisted tools and record call/result/error evidence."""

    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": name} for name in self.available()]

    def invoke(self, context: ToolContext, call: ToolCall) -> ToolResult:
        if call.name not in self._tools:
            self.ledger.event(
                context.run_id,
                "tool_error",
                "tool-registry",
                {
                    "call_id": call.call_id,
                    "tool_name": call.name,
                    "error_code": "tool_unknown",
                },
            )
            return ToolResult(call.call_id, False, "", error_code="tool_unknown")
        if call.name not in context.allowed_tools:
            self.ledger.event(
                context.run_id,
                "tool_error",
                "tool-registry",
                {
                    "call_id": call.call_id,
                    "tool_name": call.name,
                    "error_code": "tool_not_allowed",
                    "allowed_tools": list(context.allowed_tools),
                },
            )
            return ToolResult(call.call_id, False, "", error_code="tool_not_allowed")
        tool = self._tools[call.name]
        self.ledger.event(
            context.run_id,
            "tool_call",
            "tool-registry",
            {
                "call_id": call.call_id,
                "tool_name": call.name,
                "argument_keys": sorted(call.arguments),  # never raw secrets
                "remaining_steps": context.remaining_steps,
            },
        )
        try:
            result = tool.invoke(call, context)
        except Exception as exc:  # boundary: tool failures become trace data
            self.ledger.event(
                context.run_id,
                "tool_error",
                "tool-registry",
                {
                    "call_id": call.call_id,
                    "tool_name": call.name,
                    "error_code": f"tool_raised:{type(exc).__name__}",
                },
            )
            return ToolResult(call.call_id, False, "", error_code=f"tool_raised:{type(exc).__name__}")
        self.ledger.event(
            context.run_id,
            "tool_result",
            "tool-registry",
            {
                "call_id": call.call_id,
                "tool_name": call.name,
                "ok": result.ok,
                "output": result.output[:2000],
                "evidence_refs": list(result.evidence_refs),
            },
        )
        return result
