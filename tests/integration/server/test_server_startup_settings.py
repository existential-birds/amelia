"""Integration tests for server startup with database settings."""

import pytest

from amelia.server.database import Database, SettingsRepository


pytestmark = pytest.mark.integration


class TestServerStartupSettings:
    """Tests for settings initialization on startup."""

    async def test_ensure_defaults_called_on_startup(self, test_db: Database) -> None:
        """Verify server_settings are initialized on startup."""
        repo = SettingsRepository(test_db)
        await repo.ensure_defaults()

        settings = await repo.get_server_settings()
        assert settings.log_retention_days == 30
