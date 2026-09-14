"""Deterministic accuracy grading for Forge's judge/gate decision path.

Methodology (agent-accuracy-grading skill):

    Scenario Gen -> Judge Reasoning (stub) -> Grading Func -> Summary Stats

- The gate's correct verdict is COMPUTED from scenario parameters by
  ``gate_optimal_verdict`` — ground truth, never an LLM judgment.
- The stub reads ONLY the ``Gate decision:`` data line; instruction text
  containing gate vocabulary must never drive it.
- The grader re-derives numeric claims from the rendered prompt (add-on share)
  so prompt-construction bugs surface as scored dimensions instead of silent
  mis-grading. The share formula is add_on / cart — NOT add_on / (cart - add_on).
- Sweeps cover the decision boundary exactly (below / at / above every
  threshold) with per-offer-type breakdowns, and persist every case plus a
  per-dimension summary to the Ledger with failure detail.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Callable

from .ledger import Ledger

MIN_DISCOUNT_PERCENT = 5.0
MAX_DISCOUNT_PERCENT = 15.0  # cap: still accepted, but recorded as capped
MAX_ADD_ON_SHARE = 0.25

GATE_LINE_RE = re.compile(r"Gate decision:\s*([A-Z]+)(?:\s*\((.+?)\))?")
SHARE_IN_GATE_LINE_RE = re.compile(r"add-on share ([\d.]+)%")

SHARE_TOLERANCE = 0.005


@dataclass(frozen=True)
class OfferScenario:
    """One purchasable scenario the judge must evaluate."""

    offer_type: str  # discount_offer | bundle_offer
    discount_percent: float
    add_on_price_inr: float
    cart_value_inr: float


@dataclass(frozen=True)
class GateDecision:
    """The deterministic gate's verdict and why (ground truth)."""

    verdict: str  # ACCEPT | DECLINE
    reason: str   # allowed | below_min_discount | discount_capped | add_on_share_capped


def add_on_share(scenario: OfferScenario) -> float:
    """share = add_on / cart. NOT add_on / (cart - add_on)."""
    return scenario.add_on_price_inr / scenario.cart_value_inr


def gate_optimal_verdict(
    scenario: OfferScenario,
    *,
    min_discount_percent: float = MIN_DISCOUNT_PERCENT,
    max_discount_percent: float = MAX_DISCOUNT_PERCENT,
    max_add_on_share: float = MAX_ADD_ON_SHARE,
) -> GateDecision:
    """The correct decision for this scenario — used to grade the judge."""
    if scenario.discount_percent < min_discount_percent:
        return GateDecision("DECLINE", "below_min_discount")
    if scenario.discount_percent >= max_discount_percent:
        return GateDecision("ACCEPT", "discount_capped")
    if add_on_share(scenario) > max_add_on_share:
        return GateDecision("DECLINE", "add_on_share_capped")
    return GateDecision("ACCEPT", "allowed")


def render_gate_prompt(
    scenario: OfferScenario,
    *,
    share_fn: Callable[[OfferScenario], float] | None = None,
) -> str:
    """Render the context a judge sees, including the Gate decision data line.

    ``share_fn`` is injectable so a wrong-formula renderer can be tested; the
    production default is the correct add_on / cart formula.
    """
    share = (share_fn or add_on_share)(scenario)
    decision = gate_optimal_verdict(scenario)
    data_line = (
        f"Gate decision: {decision.verdict} (reason: {decision.reason}; "
        f"discount {scenario.discount_percent}%, add-on share {share * 100:.1f}%)"
    )
    return (
        "Judge instructions: you evaluate one offer against the gate. "
        "Discounts below 5% are declined; discounts above 15% are capped; "
        "add-on shares above 25% are rejected. Read the Gate decision line "
        "and route accordingly. Capped. Rejected. Declined.\n\n"
        f"{data_line}"
    )


def _gate_line(prompt: str) -> str:
    match = GATE_LINE_RE.search(prompt)
    return match.group(0) if match else ""


def parse_share_from_prompt(prompt: str) -> float | None:
    """The add-on share as rendered in the Gate decision data line only."""
    match = SHARE_IN_GATE_LINE_RE.search(_gate_line(prompt))
    return float(match.group(1)) / 100.0 if match else None


