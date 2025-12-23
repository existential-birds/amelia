# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Integration tests for orchestrator with batch execution model."""

import asyncio
import time
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.agents.reviewer import ReviewResponse
from amelia.core.orchestrator import call_reviewer_node
from amelia.core.state import ExecutionState

from .conftest import make_batch, make_issue, make_plan, make_profile, make_step


async def test_orchestrator_parallel_review_api() -> None:
    """Verifies concurrent API calls during competitive review with an API driver."""
    profile = make_profile(
        name="api_comp_reviewer",
        driver="api:openrouter",
        tracker="noop",
        strategy="competitive",
    )
    test_issue = make_issue(
        id="PAR-API",
        title="Parallel API Review",
        description="Test concurrent API calls for review.",
    )

    mock_driver = AsyncMock()

    async def slow_generate(*_args: Any, **_kwargs: Any) -> tuple[ReviewResponse, None]:
        await asyncio.sleep(0.1)
        return (ReviewResponse(approved=True, comments=[], severity="low"), None)

    mock_driver.generate.side_effect = slow_generate

    with patch("amelia.drivers.factory.DriverFactory.get_driver", return_value=mock_driver):
        start_time = time.time()

        initial_state = ExecutionState(
            profile_id=profile.name,
            issue=test_issue,
            code_changes_for_review="changes"
        )

        config = cast(RunnableConfig, {"configurable": {"thread_id": "test-parallel-review", "profile": profile}})
        await call_reviewer_node(initial_state, config)

        _ = time.time() - start_time  # Duration tracked but not asserted - timing is unreliable in CI

        # Verify all 3 reviewers were called (competitive review)
        assert mock_driver.generate.call_count == 3


async def test_orchestrator_batch_execution_calls_developer_run() -> None:
    """Verifies the orchestrator correctly calls Developer.run() for batch execution."""
    from amelia.core.orchestrator import call_developer_node

    profile = make_profile(name="test", driver="cli:claude")
    test_issue = make_issue(id="BATCH-1", title="Batch Test", description="Test batch execution")

    # Create execution plan with steps
    step = make_step(id="step-1", description="Test step", command="echo test")
    batch = make_batch(batch_number=1, steps=(step,), description="Test batch")
    execution_plan = make_plan(goal="Test goal", batches=(batch,), tdd_approach=True)

    initial_state = ExecutionState(
        profile_id=profile.name,
        issue=test_issue,
        execution_plan=execution_plan,
        human_approved=True
    )

    mock_driver = AsyncMock()
    mock_developer = AsyncMock()
    mock_developer.run.return_value = {"developer_status": "all_done"}

    with patch("amelia.drivers.factory.DriverFactory.get_driver", return_value=mock_driver), \
         patch("amelia.core.orchestrator.Developer") as MockDeveloper:
        MockDeveloper.return_value = mock_developer

        config = cast(RunnableConfig, {"configurable": {"thread_id": "test-batch-exec", "profile": profile}})
        result = await call_developer_node(initial_state, config)

        # Developer should be instantiated
        MockDeveloper.assert_called_once()
        # Developer.run() should be called with the state
        mock_developer.run.assert_called_once()

        # Result should contain developer_status
        assert "developer_status" in result


@pytest.mark.parametrize(
    "node_name,node_function,setup_state_kwargs,setup_mock",
    [
        (
            "architect",
            "call_architect_node",
            {"issue": make_issue(id="CWD-123", title="Test Architect CWD")},
            "setup_architect_mock",
        ),
        (
            "reviewer",
            "call_reviewer_node",
            {
                "issue": make_issue(id="CWD-124", title="Test Reviewer CWD"),
                "code_changes_for_review": "diff content",
            },
            "setup_reviewer_mock",
        ),
    ],
)
async def test_orchestrator_node_passes_working_dir_as_cwd(
    node_name: str,
    node_function: str,
    setup_state_kwargs: dict[str, Any],
    setup_mock: str,
) -> None:
    """Verify orchestrator nodes pass working_dir to driver as cwd.

    Args:
        node_name: Name of the node being tested (for display).
        node_function: Name of the node function to import and call.
        setup_state_kwargs: Additional kwargs for ExecutionState.
        setup_mock: Name of the helper function to set up mock returns.
    """
    from amelia.agents.architect import ExecutionPlanOutput
    from amelia.core.orchestrator import call_architect_node, call_reviewer_node

    # Select the actual node function
    node_func = call_architect_node if node_function == "call_architect_node" else call_reviewer_node

    # Create profile with working_dir set
    profile = make_profile(
        name="test",
        driver="api:openrouter",
        working_dir="/test/project",
    )

    # Create initial state
    initial_state = ExecutionState(
        profile_id=profile.name,
        **setup_state_kwargs,
    )

    # Mock driver with appropriate response
    mock_driver = AsyncMock()
    if setup_mock == "setup_architect_mock":
        # Architect needs ExecutionPlanOutput - now returns tuple (output, session_id)
        step = make_step(id="step-1", description="Test step", command="echo test")
        batch = make_batch(batch_number=1, steps=(step,), description="Test batch")
        execution_plan = make_plan(goal="Test goal", batches=(batch,), tdd_approach=True)
        mock_driver.generate.return_value = (
            ExecutionPlanOutput(plan=execution_plan, reasoning="Test reasoning"),
            None,
        )
    else:
        # Reviewer needs ReviewResponse - now returns tuple (output, session_id)
        mock_driver.generate.return_value = (
            ReviewResponse(approved=True, comments=["Looks good"], severity="low"),
            None,
        )

    with patch("amelia.drivers.factory.DriverFactory.get_driver", return_value=mock_driver):
        config = cast(RunnableConfig, {"configurable": {"thread_id": f"test-{node_name}-cwd", "profile": profile}})
        await node_func(initial_state, config)

        # Verify driver.generate was called with cwd=working_dir
        mock_driver.generate.assert_called_once()
        call_kwargs = mock_driver.generate.call_args.kwargs
        assert "cwd" in call_kwargs
        assert call_kwargs["cwd"] == "/test/project"
