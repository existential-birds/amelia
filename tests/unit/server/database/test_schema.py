# tests/unit/server/database/test_schema.py
"""Tests for initial database schema."""
from pathlib import Path

import pytest


class TestInitialSchema:
    """Tests for 001_initial_schema.sql migration."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Temporary database path."""
        return tmp_path / "test.db"

    @pytest.fixture
    def production_migrations_dir(self):
        """Path to actual migrations directory."""
        import amelia.server.database
        return Path(amelia.server.database.__file__).parent / "migrations"

    @pytest.mark.asyncio
    async def test_workflows_table_exists(self, temp_db_path, production_migrations_dir):
        """Initial schema creates workflows table."""
        from amelia.server.database.connection import Database
        from amelia.server.database.migrate import MigrationRunner

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='workflows'"
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_events_table_exists(self, temp_db_path, production_migrations_dir):
        """Initial schema creates events table."""
        from amelia.server.database.connection import Database
        from amelia.server.database.migrate import MigrationRunner

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_token_usage_table_exists(self, temp_db_path, production_migrations_dir):
        """Initial schema creates token_usage table."""
        from amelia.server.database.connection import Database
        from amelia.server.database.migrate import MigrationRunner

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='token_usage'"
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_health_check_table_exists(self, temp_db_path, production_migrations_dir):
        """Initial schema creates health_check table."""
        from amelia.server.database.connection import Database
        from amelia.server.database.migrate import MigrationRunner

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='health_check'"
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_workflows_has_required_columns(self, temp_db_path, production_migrations_dir):
        """Workflows table has all required columns."""
        from amelia.server.database.connection import Database
        from amelia.server.database.migrate import MigrationRunner

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            # Get column info
            result = await db.fetch_all("PRAGMA table_info(workflows)")
            columns = {row[1] for row in result}

            required = {
                "id", "issue_id", "worktree_path", "worktree_name",
                "status", "started_at", "completed_at", "failure_reason", "state_json"
            }
            assert required.issubset(columns)

    @pytest.mark.asyncio
    async def test_events_has_required_columns(self, temp_db_path, production_migrations_dir):
        """Events table has all required columns."""
        from amelia.server.database.connection import Database
        from amelia.server.database.migrate import MigrationRunner

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            result = await db.fetch_all("PRAGMA table_info(events)")
            columns = {row[1] for row in result}

            required = {
                "id", "workflow_id", "sequence", "timestamp",
                "agent", "event_type", "message", "data_json", "correlation_id"
            }
            assert required.issubset(columns)

    @pytest.mark.asyncio
    async def test_unique_active_worktree_constraint(self, temp_db_path, production_migrations_dir):
        """Only one active workflow per worktree is allowed."""
        import aiosqlite

        from amelia.server.database.connection import Database
        from amelia.server.database.migrate import MigrationRunner

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            # Insert first workflow
            await db.execute("""
                INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
                VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'main', 'in_progress', '{}')
            """)

            # Second workflow in same worktree should fail
            with pytest.raises(aiosqlite.IntegrityError):
                await db.execute("""
                    INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
                    VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'main', 'pending', '{}')
                """)

    @pytest.mark.asyncio
    async def test_completed_workflows_dont_conflict(self, temp_db_path, production_migrations_dir):
        """Completed workflows don't block new workflows in same worktree."""
        from amelia.server.database.connection import Database
        from amelia.server.database.migrate import MigrationRunner

        runner = MigrationRunner(temp_db_path, production_migrations_dir)
        await runner.run_migrations()

        async with Database(temp_db_path) as db:
            # Insert completed workflow
            await db.execute("""
                INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
                VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'main', 'completed', '{}')
            """)

            # New workflow in same worktree should succeed
            await db.execute("""
                INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
                VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'main', 'in_progress', '{}')
            """)

            # Verify both exist
            result = await db.fetch_all("SELECT id FROM workflows")
            assert len(result) == 2
