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
        json_candidates = [output.stdout, output.stderr]
        text = "\n".join(part for part in json_candidates if part)
    else:
        json_candidates = [output]
        text = output
    text = text.strip()
    if not text:
        raise AOCommandError("AO spawn returned no output")

    session_id: Any | None = None
    worktree: Any | None = None
    for candidate in json_candidates:
        try:
            parsed = json.loads(candidate.strip())
        except (json.JSONDecodeError, AttributeError):
            continue
        session_id = _find_json_value(parsed, {"session_id", "sessionId", "session", "id"})
        worktree = _find_json_value(parsed, {"worktree_path", "worktreePath", "worktree", "workspace", "workspace_path"})
        if session_id is not None:
            break
    if session_id is None:
        session_match = re.search(r"(?:session(?:[_ -]?id)?|id)\s*[:=]\s*([A-Za-z0-9._:-]+)", text, re.I)
        if session_match:
            session_id = session_match.group(1)
        else:
            live_match = re.search(r"\bspawned\s+session\s+([A-Za-z0-9._:-]+)\b", text, re.I)
            if live_match:
                session_id = live_match.group(1)
    if worktree is None:
        worktree_match = re.search(r"(?:worktree|workspace)(?:[_ -]?path)?\s*[:=]\s*(\S+)", text, re.I)
        if worktree_match:
            worktree = worktree_match.group(1).rstrip(",")
    if not isinstance(session_id, str) or not session_id.strip():
        if isinstance(output, AOCommandResult) and output.exit_code != 0:
            raise AOCommandError(f"AO spawn failed ({output.exit_code}): {output.stderr[-500:]}")
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
        """Resolve the `ao` CLI: env override, explicit pin, live daemon
        binary, then the stable copy installed by `forge ao install-cli`."""
        # Env override wins: AO_CLI_BINARY beats discovery.
        env_binary = os.getenv("AO_CLI_BINARY")
        if env_binary:
            return env_binary
        if self.binary:
            return self.binary
        # 1) The live daemon binary via /proc — always version-matched to the
        # running daemon. NOT gated on any hardcoded AppImage path. Regression:
        # the scan used to be nested inside `if candidate.exists()` for a
        # ~/.local/bin AppImage that does not exist on this machine, so nothing
        # resolved even with the daemon running (observed 2026-09-15); the same
        # dead path later broke resolution whenever the daemon was down
        # (observed 2026-09-28 — the AppImage lives in ~/Applications with a
        # hash suffix now).
        for proc in Path("/proc").glob("[0-9]*"):
            try:
                target = Path(os.readlink(proc / "exe"))
            except (OSError, ValueError):
                continue
            if target.name == "ao" and "resources/daemon" in str(target):
                return str(target)
        # 2) The stable CLI copy installed by `forge ao install-cli`. This is
        # what makes `ao status/start/stop` work while the daemon is down.
        stable = Path.home() / ".local" / "bin" / "ao"
        if stable.is_file() and os.access(stable, os.X_OK):
            return str(stable)
        raise AOCommandError(
            "AO CLI binary not resolved: no live daemon binary and no stable "
            f"copy at {stable}. Run `forge ao install-cli` or set AO_CLI_BINARY."
        )

    def run(self, args: tuple[str, ...], *, timeout: int = 30) -> AOCommandResult:
        command = (self.resolve_binary(), *args)
        proc = subprocess.run(command, cwd=self.cwd, capture_output=True, text=True, timeout=timeout)
        result = AOCommandResult(command, proc.returncode, proc.stdout, proc.stderr)
        if proc.returncode != 0:
            raise AOCommandError(f"AO command failed ({proc.returncode}): {proc.stderr[-500:]}")
        return result

    def status(self) -> AOCommandResult:
        return self.run(("status",))

    def discover_worktree(self, session_id: str) -> Path | None:
        """Resolve the observed AO Git worktree branch for a session."""
        root = self.cwd or Path.cwd()
        try:
            proc = subprocess.run(
                ("git", "-C", str(root), "worktree", "list", "--porcelain"),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        block: list[str] = []
        for line in proc.stdout.splitlines() + [""]:
            if line:
                block.append(line)
                continue
            worktree_line = next((item for item in block if item.startswith("worktree ")), None)
            branch_line = next((item for item in block if item.startswith("branch ")), None)
            if (
                worktree_line is not None
                and branch_line == f"branch refs/heads/ao/{session_id}/root"
            ):
                return Path(worktree_line.removeprefix("worktree ").strip())
            block = []
        return None

    def spawn_command(self, *, project: str, name: str, prompt: str, harness: str = "opencode", mode: str = "chat", model: str | None = None) -> tuple[str, ...]:
        if len(name) > 20:
            raise ValueError("AO worker name must be <=20 characters")
        command = (
            self.resolve_binary(), "spawn", "--project", project, "--kind", "worker",
            "--harness", harness, "--mode", mode, "--name", name, "--prompt", prompt,
        )
        if model:
            command = (*command, "--model", model)
        return command

    @neatlogs.span(kind="TOOL")
    def spawn(self, *, project: str, name: str, prompt: str, harness: str = "opencode", mode: str = "chat", model: str | None = None) -> AOCommandResult:
        """Execute the documented CLI spawn command.

        This is intentionally separate from ``spawn_command`` so callers can
        record the exact command before deciding whether to execute it.
        """
        command = self.spawn_command(project=project, name=name, prompt=prompt, harness=harness, mode=mode, model=model)
        # Spawn is side-effecting: preserve nonzero output so the runner can
        # reconcile a session created before the CLI reported an error.
        proc = subprocess.run(command, cwd=self.cwd, capture_output=True, text=True, timeout=30)
        return AOCommandResult(command, proc.returncode, proc.stdout, proc.stderr)

    @neatlogs.span(kind="TOOL")
    def send(self, session_id: str, message: str) -> AOCommandResult:
        return self.run(("send", "--session", session_id, "--message", message))

    @neatlogs.span(kind="TOOL")
    def kill(self, session_id: str) -> AOCommandResult:
        return self.run(("session", "kill", session_id))
