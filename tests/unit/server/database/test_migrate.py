# tests/unit/server/database/test_migrate.py
"""Tests for database migrations."""

import pytest


class TestMigrationRunner:
    """Tests for MigrationRunner."""

    @pytest.mark.asyncio
    async def test_creates_version_table(self, temp_db_path, migrations_dir):
        """Migration runner creates schema_version table."""
        from amelia.server.database.connection import Database
        from amelia.server.database.migrate import MigrationRunner

        runner = MigrationRunner(temp_db_path, migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_applies_migrations_in_order(self, temp_db_path, migrations_dir):
        """Migrations are applied in version order."""
        from amelia.server.database.connection import Database
        from amelia.server.database.migrate import MigrationRunner

        # Create test migrations
        (migrations_dir / "001_first.sql").write_text(
            "CREATE TABLE first (id INTEGER);"
        )
        (migrations_dir / "002_second.sql").write_text(
            "CREATE TABLE second (id INTEGER);"
        )
        (migrations_dir / "003_third.sql").write_text(
            "CREATE TABLE third (id INTEGER);"
        )

        runner = MigrationRunner(temp_db_path, migrations_dir)
        applied = await runner.run_migrations()

        assert applied == 3

        async with Database(temp_db_path) as db:
            # All tables should exist
            for table in ["first", "second", "third"]:
                result = await db.fetch_one(
                    f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
                )
                assert result is not None

    @pytest.mark.asyncio
    async def test_skips_already_applied_migrations(self, temp_db_path, migrations_dir):
        """Migrations are only applied once."""
        from amelia.server.database.migrate import MigrationRunner

        (migrations_dir / "001_first.sql").write_text(
            "CREATE TABLE first (id INTEGER);"
        )

        runner = MigrationRunner(temp_db_path, migrations_dir)

        # First run
        applied1 = await runner.run_migrations()
        assert applied1 == 1

        # Second run - should skip
        applied2 = await runner.run_migrations()
        assert applied2 == 0

    @pytest.mark.asyncio
    async def test_applies_new_migrations_only(self, temp_db_path, migrations_dir):
        """Only new migrations are applied on subsequent runs."""
        from amelia.server.database.migrate import MigrationRunner

        (migrations_dir / "001_first.sql").write_text(
            "CREATE TABLE first (id INTEGER);"
        )

        runner = MigrationRunner(temp_db_path, migrations_dir)
        await runner.run_migrations()

        # Add new migration
        (migrations_dir / "002_second.sql").write_text(
            "CREATE TABLE second (id INTEGER);"
        )

        # Run again
        applied = await runner.run_migrations()
        assert applied == 1

    @pytest.mark.asyncio
    async def test_records_applied_versions(self, temp_db_path, migrations_dir):
        """Applied migrations are recorded in schema_version."""
        from amelia.server.database.connection import Database
        from amelia.server.database.migrate import MigrationRunner

        (migrations_dir / "001_first.sql").write_text("SELECT 1;")
        (migrations_dir / "002_second.sql").write_text("SELECT 1;")

        runner = MigrationRunner(temp_db_path, migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_all(
                "SELECT version FROM schema_version ORDER BY version"
            )
            versions = [r[0] for r in result]
            assert versions == [1, 2]

    @pytest.mark.asyncio
    async def test_get_current_version(self, temp_db_path, migrations_dir):
        """get_current_version returns highest applied version."""
        from amelia.server.database.migrate import MigrationRunner

        (migrations_dir / "001_first.sql").write_text("SELECT 1;")
        (migrations_dir / "002_second.sql").write_text("SELECT 1;")

        runner = MigrationRunner(temp_db_path, migrations_dir)
        await runner.run_migrations()

        current = await runner.get_current_version()
        assert current == 2

    @pytest.mark.asyncio
    async def test_migration_with_multiple_statements(self, temp_db_path, migrations_dir):
        """Migrations can contain multiple SQL statements."""
        from amelia.server.database.connection import Database
        from amelia.server.database.migrate import MigrationRunner

        (migrations_dir / "001_multi.sql").write_text("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
            CREATE INDEX idx_users_name ON users(name);
            INSERT INTO users (name) VALUES ('test');
        """)

        runner = MigrationRunner(temp_db_path, migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_one("SELECT name FROM users WHERE id = 1")
            assert result[0] == "test"
