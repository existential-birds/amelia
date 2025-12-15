# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for orchestrator's call_reviewer_node state management."""

from unittest.mock import AsyncMock, patch

import pytest


class TestCallReviewerNodeStateManagement:
    """Tests for orchestrator properly preparing state before calling Reviewer."""

    @pytest.fixture
    def mock_reviewer(self):
        """Create a mock Reviewer that captures the state it receives."""
        with patch("amelia.core.orchestrator.Reviewer") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def mock_driver_factory_patch(self):
        """Patch DriverFactory.get_driver."""
        with patch("amelia.core.orchestrator.DriverFactory") as mock:
            mock.get_driver.return_value = AsyncMock()
            yield mock

    @pytest.fixture
    def mock_get_code_changes(self):
        """Patch get_code_changes_for_review."""
        with patch("amelia.core.orchestrator.get_code_changes_for_review") as mock:
            mock.return_value = "diff --git a/file.py"
            yield mock

    @pytest.mark.parametrize("plan_kwargs,state_task_id,expected_task_id", [
        ({"num_tasks": 2}, None, "1"),           # test_sets_current_task_id_when_missing_but_plan_has_tasks
        ({"num_tasks": 2}, "2", "2"),            # test_preserves_existing_current_task_id
        (None, None, None),                       # test_no_modification_when_no_plan
        ({"tasks": []}, None, None),             # test_no_modification_when_plan_has_no_tasks
    ], ids=["missing_with_tasks", "already_set", "no_plan", "empty_plan"])
    async def test_reviewer_node_task_id_handling(
        self,
        plan_kwargs,
        state_task_id,
        expected_task_id,
        mock_execution_state_factory,
        mock_task_dag_factory,
        mock_review_result_factory,
        mock_reviewer,
        mock_driver_factory_patch,
        mock_get_code_changes,
    ):
        """Orchestrator should handle current_task_id correctly in various scenarios.

        The orchestrator owns state management and should:
        - Set current_task_id to first task when missing but plan has tasks
        - Preserve existing current_task_id if already set
        - Not modify state when there's no plan
        - Not modify state when plan has no tasks
        """
        from amelia.core.orchestrator import call_reviewer_node

        # Setup plan
        plan = mock_task_dag_factory(**plan_kwargs) if plan_kwargs is not None else None

        # Setup state with optional task_id
        state = mock_execution_state_factory(plan=plan, current_task_id=state_task_id)

        mock_reviewer.review.return_value = mock_review_result_factory()

        # Run node
        config = {"configurable": {"thread_id": "test-workflow"}}
        await call_reviewer_node(state, config=config)

        # Verify reviewer.review was called
        mock_reviewer.review.assert_called_once()

        # Get the state passed to review
        call_args = mock_reviewer.review.call_args
        passed_state = call_args[0][0]  # First positional argument

        # Assert
        assert passed_state.current_task_id == expected_task_id
