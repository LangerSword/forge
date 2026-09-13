from __future__ import annotations

from forge.schema import ComparisonResult, RunResult


def test_compare_improved_pass_rate() -> None:
    baseline = RunResult(
        run_id="baseline", goal="test", condition="C0", harness="local",
        status="failed", checks=[], tools_called=5, interventions=2, wall_s=30.0,
    )
    learned = RunResult(
        run_id="learned", goal="test", condition="C1", harness="local",
        status="passed", checks=[], tools_called=3, interventions=1, wall_s=20.0,
    )
    comparison = baseline.compare(learned)
    assert comparison.improved is True
    assert comparison.regression is False
    assert comparison.deltas["passed"] == 1
    assert comparison.deltas["tools_called"] == -2
    assert comparison.deltas["interventions"] == -1


def test_compare_tool_call_regression() -> None:
    baseline = RunResult(run_id="bl", goal="g", condition="C0", harness="local", status="passed", checks=[], tools_called=2)
    learned = RunResult(run_id="ln", goal="g", condition="C1", harness="local", status="passed", checks=[], tools_called=10)
    c = baseline.compare(learned)
    assert c.improved is False
    assert c.regression is True
    assert any("regression" in r for r in c.reasons)


def test_compare_intervention_regression() -> None:
    baseline = RunResult(run_id="bl", goal="g", condition="C0", harness="local", status="passed", checks=[], interventions=0)
    learned = RunResult(run_id="ln", goal="g", condition="C1", harness="local", status="passed", checks=[], interventions=5)
    c = baseline.compare(learned)
    assert c.regression is True


def test_compare_equal_passes_no_regression() -> None:
    a = RunResult(run_id="a", goal="g", condition="C0", harness="local", status="passed", checks=[], tools_called=3, interventions=1)
    b = RunResult(run_id="b", goal="g", condition="C1", harness="local", status="passed", checks=[], tools_called=3, interventions=1)
    c = a.compare(b)
    assert c.regression is False
    assert c.improved is False
    assert c.reasons == ("no_detectable_change",)


def test_compare_absent_cost_stays_null() -> None:
    a = RunResult(run_id="a", goal="g", condition="C0", harness="local", status="failed", checks=[], cost_usd=None, tokens_in=None, tokens_out=None)
    b = RunResult(run_id="b", goal="g", condition="C1", harness="local", status="passed", checks=[], cost_usd=None, tokens_in=None, tokens_out=None)
    c = a.compare(b)
    assert c.deltas["cost_usd"] is None
    assert c.deltas["tokens_in"] is None
    assert c.deltas["tokens_out"] is None


def test_compare_baseline_failed_learned_passed_is_improvement() -> None:
    a = RunResult(run_id="a", goal="g", condition="C0", harness="local", status="failed", checks=[])
    b = RunResult(run_id="b", goal="g", condition="C1", harness="local", status="passed", checks=[])
    c = a.compare(b)
    assert c.improved is True
    assert c.regression is False


def test_compare_baseline_passed_learned_failed_is_regression() -> None:
    a = RunResult(run_id="a", goal="g", condition="C0", harness="local", status="passed", checks=[])
    b = RunResult(run_id="b", goal="g", condition="C1", harness="local", status="failed", checks=[])
    c = a.compare(b)
    assert c.improved is False
    assert c.regression is True


def test_compare_returns_delta_for_metrics() -> None:
    a = RunResult(
        run_id="a", goal="g", condition="C0", harness="local", status="passed", checks=[],
        tools_called=5, interventions=3, wall_s=15.0,
    )
    b = RunResult(
        run_id="b", goal="g", condition="C1", harness="local", status="passed", checks=[],
        tools_called=3, interventions=1, wall_s=10.0,
    )
    c = a.compare(b)
    assert c.deltas["tools_called"] == -2
    assert c.deltas["interventions"] == -2
    assert c.deltas["wall_s"] == -5.0


def test_compare_improved_tool_calls_only() -> None:
    a = RunResult(run_id="a", goal="g", condition="C0", harness="local", status="passed", checks=[], tools_called=8, interventions=0)
    b = RunResult(run_id="b", goal="g", condition="C1", harness="local", status="passed", checks=[], tools_called=3, interventions=0)
    c = a.compare(b)
    assert c.improved is True
    assert c.regression is False