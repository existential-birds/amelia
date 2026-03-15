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


@pytest.fixture(autouse=True)
def _mock_skill_detection():
    """Mock skill detection/loading for all review node tests."""
    with (
        patch(
            "amelia.pipelines.nodes._run_git_command",
            new_callable=AsyncMock,
            return_value="",
        ),
        patch("amelia.pipelines.nodes.detect_stack", return_value=set()),
        patch("amelia.pipelines.nodes.load_skills", return_value=""),
    ):
        yield


class TestCallReviewNodeBaseCommitFallback:
    """Tests for base_commit fallback computation in call_reviewer_node."""

    @pytest.mark.asyncio
    async def test_computes_base_commit_when_missing(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ):
        """When base_commit is None, review node should compute it using get_current_commit."""
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

        captured_base_commit: list[str] = []

        async def mock_agentic_review(state, base_commit: str, profile, *, workflow_id: str):
            captured_base_commit.append(base_commit)
            return mock_review_result, "session-123"

        config = mock_runnable_config(profile=profile)

        with (
            patch(
                "amelia.pipelines.nodes.get_current_commit",
                new_callable=AsyncMock,
                return_value="abc123def456",
            ) as mock_get_commit,
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_class,
            patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock),
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = mock_agentic_review
            mock_reviewer_class.return_value = mock_reviewer

            result = await call_reviewer_node(state, config)

            mock_get_commit.assert_called_once()
            assert len(captured_base_commit) == 1
            assert captured_base_commit[0] == "abc123def456"

            # reviewer_persona is overwritten with review_type ("general")
            assert len(result["last_reviews"]) == 1
            assert result["last_reviews"][0].reviewer_persona == "general"

    @pytest.mark.asyncio
    async def test_uses_existing_base_commit_when_present(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ):
        """When base_commit is already set, review node should use it directly."""
        existing_base_commit = "existing123commit"
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit=existing_base_commit,
        )

        mock_review_result = ReviewResult(
            reviewer_persona="Agentic",
            approved=True,
            comments=[],
            severity="none",
        )

        captured_base_commit: list[str] = []

        async def mock_agentic_review(state, base_commit: str, profile, *, workflow_id: str):
            captured_base_commit.append(base_commit)
            return mock_review_result, "session-123"

        config = mock_runnable_config(profile=profile)

        with (
            patch("amelia.pipelines.nodes.get_current_commit", new_callable=AsyncMock) as mock_get_commit,
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_class,
            patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock),
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = mock_agentic_review
            mock_reviewer_class.return_value = mock_reviewer

            result = await call_reviewer_node(state, config)

            mock_get_commit.assert_not_called()
            assert len(captured_base_commit) == 1
            assert captured_base_commit[0] == existing_base_commit
            assert len(result["last_reviews"]) == 1
            assert result["last_reviews"][0].reviewer_persona == "general"

    @pytest.mark.asyncio
    async def test_falls_back_to_head_when_get_current_commit_fails(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ):
        """When get_current_commit returns None, review node should fall back to HEAD."""
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

        captured_base_commit: list[str] = []

        async def mock_agentic_review(state, base_commit: str, profile, *, workflow_id: str):
            captured_base_commit.append(base_commit)
            return mock_review_result, "session-123"

        config = mock_runnable_config(profile=profile)

        with (
            patch(
                "amelia.pipelines.nodes.get_current_commit",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_get_commit,
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_class,
            patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock),
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = mock_agentic_review
            mock_reviewer_class.return_value = mock_reviewer

            await call_reviewer_node(state, config)

            mock_get_commit.assert_called_once()
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

        with (
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_class,
            patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock),
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = AsyncMock(
                return_value=(mock_review_result, "session-123")
            )
            mock_reviewer.review = AsyncMock()
            mock_reviewer_class.return_value = mock_reviewer

            await call_reviewer_node(state, config)

            mock_reviewer.agentic_review.assert_called_once()
            mock_reviewer.review.assert_not_called()


class TestCallReviewNodeMultipleReviewTypes:
    """Tests for running separate reviewer passes per review type."""

    @pytest.mark.asyncio
    async def test_loops_per_review_type(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ) -> None:
        """Reviewer should run once per review type, each tagged with reviewer_persona."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit="abc123",
        )

        general_result = ReviewResult(
            reviewer_persona="original",
            approved=True,
            comments=[],
            severity="none",
        )
        security_result = ReviewResult(
            reviewer_persona="original",
            approved=False,
            comments=["SQL injection risk"],
            severity="major",
        )

        # Wrap profile to inject review_types
        original_get_config = profile.get_agent_config
        mock_profile = MagicMock(wraps=profile)
        mock_profile.repo_root = profile.repo_root

        def patched_get_config(name: str):
            cfg = original_get_config(name)
            if name in ("reviewer", "task_reviewer"):
                return cfg.model_copy(
                    update={"options": {**cfg.options, "review_types": ["general", "security"]}}
                )
            return cfg

        mock_profile.get_agent_config = patched_get_config
        config = mock_runnable_config(profile=mock_profile)

        review_call_count = 0

        async def mock_agentic_review(state, base_commit, profile, *, workflow_id):
            nonlocal review_call_count
            review_call_count += 1
            if review_call_count == 1:
                return general_result, "session-1"
            return security_result, "session-2"

        async def mock_git_cmd(cmd, repo_root, sandbox_provider=None):
            if "--name-only" in cmd:
                return "app.py\n"
            return "import os"

        with (
            patch(
                "amelia.pipelines.nodes._run_git_command",
                side_effect=mock_git_cmd,
            ),
            patch("amelia.pipelines.nodes.detect_stack", return_value={"python"}),
            patch("amelia.pipelines.nodes.load_skills", return_value="# Guidelines") as mock_load,
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_cls,
            patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock),
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = mock_agentic_review
            mock_reviewer_cls.return_value = mock_reviewer

            result = await call_reviewer_node(state, config)

            # Reviewer constructed twice (once per review type)
            assert mock_reviewer_cls.call_count == 2
            # load_skills called once per review type
            assert mock_load.call_count == 2
            mock_load.assert_any_call({"python"}, ["general"])
            mock_load.assert_any_call({"python"}, ["security"])

            # Result contains both reviews, tagged with review type
            reviews = result["last_reviews"]
            assert len(reviews) == 2
            assert reviews[0].reviewer_persona == "general"
            assert reviews[0].approved is True
            assert reviews[1].reviewer_persona == "security"
            assert reviews[1].approved is False
            assert reviews[1].comments == ["SQL injection risk"]

    @pytest.mark.asyncio
    async def test_invalid_review_types_falls_back(
        self,
        mock_execution_state_factory,
        mock_runnable_config,
    ) -> None:
        """Invalid review_types in agent options should fall back to ['general']."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit="abc123",
        )

        mock_review_result = ReviewResult(
            reviewer_persona="original",
            approved=True,
            comments=[],
            severity="none",
        )

        # Inject invalid review_types (empty list)
        original_get_config = profile.get_agent_config
        mock_profile = MagicMock(wraps=profile)
        mock_profile.repo_root = profile.repo_root

        def patched_get_config(name: str):
            cfg = original_get_config(name)
            if name in ("reviewer", "task_reviewer"):
                return cfg.model_copy(
                    update={"options": {**cfg.options, "review_types": []}}
                )
            return cfg

        mock_profile.get_agent_config = patched_get_config
        config = mock_runnable_config(profile=mock_profile)

        with (
            patch(
                "amelia.pipelines.nodes._run_git_command",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch("amelia.pipelines.nodes.detect_stack", return_value=set()),
            patch("amelia.pipelines.nodes.load_skills", return_value="") as mock_load,
            patch("amelia.pipelines.nodes.Reviewer") as mock_reviewer_cls,
            patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock),
        ):
            mock_reviewer = MagicMock()
            mock_reviewer.driver = MagicMock()
            mock_reviewer.agentic_review = AsyncMock(
                return_value=(mock_review_result, "session-123")
            )
            mock_reviewer_cls.return_value = mock_reviewer

            result = await call_reviewer_node(state, config)

            # Should fall back to ["general"]
            mock_load.assert_called_once_with(set(), ["general"])
            assert len(result["last_reviews"]) == 1
            assert result["last_reviews"][0].reviewer_persona == "general"
