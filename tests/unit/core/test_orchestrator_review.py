"""Tests for call_reviewer_node orchestrator function.

Tests the review node behavior including base_commit fallback computation.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import ReviewResult
from amelia.pipelines.nodes import call_reviewer_node


@pytest.fixture
def mock_runnable_config(mock_profile_factory):
    """Create a mock RunnableConfig for review node tests."""
    def _create(
        profile=None,
        workflow_id: str = "test-workflow-123",
        event_bus=None,
        repository=None,
    ) -> dict[str, Any]:
        if profile is None:
            profile = mock_profile_factory(preset="cli_single")
        return {
            "configurable": {
                "thread_id": workflow_id,
                "profile": profile,
                "event_bus": event_bus,
                "repository": repository,
            }
        }
    return _create


class TestCallReviewNodeBaseCommitFallback:
    """Tests for base_commit fallback computation in call_reviewer_node."""

    @pytest.mark.asyncio
    async def test_computes_base_commit_when_missing(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ):
        """When base_commit is None, review node should compute it using get_current_commit."""
        # Create state with base_commit=None
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit=None,  # Explicitly None
        )

        # Create mock review result
        mock_review_result = ReviewResult(
            reviewer_persona="Agentic",
            approved=True,
            comments=[],
            severity="none",
        )

        # Track what base_commit was passed to agentic_review
        captured_base_commit: list[str] = []

        async def mock_agentic_review(
            state,
            base_commit: str,
            profile,
            *,
            workflow_id: str,
        ):
            captured_base_commit.append(base_commit)
            return mock_review_result, "session-123"

        config = mock_runnable_config(profile=profile)

        # Mock the Reviewer (driver is now created internally by the agent)
        with patch(
            "amelia.pipelines.nodes.get_current_commit",
            new_callable=AsyncMock,
            return_value="abc123def456",
        ) as mock_get_commit, patch(
            "amelia.pipelines.nodes.Reviewer"
        ) as mock_reviewer_class, patch(
            "amelia.pipelines.nodes._save_token_usage",
            new_callable=AsyncMock,
        ):
            # Setup reviewer mock (agent creates its own driver internally)
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = mock_agentic_review
            mock_reviewer_class.return_value = mock_reviewer

            # Call the review node
            result = await call_reviewer_node(state, config)

            # Verify get_current_commit was called
            mock_get_commit.assert_called_once()

            # Verify agentic_review was called with computed base_commit
            assert len(captured_base_commit) == 1
            assert captured_base_commit[0] == "abc123def456"

            # Verify result contains review
            assert result["last_review"] == mock_review_result

    @pytest.mark.asyncio
    async def test_uses_existing_base_commit_when_present(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ):
        """When base_commit is already set, review node should use it directly."""
        # Create state with base_commit already set
        existing_base_commit = "existing123commit"
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit=existing_base_commit,
        )

        # Create mock review result
        mock_review_result = ReviewResult(
            reviewer_persona="Agentic",
            approved=True,
            comments=[],
            severity="none",
        )

        # Track what base_commit was passed to agentic_review
        captured_base_commit: list[str] = []

        async def mock_agentic_review(
            state,
            base_commit: str,
            profile,
            *,
            workflow_id: str,
        ):
            captured_base_commit.append(base_commit)
            return mock_review_result, "session-123"

        config = mock_runnable_config(profile=profile)

        # Mock the Reviewer (driver is now created internally by the agent)
        with patch(
            "amelia.pipelines.nodes.get_current_commit",
            new_callable=AsyncMock,
        ) as mock_get_commit, patch(
            "amelia.pipelines.nodes.Reviewer"
        ) as mock_reviewer_class, patch(
            "amelia.pipelines.nodes._save_token_usage",
            new_callable=AsyncMock,
        ):
            # Setup reviewer mock (agent creates its own driver internally)
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = mock_agentic_review
            mock_reviewer_class.return_value = mock_reviewer

            # Call the review node
            result = await call_reviewer_node(state, config)

            # Verify get_current_commit was NOT called (base_commit already exists)
            mock_get_commit.assert_not_called()

            # Verify agentic_review was called with existing base_commit
            assert len(captured_base_commit) == 1
            assert captured_base_commit[0] == existing_base_commit

            # Verify result contains review
            assert result["last_review"] == mock_review_result

    @pytest.mark.asyncio
    async def test_falls_back_to_head_when_get_current_commit_fails(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ):
        """When get_current_commit returns None, review node should fall back to HEAD."""
        # Create state with base_commit=None
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit=None,
        )

        mock_review_result = ReviewResult(
            reviewer_persona="Agentic",
            approved=True,
            comments=[],
            severity="none",
        )

        # Track what base_commit was passed to agentic_review
        captured_base_commit: list[str] = []

        async def mock_agentic_review(
            state,
            base_commit: str,
            profile,
            *,
            workflow_id: str,
        ):
            captured_base_commit.append(base_commit)
            return mock_review_result, "session-123"

        config = mock_runnable_config(profile=profile)

        # Mock the Reviewer (driver is now created internally by the agent)
        with patch(
            "amelia.pipelines.nodes.get_current_commit",
            new_callable=AsyncMock,
            return_value=None,  # Simulate failure to get commit
        ) as mock_get_commit, patch(
            "amelia.pipelines.nodes.Reviewer"
        ) as mock_reviewer_class, patch(
            "amelia.pipelines.nodes._save_token_usage",
            new_callable=AsyncMock,
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = mock_agentic_review
            mock_reviewer_class.return_value = mock_reviewer

            await call_reviewer_node(state, config)

            # Verify get_current_commit was called
            mock_get_commit.assert_called_once()

            # Verify agentic_review was called with fallback "HEAD"
            assert len(captured_base_commit) == 1
            assert captured_base_commit[0] == "HEAD"

    @pytest.mark.asyncio
    async def test_always_uses_agentic_review(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ):
        """Review node should always use agentic_review, never the old review() method."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit="abc123",
        )

        mock_review_result = ReviewResult(
            reviewer_persona="Agentic",
            approved=True,
            comments=[],
            severity="none",
        )

        config = mock_runnable_config(profile=profile)

        # Mock the Reviewer (driver is now created internally by the agent)
        with patch(
            "amelia.pipelines.nodes.Reviewer"
        ) as mock_reviewer_class, patch(
            "amelia.pipelines.nodes._save_token_usage",
            new_callable=AsyncMock,
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = AsyncMock(
                return_value=(mock_review_result, "session-123")
            )
            mock_reviewer.review = AsyncMock()  # Old method - should NOT be called
            mock_reviewer_class.return_value = mock_reviewer

            await call_reviewer_node(state, config)

            # Verify agentic_review was called
            mock_reviewer.agentic_review.assert_called_once()

            # Verify old review() method was NOT called
            mock_reviewer.review.assert_not_called()
