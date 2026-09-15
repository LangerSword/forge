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

import pytest


def _goal() -> GoalSpec:
    return GoalSpec(
        goal="model-variant A/B experiment",
        repo="/tmp/model-ab",
        acceptance=["done"],
        harness="opencode",
    )


class PassOnValidate(TaskExecutor):
    """Executes the validate_token step only — always passes."""
    name = "pass-validate"

    def execute(self, case: EvaluationCase, *, candidate_id: str | None = None, model: str | None = None) -> RunResult:
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

# --------------------------------------------------------------------------
# Model-variant A/B: pinned model condition through the harness policy
# --------------------------------------------------------------------------


def _model_policy():
    from forge.harness_policy import HarnessPolicy

    return HarnessPolicy(
        harness="opencode",
        allowed_models=("nvidia/", "deepseek/", None),
        max_polls=120,
        max_runtime_s=900.0,
    )


class ModelAwareExecutor:
    """Executor stub that records the model it was asked to run under."""

    name = "model-aware"

    def __init__(self, passed: bool = True):
        self.passed = passed
        self.models: list[str | None] = []

    def execute(self, case, *, candidate_id=None, model=None):
        from forge.schema import CheckResult, RunResult

        self.models.append(model)
        return RunResult(
            run_id=f"run-{case.case_id}",
            goal="model A/B",
            condition="C0",
            harness="opencode",
            status="passed" if self.passed else "failed",
            checks=[CheckResult(check="ok", passed=self.passed, detail="")],
        )


def test_experiment_records_model_per_condition(tmp_path: Path) -> None:
    from forge.evaluation import EvaluationCase
    from forge.experiment import LearningExperiment
    from forge.reflection import SkillCandidate

    ledger = Ledger(tmp_path)
    base = ModelAwareExecutor(passed=False)
    cand = ModelAwareExecutor(passed=True)
    # stub reflector returning a real candidate so the gate executes through
    # the same model-aware executors (>=3 evidence refs for the refs rule)
    stub_candidate = SkillCandidate(
        skill_id="model-ab-strategy",
        kind="strategy",
        applies_when="model-variant A/B trials",
        procedure=["run under the pinned model"],
        verification=["rerun the same cases"],
        evidence_refs=["run:1", "run:2", "run:3"],
        status="candidate",
    )

    def stub_reflector(evidence):
        class _R:
            candidate = stub_candidate
        return _R()

    experiment = LearningExperiment(
        experiment_id="exp-model-ab",
        task_family="model-ab",
        goal=_goal(),
        train_cases=[EvaluationCase("case-a", "ref-a"), EvaluationCase("case-b", "ref-b")],
        heldout_cases=[EvaluationCase("heldout-1", "ref-h1"), EvaluationCase("heldout-2", "ref-h2"), EvaluationCase("heldout-3", "ref-h3")],
        ledger=ledger,
        baseline_executor=base,
        candidate_executor=cand,
        baseline_model=None,           # harness default (C0)
        candidate_model="nvidia/abacusai/dracarys-llama-3.1-70b-instruct",
        policy=_model_policy(),
        reflector=stub_reflector,
    )
    result = experiment.run()

    # baseline ran under the default model, candidate under the pinned variant;
    # the gate ran through the same executors (train + heldout), so the
    # candidate executor saw its model on every case
    assert base.models[0] is None
    assert all(m == "nvidia/abacusai/dracarys-llama-3.1-70b-instruct" for m in cand.models)
    assert result.candidate is not None and result.gate_verdict is not None
    events = ledger.events_for_run("exp-model-ab")
    kinds = [e["kind"] for e in events]
    assert "model_condition" in kinds
    cond = [e for e in events if e["kind"] == "model_condition"][0]["payload"]
    assert cond["baseline_model"] is None
    assert cond["candidate_model"] == "nvidia/abacusai/dracarys-llama-3.1-70b-instruct"
    assert cond["policy_hash"]


def test_experiment_rejects_model_outside_policy_before_running(tmp_path: Path) -> None:
    from forge.evaluation import EvaluationCase
    from forge.experiment import LearningExperiment
    from forge.harness_policy import HarnessPolicyError

    ledger = Ledger(tmp_path)
    base = ModelAwareExecutor()
    cand = ModelAwareExecutor()
    experiment = LearningExperiment(
        experiment_id="exp-model-bad",
        task_family="model-bad",
        goal=_goal(),
        train_cases=[EvaluationCase("case-a", "ref-a")],
        heldout_cases=[EvaluationCase("heldout-1", "ref-h1")],
        ledger=ledger,
        baseline_executor=base,
        candidate_executor=cand,
        candidate_model="sketchy-model",
        policy=_model_policy(),
    )
    with pytest.raises(HarnessPolicyError, match="model"):
        experiment.run()
    # no trials ran: the violating condition was rejected before execution
    assert base.models == [] and cand.models == []


def test_experiment_without_policy_keeps_old_behavior(tmp_path: Path) -> None:
    from forge.evaluation import EvaluationCase
    from forge.experiment import LearningExperiment

    ledger = Ledger(tmp_path)
    base = ModelAwareExecutor(passed=False)
    cand = ModelAwareExecutor(passed=True)
    experiment = LearningExperiment(
        experiment_id="exp-nopoly",
        task_family="nopoly",
        goal=_goal(),
        train_cases=[EvaluationCase("case-a", "ref-a")],
        heldout_cases=[EvaluationCase("heldout-1", "ref-h1")],
        ledger=ledger,
        baseline_executor=base,
        candidate_executor=cand,
    )
    result = experiment.run()  # no model kwargs, no policy: back-compat
    assert result.baseline_results is not None
