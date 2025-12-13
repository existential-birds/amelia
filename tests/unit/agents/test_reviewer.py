# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for Reviewer agent streaming."""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from amelia.agents.reviewer import Reviewer
from amelia.core.state import ExecutionState
from amelia.core.types import StreamEvent, StreamEventType


class TestReviewerStreamEmitter:
    """Test Reviewer agent stream emitter functionality."""

    def test_reviewer_accepts_stream_emitter(
        self,
        mock_driver: MagicMock,
    ) -> None:
        """Test that Reviewer constructor accepts optional stream_emitter parameter."""
        mock_emitter = AsyncMock()

        # Should not raise
        reviewer = Reviewer(
            driver=mock_driver,
            stream_emitter=mock_emitter,
        )

        assert reviewer._stream_emitter is mock_emitter

    def test_reviewer_works_without_stream_emitter(
        self,
        mock_driver: MagicMock,
    ) -> None:
        """Test that Reviewer works without stream_emitter (backward compatible)."""
        # Should not raise
        reviewer = Reviewer(driver=mock_driver)

        assert reviewer._stream_emitter is None

    async def test_reviewer_emits_agent_output_after_review(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_issue_factory: Callable[..., Any],
        mock_review_response_factory: Callable[..., Any],
    ) -> None:
        """Test that Reviewer emits AGENT_OUTPUT event after completing review."""
        issue = mock_issue_factory(id="TEST-123", title="Test", description="Test")

        state = mock_execution_state_factory(
            issue=issue,
            current_task_id="1",
        )

        # Add a task to the plan for review context
        from amelia.core.state import Task, TaskDAG
        task = Task(
            id="1",
            description="Test task",
            dependencies=[],
            files=[],
            steps=[],
        )
        state.plan = TaskDAG(tasks=[task], original_issue="TEST-123")

        # Mock driver to return approved review
        mock_driver.generate.return_value = mock_review_response_factory(
            approved=True,
            comments=["Looks good!"],
        )

        # Create emitter mock
        mock_emitter = AsyncMock()

        # Create reviewer with emitter
        reviewer = Reviewer(driver=mock_driver, stream_emitter=mock_emitter)

        # Perform review
        code_changes = "diff --git a/test.py b/test.py\n+print('hello')"
        result = await reviewer.review(state, code_changes, workflow_id="TEST-123")

        # Verify review was completed
        assert result.approved is True

        # Verify emitter was called
        assert mock_emitter.called
        assert mock_emitter.call_count == 1

        # Verify the emitted event
        event = mock_emitter.call_args.args[0]
        assert isinstance(event, StreamEvent)
        assert event.type == StreamEventType.AGENT_OUTPUT
        assert event.agent == "reviewer"
        assert event.workflow_id == "TEST-123"  # Uses provided workflow_id
        assert "Approved" in event.content
        assert isinstance(event.timestamp, datetime)

    async def test_reviewer_emits_changes_requested_event(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_review_response_factory: Callable[..., Any],
    ) -> None:
        """Test that Reviewer emits event with 'Changes requested' when not approved."""
        state = mock_execution_state_factory(
            workflow_id="test-workflow-456",
            current_task_id="1",
        )

        from amelia.core.state import Task, TaskDAG
        task = Task(id="1", description="Test task", dependencies=[], files=[], steps=[])
        state.plan = TaskDAG(tasks=[task], original_issue="TEST-123")

        # Mock driver to return rejected review
        mock_driver.generate.return_value = mock_review_response_factory(
            approved=False,
            comments=["Needs fixes"],
        )

        mock_emitter = AsyncMock()
        reviewer = Reviewer(driver=mock_driver, stream_emitter=mock_emitter)

        code_changes = "diff --git a/test.py b/test.py\n+bad code"
        result = await reviewer.review(state, code_changes, workflow_id="test-workflow-456")

        # Verify review was not approved
        assert result.approved is False

        # Verify the emitted event
        event = mock_emitter.call_args.args[0]
        assert event.type == StreamEventType.AGENT_OUTPUT
        assert "Changes requested" in event.content

    async def test_reviewer_does_not_emit_when_no_emitter_configured(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_review_response_factory: Callable[..., Any],
    ) -> None:
        """Test that Reviewer does not crash when no emitter is configured."""
        state = mock_execution_state_factory(
            workflow_id="test-workflow-789",
            current_task_id="1",
        )

        from amelia.core.state import Task, TaskDAG
        task = Task(id="1", description="Test task", dependencies=[], files=[], steps=[])
        state.plan = TaskDAG(tasks=[task], original_issue="TEST-123")

        mock_driver.generate.return_value = mock_review_response_factory(approved=True)

        # Create reviewer WITHOUT emitter
        reviewer = Reviewer(driver=mock_driver)

        # Should not raise even without emitter
        code_changes = "diff --git a/test.py b/test.py\n+print('test')"
        result = await reviewer.review(state, code_changes, workflow_id="test-workflow-789")
        assert result.approved is True

    async def test_reviewer_emits_for_competitive_review(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., ExecutionState],
        mock_profile_factory: Callable[..., Any],
        mock_review_response_factory: Callable[..., Any],
    ) -> None:
        """Test that Reviewer emits event for competitive review strategy."""
        # Create profile with competitive strategy
        profile = mock_profile_factory(strategy="competitive")
        state = mock_execution_state_factory(
            profile=profile,
            workflow_id="test-workflow-competitive",
            current_task_id="1",
        )

        from amelia.core.state import Task, TaskDAG
        task = Task(id="1", description="Test task", dependencies=[], files=[], steps=[])
        state.plan = TaskDAG(tasks=[task], original_issue="TEST-123")

        # Mock driver to return approved reviews for all personas
        mock_driver.generate.return_value = mock_review_response_factory(
            approved=True,
            comments=["Good"],
        )

        mock_emitter = AsyncMock()
        reviewer = Reviewer(driver=mock_driver, stream_emitter=mock_emitter)

        code_changes = "diff --git a/test.py b/test.py\n+good code"
        result = await reviewer.review(state, code_changes, workflow_id="test-workflow-competitive")

        # Competitive review runs multiple personas, but only emits once per _single_review call
        # Since competitive review calls _single_review multiple times in parallel,
        # we should see multiple emissions
        assert mock_emitter.call_count >= 1
        assert result.approved is True
