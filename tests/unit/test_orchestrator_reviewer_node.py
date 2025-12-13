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

    async def test_sets_current_task_id_when_missing_but_plan_has_tasks(
        self,
        mock_execution_state_factory,
        mock_task_dag_factory,
        mock_review_result_factory,
        mock_reviewer,
        mock_driver_factory_patch,
        mock_get_code_changes,
    ):
        """Orchestrator should set current_task_id when plan has tasks but it's missing.

        The orchestrator owns state management. If current_task_id is missing
        but required (plan has tasks), it should set it before calling the Reviewer.
        """
        from amelia.core.orchestrator import call_reviewer_node

        plan = mock_task_dag_factory(num_tasks=2)
        state = mock_execution_state_factory(
            plan=plan,
            current_task_id=None,  # Missing!
        )

        mock_reviewer.review.return_value = mock_review_result_factory()

        await call_reviewer_node(state)

        # Verify reviewer.review was called
        mock_reviewer.review.assert_called_once()

        # Get the state passed to review
        call_args = mock_reviewer.review.call_args
        passed_state = call_args[0][0]  # First positional argument

        # Orchestrator should have set current_task_id to first task
        assert passed_state.current_task_id == "1"

    async def test_preserves_existing_current_task_id(
        self,
        mock_execution_state_factory,
        mock_task_dag_factory,
        mock_review_result_factory,
        mock_reviewer,
        mock_driver_factory_patch,
        mock_get_code_changes,
    ):
        """Orchestrator should not modify current_task_id if already set."""
        from amelia.core.orchestrator import call_reviewer_node

        plan = mock_task_dag_factory(num_tasks=2)
        state = mock_execution_state_factory(
            plan=plan,
            current_task_id="2",  # Already set to second task
        )

        mock_reviewer.review.return_value = mock_review_result_factory()

        await call_reviewer_node(state)

        # Get the state passed to review
        call_args = mock_reviewer.review.call_args
        passed_state = call_args[0][0]

        # Should preserve the existing current_task_id
        assert passed_state.current_task_id == "2"

    async def test_no_modification_when_no_plan(
        self,
        mock_execution_state_factory,
        mock_review_result_factory,
        mock_reviewer,
        mock_driver_factory_patch,
        mock_get_code_changes,
    ):
        """Orchestrator should not modify state when there's no plan."""
        from amelia.core.orchestrator import call_reviewer_node

        state = mock_execution_state_factory(
            plan=None,
            current_task_id=None,
        )

        mock_reviewer.review.return_value = mock_review_result_factory()

        await call_reviewer_node(state)

        # Get the state passed to review
        call_args = mock_reviewer.review.call_args
        passed_state = call_args[0][0]

        # Should not have set current_task_id
        assert passed_state.current_task_id is None

    async def test_no_modification_when_plan_has_no_tasks(
        self,
        mock_execution_state_factory,
        mock_task_dag_factory,
        mock_review_result_factory,
        mock_reviewer,
        mock_driver_factory_patch,
        mock_get_code_changes,
    ):
        """Orchestrator should not modify state when plan has no tasks."""
        from amelia.core.orchestrator import call_reviewer_node

        plan = mock_task_dag_factory(tasks=[])  # Empty plan
        state = mock_execution_state_factory(
            plan=plan,
            current_task_id=None,
        )

        mock_reviewer.review.return_value = mock_review_result_factory()

        await call_reviewer_node(state)

        # Get the state passed to review
        call_args = mock_reviewer.review.call_args
        passed_state = call_args[0][0]

        # Should not have set current_task_id
        assert passed_state.current_task_id is None

    async def test_logs_warning_when_setting_fallback_current_task_id(
        self,
        mock_execution_state_factory,
        mock_task_dag_factory,
        mock_review_result_factory,
        mock_reviewer,
        mock_driver_factory_patch,
        mock_get_code_changes,
    ):
        """Orchestrator should log a warning when using fallback for current_task_id.

        This situation indicates a potential workflow issue since developer_node
        should have set current_task_id.
        """
        from io import StringIO

        from loguru import logger

        from amelia.core.orchestrator import call_reviewer_node

        plan = mock_task_dag_factory(num_tasks=1)
        state = mock_execution_state_factory(
            plan=plan,
            current_task_id=None,
        )

        mock_reviewer.review.return_value = mock_review_result_factory()

        # Capture loguru output
        log_output = StringIO()
        handler_id = logger.add(log_output, format="{message}", level="WARNING")

        try:
            await call_reviewer_node(state)

            # Should have logged a warning
            log_content = log_output.getvalue()
            assert "current_task_id not set despite plan having tasks" in log_content
        finally:
            logger.remove(handler_id)
