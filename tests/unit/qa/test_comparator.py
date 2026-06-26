"""Unit tests for the QA comparator (net-new capability)."""

from amelia.qa.comparator import compare
from amelia.qa.models import Baseline, RunMetrics, Thresholds


def _baseline(cost: float = 0.10, tokens: int = 1000, dur: int = 2000) -> Baseline:
    return Baseline(
        scenario_id="s1",
        driver="api",
        metrics=RunMetrics(
            status="completed",
            trajectory_path="/b",
            total_cost_usd=cost,
            total_tokens=tokens,
            total_duration_ms=dur,
        ),
        thresholds=Thresholds(),
    )


def test_completed_within_bands_passes() -> None:
    run = RunMetrics(
        status="completed",
        trajectory_path="/x",
        total_cost_usd=0.11,
        total_tokens=1050,
        total_duration_ms=2500,
    )
    out = compare(run, _baseline())
    assert out.smoke_passed and out.passed and out.breaches == []


def test_not_completed_fails_smoke() -> None:
    run = RunMetrics(
        status="failed",
        trajectory_path=None,
        total_cost_usd=None,
        total_tokens=None,
        total_duration_ms=None,
    )
    out = compare(run, _baseline())
    assert out.smoke_passed is False and out.passed is False


def test_cost_over_band_fails_efficiency() -> None:
    run = RunMetrics(
        status="completed",
        trajectory_path="/x",
        total_cost_usd=0.20,
        total_tokens=1000,
        total_duration_ms=2000,
    )
    out = compare(run, _baseline())  # +100% cost vs +/-15%
    assert out.smoke_passed is True and out.passed is False
    assert any("cost" in b for b in out.breaches)


def test_duration_uses_wider_band() -> None:
    run = RunMetrics(
        status="completed",
        trajectory_path="/x",
        total_cost_usd=0.10,
        total_tokens=1000,
        total_duration_ms=2900,
    )
    out = compare(run, _baseline())  # +45% duration vs +/-50% -> ok
    assert out.passed is True


def test_under_budget_never_breaches() -> None:
    run = RunMetrics(
        status="completed",
        trajectory_path="/x",
        total_cost_usd=0.01,  # -90% cost
        total_tokens=100,  # -90% tokens
        total_duration_ms=100,  # -95% duration
    )
    out = compare(run, _baseline())
    assert out.passed is True and out.breaches == []


def test_missing_baseline_metric_is_skipped_not_breach() -> None:
    baseline = Baseline(
        scenario_id="s1",
        driver="api",
        metrics=RunMetrics(
            status="completed",
            trajectory_path="/b",
            total_cost_usd=None,  # missing -> skip
            total_tokens=1000,
            total_duration_ms=2000,
        ),
        thresholds=Thresholds(),
    )
    run = RunMetrics(
        status="completed",
        trajectory_path="/x",
        total_cost_usd=999.0,  # would breach if base were present
        total_tokens=1050,
        total_duration_ms=2000,
    )
    out = compare(run, baseline)
    assert out.passed is True
    assert "cost" not in out.deltas
