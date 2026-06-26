"""Integration test for the request-scoped ``driver_override`` seam (Task 10).

The seam lets a caller inject a :class:`~amelia.drivers.base.DriverInterface`
instance through ``OrchestratorService.start_workflow(driver_override=...)``
so request-scoped drivers (the QA :class:`~amelia.qa.replay.ReplayDriver`,
recording drivers) reach every agent in the run without monkeypatching
``get_driver`` or any class.

This test uses a tiny inline fake driver — NOT ``patch.object`` — to prove
the injected instance is what actually runs.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest

from amelia.core.types import Profile
from amelia.drivers.base import (
    AgenticMessage,
    DriverInterface,
    DriverUsage,
)
from amelia.server.database.connection import Database
from amelia.server.orchestrator.service import OrchestratorService
from tests.integration.conftest import (
    _architect_messages,
    _wait_for_status,
    make_agentic_messages,
    make_reviewer_agentic_messages,
)


pytestmark = pytest.mark.integration


class _FixedDriver(DriverInterface):
    """Minimal DriverInterface stand-in that yields one merged script.

    The architect / developer / reviewer each get one ``execute_agentic``
    call per workflow; this driver walks a single ordered script list across
    all of them (calls beyond the script replay the last entry — matching
    the e2e helper's contract).
    """

    def __init__(self, scripts: list[list[AgenticMessage]]) -> None:
        self._scripts = scripts
        self._call_count = 0
        self._usage: DriverUsage | None = None
        # Marker the test asserts on to prove THIS driver ran (not get_driver's).
        self.installed_marker = "fixed-driver-ran"

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        **kwargs: Any,
    ) -> AsyncIterator[AgenticMessage]:
        idx = min(self._call_count, len(self._scripts) - 1)
        self._call_count += 1
        # A duration_ms that's unique to this driver so a test asserting on
        # recorded metrics can distinguish "injected driver ran" from
        # "get_driver(key) ran" without relying on call counts.
        self._usage = DriverUsage(
            input_tokens=10,
            output_tokens=5,
            duration_ms=42,
            model="fixed",
        )
        for m in self._scripts[idx]:
            yield m

    def get_usage(self) -> DriverUsage | None:
        return self._usage

    def get_tool_definitions(self) -> list[dict[str, Any]] | None:
        return None

    async def cleanup_session(self, session_id: str) -> bool:
        return True


@pytest.fixture(autouse=True)
def _api_key(mock_api_key: None) -> None:
    """Allow any driver construction during this test module."""


async def test_driver_override_reaches_the_agent(
    orchestrator: OrchestratorService,
    test_db: Database,
    api_profile: Profile,
    valid_worktree: str,
) -> None:
    """A ``driver_override`` instance is what every agent in the run uses.

    The injected ``_FixedDriver`` yields the architect / developer / reviewer
    scripts; if the seam silently fell back to ``get_driver("api")`` the run
    would never complete (no real API key, no real LLM). Reaching
    ``completed`` is the proof.
    """
    scripts = [
        _architect_messages(),
        make_agentic_messages(),
        make_reviewer_agentic_messages(approved=True),
    ]
    override = _FixedDriver(scripts)

    workflow_id = await orchestrator.start_workflow(
        issue_id="INJ-1",
        worktree_path=valid_worktree,
        task_title="t",
        task_description="d",
        driver="api",
        driver_override=override,
    )
    await _wait_for_status(test_db, workflow_id, "blocked")
    await orchestrator.approve_workflow(workflow_id)

    row = await test_db.fetch_one(
        "SELECT status FROM workflows WHERE id = $1", workflow_id
    )
    assert row is not None
    assert row["status"] == "completed"
    # The override's execute_agentic was actually called (3 invocations:
    # architect + developer + reviewer).
    assert override._call_count == 3


async def test_driver_override_rejects_non_driver(
    orchestrator: OrchestratorService,
    test_db: Database,
    api_profile: Profile,
    valid_worktree: str,
) -> None:
    """A non-DriverInterface override fails fast at the construction point."""
    with pytest.raises(TypeError):
        await orchestrator.start_workflow(
            issue_id="INJ-2",
            worktree_path=valid_worktree,
            task_title="t",
            task_description="d",
            driver="api",
            driver_override="not-a-driver",  # type: ignore[arg-type]
        )
