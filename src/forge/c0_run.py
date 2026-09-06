"""Run the deterministic C0 fixture and persist its evidence."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import neatlogs

from .c0_fixture import create_fixture, run_fixture_verification
from .ledger import Ledger


@neatlogs.span(kind="WORKFLOW", name="run_c0")
def run_c0(root: Path, run_id: str = "c0-name-normalizer", candidate: Path | None = None) -> dict:
    if candidate is None:
        raise ValueError("candidate path is required; C0 never writes the solution under test")
    ledger = Ledger(root)
    ledger.run(run_id, "Implement and verify normalize_name", "C0", "local-fixture", "running")
    ledger.event(run_id, "goal", "c0-runner", {"task_id": "c0-name-normalizer-v1"})
    with TemporaryDirectory(prefix="forge-c0-") as temp:
        fixture = create_fixture(Path(temp))
        ledger.event(run_id, "fixture", "c0-runner", {"path": str(fixture), "status": "red_baseline"})
        baseline = run_fixture_verification(fixture)
        ledger.event(run_id, "baseline", "verifier", baseline)
        candidate_path = candidate or fixture
        result = run_fixture_verification(candidate_path)
        ledger.event(run_id, "verdict", "verifier", result)
        ledger.db.execute("UPDATE runs SET status=? WHERE run_id=?", ("passed" if result["passed"] else "failed", run_id))
        ledger.db.commit()
        return {"run_id": run_id, "baseline": baseline, "result": result, "ledger": ledger.counts()}
