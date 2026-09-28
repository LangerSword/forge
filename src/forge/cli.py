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
from .ao_cli import AOCLI, AOCommandError, install_cli
from .c0_run import run_c0
from .experiment import LearningExperiment, TaskExecutor
from .fleet import FleetController, build_bounded_goal_graph
from .graph import compile_goal_graph, graph_counts
from .harness_readiness import build_harness_report
from .openai_provider import OpenAIProvider, ProviderError
from .submission import run_submission_mvp
from .ledger import Ledger
from .review import run_review
from .schema import GoalSpec


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


def cmd_experiment(experiment_id: str, goal_file: str, *, model_baseline: str | None = None,
                   model_candidate: str | None = None) -> int:
    """Run a deterministic learning experiment with a local executor.

    With model kwargs and the declared harness policy, this is the
    model-variant A/B: conditions are validated against the policy BEFORE
    any trial executes, and the model_condition (both models + policy_hash)
    is recorded to the ledger and reported.
    """
    try:
        goal = GoalSpec.model_validate_json(Path(goal_file).read_text())
    except Exception as exc:
        print(json.dumps({"schema_version": "forge.experiment.v1", "ok": False,
                          "error": "invalid_goal", "message": str(exc)}, indent=2))
        return 1
    from .evaluation import EvaluationCase
    from .harness_policy import HarnessPolicy, HarnessPolicyError, policy_hash

    policy: HarnessPolicy | None = None
    policy_path = root() / ".forge" / "harness-policy.json"
    if (model_baseline is not None or model_candidate is not None) and policy_path.exists():
        policy = HarnessPolicy.load(policy_path)
    ledger = Ledger(root())
    experiment = LearningExperiment(
        experiment_id=experiment_id,
        task_family=experiment_id,
        goal=goal,
        train_cases=[EvaluationCase("case-a", "ref-a")],
        heldout_cases=[EvaluationCase("heldout-1", "ref-h1")],
        ledger=ledger,
        baseline_executor=_default_task_executor(),
        candidate_executor=_default_task_executor(),
        baseline_model=model_baseline,
        candidate_model=model_candidate,
        policy=policy,
    )
    try:
        result = experiment.run()
    except HarnessPolicyError as exc:
        print(json.dumps({"schema_version": "forge.experiment.v1", "ok": False,
                          "error": "policy_violation", "message": str(exc)[:500]}, indent=2))
        return 1
    output = {
        "schema_version": "forge.experiment.v1", "ok": True,
        "experiment_id": result.experiment_id,
        "baseline_count": len(result.baseline_results or []),
        "learned_count": len(result.learned_results or []),
        "candidate": result.candidate.skill_id if result.candidate else None,
        "gate_status": result.gate_verdict.status if result.gate_verdict else None,
    }
    if model_baseline is not None or model_candidate is not None:
        output["model_condition"] = {
            "baseline_model": model_baseline,
            "candidate_model": model_candidate,
            "policy_hash": policy_hash(policy) if policy else None,
        }
    if result.comparison:
        output["comparison"] = {
            "improved": result.comparison.improved,
            "regression": result.comparison.regression,
            "deltas": result.comparison.deltas,
            "reasons": list(result.comparison.reasons),
        }
    print(json.dumps(output, indent=2))
    return 0


def cmd_experiments() -> int:
    """List completed experiments from the ledger."""
    ledger = Ledger(root())
    runs = ledger.list_runs()
    experiments = [r for r in runs if r.get("run_id", "").startswith("exp-")]
    print(json.dumps({"schema_version": "forge.experiments.v1", "ok": True,
                      "count": len(experiments), "experiments": experiments}, indent=2))
    return 0


def cmd_graph(goal_file: str) -> int:
    """Compile a goal JSON into its typed execution graph and print it."""
    try:
        goal = GoalSpec.model_validate_json(Path(goal_file).read_text())
        graph = compile_goal_graph(goal)
    except Exception as exc:
        print(json.dumps({
            "schema_version": "forge.graph.v1", "ok": False,
            "error": type(exc).__name__, "message": str(exc)[:500],
        }, indent=2))
        return 1
    print(json.dumps({
        "schema_version": "forge.graph.v1", "ok": True,
        "goal": goal.model_dump(),
        "graph": graph.model_dump(),
        "counts": graph_counts(graph),
    }, indent=2, sort_keys=True))
    return 0


def _default_task_executor():
    class SimpleExecutor:
        name = "cli-executor"
        def execute(self, case, *, candidate_id=None, model=None):
            from .schema import RunResult
            return RunResult(
                run_id=f"cli-trial-{case.case_id}",
                goal=case.evidence_ref,
                condition="C1" if candidate_id else "C0",
                harness="local", status="passed", checks=[], tools_called=1,
            )
    return SimpleExecutor()


