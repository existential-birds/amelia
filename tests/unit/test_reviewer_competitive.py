# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for competitive review persona attribution."""

from unittest.mock import AsyncMock

from amelia.agents.reviewer import Reviewer, ReviewResponse


class TestCompetitiveReviewPersonaAttribution:
    """Tests for preserving persona context in competitive review comments."""

    async def test_competitive_review_prefixes_comments_with_persona(
        self,
        mock_execution_state_factory,
        mock_task_dag_factory,
        mock_async_driver_factory,
    ):
        """
        Comments from competitive review should be prefixed with persona name
        so users can identify which perspective raised each concern.
        """
        # Set up state with plan, current_task_id, and code changes
        plan = mock_task_dag_factory(num_tasks=1)
        state = mock_execution_state_factory(
            plan=plan,
            current_task_id="1",  # Required when plan has tasks
            code_changes_for_review="diff --git a/file.py"
        )

        # Mock driver to return different comments for each persona
        responses = iter([
            ReviewResponse(approved=True, comments=["Input validation needed"], severity="medium"),
            ReviewResponse(approved=True, comments=["Consider caching"], severity="low"),
            ReviewResponse(approved=True, comments=["Add loading states"], severity="low"),
        ])

        mock_driver = AsyncMock()
        mock_driver.generate = AsyncMock(side_effect=lambda **kwargs: next(responses))

        reviewer = Reviewer(mock_driver)
        # Override profile strategy for competitive review
        state.profile = state.profile.model_copy(update={"strategy": "competitive"})

        result = await reviewer.review(state, code_changes="diff --git a/file.py", workflow_id="test-workflow")

        # Each comment should be prefixed with its persona
        assert any("Security" in c for c in result.comments), \
            "Security persona comments should be attributed"
        assert any("Performance" in c for c in result.comments), \
            "Performance persona comments should be attributed"
        assert any("Usability" in c for c in result.comments), \
            "Usability persona comments should be attributed"

    async def test_competitive_review_handles_empty_comments(
        self,
        mock_execution_state_factory,
        mock_task_dag_factory,
        mock_async_driver_factory,
    ):
        """Personas with no comments should not add empty prefixed entries."""
        plan = mock_task_dag_factory(num_tasks=1)
        state = mock_execution_state_factory(
            plan=plan,
            current_task_id="1",  # Required when plan has tasks
            code_changes_for_review="diff --git a/file.py"
        )

        # One persona has no comments
        responses = iter([
            ReviewResponse(approved=True, comments=[], severity="low"),
            ReviewResponse(approved=True, comments=["Consider optimization"], severity="low"),
            ReviewResponse(approved=True, comments=[], severity="low"),
        ])

        mock_driver = AsyncMock()
        mock_driver.generate = AsyncMock(side_effect=lambda **kwargs: next(responses))

        reviewer = Reviewer(mock_driver)
        # Override profile strategy for competitive review
        state.profile = state.profile.model_copy(update={"strategy": "competitive"})

        result = await reviewer.review(state, code_changes="diff --git a/file.py", workflow_id="test-workflow")

        # Should only have comments from Performance (the one that had comments)
        assert len(result.comments) == 1
        assert "Performance" in result.comments[0]
