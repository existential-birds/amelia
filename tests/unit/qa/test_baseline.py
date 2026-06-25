"""Unit tests for the QA baseline store."""

from amelia.qa.baseline import load_baseline, save_baseline
from amelia.qa.models import RunMetrics, Thresholds


def _metrics() -> RunMetrics:
    return RunMetrics(
        status="completed",
        trajectory_path="/x",
        total_cost_usd=0.1,
        total_tokens=1000,
        total_duration_ms=2000,
    )


def test_missing_baseline_returns_none(tmp_path):
    assert load_baseline(tmp_path, "s1", "api") is None


def test_save_then_load_round_trip(tmp_path):
    save_baseline(tmp_path, "s1", "api", _metrics(), Thresholds())
    b = load_baseline(tmp_path, "s1", "api")
    assert b is not None
    assert b.scenario_id == "s1" and b.driver == "api"
    assert b.metrics.total_cost_usd == 0.1


def test_rebaseline_overwrites(tmp_path):
    save_baseline(tmp_path, "s1", "api", _metrics(), Thresholds())
    newer = _metrics().model_copy(update={"total_cost_usd": 0.2})
    save_baseline(tmp_path, "s1", "api", newer, Thresholds())
    loaded = load_baseline(tmp_path, "s1", "api")
    assert loaded is not None
    assert loaded.metrics.total_cost_usd == 0.2


def test_save_creates_dir(tmp_path):
    nested = tmp_path / "nested" / "baselines"
    save_baseline(nested, "s1", "api", _metrics(), Thresholds())
    assert nested.exists()
    assert load_baseline(nested, "s1", "api") is not None
