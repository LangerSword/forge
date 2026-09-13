import json

from forge.harness import EvaluationEvidence, GateVerdict, evaluate_candidate, promote_candidate
from forge.skills import apply_gate_verdict, read_skill


def test_promotion_requires_all_gates():
    assert promote_candidate(GateVerdict("validated", True, True, True))
    assert not promote_candidate(GateVerdict("candidate", True, True, True))
    assert not promote_candidate(GateVerdict("validated", True, False, True))


def test_evaluation_requires_comparable_trials_and_evidence():
    evidence = EvaluationEvidence(
        candidate_id="repair-a",
        applicability_cases=("case-a", "case-b"),
        baseline_passed=1,
        candidate_passed=2,
        heldout_passed=2,
        heldout_total=2,
        evidence_refs=("run:baseline", "run:candidate", "run:heldout"),
    )
    verdict = evaluate_candidate(evidence)
    assert verdict.status == "validated"
    assert promote_candidate(verdict)


def test_evaluation_keeps_candidate_when_ab_trial_does_not_improve():
    evidence = EvaluationEvidence(
        candidate_id="repair-a",
        applicability_cases=("case-a",),
        baseline_passed=1,
        candidate_passed=1,
        heldout_passed=1,
        heldout_total=1,
        evidence_refs=("run:baseline", "run:candidate", "run:heldout"),
    )
    verdict = evaluate_candidate(evidence)
    assert verdict.status == "candidate"
    assert not promote_candidate(verdict)


def test_evaluation_rejects_missing_heldout_evidence():
    evidence = EvaluationEvidence(
        candidate_id="repair-a",
        applicability_cases=("case-a",),
        baseline_passed=1,
        candidate_passed=2,
        heldout_passed=0,
        heldout_total=0,
        evidence_refs=("run:baseline", "run:candidate"),
    )
    verdict = evaluate_candidate(evidence)
    assert verdict.status == "rejected"
    assert "heldout" in " ".join(verdict.reasons)


def test_gate_verdict_persists_on_candidate_record(tmp_path):
    path = tmp_path / ".forge" / "skills" / "repair-a.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "skill_id": "repair-a",
        "kind": "skill",
        "applies_when": "case",
        "procedure": ["step"],
        "verification": ["check"],
        "evidence_refs": ["run:candidate"],
        "status": "candidate",
        "gate_results": {},
    }))
    evidence = EvaluationEvidence(
        candidate_id="repair-a",
        applicability_cases=("case-a", "case-b"),
        baseline_passed=1,
        candidate_passed=2,
        heldout_passed=2,
        heldout_total=2,
        evidence_refs=("run:baseline", "run:candidate", "run:heldout"),
    )
    verdict = evaluate_candidate(evidence)
    updated = apply_gate_verdict(path, evidence, verdict)
    record = read_skill(updated)
    assert record["status"] == "validated"
    assert record["gate_results"]["heldout_no_regression"] is True
    assert record["gate_results"]["evidence_refs"] == ["run:baseline", "run:candidate", "run:heldout"]
