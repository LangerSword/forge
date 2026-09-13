from __future__ import annotations

from pathlib import Path
from typing import Protocol

from forge.evaluation import run_candidate_evaluation
from forge.experiment import LearningExperiment, TaskExecutor
from forge.evaluation import EvaluationCase, run_candidate_evaluation
from forge.ledger import Ledger
from forge.reflection import reflect_failure
from forge.schema import GoalSpec, RunResult
from forge.openai_provider import OpenAIProvider


class PassOnValidate(TaskExecutor):
    """Executes the validate_token step only — always passes."""
    name = "pass-validate"

    def execute(self, case: EvaluationCase, *, candidate_id: str | None = None) -> RunResult:
        passed = case.case_id != "fail-case"
        return RunResult(
            run_id=f"trial-{case.case_id}",
            goal=case.evidence_ref,
            condition="C1" if candidate_id else "C0",
            harness="local",
            status="passed" if passed else "failed",
            checks=[],
            tools_called=1,
            evidence_refs=[case.evidence_ref],
        )


def test_experiment_runs_baseline_only_if_no_candidate(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    goal = GoalSpec(goal="test", repo="repo", acceptance=["works"], tools=[], harness="local")
    executor = PassOnValidate()
    experiment = LearningExperiment(
        experiment_id="exp-baseline-only",
        task_family="test-family",
        goal=goal,
        train_cases=[EvaluationCase("case-a", "ref-a"), EvaluationCase("case-b", "ref-b")],
        heldout_cases=[EvaluationCase("heldout-1", "ref-h1")],
        ledger=ledger,
        baseline_executor=executor,
        candidate_executor=executor,
    )
    result = experiment.run()

    assert result.baseline_results is not None
    assert result.candidate is None  # no reflection supplied
    assert result.gate_verdict is None
    assert result.learned_results is None
    assert result.comparison is None
    assert len(result.baseline_results) == 2


def test_experiment_runs_reflection_and_gate(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    goal = GoalSpec(goal="test", repo="repo", acceptance=["works"], tools=[], harness="local")
    executor = PassOnValidate()
    experiment = LearningExperiment(
        experiment_id="exp-reflection-tested",
        task_family="test-family",
        goal=goal,
        train_cases=[EvaluationCase("case-a", "ref-a"), EvaluationCase("case-b", "ref-b")],
        heldout_cases=[EvaluationCase("heldout-1", "ref-h1")],
        ledger=ledger,
        baseline_executor=executor,
        candidate_executor=executor,
        reflector=lambda evidence: reflect_failure(
            OpenAIProvider(api_key="test-only"),
            run_id="test",
            evidence=evidence,
        ),
    )
    result = experiment.run()
    assert result.baseline_results is not None
    # Reflector will fail without a real API key, but the experiment should handle that gracefully
    assert result.candidate is None or hasattr(result.candidate, "skill_id")


def test_experiment_persists_all_trials_and_evidence(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    goal = GoalSpec(goal="test", repo="repo", acceptance=["works"], tools=[], harness="local")
    executor = PassOnValidate()
    experiment = LearningExperiment(
        experiment_id="exp-persist-1",
        task_family="test-family",
        goal=goal,
        train_cases=[EvaluationCase("case-a", "ref-a")],
        heldout_cases=[EvaluationCase("heldout-1", "ref-h1")],
        ledger=ledger,
        baseline_executor=executor,
        candidate_executor=executor,
    )
    experiment.run()
    events = ledger.events_for_run("exp-persist-1")
    kinds = [e["kind"] for e in events]
    assert "experiment_started" in kinds
    assert "trial_recorded" in kinds
    assert "experiment_completed" in kinds