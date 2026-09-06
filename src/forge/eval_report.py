"""Submission-ready before/after evaluation report."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_eval_report(root: Path, *, run_id: str, baseline: dict[str, Any], repaired: dict[str, Any], skill_path: Path | None) -> Path:
    report = {
        "schema_version": "forge.eval.v1",
        "run_id": run_id,
        "task": "c0-name-normalizer-v1",
        "conditions": {
            "C0_baseline": {"passed": baseline["passed"], "exit_code": baseline["exit_code"]},
            "C0_repaired": {"passed": repaired["passed"], "exit_code": repaired["exit_code"]},
        },
        "improvement": {
            "baseline_failed": not baseline["passed"],
            "repaired_passed": repaired["passed"],
            "skill_created": skill_path is not None,
        },
        "evidence": {
            "baseline_failure_code": baseline.get("failure_code"),
            "repaired_changed_files": repaired.get("changed_files", []),
            "skill_path": str(skill_path) if skill_path else None,
        },
        "claims": [
            "The verifier observed a failing baseline and a passing repaired candidate.",
            "The skill is validated only for this bounded C0 task family; no cross-domain transfer is claimed.",
        ],
    }
    path = root / ".forge" / "runs" / f"{run_id}-eval.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return path
