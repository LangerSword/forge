"""Promote observed repair lessons into explicit candidate/validated skills."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .harness import EvaluationEvidence, GateVerdict, promote_candidate


@dataclass(frozen=True)
class SkillRecord:
    skill_id: str
    kind: str
    applies_when: str
    procedure: list[str]
    verification: list[str]
    evidence_refs: list[str]
    status: str
    gate_results: dict[str, Any]


def skill_from_repair(run_id: str, result: Any, *, evidence_ref: str) -> SkillRecord:
    return SkillRecord(
        skill_id=f"repair-{run_id}",
        kind="skill",
        applies_when="A C0 name-normalizer candidate fails a frozen acceptance check.",
        procedure=[
            "Read the verifier failure output without changing frozen tests.",
            "Apply one bounded implementation repair to c0_target.py.",
            "Re-run the frozen verifier and stop after the repair budget.",
        ],
        verification=["frozen C0 test bundle passes", "changed_files contains only the candidate implementation"],
        evidence_refs=[evidence_ref],
        status="candidate",
        gate_results={"repair_attempts": result.attempts, "passed": result.passed, "negative_lesson": result.negative_lesson},
    )


def write_skill(record: SkillRecord, root: Path) -> Path:
    path = root / ".forge" / "skills" / f"{record.skill_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(record), indent=2, sort_keys=True) + "\n")
    return path


def read_skill(path: Path) -> dict[str, Any]:
    record = json.loads(path.read_text())
    if not isinstance(record, dict) or not isinstance(record.get("skill_id"), str):
        raise ValueError("invalid skill record")
    return record


def apply_gate_verdict(path: Path, evidence: EvaluationEvidence, verdict: GateVerdict) -> Path:
    """Persist evaluator-owned gates without allowing reflection to promote."""
    record = read_skill(path)
    if record["skill_id"] != evidence.candidate_id:
        raise ValueError("candidate_id does not match skill record")
    promoted = promote_candidate(verdict)
    record["status"] = "validated" if promoted else verdict.status
    record["gate_results"] = {
        "applicability": verdict.applicability,
        "ab_benefit": verdict.ab_benefit,
        "heldout_no_regression": verdict.heldout_no_regression,
        "reasons": list(verdict.reasons),
        "candidate_id": evidence.candidate_id,
        "applicability_cases": list(evidence.applicability_cases),
        "baseline_passed": evidence.baseline_passed,
        "candidate_passed": evidence.candidate_passed,
        "heldout_passed": evidence.heldout_passed,
        "heldout_total": evidence.heldout_total,
        "evidence_refs": list(evidence.evidence_refs),
    }
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path
