from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(override=False)

import neatlogs

neatlogs.init(api_key=os.getenv("NEATLOGS_API_KEY"), workflow_name="forge-cli")
logging.getLogger("neatlogs").setLevel(logging.WARNING)

from . import __version__
from .ao import AOClient
from .c0_run import run_c0
from .harness_readiness import build_harness_report
from .openai_provider import OpenAIProvider, ProviderError
from .submission import run_submission_mvp
from .ledger import Ledger


DEFAULT_SUPPORTED_HARNESSES = ("opencode", "claude-code", "codex")


def root() -> Path:
    return Path.cwd()


def _smoke_tested_from_payload(payload: dict[str, Any]) -> dict[str, bool]:
    """Read explicit smoke evidence only; never infer it from AO state."""
    value = payload.get("smoke_tested", payload.get("smokeTested", {}))
    if not isinstance(value, dict):
        return {}
    return {str(name): passed is True for name, passed in value.items()}


def _harness_names(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                for key in ("id", "name", "slug", "type"):
                    name = item.get(key)
                    if isinstance(name, str) and name.strip():
                        result.append(name.strip())
                        break
            elif isinstance(item, str) and item.strip():
                result.append(item.strip())
        return tuple(dict.fromkeys(result))
    return ()


def harness_report(*, ao: AOClient | None = None, payload: dict[str, Any] | None = None):
    if payload is None:
        if ao is None:
            ao = AOClient()
        payload = ao.agents()
    supported = payload.get(
        "supported_catalog",
        payload.get("supportedCatalog", payload.get("supported", DEFAULT_SUPPORTED_HARNESSES)),
    )
    supported = _harness_names(supported) or DEFAULT_SUPPORTED_HARNESSES
    return build_harness_report(
        payload,
        supported_catalog=supported,
        smoke_tested=_smoke_tested_from_payload(payload),
    )


def cmd_harnesses() -> int:
    """Print a read-only, evidence-bounded harness readiness report."""
    try:
        report = harness_report(ao=AOClient())
    except Exception as exc:
        print(json.dumps({
            "schema_version": "forge.harness-readiness.v1",
            "ok": False,
            "error": "ao_unavailable",
            "message": str(exc),
        }, indent=2))
        return 1
    payload = report.to_dict()
    payload["ok"] = True
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_status() -> int:
    ao = AOClient()
    ledger = Ledger(root())
    try:
        payload = {
            "forge_version": __version__,
            "project_root": str(root()),
            "ledger": ledger.counts(),
            "ao": {
                "health": ao.health(),
                "ready": ao.ready(),
                "agents": ao.agents(),
                "projects": ao.projects(),
                "sessions": ao.sessions(),
            },
        }
    except Exception as exc:
        print(json.dumps({"forge_version": __version__, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(payload, indent=2))
    return 0


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            body = json.dumps({"status": "ok", "service": "forge-dashboard"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b"<html><body><h1>Forge</h1><p>Dashboard scaffold is running.</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002
        return None


def cmd_dashboard(port: int) -> int:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Forge dashboard: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("harnesses", help="read-only AO harness readiness JSON")
    c0 = sub.add_parser("run-c0")
    sub.add_parser("openai-smoke")
    submission = sub.add_parser("submission-mvp")
    submission.add_argument("--reflect", action="store_true", help="use configured GPT-5 Nano reflection")
    c0.add_argument("--candidate", required=True, help="candidate worktree containing c0_target.py")
    sub.add_parser("runs")
    run = sub.add_parser("run")
    run.add_argument("run_id")
    dash = sub.add_parser("dashboard")
    dash.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    if args.command == "status":
        return cmd_status()
    if args.command == "harnesses":
        return cmd_harnesses()
    if args.command == "runs":
        print(json.dumps({"schema_version": "1", "command": "runs", "ok": True,
                          "runs": Ledger(root()).list_runs(), "error": None}, indent=2))
        return 0
    if args.command == "run":
        try:
            result = Ledger(root()).get_run(args.run_id)
        except ValueError as exc:
            print(json.dumps({"schema_version": "1", "command": "run", "ok": False,
                              "error": "corrupt_event", "message": str(exc)}, indent=2))
            return 1
        if result is None:
            print(json.dumps({"schema_version": "1", "command": "run", "ok": False,
                              "error": "run_not_found", "run_id": args.run_id}, indent=2))
            return 1
        run = {k: v for k, v in result.items() if k != "events"}
        print(json.dumps({"schema_version": "1", "command": "run", "ok": True,
                          "run": run, "events": result["events"], "error": None}, indent=2))
        return 0
    if args.command == "run-c0":
        result = run_c0(root(), run_id="c0-name-normalizer-v1", candidate=Path(args.candidate))
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["result"]["passed"] else 1
    if args.command == "openai-smoke":
        with neatlogs.trace("openai-smoke", kind="WORKFLOW") as wf:
            wf.set_attribute("neatlogs.workflow_name", "openai-smoke")
            try:
                result = OpenAIProvider().complete(instructions="Return exactly JSON: {\"ok\":true}", input_text="health check")
            except ProviderError as exc:
                print(json.dumps({"ok": False, "error": exc.kind, "message": str(exc)}))
                return 1
            print(json.dumps({"ok": True, "model": result.model, "text": result.text,
                              "input_tokens": result.input_tokens, "output_tokens": result.output_tokens}))
        return 0
    if args.command == "submission-mvp":
        result = run_submission_mvp(root(), use_reflection=args.reflect)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result["final"]["passed"] else 1
    if args.command == "dashboard":
        return cmd_dashboard(args.port)
    return 2


def main_from_args_for_test(argv: list[str]) -> int:
    """Test seam for exercising CLI JSON commands without a subprocess."""
    return main(argv)


def cli_entrypoint() -> int:
    """Console entrypoint with one outermost Neatlogs lifecycle."""
    try:
        return main()
    finally:
        with contextlib.redirect_stdout(sys.stderr):
            neatlogs.flush()
            neatlogs.shutdown()


if __name__ == "__main__":
    raise SystemExit(cli_entrypoint())
