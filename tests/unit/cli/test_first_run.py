"""Tests for first-run interactive setup."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.cli.config import check_and_run_first_time_setup
from amelia.server.database import ProfileRecord


class TestFirstRunDetection:
    """Tests for first-run detection logic."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Database."""
        mock = MagicMock()
        mock.connect = AsyncMock()
        mock.close = AsyncMock()
        mock.ensure_schema = AsyncMock()
        return mock

    async def test_not_first_run_when_profiles_exist(
        self, mock_db: MagicMock
    ) -> None:
        """First-run detection returns True when profiles exist."""
        existing_profile = ProfileRecord(
            id="existing",
            driver="cli:claude",
            model="sonnet",
            validator_model="haiku",
            tracker="noop",
            working_dir="/tmp",
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
        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=[])
        mock_repo.create_profile = AsyncMock(
            return_value=ProfileRecord(
                id="dev",
                driver="cli:claude",
                model="opus",
                validator_model="haiku",
                tracker="noop",
                working_dir="/tmp",
            )
        )
        mock_repo.set_active = AsyncMock()

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo), \
             patch("typer.prompt") as mock_prompt:
            # Simulate user input for prompts
            mock_prompt.side_effect = [
                "dev",  # Profile name
                "cli:claude",  # Driver
                "opus",  # Model
                "/tmp",  # Working directory
            ]

            result = await check_and_run_first_time_setup()

        assert result is True
        mock_repo.list_profiles.assert_called_once()
        mock_repo.create_profile.assert_called_once()
        mock_repo.set_active.assert_called_once_with("dev")


class TestFirstRunProfileCreation:
    """Tests for first-run profile creation."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Database."""
        mock = MagicMock()
        mock.connect = AsyncMock()
        mock.close = AsyncMock()
        mock.ensure_schema = AsyncMock()
        return mock

    async def test_profile_created_with_correct_values(
        self, mock_db: MagicMock
    ) -> None:
        """First-run creates profile with user-provided values."""
        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=[])
        mock_repo.create_profile = AsyncMock(
            return_value=ProfileRecord(
                id="myprofile",
                driver="api:openrouter",
                model="sonnet",
                validator_model="haiku",
                tracker="noop",
                working_dir="/home/user/project",
            )
        )
        mock_repo.set_active = AsyncMock()

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo), \
             patch("typer.prompt") as mock_prompt:
            mock_prompt.side_effect = [
                "myprofile",  # Profile name
                "api:openrouter",  # Driver
                "sonnet",  # Model
                "/home/user/project",  # Working directory
            ]

            await check_and_run_first_time_setup()

        # Verify profile was created with correct values
        call_args = mock_repo.create_profile.call_args
        created_profile: ProfileRecord = call_args[0][0]

        assert created_profile.id == "myprofile"
        assert created_profile.driver == "api:openrouter"
        assert created_profile.model == "sonnet"
        assert created_profile.validator_model == "haiku"
        assert created_profile.tracker == "noop"
        assert created_profile.working_dir == "/home/user/project"

    async def test_profile_set_as_active(self, mock_db: MagicMock) -> None:
        """First-run sets created profile as active."""
        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=[])
        mock_repo.create_profile = AsyncMock(
            return_value=ProfileRecord(
                id="testprofile",
                driver="cli:claude",
                model="opus",
                validator_model="haiku",
                tracker="noop",
                working_dir="/tmp",
            )
        )
        mock_repo.set_active = AsyncMock()

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo), \
             patch("typer.prompt") as mock_prompt:
            mock_prompt.side_effect = [
                "testprofile",
                "cli:claude",
                "opus",
                "/tmp",
            ]

            await check_and_run_first_time_setup()

        mock_repo.set_active.assert_called_once_with("testprofile")

    async def test_database_closed_after_setup(self, mock_db: MagicMock) -> None:
        """Database connection is closed after first-run setup."""
        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=[])
        mock_repo.create_profile = AsyncMock(
            return_value=ProfileRecord(
                id="dev",
                driver="cli:claude",
                model="opus",
                validator_model="haiku",
                tracker="noop",
                working_dir="/tmp",
            )
        )
        mock_repo.set_active = AsyncMock()

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo), \
             patch("typer.prompt") as mock_prompt:
            mock_prompt.side_effect = ["dev", "cli:claude", "opus", "/tmp"]

            await check_and_run_first_time_setup()

        mock_db.close.assert_called_once()

    async def test_database_closed_on_existing_profiles(
        self, mock_db: MagicMock
    ) -> None:
        """Database connection is closed when profiles exist."""
        existing_profile = ProfileRecord(
            id="existing",
            driver="cli:claude",
            model="sonnet",
            validator_model="haiku",
            tracker="noop",
            working_dir="/tmp",
        )

        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=[existing_profile])

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            await check_and_run_first_time_setup()

        mock_db.close.assert_called_once()
