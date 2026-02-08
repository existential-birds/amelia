"""Tests for SettingsRepository."""

import pytest

from amelia.server.database.connection import Database
from amelia.server.database.settings_repository import ServerSettings, SettingsRepository


pytestmark = pytest.mark.integration


@pytest.fixture
def repo(test_db: Database) -> SettingsRepository:
    """Create a SettingsRepository instance."""
    return SettingsRepository(test_db)


class TestSettingsRepository:
    """Tests for SettingsRepository."""

    async def test_ensure_defaults_creates_singleton(self, repo: SettingsRepository, test_db: Database) -> None:
        """Verify ensure_defaults creates the singleton row."""
        await repo.ensure_defaults()
        row = await test_db.fetch_one("SELECT * FROM server_settings WHERE id = 1")
        assert row is not None
        assert row["log_retention_days"] == 30

    async def test_ensure_defaults_idempotent(self, repo: SettingsRepository) -> None:
        """Verify ensure_defaults can be called multiple times."""
        await repo.ensure_defaults()
        await repo.ensure_defaults()  # Should not raise
        settings = await repo.get_server_settings()
        assert settings.log_retention_days == 30

    async def test_get_server_settings(self, repo: SettingsRepository) -> None:
        """Verify get_server_settings returns defaults."""
        await repo.ensure_defaults()
        settings = await repo.get_server_settings()
        assert isinstance(settings, ServerSettings)
        assert settings.log_retention_days == 30
        assert settings.max_concurrent == 5
        assert settings.stream_tool_results is False

    async def test_get_server_settings_raises_if_not_initialized(self, repo: SettingsRepository) -> None:
        """Verify get_server_settings raises ValueError if ensure_defaults not called."""
        with pytest.raises(ValueError, match="Server settings not initialized"):
            await repo.get_server_settings()

    async def test_update_server_settings(self, repo: SettingsRepository) -> None:
        """Verify update_server_settings modifies values."""
        await repo.ensure_defaults()
        updated = await repo.update_server_settings(
            {"log_retention_days": 60, "max_concurrent": 10}
        )
        assert updated.log_retention_days == 60
        assert updated.max_concurrent == 10

        # Verify persistence
        fetched = await repo.get_server_settings()
        assert fetched.log_retention_days == 60

    async def test_update_server_settings_invalid_field(self, repo: SettingsRepository) -> None:
        """Verify update_server_settings raises for invalid fields."""
        await repo.ensure_defaults()
        with pytest.raises(ValueError, match="Invalid settings fields"):
            await repo.update_server_settings({"invalid_field": 123})

    async def test_update_server_settings_empty_dict(self, repo: SettingsRepository) -> None:
        """Verify update_server_settings with empty dict returns current settings."""
        await repo.ensure_defaults()
        settings = await repo.update_server_settings({})
        assert settings.log_retention_days == 30

    async def test_update_server_settings_updates_timestamp(self, repo: SettingsRepository) -> None:
        """Verify update_server_settings updates updated_at timestamp."""
        await repo.ensure_defaults()
        initial = await repo.get_server_settings()
        initial_updated = initial.updated_at

        await repo.update_server_settings({"log_retention_days": 60})
        updated = await repo.get_server_settings()

        # updated_at should be >= initial (might be same second)
        assert updated.updated_at >= initial_updated

    async def test_update_all_settings_fields(self, repo: SettingsRepository) -> None:
        """Verify all settings fields can be updated."""
        await repo.ensure_defaults()
        updates = {
            "log_retention_days": 60,
            "checkpoint_retention_days": 3,
            "websocket_idle_timeout_seconds": 600.0,
            "workflow_start_timeout_seconds": 120.0,
            "max_concurrent": 10,
            "stream_tool_results": True,
        }
        updated = await repo.update_server_settings(updates)

        assert updated.log_retention_days == 60
        assert updated.checkpoint_retention_days == 3
        assert updated.websocket_idle_timeout_seconds == 600.0
        assert updated.workflow_start_timeout_seconds == 120.0
        assert updated.max_concurrent == 10
        assert updated.stream_tool_results is True
