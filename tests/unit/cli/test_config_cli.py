"""Tests for config CLI commands."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from amelia.core.types import AgentConfig, Profile
from amelia.main import app


class TestConfigCLI:
    """Tests for 'amelia config' command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Typer CLI test runner."""
        return CliRunner()

    def test_config_command_exists(self, runner: CliRunner) -> None:
        """'amelia config' command is registered."""
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "Configuration management commands" in result.stdout

    def test_profile_list_command_exists(self, runner: CliRunner) -> None:
        """'amelia config profile list' command is registered."""
        result = runner.invoke(app, ["config", "profile", "--help"])
        assert result.exit_code == 0
        assert "Profile management commands" in result.stdout

    def test_server_settings_command_exists(self, runner: CliRunner) -> None:
        """'amelia config server' command is registered."""
        result = runner.invoke(app, ["config", "server", "--help"])
        assert result.exit_code == 0
        assert "Server settings commands" in result.stdout


class TestProfileList:
    """Tests for 'amelia config profile list' command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Typer CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Database."""
        mock = MagicMock()
        mock.connect = AsyncMock()
        mock.close = AsyncMock()
        mock.ensure_schema = AsyncMock()
        return mock

    def test_profile_list_empty(self, runner: CliRunner, mock_db: MagicMock) -> None:
        """'amelia config profile list' shows message when no profiles."""
        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=[])

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            result = runner.invoke(app, ["config", "profile", "list"])

        assert result.exit_code == 0
        assert "No profiles found" in result.stdout

    def test_profile_list_with_profiles(
        self, runner: CliRunner, mock_db: MagicMock
    ) -> None:
        """'amelia config profile list' shows profiles in table."""
        # ProfileRepository.list_profiles returns Profile objects, not ProfileRecord
        mock_profiles = [
            Profile(
                name="test-profile",
                tracker="none",
                working_dir="/tmp/test",
                agents={
                    "architect": AgentConfig(driver="cli", model="sonnet"),
                    "developer": AgentConfig(driver="cli", model="sonnet"),
                    "reviewer": AgentConfig(driver="cli", model="sonnet"),
                },
            ),
            Profile(
                name="prod-profile",
                tracker="github",
                working_dir="/home/user/project",
                agents={
                    "architect": AgentConfig(driver="api", model="anthropic/claude-sonnet-4-20250514"),
                    "developer": AgentConfig(driver="api", model="anthropic/claude-sonnet-4-20250514"),
                    "reviewer": AgentConfig(driver="api", model="anthropic/claude-sonnet-4-20250514"),
                },
            ),
        ]

        mock_repo = MagicMock()
        mock_repo.list_profiles = AsyncMock(return_value=mock_profiles)

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            result = runner.invoke(app, ["config", "profile", "list"])

        assert result.exit_code == 0
        assert "test-profile" in result.stdout
        assert "prod-profile" in result.stdout
        assert "cli" in result.stdout
        assert "api" in result.stdout


class TestProfileShow:
    """Tests for 'amelia config profile show' command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Typer CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Database."""
        mock = MagicMock()
        mock.connect = AsyncMock()
        mock.close = AsyncMock()
        mock.ensure_schema = AsyncMock()
        return mock

    def test_profile_show_not_found(
        self, runner: CliRunner, mock_db: MagicMock
    ) -> None:
        """'amelia config profile show' handles missing profile."""
        mock_repo = MagicMock()
        mock_repo.get_profile = AsyncMock(return_value=None)

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            result = runner.invoke(app, ["config", "profile", "show", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_profile_show_found(self, runner: CliRunner, mock_db: MagicMock) -> None:
        """'amelia config profile show' displays profile details."""
        # ProfileRepository.get_profile returns Profile object, not ProfileRecord
        mock_profile = Profile(
            name="my-profile",
            tracker="github",
            working_dir="/home/user/code",
            plan_output_dir="docs/plans",
            agents={
                "architect": AgentConfig(driver="cli", model="sonnet"),
                "developer": AgentConfig(driver="cli", model="sonnet"),
                "reviewer": AgentConfig(driver="cli", model="sonnet"),
                "plan_validator": AgentConfig(driver="cli", model="opus"),
            },
        )

        mock_repo = MagicMock()
        mock_repo.get_profile = AsyncMock(return_value=mock_profile)

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            result = runner.invoke(app, ["config", "profile", "show", "my-profile"])

        assert result.exit_code == 0
        assert "my-profile" in result.stdout
        assert "cli" in result.stdout
        assert "sonnet" in result.stdout


class TestProfileCreate:
    """Tests for 'amelia config profile create' command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Typer CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Database."""
        mock = MagicMock()
        mock.connect = AsyncMock()
        mock.close = AsyncMock()
        mock.ensure_schema = AsyncMock()
        return mock

    def test_profile_create_with_options(
        self, runner: CliRunner, mock_db: MagicMock
    ) -> None:
        """'amelia config profile create' creates profile with CLI options."""
        # create_profile returns Profile, not ProfileRecord
        created_profile = Profile(
            name="new-profile",
            tracker="none",
            working_dir="/tmp",
            agents={
                "architect": AgentConfig(driver="cli", model="sonnet"),
                "developer": AgentConfig(driver="cli", model="sonnet"),
                "reviewer": AgentConfig(driver="cli", model="sonnet"),
                "plan_validator": AgentConfig(driver="cli", model="sonnet"),
            },
        )

        mock_repo = MagicMock()
        mock_repo.get_profile = AsyncMock(return_value=None)
        mock_repo.create_profile = AsyncMock(return_value=created_profile)

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            result = runner.invoke(app, [
                "config", "profile", "create", "new-profile",
                "--driver", "cli",
                "--model", "sonnet",
                "--tracker", "none",
                "--working-dir", "/tmp",
            ])

        assert result.exit_code == 0
        assert "created successfully" in result.stdout
        mock_repo.create_profile.assert_called_once()

    def test_profile_create_already_exists(
        self, runner: CliRunner, mock_db: MagicMock
    ) -> None:
        """'amelia config profile create' fails if profile exists."""
        # get_profile returns Profile, not ProfileRecord
        existing_profile = Profile(
            name="existing",
            tracker="none",
            working_dir="/tmp",
            agents={
                "architect": AgentConfig(driver="cli", model="sonnet"),
                "developer": AgentConfig(driver="cli", model="sonnet"),
                "reviewer": AgentConfig(driver="cli", model="sonnet"),
            },
        )

        mock_repo = MagicMock()
        mock_repo.get_profile = AsyncMock(return_value=existing_profile)

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            result = runner.invoke(app, [
                "config", "profile", "create", "existing",
                "--driver", "cli",
                "--model", "sonnet",
                "--tracker", "none",
                "--working-dir", "/tmp",
            ])

        assert result.exit_code == 1
        assert "already exists" in result.stdout


class TestProfileDelete:
    """Tests for 'amelia config profile delete' command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Typer CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Database."""
        mock = MagicMock()
        mock.connect = AsyncMock()
        mock.close = AsyncMock()
        mock.ensure_schema = AsyncMock()
        return mock

    def test_profile_delete_with_force(
        self, runner: CliRunner, mock_db: MagicMock
    ) -> None:
        """'amelia config profile delete --force' deletes without confirmation."""
        mock_repo = MagicMock()
        mock_repo.delete_profile = AsyncMock(return_value=True)

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            result = runner.invoke(
                app, ["config", "profile", "delete", "test-profile", "--force"]
            )

        assert result.exit_code == 0
        assert "deleted" in result.stdout
        mock_repo.delete_profile.assert_called_once_with("test-profile")

    def test_profile_delete_not_found(
        self, runner: CliRunner, mock_db: MagicMock
    ) -> None:
        """'amelia config profile delete' handles missing profile."""
        mock_repo = MagicMock()
        mock_repo.delete_profile = AsyncMock(return_value=False)

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            result = runner.invoke(
                app, ["config", "profile", "delete", "nonexistent", "--force"]
            )

        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestProfileActivate:
    """Tests for 'amelia config profile activate' command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Typer CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Database."""
        mock = MagicMock()
        mock.connect = AsyncMock()
        mock.close = AsyncMock()
        mock.ensure_schema = AsyncMock()
        return mock

    def test_profile_activate_success(
        self, runner: CliRunner, mock_db: MagicMock
    ) -> None:
        """'amelia config profile activate' activates profile."""
        mock_repo = MagicMock()
        mock_repo.set_active = AsyncMock()

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            result = runner.invoke(
                app, ["config", "profile", "activate", "my-profile"]
            )

        assert result.exit_code == 0
        assert "is now active" in result.stdout
        mock_repo.set_active.assert_called_once_with("my-profile")

    def test_profile_activate_not_found(
        self, runner: CliRunner, mock_db: MagicMock
    ) -> None:
        """'amelia config profile activate' handles missing profile."""
        mock_repo = MagicMock()
        mock_repo.set_active = AsyncMock(
            side_effect=ValueError("Profile not found: nonexistent")
        )

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.ProfileRepository", return_value=mock_repo):
            result = runner.invoke(
                app, ["config", "profile", "activate", "nonexistent"]
            )

        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestServerShow:
    """Tests for 'amelia config server show' command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Typer CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Database."""
        mock = MagicMock()
        mock.connect = AsyncMock()
        mock.close = AsyncMock()
        mock.ensure_schema = AsyncMock()
        return mock

    def test_server_show(self, runner: CliRunner, mock_db: MagicMock) -> None:
        """'amelia config server show' displays server settings."""
        from datetime import datetime

        from amelia.server.database import ServerSettings

        mock_settings = ServerSettings(
            log_retention_days=30,
            log_retention_max_events=100000,
            trace_retention_days=7,
            checkpoint_retention_days=0,
            checkpoint_path="~/.amelia/checkpoints.db",
            websocket_idle_timeout_seconds=300.0,
            workflow_start_timeout_seconds=60.0,
            max_concurrent=5,
            stream_tool_results=False,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        mock_repo = MagicMock()
        mock_repo.ensure_defaults = AsyncMock()
        mock_repo.get_server_settings = AsyncMock(return_value=mock_settings)

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.SettingsRepository", return_value=mock_repo):
            result = runner.invoke(app, ["config", "server", "show"])

        assert result.exit_code == 0
        assert "Server Settings" in result.stdout
        assert "30" in result.stdout  # log_retention_days


class TestServerSet:
    """Tests for 'amelia config server set' command."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Typer CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock Database."""
        mock = MagicMock()
        mock.connect = AsyncMock()
        mock.close = AsyncMock()
        mock.ensure_schema = AsyncMock()
        return mock

    def test_server_set_int_value(
        self, runner: CliRunner, mock_db: MagicMock
    ) -> None:
        """'amelia config server set' sets integer value."""
        mock_repo = MagicMock()
        mock_repo.ensure_defaults = AsyncMock()
        mock_repo.update_server_settings = AsyncMock()

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.SettingsRepository", return_value=mock_repo):
            result = runner.invoke(
                app, ["config", "server", "set", "max_concurrent", "10"]
            )

        assert result.exit_code == 0
        assert "Set max_concurrent = 10" in result.stdout
        mock_repo.update_server_settings.assert_called_once_with({"max_concurrent": 10})

    def test_server_set_bool_value(
        self, runner: CliRunner, mock_db: MagicMock
    ) -> None:
        """'amelia config server set' sets boolean value."""
        mock_repo = MagicMock()
        mock_repo.ensure_defaults = AsyncMock()
        mock_repo.update_server_settings = AsyncMock()

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.SettingsRepository", return_value=mock_repo):
            result = runner.invoke(
                app, ["config", "server", "set", "stream_tool_results", "true"]
            )

        assert result.exit_code == 0
        assert "Set stream_tool_results = True" in result.stdout
        mock_repo.update_server_settings.assert_called_once_with(
            {"stream_tool_results": True}
        )

    def test_server_set_unknown_setting(
        self, runner: CliRunner, mock_db: MagicMock
    ) -> None:
        """'amelia config server set' handles unknown setting."""
        mock_repo = MagicMock()
        mock_repo.ensure_defaults = AsyncMock()

        with patch("amelia.cli.config.get_database", return_value=mock_db), \
             patch("amelia.cli.config.SettingsRepository", return_value=mock_repo):
            result = runner.invoke(
                app, ["config", "server", "set", "unknown_setting", "value"]
            )

        assert result.exit_code == 1
        assert "Unknown setting" in result.stdout
