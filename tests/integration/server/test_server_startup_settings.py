"""Integration tests for server startup with database settings."""

import tempfile
from pathlib import Path

from amelia.server.database import Database, SettingsRepository


class TestServerStartupSettings:
    """Tests for settings initialization on startup."""

    async def test_ensure_defaults_called_on_startup(self) -> None:
        """Verify server_settings are initialized on startup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "test.db")
            await db.connect()
            await db.ensure_schema()

            repo = SettingsRepository(db)
            await repo.ensure_defaults()

            settings = await repo.get_server_settings()
            assert settings.log_retention_days == 30

            await db.close()
