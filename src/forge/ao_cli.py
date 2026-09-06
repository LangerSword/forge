"""Safe AO CLI adapter.

The installed AO CLI is the authoritative spawn interface. This adapter does
not guess the daemon's POST /api/v1/sessions JSON body. Spawn commands are
constructed for explicit execution by the controller and recorded first.
"""
from __future__ import annotations

import os
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import neatlogs


class AOCommandError(RuntimeError):
    pass


@dataclass(frozen=True)
class AOCommandResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class AOSpawnResult:
    """The small, non-secret subset Forge needs from ``ao spawn`` output."""

    session_id: str
    worktree: Path | None = None


def _find_json_value(value: Any, names: set[str]) -> Any | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in names and item not in (None, ""):
                return item
        for item in value.values():
            found = _find_json_value(item, names)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_json_value(item, names)
            if found not in (None, ""):
                return found
    return None


def parse_spawn_output(output: str | AOCommandResult) -> AOSpawnResult:
    """Parse only observed ``ao spawn`` result shapes.

    AO's documented CLI flags are the source of truth for spawning.  The
    parser deliberately accepts either JSON emitted by a CLI wrapper or the
    short human-readable lines used by the desktop CLI; it never constructs a
    guessed HTTP spawn payload.
    """
    if isinstance(output, AOCommandResult):
        if output.exit_code != 0:
            raise AOCommandError(f"AO spawn failed ({output.exit_code}): {output.stderr[-500:]}")
        text = output.stdout
    else:
        text = output
    text = text.strip()
    if not text:
        raise AOCommandError("AO spawn returned no output")

    session_id: Any | None = None
    worktree: Any | None = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if parsed is not None:
        session_id = _find_json_value(parsed, {"session_id", "sessionId", "session", "id"})
        worktree = _find_json_value(parsed, {"worktree_path", "worktreePath", "worktree", "workspace", "workspace_path"})
    if session_id is None:
        session_match = re.search(r"(?:session(?:[_ -]?id)?|id)\s*[:=]\s*([A-Za-z0-9._:-]+)", text, re.I)
        if session_match:
            session_id = session_match.group(1)
    if worktree is None:
        worktree_match = re.search(r"(?:worktree|workspace)(?:[_ -]?path)?\s*[:=]\s*(\S+)", text, re.I)
        if worktree_match:
            worktree = worktree_match.group(1).rstrip(",")
    if not isinstance(session_id, str) or not session_id.strip():
        raise AOCommandError("AO spawn output did not contain a session id")
    if isinstance(worktree, dict):
        worktree = _find_json_value(worktree, {"path", "absolute_path"})
    return AOSpawnResult(
        session_id=session_id.strip(),
        worktree=Path(str(worktree)).expanduser() if isinstance(worktree, (str, Path)) and str(worktree).strip() else None,
    )


@dataclass
class AOCLI:
    binary: str | None = None
    cwd: Path | None = None

    def resolve_binary(self) -> str:
        if self.binary:
            return self.binary
        candidate = Path("/home/lakshaya/.local/bin/agent-orchestrator-linux-x64.AppImage")
        if candidate.exists():
            # AppImage is not the CLI itself; prefer the live daemon binary when available.
            for proc in Path("/proc").glob("[0-9]*"):
                try:
                    target = Path(os.readlink(proc / "exe"))
                except (OSError, ValueError):
                    continue
                if target.name == "ao" and "resources/daemon" in str(target):
                    return str(target)
        raise AOCommandError("AO CLI binary not resolved; run AO or set AO_CLI_BINARY")

    def run(self, args: tuple[str, ...], *, timeout: int = 30) -> AOCommandResult:
        command = (self.resolve_binary(), *args)
        proc = subprocess.run(command, cwd=self.cwd, capture_output=True, text=True, timeout=timeout)
        result = AOCommandResult(command, proc.returncode, proc.stdout, proc.stderr)
        if proc.returncode != 0:
            raise AOCommandError(f"AO command failed ({proc.returncode}): {proc.stderr[-500:]}")
        return result

    def status(self) -> AOCommandResult:
        return self.run(("status",))

    def spawn_command(self, *, project: str, name: str, prompt: str, harness: str = "opencode", mode: str = "chat") -> tuple[str, ...]:
        if len(name) > 20:
            raise ValueError("AO worker name must be <=20 characters")
        return (
            self.resolve_binary(), "spawn", "--project", project, "--kind", "worker",
            "--harness", harness, "--mode", mode, "--name", name, "--prompt", prompt,
        )

    @neatlogs.span(kind="TOOL")
    def spawn(self, *, project: str, name: str, prompt: str, harness: str = "opencode", mode: str = "chat") -> AOCommandResult:
        """Execute the documented CLI spawn command.

        This is intentionally separate from ``spawn_command`` so callers can
        record the exact command before deciding whether to execute it.
        """
        command = self.spawn_command(project=project, name=name, prompt=prompt, harness=harness, mode=mode)
        return self.run(command[1:])

    @neatlogs.span(kind="TOOL")
    def send(self, session_id: str, message: str) -> AOCommandResult:
        return self.run(("send", "--session", session_id, "--message", message))

    @neatlogs.span(kind="TOOL")
    def kill(self, session_id: str) -> AOCommandResult:
        return self.run(("session", "kill", session_id))
