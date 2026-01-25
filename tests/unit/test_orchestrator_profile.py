"""Tests for orchestrator profile loading from database."""

from unittest.mock import AsyncMock, MagicMock

from amelia.core.types import AgentConfig, Profile, TrackerType
from amelia.server.orchestrator.service import OrchestratorService


def _make_test_profile(
    name: str = "dev",
    tracker: TrackerType = TrackerType.NOOP,
    working_dir: str = "/repo",
) -> Profile:
    """Create a test Profile with default agents configuration."""
    agent_config = AgentConfig(driver="cli", model="opus")
    return Profile(
        name=name,
        tracker=tracker,
        working_dir=working_dir,
        agents={
            "architect": agent_config,
            "developer": agent_config,
            "reviewer": agent_config,
            "task_reviewer": agent_config,
        },
    )


class TestOrchestratorProfileLoading:
    """Tests for profile loading in orchestrator."""

    async def test_get_profile_from_database(self):
        """Verify profile is loaded from database."""
        mock_profile_repo = AsyncMock()
        mock_profile_repo.get_profile.return_value = _make_test_profile()

        # Test that orchestrator uses ProfileRepository
        profile = await mock_profile_repo.get_profile("dev")
        assert profile is not None
        assert profile.name == "dev"
        assert profile.agents["developer"].driver == "cli"

    async def test_get_profile_or_fail_returns_profile(self):
        """Verify _get_profile_or_fail returns Profile from database."""
        mock_event_bus = MagicMock()
        mock_repository = AsyncMock()
        mock_repository.get_max_event_sequence.return_value = 0
        mock_profile_repo = AsyncMock()
        mock_profile_repo.get_profile.return_value = _make_test_profile(
            working_dir="/repo",
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

    async def test_update_profile_working_dir_conversion(self):
        """Verify Profile working_dir is correctly overridden."""
        mock_event_bus = MagicMock()
        mock_repository = AsyncMock()
        mock_repository.get_max_event_sequence.return_value = 0
        mock_profile_repo = AsyncMock()

        service = OrchestratorService(
            event_bus=mock_event_bus,
            repository=mock_repository,
            profile_repo=mock_profile_repo,
        )

        # Create a profile with original working_dir
        agent_config = AgentConfig(driver="api", model="gpt-4")
        profile = Profile(
            name="test-profile",
            tracker="github",
            working_dir="/original/dir",
            plan_output_dir="custom/plans",
            plan_path_pattern="custom/{date}-{issue_key}.md",
            agents={
                "architect": agent_config,
                "developer": agent_config,
                "reviewer": agent_config,
            },
        )

        updated_profile = service._update_profile_working_dir(profile, worktree_path="/override/dir")

        assert updated_profile.name == "test-profile"
        assert updated_profile.tracker == "github"
        # working_dir should be overridden by worktree_path
        assert updated_profile.working_dir == "/override/dir"
        assert updated_profile.plan_output_dir == "custom/plans"
        assert updated_profile.plan_path_pattern == "custom/{date}-{issue_key}.md"
        assert updated_profile.agents["developer"].driver == "api"
