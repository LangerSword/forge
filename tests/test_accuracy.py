"""Deterministic accuracy grading for Forge's judge/gate decision path.

Architecture (from the agent-accuracy-grading skill):
    Scenario Gen → Judge Reasoning (stub) → Grading Func → Summary Stats
The gate's correct verdict is COMPUTED from the scenario by
`gate_optimal_verdict` — ground truth, not an LLM judgment. The stub reads only
the `Gate decision:` data line (never instruction text), and the grader
re-derives the prompt's numeric claims so prompt-construction bugs surface as
scored dimensions instead of silent mis-grading.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from forge.accuracy import (
    GateDecision,
    OfferScenario,
    gate_optimal_verdict,
    generate_sweep_scenarios,
    grade_case,
    parse_share_from_prompt,
    render_gate_prompt,
    run_accuracy_sweep,
    stub_judge_from_prompt,
)
from forge.ledger import Ledger


def _scenario(**overrides) -> OfferScenario:
    base = dict(
        offer_type="bundle_offer",
        discount_percent=8.0,
        add_on_price_inr=40.0,
        cart_value_inr=200.0,
    )
    base.update(overrides)
    return OfferScenario(**base)


# --------------------------------------------------------------------------
# Ground truth: the deterministic gate policy
# --------------------------------------------------------------------------

def test_gate_below_min_discount_is_declined() -> None:
    decision = gate_optimal_verdict(_scenario(discount_percent=3.0))
    assert decision.verdict == "DECLINE"
    assert decision.reason == "below_min_discount"


def test_gate_at_min_discount_boundary_is_allowed() -> None:
    decision = gate_optimal_verdict(_scenario(discount_percent=5.0))
    assert decision.verdict == "ACCEPT"
    assert decision.reason == "allowed"


def test_gate_at_cap_boundary_is_capped_not_rejected() -> None:
    decision = gate_optimal_verdict(_scenario(discount_percent=15.0))
    assert decision.verdict == "ACCEPT"
    assert decision.reason == "discount_capped"


def test_gate_above_cap_is_still_capped() -> None:
    decision = gate_optimal_verdict(_scenario(discount_percent=16.0))
    assert decision.verdict == "ACCEPT"
    assert decision.reason == "discount_capped"


def test_gate_share_formula_is_add_on_over_cart() -> None:
    """Regression: share = add_on / cart, NOT add_on / (cart - add_on).

    add_on=40, cart=200 → 20% share (allowed), not 25% (which would be
    mislabeled as acceptable at the boundary).
    """
    decision = gate_optimal_verdict(_scenario(add_on_price_inr=40.0, cart_value_inr=200.0))
    assert decision.verdict == "ACCEPT"
    assert decision.reason == "allowed"


def test_gate_exact_max_share_is_allowed() -> None:
    decision = gate_optimal_verdict(_scenario(add_on_price_inr=50.0, cart_value_inr=200.0))
    assert decision.verdict == "ACCEPT"
    assert decision.reason == "allowed"


def test_gate_share_above_max_is_capped() -> None:
    decision = gate_optimal_verdict(_scenario(add_on_price_inr=60.0, cart_value_inr=200.0))
    assert decision.verdict == "DECLINE"
    assert decision.reason == "add_on_share_capped"


# --------------------------------------------------------------------------
# Prompt construction must be numerically self-consistent (silent-bug guard)
# --------------------------------------------------------------------------

def test_parse_share_from_gate_line_matches_scenario() -> None:
    scenario = _scenario(add_on_price_inr=40.0, cart_value_inr=200.0)
    prompt = render_gate_prompt(scenario)
    assert parse_share_from_prompt(prompt) == pytest.approx(0.20, abs=0.005)


def test_parse_share_is_scoped_to_the_gate_line() -> None:
    """Instruction text may mention shares; the parser must ignore it."""
    prompt = (
        "Policy: shares above 25% are capped and rejected. The cap is 15%.\n"
        "Remember: add-on share 99% is forbidden.\n"
        "Gate decision: ACCEPT (reason: allowed; discount 8.0%, add-on share 20.0%)\n"
    )
    assert parse_share_from_prompt(prompt) == pytest.approx(0.20, abs=0.005)


def test_wrong_share_formula_is_detected_by_parse_back() -> None:
    """A broken renderer that uses add_on/(cart - add_on) surfaces as a mismatch."""
    broken_prompt = (
        "Gate decision: ACCEPT (reason: allowed; discount 8.0%, add-on share 66.7%)\n"
    )
    scenario = _scenario(add_on_price_inr=40.0, cart_value_inr=100.0)
    correct_share = scenario.add_on_price_inr / scenario.cart_value_inr
    assert parse_share_from_prompt(broken_prompt) != pytest.approx(correct_share, abs=0.005)


# --------------------------------------------------------------------------
# Stub scoping: read ONLY the Gate decision line
# --------------------------------------------------------------------------

def test_stub_reads_only_gate_decision_line() -> None:
    """Instruction text containing gate vocabulary must not drive the stub."""
    prompt = (
        "Instructions: if the gate says capped, stop; if rejected, escalate; "
        "the cap is 15% and the share cap is 25%. Capped. Rejected. Declined.\n"
        "Gate decision: ACCEPT (reason: allowed; discount 8.0%, add-on share 20.0%)\n"
    )
    actual = stub_judge_from_prompt(prompt)
    assert actual["decision"] == "continue"
    assert actual["gate"]["allowed"] is True
    assert actual["gate"]["capped"] is False
    assert actual["gate"]["rejected"] is False


def test_stub_detects_capped_and_rejected_states() -> None:
    capped = stub_judge_from_prompt(
        "Gate decision: ACCEPT (reason: discount_capped; discount 16.0%, add-on share 10.0%)\n"
    )
    assert capped["decision"] == "continue"
    assert capped["gate"]["capped"] is True

    rejected = stub_judge_from_prompt(
        "Gate decision: DECLINE (reason: add_on_share_capped; discount 8.0%, add-on share 30.0%)\n"
    )
    assert rejected["decision"] == "stop"
    assert rejected["gate"]["rejected"] is True


def test_stub_absence_of_gate_line_fails_closed() -> None:
    actual = stub_judge_from_prompt("no gate decision line here")
    assert actual["decision"] == "stop"
    assert actual["reason"] == "no_gate_decision_line"


def test_stub_accepts_verdict_aliases() -> None:
    """Verdict parsing must accept ACCEPT/APPROVE and DECLINE/REJECT aliases."""
    approve = stub_judge_from_prompt(
        "Gate decision: APPROVE (reason: allowed; discount 9.0%, add-on share 10.0%)\n"
    )
    assert approve["decision"] == "continue"

    reject = stub_judge_from_prompt(
        "Gate decision: REJECT (reason: below_min_discount; discount 2.0%, add-on share 5.0%)\n"
    )
    assert reject["decision"] == "stop"


# --------------------------------------------------------------------------
# Grading
# --------------------------------------------------------------------------

def test_grade_case_scores_all_dimensions() -> None:
    scenario = _scenario()
    expected = gate_optimal_verdict(scenario)
    prompt = render_gate_prompt(scenario)
    actual = stub_judge_from_prompt(prompt)
    grade = grade_case(scenario, expected, actual, prompt)

    assert grade.verdict_correct is True
    assert grade.gate_aware is True
    assert grade.limits_accurate is True
    assert grade.routing_appropriate is True
    assert grade.prompt_math_consistent is True
    assert grade.failure is None


def test_grade_case_flags_wrong_decision() -> None:
    scenario = _scenario()
    expected = gate_optimal_verdict(scenario)
    prompt = render_gate_prompt(scenario)
    wrong = {"decision": "stop", "reason": "allowed", "gate": {"allowed": True}}
    grade = grade_case(scenario, expected, wrong, prompt)

    assert grade.verdict_correct is False
    assert grade.routing_appropriate is False
    assert grade.failure is not None


# --------------------------------------------------------------------------
# Sweep: boundaries, per offer type, persisted, with failure detail
# --------------------------------------------------------------------------

def test_sweep_covers_boundaries_exactly() -> None:
    scenarios = generate_sweep_scenarios()
    discount_values = sorted({round(s.discount_percent, 4) for s in scenarios})
    share_values = sorted({round(s.add_on_price_inr / s.cart_value_inr, 4) for s in scenarios})
    assert discount_values == [3.0, 5.0, 8.0, 15.0, 16.0]
    assert share_values == [0.10, 0.25, 0.30]
    assert {s.offer_type for s in scenarios} == {"discount_offer", "bundle_offer"}


def test_sweep_is_perfect_on_correct_stub(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    result = run_accuracy_sweep(ledger, run_id="sweep-ok")

    summary = result["summary"]
    assert summary["total_cases"] == 60
    assert summary["verdict_correct"] == 1.0
    assert summary["gate_aware"] == 1.0
    assert summary["limits_accurate"] == 1.0
    assert summary["routing_appropriate"] == 1.0
    assert summary["prompt_math_consistent"] == 1.0
    assert summary["all_dimensions_100"] is True
    assert summary["by_offer_type"]["discount_offer"]["verdict_correct"] == 1.0
    assert summary["by_offer_type"]["bundle_offer"]["verdict_correct"] == 1.0


def test_sweep_persists_cases_and_summary_to_ledger(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    run_accuracy_sweep(ledger, run_id="sweep-persist")

    events = ledger.events_for_run("sweep-persist")
    kinds = [event["kind"] for event in events]
    assert kinds.count("accuracy_case") == 60
    assert "accuracy_summary" in kinds
    assert ledger.get_run("sweep-persist")["status"] == "passed"


def test_sweep_reports_failure_detail_when_stub_is_wrong(tmp_path: Path) -> None:
    """A stub that always declines must produce per-case failures, not noise."""

    def always_decline(prompt):
        return {"decision": "stop", "reason": "pessimistic", "gate": {"allowed": False}}

    ledger = Ledger(tmp_path)
    result = run_accuracy_sweep(
        ledger, run_id="sweep-bad", judge_stub=always_decline
    )

    summary = result["summary"]
    assert summary["verdict_correct"] < 1.0
    assert summary["all_dimensions_100"] is False
    assert summary["failure_count"] == summary["total_cases"]
    assert ledger.get_run("sweep-bad")["status"] == "failed"
    failures = [g for g in result["grades"] if not g.verdict_correct]
    first = failures[0]
    assert "expected ACCEPT" in first.failure
    assert first.scenario.offer_type in ("discount_offer", "bundle_offer")


def test_cli_accuracy_command_reports_sweep(capsys) -> None:
    import json

    from forge.cli import main_from_args_for_test

    code = main_from_args_for_test(["accuracy", "--run-id", "accuracy-cli-wireup"])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["ok"] is True
    assert out["summary"]["total_cases"] == 60
    assert out["summary"]["all_dimensions_100"] is True
    assert out["failure_count"] == 0