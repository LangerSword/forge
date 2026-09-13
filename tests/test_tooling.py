from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forge.ledger import Ledger
from forge.tooling import ToolCall, ToolContext, ToolRegistry, ToolResult


@dataclass
class EchoTool:
    name: str = "echo"

    def invoke(self, call: ToolCall, context: ToolContext) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            ok=True,
            output=str(call.arguments["value"]),
            evidence_refs=(f"file:{context.task_id}",),
        )


def test_tool_registry_records_safe_call_and_result_events(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    registry = ToolRegistry(ledger)
    registry.register(EchoTool())
    context = ToolContext(
        run_id="run-tools",
        task_id="task-a",
        worktree=tmp_path,
        allowed_tools=("echo",),
        remaining_steps=3,
    )

    result = registry.invoke(
        context,
        ToolCall("call-1", "echo", {"value": "hello", "api_key": "secret-value"}),
    )

    assert result.ok is True
    assert result.output == "hello"
    events = ledger.events_for_run("run-tools")
    assert [event["kind"] for event in events] == ["tool_call", "tool_result"]
    assert events[0]["payload"]["tool_name"] == "echo"
    assert events[0]["payload"]["argument_keys"] == ["api_key", "value"]
    assert "secret-value" not in events[0]["payload"]
    assert events[1]["payload"]["evidence_refs"] == ["file:task-a"]


def test_tool_registry_rejects_tool_outside_allowlist(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    registry = ToolRegistry(ledger)
    registry.register(EchoTool())
    context = ToolContext(
        run_id="run-tools-blocked",
        task_id="task-a",
        worktree=tmp_path,
        allowed_tools=(),
        remaining_steps=3,
    )

    result = registry.invoke(context, ToolCall("call-1", "echo", {"value": "hello"}))

    assert result.ok is False
    assert result.error_code == "tool_not_allowed"
    assert [event["kind"] for event in ledger.events_for_run("run-tools-blocked")] == ["tool_error"]