def cmd_review(run_id: str) -> int:
    """Grade Forge's own verdict systems against deterministic oracles.

    Exit code 0 only when every suite scores 100% on every dimension; the
    per-suite reports (and each failing case) are persisted to the ledger.
    """
    result = run_review(Ledger(root()), run_id=run_id)
    payload = {
        "schema_version": "forge.review.v1",
        "ok": result["all_suites_100"],
        "run_id": run_id,
        "all_suites_100": result["all_suites_100"],
        "suites": result["suites"],
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0 if result["all_suites_100"] else 1


def cmd_ao(args: argparse.Namespace) -> int:
    """Agent Orchestrator CLI commands (lifecycle commands land in task 3/5)."""
    if args.ao_command == "install-cli":
        try:
            result = install_cli(force=args.force)
        except AOCommandError as exc:
            print(json.dumps({"schema_version": "forge.ao.v1", "ok": False, "error": "install_failed", "message": str(exc)}, indent=2))
            return 1
        print(json.dumps({"schema_version": "forge.ao.v1", "ok": True, **result}, indent=2, sort_keys=True))
        return 0
    print(json.dumps({"schema_version": "forge.ao.v1", "ok": False, "error": "unknown_ao_command"}, indent=2))
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("harnesses", help="read-only AO harness readiness JSON")
    plan = sub.add_parser("plan", help="show the bounded task graph for a goal JSON")
    plan.add_argument("goal_file")
    fleet = sub.add_parser("fleet", help="run a bounded Forge fleet through AO")
    fleet.add_argument("goal_file")
    fleet.add_argument("--dry-run", action="store_true", help="plan and ledger the fleet without spawning AO")
    c0 = sub.add_parser("run-c0")
    sub.add_parser("openai-smoke")
    submission = sub.add_parser("submission-mvp")
    submission.add_argument("--reflect", action="store_true", help="use configured GPT-5 Nano reflection")
    c0.add_argument("--candidate", required=True, help="candidate worktree containing c0_target.py")
    sub.add_parser("runs")
    run = sub.add_parser("run")
    run.add_argument("run_id")
    exp = sub.add_parser("experiment", help="run a deterministic learning experiment")
    exp.add_argument("experiment_id", help="experiment identifier")
    exp.add_argument("goal_file", help="path to GoalSpec JSON file")
    exp.add_argument("--trials", type=int, default=3, help="number of trials per condition")
    exp.add_argument("--model-baseline", default=None, help="pinned baseline model (model-variant A/B; policy-checked)")
    exp.add_argument("--model-candidate", default=None, help="pinned candidate model (model-variant A/B; policy-checked)")
    sub.add_parser("experiments", help="list completed experiments")
    graph_cmd = sub.add_parser("graph", help="compile a goal into its typed execution graph")
    graph_cmd.add_argument("goal_file", help="path to GoalSpec JSON file")
    review_cmd = sub.add_parser("review", help="grade Forge's own verdict systems against deterministic oracles")
    review_cmd.add_argument("--run-id", default="review-suite")
    ao_cmd = sub.add_parser("ao", help="manage the Agent Orchestrator daemon and its CLI")
    ao_sub = ao_cmd.add_subparsers(dest="ao_command", required=True)
    ao_install = ao_sub.add_parser("install-cli", help="extract the ao CLI from the Agent Orchestrator AppImage to ~/.local/bin/ao")
    ao_install.add_argument("--force", action="store_true")
    dash = sub.add_parser("dashboard")
    dash.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    if args.command == "status":
        return cmd_status()
    if args.command == "harnesses":
        return cmd_harnesses()
    if args.command == "ao":
        return cmd_ao(args)
    if args.command in {"plan", "fleet"}:
        try:
            goal = GoalSpec.model_validate_json(Path(args.goal_file).read_text())
            graph = build_bounded_goal_graph(goal)
            if args.command == "plan":
                print(json.dumps({"schema_version": "forge.task-graph.v1", "ok": True, "goal": goal.model_dump(), "graph": graph.model_dump()}, indent=2, sort_keys=True))
                return 0
            controller = FleetController(
                root(),
                runner_factory=lambda request: __import__("forge.ao_runner", fromlist=["AORunner"]).AORunner(
                    ao_cli=AOCLI(), ao_client=AOClient(), ledger=Ledger(root())
                ),
            )
            report = controller.run(goal, graph, dry_run=args.dry_run)
            print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
            return 0 if report.status in {"planned", "passed"} else 1
        except Exception as exc:
            print(json.dumps({"schema_version": "forge.fleet.v1", "ok": False, "error": type(exc).__name__, "message": str(exc)[:500]}, indent=2))
            return 1
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
    if args.command == "experiment":
        return cmd_experiment(
            args.experiment_id, args.goal_file,
            model_baseline=args.model_baseline,
            model_candidate=args.model_candidate,
        )
    if args.command == "experiments":
        return cmd_experiments()
    if args.command == "graph":
        return cmd_graph(args.goal_file)
    if args.command == "review":
        return cmd_review(args.run_id)
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
