"""Tests for orchestrator plan extraction from predictable path."""

from collections.abc import AsyncIterator, Callable
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile


async def test_call_architect_node_creates_plan_directory_if_missing(
    tmp_path: Path,
    mock_issue_factory: Callable[..., Issue],
    mock_profile_factory: Callable[..., Profile],
    mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
) -> None:
    """The docs/plans directory should be created if it doesn't exist."""
    from amelia.core.orchestrator import call_architect_node

    today = date.today().isoformat()
    plan_dir = tmp_path / "docs" / "plans"

    # Verify directory doesn't exist yet
    assert not plan_dir.exists()

    # Create profile with our tmp_path as working_dir
    profile = mock_profile_factory(working_dir=str(tmp_path))

    # Create state with the issue ID
    issue = mock_issue_factory(id="TEST-1", title="Test", description="Test issue")
    state, _ = mock_execution_state_factory(
        profile=profile,
        issue=issue,
    )

    # Track when architect.plan() is called to verify directory exists at that point
    directory_existed_when_architect_called = False
    plan_file = plan_dir / f"{today}-test-1.md"
    plan_content = """# Test Plan

**Goal:** Implement feature X

## Tasks
- Task 1
"""

    # Mock the Architect to write the plan file and check directory exists
    async def mock_plan(*args: Any, **kwargs: Any) -> AsyncIterator[tuple[Any, Any]]:
        nonlocal directory_existed_when_architect_called
        # Check if directory exists when architect is called
        directory_existed_when_architect_called = plan_dir.exists()
        # Simulate architect writing the plan
        plan_file.write_text(plan_content)
        # Create mock final state
        mock_final_state = MagicMock()
        mock_final_state.raw_architect_output = "Plan written to file."
        mock_final_state.tool_calls = []
        mock_final_state.plan_path = None
        yield mock_final_state, MagicMock()

    # Mock the driver factory and Architect
    with (
        patch("amelia.core.orchestrator.DriverFactory") as mock_factory,
        patch("amelia.core.orchestrator.Architect") as mock_architect_class,
        patch("amelia.core.orchestrator._save_token_usage", new_callable=AsyncMock),
    ):
        mock_driver = MagicMock()
        mock_factory.get_driver.return_value = mock_driver

        mock_architect = MagicMock()
        mock_architect.plan = mock_plan
        mock_architect_class.return_value = mock_architect

        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-123",
                "profile": profile,
            }
        }

        await call_architect_node(state, config)

    # Verify the directory existed when architect was called
    assert directory_existed_when_architect_called, (
        "Plan directory should be created before architect.plan() is called"
    )
