"""The AO-backed model-variant A/B executor.

Each trial runs through the real ``AORunner`` under the declared harness
policy: the model comes from the experiment condition (labeled, pinned,
policy-hash comparable), never from the worker. One bounded spawn per trial;
verifier authority is unchanged — a pass counts only with a fresh artifact
and, when configured, an independent verifier.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .ao import AOClient
from .ao_cli import AOCLI
from .ao_runner import AORunRequest, AORunner
from .harness_policy import HarnessPolicy, policy_hash
from .ledger import Ledger
from .schema import CheckResult, RunResult


class ModelABExecutor:
    """Run one trial case as a bounded AO worker under a pinned model.

    Satisfies the experiment ``TaskExecutor`` protocol: ``execute(case,
    candidate_id=..., model=...)`` → ``RunResult``. Every call spawns a
    fresh, uniquely-identified session (``run_prefix:case_id[:attempt]``) so
    trials never collide in the ledger.
    """

    name = "model-ab-executor"

    def __init__(
        self,
        *,
        ao_cli: AOCLI | None = None,
        ao_client: Any | None = None,
        ledger: Ledger,
        project: str,
        worktree: Path,
        artifact_path: Path | None,
        run_prefix: str = "model-ab",
        policy: HarnessPolicy | None = None,
        goal: str = "model-variant A/B trial",
        independent_verifier: Any | None = None,
    ) -> None:
        self.ao_cli = ao_cli or AOCLI()
        self.ao_client = ao_client or AOClient()
        self.ledger = ledger
        self.project = project
        self.worktree = worktree
        self.artifact_path = artifact_path
        self.run_prefix = run_prefix
        self.policy = policy
        self.goal = goal
        self.independent_verifier = independent_verifier
        self._attempt = 0
        self._runner = AORunner(ao_cli=self.ao_cli, ao_client=self.ao_client, ledger=ledger)

    def execute(self, case: Any, *, candidate_id: str | None = None, model: str | None = None) -> RunResult:
        self._attempt += 1
        run_id = f"{self.run_prefix}:{case.case_id}:{self._attempt}"

        # The policy is validated BEFORE any spawn — a violating model fails
        # loud here, never as a downgraded run.
        if self.policy is not None:
            self.policy.validate_request(
                AORunRequest(
                    run_id=run_id,
                    goal=self.goal,
                    project=self.project,
                    worker_name=f"ab-{case.case_id}"[:20],
                    prompt=self.goal,
                    model=model,
                )
            )

        request = AORunRequest(
            run_id=run_id,
            goal=self.goal,
            project=self.project,
            worker_name=f"ab-{case.case_id}"[:20],
            prompt=self.goal,
            harness="opencode",
            mode="chat",
            model=model,
            artifact_path=self.artifact_path,
            worktree=self.worktree,
            independent_verifier=self.independent_verifier,
            max_polls=40,
            poll_interval_s=2.0,
            max_runtime_s=300.0,
            max_idle_s=90.0,
        )
        result = self._runner.run(request, policy=self.policy)

        return RunResult(
            run_id=run_id,
            goal=self.goal,
            condition="C2" if candidate_id else "C0",
            harness="opencode",
            status=result.status,  # type: ignore[arg-type]
            checks=[CheckResult(
                check="ao_worker_completed",
                passed=result.passed,
                detail=result.reason[:300],
                evidence=[result.to_dict()["schema_version"]],
            )],
            tools_called=1,
            interventions=0,
            evidence_refs=[
                f"session:{result.session_id}" if result.session_id else "session:unavailable",
                f"artifact:{self.artifact_path}" if self.artifact_path else "artifact:none",
                f"policy:{policy_hash(self.policy)}" if self.policy else "policy:unset",
            ],
        )
