"""Integration tests for the QA runner (live mode).

Enters through ``OrchestratorService`` with real Postgres, mocking only the
``ApiDriver.execute_agentic`` external boundary — the established integration
pattern (CLAUDE.md). This boundary mock is test isolation; the shipped
replay path injects a real driver via the Task 10 ``driver_override`` seam.
"""

from unittest.mock import patch

import pytest

from amelia.drivers.api import ApiDriver
from amelia.qa.baseline import save_baseline
from amelia.qa.models import QaMode, RunMetrics, Scenario, Thresholds
from tests.integration.conftest import (
    _architect_messages,
    _scripted_execute_agentic,
    _wait_for_status,
    make_agentic_messages,
    make_reviewer_agentic_messages,
)


pytestmark = pytest.mark.integration


async def test_run_scenario_drives_to_completed_and_compares(
    orchestrator,  # type: ignore[no-untyped-def]
    test_db,  # type: ignore[no-untyped-def]
    api_profile,  # type: ignore[no-untyped-def]
    valid_worktree,  # type: ignore[no-untyped-def]
    tmp_path,  # type: ignore[no-untyped-def]
):
    from amelia.qa.runner import run_scenario

    scenario = Scenario(
        id="s1",
        task_title="Add greeting helper",
        task_description="Add a greet() helper to hello.py",
        worktree_path=valid_worktree,
        drivers=["api"],
    )
    scripts = [
        _architect_messages(),
        make_agentic_messages(),
        make_reviewer_agentic_messages(approved=True),
    ]
    save_baseline(
        tmp_path,
        "s1",
        "api",
        RunMetrics(
            status="completed",
            trajectory_path="/b",
            total_cost_usd=0.001,
            total_tokens=150,
            total_duration_ms=1500,
        ),
        Thresholds(),
    )
    with patch.object(ApiDriver, "execute_agentic", _scripted_execute_agentic(scripts)):
        result = await run_scenario(
            scenario,
            driver="api",
            mode=QaMode.LIVE,
            orchestrator=orchestrator,
            baseline_dir=tmp_path,
        )
    assert result.metrics.status == "completed"
    assert result.metrics.trajectory_path
    assert result.metrics.total_duration_ms is not None
    assert result.comparison is not None and result.comparison.smoke_passed
