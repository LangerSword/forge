"""Deterministic learning experiment: baseline → reflect → gate → learned → compare.

This is the core thesis loop: run a repeatable task with no learned capability,
optionally reflect on failures, gate the candidate, and if validated, re-run
with the playbook injected. Every trial is persisted as a ledger event.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from .evaluation import EvaluationCase, run_candidate_evaluation
from .harness import evaluate_candidate, promote_candidate
from .ledger import Ledger
from .playbook import Playbook, PlaybookRegistry, run_playbook_trial
from .reflection import SkillCandidate
from .schema import ComparisonResult, GoalSpec, RunResult
from .tooling import Tool, ToolRegistry


class TaskExecutor(Protocol):
    """Executes a single trial case, with optional candidate ID."""

    name: str

    def execute(self, case: EvaluationCase, *, candidate_id: str | None = None, model: str | None = None) -> RunResult: ...


class _PolicyProbe:
    """Minimal request-shaped probe so the harness policy can validate an
    experiment's model conditions without a full AORunRequest."""

    def __init__(self, *, harness: str, mode: str, model: str | None):
        self.harness = harness
        self.mode = mode
        self.model = model
        self.max_polls = 0
        self.poll_interval_s = 0.0
        self.max_runtime_s = None
        self.max_idle_s = 0.0