def stub_judge_from_prompt(prompt: str) -> dict[str, Any]:
    """Scenario-aware stub: driven ONLY by the Gate decision data line.

    Missing data line -> fail closed (stop with no_gate_decision_line).
    Verdict aliases normalize: ACCEPT/APPROVE accept, DECLINE/REJECT reject.
    """
    match = GATE_LINE_RE.search(prompt)
    if match is None:
        return {"decision": "stop", "reason": "no_gate_decision_line", "gate": None}
    verdict = match.group(1).upper()
    detail = (match.group(2) or "").lower()
    reason_token = detail.split(";")[0].strip() if detail else ""
    if reason_token.startswith("reason:"):
        reason_token = reason_token[len("reason:"):].strip()
    accepted = verdict in ("ACCEPT", "APPROVE")
    gate = {
        "verdict": verdict,
        "accepted": accepted,
        "capped": "discount_capped" in detail,
        "rejected": "add_on_share_capped" in detail,
        "below_min": "below_min_discount" in detail,
        "allowed": "allowed" in detail,
    }
    decision = "continue" if accepted else "stop"
    return {"decision": decision, "reason": reason_token, "gate": gate}


@dataclass
class CaseGrade:
    """One graded scenario with per-dimension scores and failure detail."""

    scenario: OfferScenario
    expected: GateDecision
    actual_decision: str
    gate_aware: bool
    limits_accurate: bool
    verdict_correct: bool
    routing_appropriate: bool
    prompt_math_consistent: bool
    failure: str | None = None


def grade_case(
    scenario: OfferScenario,
    expected: GateDecision,
    actual: dict[str, Any],
    prompt: str,
) -> CaseGrade:
    """Score one judge decision against the computable ground truth."""
    gate = actual.get("gate") or {}
    expected_accepted = expected.verdict == "ACCEPT"

    if expected.reason == "allowed":
        correct_state = bool(gate.get("allowed"))
    elif expected.reason == "discount_capped":
        correct_state = bool(gate.get("capped"))
    elif expected.reason == "add_on_share_capped":
        correct_state = bool(gate.get("rejected"))
    elif expected.reason == "below_min_discount":
        correct_state = bool(gate.get("below_min"))
    else:  # unknown reason: cannot be aware of the gate
        correct_state = False

    # verdict_correct: decision direction matches the gate's verdict
    actual_accepted = actual.get("decision") in ("continue", "retry", "reroute")
    verdict_correct = actual_accepted == expected_accepted

    # limits_accurate: the stub's cited reason matches the gate's reason exactly
    limits_accurate = str(actual.get("reason", "")).strip() == expected.reason

    # routing_appropriate: accepted -> continue; declined -> stop/escalate
    routing_appropriate = (
        actual.get("decision") == "continue"
        if expected_accepted
        else actual.get("decision") in ("stop", "escalate")
    )

    # prompt_math_consistent: rendered share re-derived from the scenario
    shown_share = parse_share_from_prompt(prompt)
    math_ok = (
        shown_share is not None
        and abs(shown_share - add_on_share(scenario)) <= SHARE_TOLERANCE
    )

    failures: list[str] = []
    if not verdict_correct:
        failures.append(
            f"expected {'ACCEPT' if expected_accepted else 'DECLINE'}, "
            f"got decision={actual.get('decision')!r}"
        )
    if not correct_state:
        failures.append(f"gate state mismatch: expected reason={expected.reason}")
    if not limits_accurate:
        failures.append(
            f"limits: expected reason={expected.reason!r}, "
            f"cited={actual.get('reason')!r}"
        )
    if not routing_appropriate:
        failures.append(f"routing not appropriate for decision={actual.get('decision')!r}")
    if not math_ok:
        failures.append(
            f"prompt share {shown_share} != scenario share {add_on_share(scenario):.4f}"
        )

    return CaseGrade(
            scenario=scenario,
            expected=expected,
            actual_decision=str(actual.get("decision")),
            gate_aware=correct_state,
            limits_accurate=limits_accurate,
            verdict_correct=verdict_correct,
            routing_appropriate=routing_appropriate,
            prompt_math_consistent=math_ok,
            failure="; ".join(failures) if failures else None,
        )


