"""Unit tests for the QA harness data models."""

import pytest
from pydantic import ValidationError

from amelia.qa.models import QaMode, RunMetrics, Scenario, Thresholds


def test_scenario_requires_at_least_one_driver() -> None:
    with pytest.raises(ValidationError):
        Scenario(id="s1", task_title="t", task_description="d", drivers=[])


def test_thresholds_defaults() -> None:
    t = Thresholds()
    assert (t.cost_pct, t.tokens_pct, t.duration_pct) == (0.15, 0.15, 0.50)


def test_qamode_values() -> None:
    assert {m.value for m in QaMode} == {"live", "replay"}


def test_runmetrics_completed_flag() -> None:
    m = RunMetrics(
        status="completed",
        trajectory_path="/x",
        total_cost_usd=0.1,
        total_tokens=150,
        total_duration_ms=1500,
    )
    assert m.completed is True
    assert (
        RunMetrics(
            status="failed",
            trajectory_path=None,
            total_cost_usd=None,
            total_tokens=None,
            total_duration_ms=None,
        ).completed
        is False
    )


def test_scenario_issue_id_defaults_from_id() -> None:
    s = Scenario(id="greeting-helper", task_title="t", task_description="d", drivers=["api"])
    assert s.issue_id == "greeting-helper"
