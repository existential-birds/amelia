# tests/unit/server/database/test_schema.py
"""Tests for initial database schema."""
import pytest


class TestInitialSchema:
    """Tests for 001_initial_schema.sql migration."""

    @pytest.mark.parametrize("table_name", ["workflows", "events", "token_usage", "health_check"])
    @pytest.mark.asyncio
    async def test_table_exists(self, migrated_db, table_name):
        """Initial schema creates required tables."""
        result = await migrated_db.fetch_one(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_workflows_has_required_columns(self, migrated_db):
        """Workflows table has all required columns."""
        # Get column info
        result = await migrated_db.fetch_all("PRAGMA table_info(workflows)")
        columns = {row[1] for row in result}

        required = {
            "id", "issue_id", "worktree_path", "worktree_name",
            "status", "started_at", "completed_at", "failure_reason", "state_json"
        }
        assert required.issubset(columns)

    @pytest.mark.asyncio
    async def test_events_has_required_columns(self, migrated_db):
        """Events table has all required columns."""
        result = await migrated_db.fetch_all("PRAGMA table_info(events)")
        columns = {row[1] for row in result}

        required = {
            "id", "workflow_id", "sequence", "timestamp",
            "agent", "event_type", "message", "data_json", "correlation_id"
        }
        assert required.issubset(columns)

    @pytest.mark.asyncio
    async def test_unique_active_worktree_constraint(self, migrated_db):
        """Only one active workflow per worktree is allowed."""
        import aiosqlite

        # Insert first workflow
        await migrated_db.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
            VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'main', 'in_progress', '{}')
        """)

        # Second workflow in same worktree should fail
        with pytest.raises(aiosqlite.IntegrityError):
            await migrated_db.execute("""
                INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
                VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'main', 'pending', '{}')
            """)

    @pytest.mark.asyncio
    async def test_completed_workflows_dont_conflict(self, migrated_db):
        """Completed workflows don't block new workflows in same worktree."""
        # Insert completed workflow
        await migrated_db.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
            VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'main', 'completed', '{}')
        """)

        # New workflow in same worktree should succeed
        await migrated_db.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
            VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'main', 'in_progress', '{}')
        """)

        # Verify both exist
        result = await migrated_db.fetch_all("SELECT id FROM workflows")
        assert len(result) == 2
