"""Unit tests for QA report assembly, exit code, and table rendering."""

from amelia.qa.models import ComparisonOutcome, QaMode, RunMetrics, ScenarioResult
from amelia.qa.report import build_report, exit_code, render_table


def _result(passed: bool) -> ScenarioResult:
    return ScenarioResult(
        scenario_id="s1",
        driver="api",
        mode=QaMode.LIVE,
        metrics=RunMetrics(
            status="completed",
            trajectory_path="/x",
            total_cost_usd=0.1,
            total_tokens=1000,
            total_duration_ms=2000,
        ),
        comparison=ComparisonOutcome(
            passed=passed, smoke_passed=True, breaches=[], deltas={}
        ),
    )


def test_all_pass_overall_pass() -> None:
    r = build_report([_result(True), _result(True)])
    assert r.passed is True and exit_code(r) == 0


def test_one_fail_overall_fail() -> None:
    r = build_report([_result(True), _result(False)])
    assert r.passed is False and exit_code(r) == 1


def test_empty_results_is_not_a_pass() -> None:
    assert build_report([]).passed is False


def test_table_contains_each_cell() -> None:
    table = render_table(build_report([_result(True)]))
    assert "s1" in table and "api" in table
