"""Integration tests for server startup with database settings."""

from amelia.server.database import Database, SettingsRepository
from amelia.server.database.migrator import Migrator


DATABASE_URL = "postgresql://amelia:amelia@localhost:5432/amelia_test"


class TestServerStartupSettings:
    """Tests for settings initialization on startup."""

    async def test_ensure_defaults_called_on_startup(self) -> None:
        """Verify server_settings are initialized on startup."""
        db = Database(DATABASE_URL)
        await db.connect()
        migrator = Migrator(db)
        await migrator.run()

        repo = SettingsRepository(db)
        await repo.ensure_defaults()

        settings = await repo.get_server_settings()
        assert settings.log_retention_days == 30

        await db.close()