@dataclass
class LearningExperiment:
    """Run baseline trials, optionally reflect, gate, and run learned trials.

    All trials are persisted to the ledger. The comparison is computed only
    if both baseline and learned results exist.
    """

    experiment_id: str
    task_family: str
    goal: GoalSpec
    train_cases: list[EvaluationCase]
    heldout_cases: list[EvaluationCase]
    ledger: Ledger
    baseline_executor: TaskExecutor
    candidate_executor: TaskExecutor
    baseline_model: str | None = None
    candidate_model: str | None = None
    policy: Any | None = None
    reflector: Callable[[dict[str, Any]], Any] | None = None
    playbook: Playbook | None = None
    tool_registry: ToolRegistry | None = None

    # Filled by .run()
    baseline_results: list[RunResult] | None = None
    candidate: SkillCandidate | None = None
    gate_verdict: Any = None
    learned_results: list[RunResult] | None = None
    comparison: ComparisonResult | None = None

    def run(self) -> LearningExperiment:
        # Harness policy is validated BEFORE any trial executes: a model
        # outside the allowlist fails loud here, never as a downgraded run.
        if self.policy is not None:
            from .harness_policy import policy_hash

            self.policy.validate_request(
                _PolicyProbe(
                    harness=self.goal.harness,
                    mode="chat",
                    model=self.baseline_model,
                )
            )
            self.policy.validate_request(
                _PolicyProbe(
                    harness=self.goal.harness,
                    mode="chat",
                    model=self.candidate_model,
                )
            )
            self.ledger.event(self.experiment_id, "model_condition", "experiment", {
                "baseline_model": self.baseline_model,
                "candidate_model": self.candidate_model,
                "policy_hash": policy_hash(self.policy),
                "harness": self.goal.harness,
            })

        self.ledger.event(self.experiment_id, "experiment_started", "experiment", {
            "task_family": self.task_family,
            "goal": self.goal.goal,
            "train_count": len(self.train_cases),
            "heldout_count": len(self.heldout_cases),
        })

        # Phase 1: Baseline trials
        self.baseline_results = []
        for case in self.train_cases:
            result = self.baseline_executor.execute(case, candidate_id=None, model=self.baseline_model)
            self.baseline_results.append(result)
            self.ledger.event(self.experiment_id, "trial_recorded", "experiment", {
                "case_id": case.case_id,
                "condition": "baseline",
                "passed": result.status == "passed",
                "tools_called": result.tools_called,
                "interventions": result.interventions,
            })

        # Phase 2: Optional reflection → candidate
        if self.reflector is not None:
            baseline_passed = all(r.status == "passed" for r in self.baseline_results)
            if not baseline_passed:
                evidence = {
                    "task_id": self.experiment_id,
                    "failure_code": "baseline_failure",
                    "changed_files": [],
                    "test_bundle_sha256": "",
                    "passed": False,
                    "exit_code": 1,
                }
                try:
                    reflection = self.reflector(evidence)
                    self.candidate = reflection.candidate if hasattr(reflection, "candidate") else None
                except Exception:
                    self.candidate = None

        # Phase 3: Gate evaluation
        if self.candidate is not None:
            try:
                eval_run = run_candidate_evaluation(
                    candidate_id=self.candidate.skill_id,
                    train_cases=self.train_cases,
                    heldout_cases=self.heldout_cases,
                    baseline_executor=lambda case, cid=None: self.baseline_executor.execute(case, candidate_id=cid, model=self.baseline_model).status == "passed",
                    candidate_executor=lambda case, cid=None: self.candidate_executor.execute(case, candidate_id=cid, model=self.candidate_model).status == "passed",
                )
                self.gate_verdict = eval_run.verdict
                self.ledger.event(self.experiment_id, "gate_verdict", "experiment", {
                    "candidate_id": self.candidate.skill_id,
                    "status": self.gate_verdict.status,
                    "applicability": self.gate_verdict.applicability,
                    "ab_benefit": self.gate_verdict.ab_benefit,
                    "heldout_no_regression": self.gate_verdict.heldout_no_regression,
                })
            except Exception as exc:
                self.ledger.event(self.experiment_id, "gate_error", "experiment", {
                    "error": str(exc),
                })

        # Phase 4: Learned trials (only if validated)
        if self.gate_verdict is not None and promote_candidate(self.gate_verdict):
            if self.playbook is not None:
                self.learned_results = []
                for case in self.train_cases:
                    trial = run_playbook_trial(
                        ledger=self.ledger,
                        run_id=f"{self.experiment_id}:{case.case_id}",
                        task_id=case.case_id,
                        goal=self.goal,
                        worktree=Path(self.goal.repo),
                        playbook=self.playbook,
                        tool_registry=self.tool_registry,
                    )
                    self.learned_results.append(RunResult(
                        run_id=trial.trial_id,
                        goal=self.goal.goal,
                        condition="C2",
                        harness="local",
                        status="passed" if trial.passed else "failed",
                        checks=[],
                        tools_called=len(trial.tool_calls),
                        interventions=trial.interventions,
                        evidence_refs=list(trial.evidence_refs),
                    ))
                    self.ledger.event(self.experiment_id, "trial_recorded", "experiment", {
                        "case_id": case.case_id,
                        "condition": "learned",
                        "playbook_id": self.playbook.playbook_id,
                        "passed": trial.passed,
                        "tool_calls": len(trial.tool_calls),
                        "interventions": trial.interventions,
                    })

        # Phase 5: Comparison
        if self.baseline_results and self.learned_results:
            avg_base = self._aggregate(self.baseline_results)
            avg_learned = self._aggregate(self.learned_results)
            self.comparison = avg_base.compare(avg_learned)
            self.ledger.event(self.experiment_id, "experiment_completed", "experiment", {
                "improved": self.comparison.improved,
                "regression": self.comparison.regression,
                "deltas": self.comparison.deltas,
                "reasons": list(self.comparison.reasons),
            })
        else:
            self.ledger.event(self.experiment_id, "experiment_completed", "experiment", {
                "improved": False,
                "regression": False,
                "note": "no_learned_results_to_compare",
            })

        return self

    @staticmethod
    def _aggregate(results: list[RunResult]) -> RunResult:
        """Average multiple trials into one representative RunResult."""
        n = len(results)
        if n == 0:
            return RunResult(run_id="aggregate", goal="", condition="C0", harness="local", status="failed", checks=[])
        return RunResult(
            run_id=f"aggregate-{results[0].run_id}",
            goal=results[0].goal,
            condition=results[0].condition,
            harness="local",
            status="passed" if all(r.status == "passed" for r in results) else "failed",
            checks=[],
            tools_called=sum(r.tools_called for r in results) // n,
            interventions=sum(r.interventions for r in results) // n,
            wall_s=sum(r.wall_s or 0 for r in results) / n,
            tokens_in=sum(r.tokens_in or 0 for r in results) // n if any(r.tokens_in is not None for r in results) else None,
            tokens_out=sum(r.tokens_out or 0 for r in results) // n if any(r.tokens_out is not None for r in results) else None,
            cost_usd=sum(r.cost_usd or 0 for r in results) / n if any(r.cost_usd is not None for r in results) else None,
            evidence_refs=[ref for r in results for ref in r.evidence_refs],
        )