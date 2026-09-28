"""Forge-side Agent Orchestrator daemon lifecycle via the ``ao`` CLI.

The daemon normally belongs to the desktop app, but the CLI exposes a hidden
``ao daemon`` command that runs the same backend headless — verified live
2026-09-28: ``ao daemon`` → healthz/readyz on :3001 → graceful ``ao stop``
(run-file written and removed cleanly). These helpers wrap that contract so
every Forge entry point shares one lifecycle definition.

Failure discipline: every helper fails loud with the exact fix. No hidden
retries, no silent downgrades.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from .ao import AOClient, AOTransportError
from .ao_cli import AOCLI, AOCommandError


def _default_log_path() -> Path:
    return Path.home() / ".ao" / "forge-daemon.log"


def _log_tail(path: Path, limit: int = 500) -> str:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return "(log unavailable)"
    return text[-limit:].strip()


def daemon_status(cli: AOCLI | None = None) -> dict[str, Any]:
    """Authoritative daemon state via ``ao status --json``.

    Works while the daemon is down (the stable CLI copy reports
    ``state: stopped|stale``), which is what makes offline preflight possible.
    """
    cli = cli or AOCLI()
    result = cli.run(("status", "--json"))
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AOCommandError(f"ao status returned non-JSON output: {result.stdout[:200]}") from exc
    if not isinstance(payload, dict):
        raise AOCommandError(f"ao status returned unexpected payload: {type(payload).__name__}")
    return payload


def daemon_ready(cli: AOCLI | None = None) -> bool:
    try:
        return daemon_status(cli=cli).get("state") == "ready"
    except AOCommandError:
        return False


def start_daemon(
    *,
    cli: AOCLI | None = None,
    client: AOClient | None = None,
    timeout_s: float = 30.0,
    poll_s: float = 0.3,
    log_path: Path | None = None,
    popen=None,
) -> dict[str, Any]:
    """Start the daemon headless (``ao daemon``) and wait until ``/readyz``.

    Idempotent: a ready daemon is reported as ``already_running`` and no
    process is spawned. The daemon is detached (new session) so it survives
    the forge process.
    """
    cli = cli or AOCLI()
    client = client or AOClient()
    spawn = popen or subprocess.Popen

    current = daemon_status(cli)
    if current.get("state") == "ready":
        return {"status": "already_running", "daemon": current}

    log_path = log_path or _default_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = (cli.resolve_binary(), "daemon")
    with log_path.open("ab") as log_handle:
        spawn(command, stdout=log_handle, stderr=subprocess.STDOUT, start_new_session=True)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            client.ready()
            break
        except AOTransportError:
            time.sleep(poll_s)
    else:
        raise AOCommandError(
            f"AO daemon did not become ready within {timeout_s}s; "
            f"log tail ({log_path}): {_log_tail(log_path)}"
        )
    return {"status": "started", "daemon": daemon_status(cli), "log": str(log_path)}


def stop_daemon(*, cli: AOCLI | None = None, client: AOClient | None = None, timeout_s: float = 15.0) -> dict[str, Any]:
    """Stop the daemon via ``ao stop`` and verify the endpoint actually closes."""
    cli = cli or AOCLI()
    client = client or AOClient()
    current = daemon_status(cli)
    if current.get("state") != "ready":
        return {"status": "not_running", "daemon": current}
    result = cli.run(("stop", "--timeout", f"{int(timeout_s)}s"))
    deadline = time.monotonic() + timeout_s + 5.0
    while time.monotonic() < deadline:
        try:
            client.health()
        except AOTransportError:
            break
        time.sleep(0.2)
    else:
        raise AOCommandError("AO daemon did not stop within the timeout")
    return {"status": "stopped", "message": result.stdout.strip(), "daemon": daemon_status(cli)}


def require_ao_ready(cli: AOCLI | None = None) -> dict[str, Any]:
    """Fail loud (with the fix) when the AO daemon is not ready."""
    try:
        status = daemon_status(cli=cli)
    except AOCommandError as exc:
        raise AOCommandError(f"AO daemon not reachable: {exc}") from exc
    if status.get("state") != "ready":
        detail = status.get("error") or f"state={status.get('state', 'unknown')}"
        raise AOCommandError(f"AO daemon is not ready ({detail}); start it with `forge ao start`")
    return status