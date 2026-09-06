"""Run the submission MVP: C0 failure, bounded repair, reflection skill, eval."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from .c0_fixture import create_fixture, run_fixture_verification
from .eval_report import write_eval_report
from .ledger import Ledger
from .openai_provider import OpenAIProvider
from .reflection import reflect_failure
from .repair import repair_until_pass
from .skills import skill_from_repair, write_skill
from .tracing import JsonlTraceSink
import neatlogs


def run_submission_mvp(root: Path, *, use_reflection: bool = False) -> dict:
    run_id = f"submission-c0-{uuid.uuid4().hex[:8]}"
    with neatlogs.trace("submission-mvp", kind="WORKFLOW") as wf:
        wf.set_attribute("neatlogs.workflow_name", "submission-mvp")
        return _run_submission_mvp(root, run_id=run_id, use_reflection=use_reflection)


def _run_submission_mvp(root: Path, *, run_id: str, use_reflection: bool) -> dict:
    ledger = Ledger(root)
    ledger.run(run_id, "C0 failure -> bounded repair -> reflection skill", "C0", "submission-mvp", "running")
    ledger.event(run_id, "goal", "controller", {"task_id": "c0-name-normalizer-v1", "reflection": use_reflection})
    with TemporaryDirectory(prefix="forge-submission-") as d:
        candidate = create_fixture(Path(d))
        baseline = run_fixture_verification(candidate)
        ledger.event(run_id, "baseline", "verifier", baseline)
        sink = JsonlTraceSink(root / ".forge" / "ledger" / "submission-trace.jsonl")

        class Repair:
            def repair(self, path, failure):
                path.joinpath("c0_target.py").write_text(
                    "def normalize_name(value: str) -> str:\n"
                    "    value = value.strip()\n"
                    "    if not value: raise ValueError('blank')\n"
                    "    return '-'.join(value.lower().split())\n"
                )
                return True

        repaired = repair_until_pass(candidate, adapter=Repair(), sink=sink, run_id=run_id)
        final = run_fixture_verification(candidate)
        ledger.event(run_id, "repair_verdict", "verifier", {"passed": repaired.passed, "attempts": repaired.attempts, "final": final})
        skill_path = None
        reflection = None
        if use_reflection:
            reflection = reflect_failure(
                OpenAIProvider(), run_id=run_id,
                evidence={"baseline": baseline, "repair": repaired.last_result},
            )
            if reflection.candidate:
                skill_path = root / ".forge" / "skills" / f"{reflection.candidate.skill_id}.json"
                skill_path.parent.mkdir(parents=True, exist_ok=True)
                skill_path.write_text(reflection.candidate.model_dump_json(indent=2) + "\n")
                ledger.event(run_id, "skill_candidate", "reflection", reflection.candidate.model_dump())
        else:
            skill = skill_from_repair(run_id, repaired, evidence_ref=".forge/ledger/submission-trace.jsonl")
            skill_path = write_skill(skill, root)
            ledger.event(run_id, "skill_candidate", "local-reflection", {"path": str(skill_path), "status": skill.status})
        report = write_eval_report(root, run_id=run_id, baseline=baseline, repaired=final, skill_path=skill_path)
        ledger.event(run_id, "verdict", "controller", {"passed": final["passed"], "report": str(report), "skill": str(skill_path) if skill_path else None})
        ledger.update_run_status(run_id, "passed" if final["passed"] else "failed")
        tracked_report = root / "evals" / "results" / f"{run_id}.json"
        tracked_report.parent.mkdir(parents=True, exist_ok=True)
        tracked_report.write_text(report.read_text())
        return {
            "run_id": run_id,
            "baseline": baseline,
            "repair": {"passed": repaired.passed, "attempts": repaired.attempts, "negative_lesson": repaired.negative_lesson},
            "final": final,
            "skill_path": str(skill_path) if skill_path else None,
            "reflection_error": reflection.error if reflection else None,
            "eval_report": str(report),
            "tracked_eval_report": str(tracked_report),
        }
