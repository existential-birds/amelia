# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for batch_approval_node in orchestrator."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from amelia.core.orchestrator import batch_approval_node
from amelia.core.state import BatchApproval, ExecutionState


class TestBatchApprovalNode:
    """Tests for batch_approval_node function."""

    @pytest.mark.asyncio
    async def test_approved_path_records_approval_correctly(
        self,
        mock_execution_state_factory: Callable[..., ExecutionState],
    ) -> None:
        """Test that approval is recorded correctly when approved."""
        # Arrange
        state = mock_execution_state_factory(
            human_approved=True,
            current_batch_index=0,
        )

        # Act
        result = await batch_approval_node(state)

        # Assert
        assert "batch_approvals" in result
        approvals = result["batch_approvals"]
        assert len(approvals) == 1

        approval = approvals[0]
        assert isinstance(approval, BatchApproval)
        assert approval.batch_number == 0
        assert approval.approved is True
        assert approval.feedback is None
        assert isinstance(approval.approved_at, datetime)

        # Verify human_approved is reset
        assert result["human_approved"] is None

    @pytest.mark.asyncio
    async def test_rejected_path_records_disapproval(
        self,
        mock_execution_state_factory: Callable[..., ExecutionState],
    ) -> None:
        """Test that disapproval is recorded correctly when rejected."""
        # Arrange
        state = mock_execution_state_factory(
            human_approved=False,
            current_batch_index=1,
        )

        # Act
        result = await batch_approval_node(state)

        # Assert
        assert "batch_approvals" in result
        approvals = result["batch_approvals"]
        assert len(approvals) == 1

        approval = approvals[0]
        assert approval.batch_number == 1
        assert approval.approved is False
        assert approval.feedback is None

        # Verify human_approved is reset
        assert result["human_approved"] is None

    @pytest.mark.asyncio
    async def test_feedback_is_captured_when_provided(
        self,
        mock_execution_state_factory: Callable[..., ExecutionState],
    ) -> None:
        """Test that feedback is captured when provided."""
        # Arrange
        feedback_text = "Please add more error handling"
        state = mock_execution_state_factory(
            human_approved=False,
            current_batch_index=2,
            human_feedback=feedback_text,
        )

        # Act
        result = await batch_approval_node(state)

        # Assert
        approvals = result["batch_approvals"]
        approval = approvals[0]
        assert approval.feedback == feedback_text
        assert approval.batch_number == 2
        assert approval.approved is False

    @pytest.mark.asyncio
    async def test_appends_to_existing_batch_approvals(
        self,
        mock_execution_state_factory: Callable[..., ExecutionState],
    ) -> None:
        """Test that new approval is appended to existing batch_approvals list."""
        # Arrange
        existing_approval = BatchApproval(
            batch_number=0,
            approved=True,
            feedback=None,
            approved_at=datetime.now(UTC),
        )
        state = mock_execution_state_factory(
            human_approved=False,
            current_batch_index=1,
            batch_approvals=[existing_approval],
        )

        # Act
        result = await batch_approval_node(state)

        # Assert
        approvals = result["batch_approvals"]
        assert len(approvals) == 2
        assert approvals[0] == existing_approval  # Original approval preserved
        assert approvals[1].batch_number == 1
        assert approvals[1].approved is False

