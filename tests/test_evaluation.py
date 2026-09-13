import pytest

from forge.evaluation import EvaluationCase, run_candidate_evaluation


def test_evaluator_runs_baseline_candidate_and_heldout_separately():
    calls = []

    def baseline(case, candidate_id):
        calls.append(("baseline", case.case_id, candidate_id))
        return case.case_id == "train-1"

    def candidate(case, candidate_id):
        calls.append(("candidate", case.case_id, candidate_id))
        return True

    result = run_candidate_evaluation(
        "repair-a",
        [EvaluationCase("train-1", "run:train-1"), EvaluationCase("train-2", "run:train-2")],
        [EvaluationCase("heldout-1", "run:heldout-1")],
        baseline_executor=baseline,
        candidate_executor=candidate,
    )
    assert result.evidence.baseline_passed == 1
    assert result.evidence.candidate_passed == 2
    assert result.evidence.heldout_passed == 1
    assert result.verdict.status == "validated"
    assert ("baseline", "train-1", None) in calls
    assert ("candidate", "heldout-1", "repair-a") in calls


def test_evaluator_rejects_overlap_between_train_and_heldout():
    case = EvaluationCase("same", "run:same")
    with pytest.raises(ValueError, match="disjoint"):
        run_candidate_evaluation(
            "repair-a",
            [case],
            [case],
            baseline_executor=lambda _case, _candidate: True,
            candidate_executor=lambda _case, _candidate: True,
        )


def test_evaluator_rejects_heldout_regression():
    result = run_candidate_evaluation(
        "repair-a",
        [EvaluationCase("train-1", "run:train-1")],
        [EvaluationCase("heldout-1", "run:heldout-1")],
        baseline_executor=lambda _case, _candidate: False,
        candidate_executor=lambda case, _candidate: case.case_id != "heldout-1",
    )
    assert result.verdict.status == "rejected"
    assert result.verdict.heldout_no_regression is False
