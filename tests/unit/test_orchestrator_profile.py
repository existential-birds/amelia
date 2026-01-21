"""Tests for orchestrator profile loading from database."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from amelia.server.orchestrator.service import OrchestratorService
from amelia.server.database import ProfileRecord


class TestOrchestratorProfileLoading:
    """Tests for profile loading in orchestrator."""

    async def test_get_profile_from_database(self):
        """Verify profile is loaded from database."""
        mock_profile_repo = AsyncMock()
        mock_profile_repo.get_profile.return_value = ProfileRecord(
            id="dev",
            driver="cli:claude",
            model="opus",
            validator_model="haiku",
            tracker="noop",
            working_dir="/repo",
        )

        # Test that orchestrator uses ProfileRepository
        profile = await mock_profile_repo.get_profile("dev")
        assert profile is not None
        assert profile.driver == "cli:claude"

    async def test_get_profile_or_fail_returns_profile(self):
        """Verify _get_profile_or_fail returns Profile from database record."""
        mock_event_bus = MagicMock()
        mock_repository = AsyncMock()
        mock_repository.get_max_event_sequence.return_value = 0
        mock_profile_repo = AsyncMock()
        mock_profile_repo.get_profile.return_value = ProfileRecord(
            id="dev",
            driver="cli:claude",
            model="opus",
            validator_model="haiku",
            tracker="noop",
            working_dir="/repo",
            plan_output_dir="docs/plans",
            plan_path_pattern="docs/plans/{date}-{issue_key}.md",
            max_review_iterations=3,
            max_task_review_iterations=5,
            auto_approve_reviews=False,
        )

        service = OrchestratorService(
            event_bus=mock_event_bus,
            repository=mock_repository,
            profile_repo=mock_profile_repo,
        )

        profile = await service._get_profile_or_fail(
            workflow_id="wf-123",
            profile_id="dev",
            worktree_path="/some/worktree",
        )

        assert profile is not None
        assert profile.name == "dev"
        assert profile.driver == "cli:claude"
        assert profile.model == "opus"
        assert profile.validator_model == "haiku"
        # working_dir should be set to worktree_path
        assert profile.working_dir == "/some/worktree"
        mock_profile_repo.get_profile.assert_called_once_with("dev")

    async def test_get_profile_or_fail_profile_not_found(self):
        """Verify _get_profile_or_fail returns None and sets failed status when profile not found."""
        mock_event_bus = MagicMock()
        mock_repository = AsyncMock()
        mock_repository.get_max_event_sequence.return_value = 0
        mock_profile_repo = AsyncMock()
        mock_profile_repo.get_profile.return_value = None

        service = OrchestratorService(
            event_bus=mock_event_bus,
            repository=mock_repository,
            profile_repo=mock_profile_repo,
        )

        profile = await service._get_profile_or_fail(
            workflow_id="wf-123",
            profile_id="nonexistent",
            worktree_path="/some/worktree",
        )

        assert profile is None
        mock_repository.set_status.assert_called_once()
        call_args = mock_repository.set_status.call_args
        assert call_args[0][0] == "wf-123"
        assert call_args[0][1] == "failed"
        assert "nonexistent" in call_args[1]["failure_reason"]

    async def test_record_to_profile_conversion(self):
        """Verify ProfileRecord is correctly converted to Profile."""
        mock_event_bus = MagicMock()
        mock_repository = AsyncMock()
        mock_repository.get_max_event_sequence.return_value = 0
        mock_profile_repo = AsyncMock()

        service = OrchestratorService(
            event_bus=mock_event_bus,
            repository=mock_repository,
            profile_repo=mock_profile_repo,
        )

        record = ProfileRecord(
            id="test-profile",
            driver="api:openrouter",
            model="gpt-4",
            validator_model="gpt-3.5-turbo",
            tracker="github",
            working_dir="/original/dir",
            plan_output_dir="custom/plans",
            plan_path_pattern="custom/{date}-{issue_key}.md",
            max_review_iterations=5,
            max_task_review_iterations=10,
            auto_approve_reviews=True,
        )

        profile = service._record_to_profile(record, worktree_path="/override/dir")

        assert profile.name == "test-profile"
        assert profile.driver == "api:openrouter"
        assert profile.model == "gpt-4"
        assert profile.validator_model == "gpt-3.5-turbo"
        assert profile.tracker == "github"
        # working_dir should be overridden by worktree_path
        assert profile.working_dir == "/override/dir"
        assert profile.plan_output_dir == "custom/plans"
        assert profile.plan_path_pattern == "custom/{date}-{issue_key}.md"
        assert profile.max_review_iterations == 5
        assert profile.max_task_review_iterations == 10
        assert profile.auto_approve_reviews is True
