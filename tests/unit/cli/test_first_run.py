"""Tests for first-run interactive setup."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer

from amelia.cli.config import _validate_tracker, check_and_run_first_time_setup
from amelia.core.types import AgentConfig, DriverType, Profile, TrackerType


class TestFirstRunDetection:
    """Tests for first-run detection logic."""

    async def test_not_first_run_when_profiles_exist(
        self, mock_db: MagicMock
    ) -> None:
        """First-run detection returns True when profiles exist."""
        # ProfileRepository.list_profiles returns Profile objects
        existing_profile = Profile(
            name="existing",
            tracker=TrackerType.NOOP,
            working_dir="/tmp",
            agents={
                "architect": AgentConfig(driver=DriverType.CLI, model="sonnet"),
                "developer": AgentConfig(driver=DriverType.CLI, model="sonnet"),
                "reviewer": AgentConfig(driver=DriverType.CLI, model="sonnet"),
            },
        )

        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=[existing_profile])

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            result = await check_and_run_first_time_setup()

        assert result is True
        mock_repo.list_profiles.assert_called_once()
        # Should not prompt for profile creation
        mock_repo.create_profile.assert_not_called()

    async def test_first_run_detected_when_no_profiles(
        self, mock_db: MagicMock
    ) -> None:
        """First-run detection prompts user when no profiles exist."""
        # create_profile returns Profile objects
        created_profile = Profile(
            name="dev",
            tracker=TrackerType.NOOP,
            working_dir="/tmp",
            agents={
                "architect": AgentConfig(driver=DriverType.CLI, model="opus"),
                "developer": AgentConfig(driver=DriverType.CLI, model="opus"),
                "reviewer": AgentConfig(driver=DriverType.CLI, model="opus"),
            },
        )

        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=[])
        mock_repo.create_profile = AsyncMock(return_value=created_profile)
        mock_repo.set_active = AsyncMock()

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo), \
             patch("typer.prompt") as mock_prompt:
            # Simulate user input for prompts
            mock_prompt.side_effect = [
                "local_opus",  # Profile name
                "cli",  # Driver
                "opus",  # Model
                "noop",  # Tracker
                "/tmp",  # Working directory
            ]

            result = await check_and_run_first_time_setup()

        assert result is True
        mock_repo.list_profiles.assert_called_once()
        mock_repo.create_profile.assert_called_once()
        mock_repo.set_active.assert_called_once_with("local_opus")


class TestFirstRunProfileCreation:
    """Tests for first-run profile creation."""

    async def test_profile_created_with_correct_values(
        self, mock_db: MagicMock
    ) -> None:
        """First-run creates profile with user-provided values."""
        # create_profile returns Profile objects
        created_profile = Profile(
            name="myprofile",
            tracker=TrackerType.NOOP,
            working_dir="/home/user/project",
            agents={
                "architect": AgentConfig(driver=DriverType.API, model="sonnet"),
                "developer": AgentConfig(driver=DriverType.API, model="sonnet"),
                "reviewer": AgentConfig(driver=DriverType.API, model="sonnet"),
            },
        )

        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=[])
        mock_repo.create_profile = AsyncMock(return_value=created_profile)
        mock_repo.set_active = AsyncMock()

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo), \
             patch("typer.prompt") as mock_prompt:
            mock_prompt.side_effect = [
                "myprofile",  # Profile name
                "api",  # Driver
                "sonnet",  # Model
                "github",  # Tracker
                "/home/user/project",  # Working directory
            ]

            await check_and_run_first_time_setup()

        # Verify profile was created with correct values
        call_args = mock_repo.create_profile.call_args
        created_profile_arg: Profile = call_args[0][0]

        assert created_profile_arg.name == "myprofile"
        assert created_profile_arg.tracker == "github"
        assert created_profile_arg.working_dir == "/home/user/project"
        # Check that agents were created with correct driver/model
        assert "architect" in created_profile_arg.agents
        assert created_profile_arg.agents["architect"].driver == "api"
        assert created_profile_arg.agents["architect"].model == "sonnet"

    async def test_profile_set_as_active(self, mock_db: MagicMock) -> None:
        """First-run sets created profile as active."""
        created_profile = Profile(
            name="testprofile",
            tracker=TrackerType.NOOP,
            working_dir="/tmp",
            agents={
                "architect": AgentConfig(driver=DriverType.CLI, model="opus"),
                "developer": AgentConfig(driver=DriverType.CLI, model="opus"),
                "reviewer": AgentConfig(driver=DriverType.CLI, model="opus"),
            },
        )

        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=[])
        mock_repo.create_profile = AsyncMock(return_value=created_profile)
        mock_repo.set_active = AsyncMock()

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo), \
             patch("typer.prompt") as mock_prompt:
            mock_prompt.side_effect = [
                "testprofile",
                "cli",
                "opus",
                "noop",
                "/tmp",
            ]

            await check_and_run_first_time_setup()

        mock_repo.set_active.assert_called_once_with("testprofile")

    async def test_database_closed_after_setup(self, mock_db: MagicMock) -> None:
        """Database connection is closed after first-run setup."""
        created_profile = Profile(
            name="dev",
            tracker=TrackerType.NOOP,
            working_dir="/tmp",
            agents={
                "architect": AgentConfig(driver=DriverType.CLI, model="opus"),
                "developer": AgentConfig(driver=DriverType.CLI, model="opus"),
                "reviewer": AgentConfig(driver=DriverType.CLI, model="opus"),
            },
        )

        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=[])
        mock_repo.create_profile = AsyncMock(return_value=created_profile)
        mock_repo.set_active = AsyncMock()

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo), \
             patch("typer.prompt") as mock_prompt:
            mock_prompt.side_effect = ["local_opus", "cli", "opus", "noop", "/tmp"]

            await check_and_run_first_time_setup()

        mock_db.close.assert_called_once()

    async def test_database_closed_on_existing_profiles(
        self, mock_db: MagicMock
    ) -> None:
        """Database connection is closed when profiles exist."""
        existing_profile = Profile(
            name="existing",
            tracker=TrackerType.NOOP,
            working_dir="/tmp",
            agents={
                "architect": AgentConfig(driver=DriverType.CLI, model="sonnet"),
                "developer": AgentConfig(driver=DriverType.CLI, model="sonnet"),
                "reviewer": AgentConfig(driver=DriverType.CLI, model="sonnet"),
            },
        )

        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=[existing_profile])

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            await check_and_run_first_time_setup()

        mock_db.close.assert_called_once()


class TestTrackerValidation:
    """Tests for tracker input validation."""

    @pytest.mark.parametrize("valid_tracker", ["noop", "github", "jira"])
    def test_validate_tracker_accepts_valid_values(self, valid_tracker: str) -> None:
        """_validate_tracker accepts all valid TrackerType values."""
        result = _validate_tracker(valid_tracker)
        assert result == valid_tracker

    @pytest.mark.parametrize("invalid_tracker", ["invalid", "", "NOOP", "gitlab"])
    def test_validate_tracker_rejects_invalid_values(
        self, invalid_tracker: str
    ) -> None:
        """_validate_tracker raises BadParameter for invalid input."""
        with pytest.raises(typer.BadParameter):
            _validate_tracker(invalid_tracker)
