# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""E2E integration tests for review-fix graph execution."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

from amelia.core.orchestrator import create_review_graph
from amelia.core.state import ExecutionState, ReviewResult


if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


@pytest.fixture
def review_graph() -> CompiledStateGraph[Any]:
    """Create review graph with memory checkpointer."""
    checkpointer = MemorySaver()
    return create_review_graph(checkpointer)


@pytest.fixture
def make_review_state(
    mock_profile_factory: Callable[..., Any],
    mock_issue_factory: Callable[..., Any],
    mock_execution_plan_factory: Callable[..., Any],
) -> Callable[..., ExecutionState]:
    """Factory for creating ExecutionState for review tests."""
    def _make(
        diff_content: str = "+ added line",
        review_iteration: int = 0,
        last_review: ReviewResult | None = None,
    ) -> ExecutionState:
        # Create a minimal execution plan with one batch for context
        plan = mock_execution_plan_factory(num_batches=1, steps_per_batch=1)
        return ExecutionState(
            profile=mock_profile_factory(),
            issue=mock_issue_factory(),
            execution_plan=plan,
            current_batch_index=0,
            code_changes_for_review=diff_content,
            review_iteration=review_iteration,
            last_review=last_review,
        )
    return _make


class TestReviewGraphExecution:
    """Tests for review-fix graph execution."""

    async def test_review_approves_first_pass(
        self,
        review_graph: CompiledStateGraph[Any],
        make_review_state: Callable[..., ExecutionState],
    ) -> None:
        """Review workflow completes immediately when reviewer approves."""
        state = make_review_state(diff_content="+ good code")
        mock_driver = AsyncMock()
        mock_driver.generate = AsyncMock(return_value=ReviewResult(
            approved=True,
            comments=[],
            severity="low",
            reviewer_persona="Test Reviewer",
        ))

        config: RunnableConfig = {"configurable": {"thread_id": "test-1"}}

        with patch("amelia.core.orchestrator.DriverFactory.get_driver", return_value=mock_driver):
            chunks = []
            async for chunk in review_graph.astream(
                state.model_dump(mode="json"),
                config=config,
                stream_mode="updates",
            ):
                chunks.append(chunk)

        # Should have reviewer output only (no developer needed)
        assert len(chunks) == 1
        # Reviewer should have been called
        assert mock_driver.generate.call_count == 1

    async def test_review_fix_loop_single_iteration(
        self,
        review_graph: CompiledStateGraph[Any],
        make_review_state: Callable[..., ExecutionState],
    ) -> None:
        """Review rejects once, developer fixes, review approves."""
        state = make_review_state(diff_content="+ buggy code")

        # Mock driver that rejects once then approves
        mock_driver = AsyncMock()
        mock_driver.generate = AsyncMock(side_effect=[
            # First review - reject
            ReviewResult(
                approved=False,
                comments=["Fix bug"],
                severity="medium",
                reviewer_persona="Test Reviewer",
            ),
            # Second review - approve
            ReviewResult(
                approved=True,
                comments=[],
                severity="low",
                reviewer_persona="Test Reviewer",
            ),
        ])
        mock_driver.execute_tool = AsyncMock(return_value="Fixed the bug")

        config: RunnableConfig = {"configurable": {"thread_id": "test-2"}}

        with patch("amelia.core.orchestrator.DriverFactory.get_driver", return_value=mock_driver):
            chunks = []
            async for chunk in review_graph.astream(
                state.model_dump(mode="json"),
                config=config,
                stream_mode="updates",
            ):
                chunks.append(chunk)

        # reviewer(reject) -> developer -> reviewer(approve)
        # Driver.generate called for 2 reviews
        assert mock_driver.generate.call_count == 2
        # Developer attempts to execute (even if it fails due to synthetic plan issues)
        # The important thing is the loop executed correctly

    async def test_review_fix_loop_max_iterations_terminates(
        self,
        review_graph: CompiledStateGraph[Any],
        make_review_state: Callable[..., ExecutionState],
    ) -> None:
        """Review loop terminates at max 3 iterations even if not approved."""
        state = make_review_state(diff_content="+ unfixable code")

        # Mock driver that always rejects
        mock_driver = AsyncMock()
        mock_driver.generate = AsyncMock(return_value=ReviewResult(
            approved=False,
            comments=["Still wrong"],
            severity="high",
            reviewer_persona="Test Reviewer",
        ))
        mock_driver.execute_tool = AsyncMock(return_value="Attempted fix")

        config: RunnableConfig = {
            "configurable": {"thread_id": "test-3"},
            "recursion_limit": 50,  # Increase limit to allow proper termination
        }

        with patch("amelia.core.orchestrator.DriverFactory.get_driver", return_value=mock_driver):
            chunks = []
            async for chunk in review_graph.astream(
                state.model_dump(mode="json"),
                config=config,
                stream_mode="updates",
            ):
                chunks.append(chunk)

        # Should terminate at 3 iterations (initial + 3 fixes = 4 reviews max)
        # But the condition is review_iteration >= 3, so after 3 developer calls
        # Verify it actually terminates at 4 reviews
        assert mock_driver.generate.call_count == 4
