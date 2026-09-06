"""Independent deterministic verification for Forge artifacts."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from .ledger import Ledger
from .schema import CheckResult, RunResult


@dataclass(frozen=True)
class CommandCheck:
    name: str
    command: tuple[str, ...]


def run_command_check(root: Path, check: CommandCheck) -> CheckResult:
    started = monotonic()
    try:
        proc = subprocess.run(check.command, cwd=root, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return CheckResult(check=check.name, passed=False, evidence=[f"timeout:{check.command}"], detail="timeout")
    duration = round(monotonic() - started, 3)
    evidence = [f"exit_code={proc.returncode}", f"duration_s={duration}"]
    if proc.stdout.strip():
        evidence.append(f"stdout={proc.stdout[-1000:]}")
    if proc.stderr.strip():
        evidence.append(f"stderr={proc.stderr[-1000:]}")
    return CheckResult(check=check.name, passed=proc.returncode == 0, evidence=evidence)


def _safe_ledger(root: Path, operation) -> None:
    """Ledger instrumentation is observational and never changes verification."""
    try:
        operation(Ledger(root))
    except Exception:
        pass


def verify_local_smoke(root: Path, run_id: str = "local-c0") -> RunResult:
    """Verify Forge's package and declared regression subset.

    Ledger writes are best-effort telemetry; the returned RunResult is always
    determined by the checks themselves.
    """
    goal = "Verify the Forge package and deterministic test suite"
    _safe_ledger(root, lambda ledger: ledger.run(run_id, goal, "C0", "local-verifier", "running"))
    _safe_ledger(root, lambda ledger: ledger.event(run_id, "goal", "local-verifier", {
        "goal": goal, "condition": "C0", "harness": "local-verifier",
    }))
    checks = [
        run_command_check(root, CommandCheck("package_import", ("uv", "run", "python", "-c", "import forge"))),
        run_command_check(root, CommandCheck("test_suite", ("uv", "run", "pytest", "-q", "tests/test_capture_contracts.py", "tests/test_journal.py", "tests/test_watchdog.py"))),
    ]
    for check in checks:
        _safe_ledger(root, lambda ledger, c=check: ledger.event(run_id, "check", "local-verifier", c.model_dump()))
    result = RunResult(
        run_id=run_id,
        goal=goal,
        condition="C0",
        harness="local-verifier",
        status="passed" if all(c.passed for c in checks) else "failed",
        checks=checks,
        wall_s=0,
        evidence_refs=[str(root / "src"), str(root / "tests")],
    )
    _safe_ledger(root, lambda ledger: ledger.update_run_status(run_id, result.status))
    _safe_ledger(root, lambda ledger: ledger.event(run_id, "verdict", "local-verifier", {
        "status": result.status, "condition": result.condition, "harness": result.harness,
        "evidence_refs": result.evidence_refs,
    }))
    return result