def generate_sweep_scenarios() -> list[OfferScenario]:
    """Exact boundary coverage: below / at / above each threshold, both types."""
    discounts = [3.0, 5.0, 8.0, 15.0, 16.0]   # below min, at min, between, at cap, above cap
    shares = [0.10, 0.25, 0.30]                 # below max, at max, above max
    carts = [100.0, 400.0]
    scenarios: list[OfferScenario] = []
    for offer_type in ("discount_offer", "bundle_offer"):
        for cart in carts:
            for discount in discounts:
                for share in shares:
                    add_on = round(cart * share, 2)
                    scenarios.append(
                        OfferScenario(offer_type, discount, add_on, cart)
                    )
    return scenarios


def _rate(items: list[bool]) -> float:
    return sum(items) / len(items) if items else 0.0


def run_accuracy_sweep(
    ledger: Ledger,
    *,
    run_id: str = "accuracy-sweep",
    scenarios: list[OfferScenario] | None = None,
    judge_stub: Callable[[str], dict[str, Any]] = stub_judge_from_prompt,
    renderer: Callable[[OfferScenario], str] = render_gate_prompt,
) -> dict[str, Any]:
    """Run the boundary sweep and persist every case + summary to the ledger."""
    scenarios = scenarios if scenarios is not None else generate_sweep_scenarios()
    grades: list[CaseGrade] = []
    for scenario in scenarios:
        prompt = renderer(scenario)
        actual = judge_stub(prompt)
        expected = gate_optimal_verdict(scenario)
        grade = grade_case(scenario, expected, actual, prompt)
        grades.append(grade)
        ledger.event(run_id, "accuracy_case", "accuracy-grader", {
            "offer_type": scenario.offer_type,
            "discount_percent": scenario.discount_percent,
            "add_on_price_inr": scenario.add_on_price_inr,
            "cart_value_inr": scenario.cart_value_inr,
            "expected_verdict": expected.verdict,
            "expected_reason": expected.reason,
            "actual_decision": grade.actual_decision,
            "verdict_correct": grade.verdict_correct,
            "gate_aware": grade.gate_aware,
            "limits_accurate": grade.limits_accurate,
            "routing_appropriate": grade.routing_appropriate,
            "prompt_math_consistent": grade.prompt_math_consistent,
            "failure": grade.failure,
        })

    by_type: dict[str, dict[str, Any]] = {}
    for offer_type in ("discount_offer", "bundle_offer"):
        subset = [g for g in grades if g.scenario.offer_type == offer_type]
        by_type[offer_type] = {
            "total": len(subset),
            "verdict_correct": _rate([g.verdict_correct for g in subset]),
            "gate_aware": _rate([g.gate_aware for g in subset]),
            "limits_accurate": _rate([g.limits_accurate for g in subset]),
            "routing_appropriate": _rate([g.routing_appropriate for g in subset]),
            "prompt_math_consistent": _rate([g.prompt_math_consistent for g in subset]),
        }

    summary: dict[str, Any] = {
        "total_cases": len(grades),
        "verdict_correct": _rate([g.verdict_correct for g in grades]),
        "gate_aware": _rate([g.gate_aware for g in grades]),
        "limits_accurate": _rate([g.limits_accurate for g in grades]),
        "routing_appropriate": _rate([g.routing_appropriate for g in grades]),
        "prompt_math_consistent": _rate([g.prompt_math_consistent for g in grades]),
        "failure_count": sum(1 for g in grades if g.failure is not None),
        "by_offer_type": by_type,
    }
    summary["all_dimensions_100"] = all(
        abs(summary[dim] - 1.0) < 1e-9
        for dim in ("verdict_correct", "gate_aware", "limits_accurate",
                    "routing_appropriate", "prompt_math_consistent")
    )
    ledger.event(run_id, "accuracy_summary", "accuracy-grader", summary)
    ledger.run(
        run_id,
        "deterministic accuracy sweep for the judge/gate path",
        "EVAL",
        "accuracy-grader",
        "passed" if summary["all_dimensions_100"] else "failed",
    )
    return {
        "run_id": run_id,
        "grades": grades,
        "summary": summary,
    }