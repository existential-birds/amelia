# tests/unit/server/database/test_schema.py
"""Tests for initial database schema."""
import pytest


class TestInitialSchema:
    """Tests for database schema creation."""

    @pytest.mark.parametrize("table_name", ["workflows", "events", "token_usage"])
    @pytest.mark.asyncio
    async def test_table_exists(self, db_with_schema, table_name):
        """Initial schema creates required tables."""
        result = await db_with_schema.fetch_one(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_workflows_has_required_columns(self, db_with_schema):
        """Workflows table has all required columns."""
        # Get column info
        result = await db_with_schema.fetch_all("PRAGMA table_info(workflows)")
        columns = {row[1] for row in result}

        required = {
            "id", "issue_id", "worktree_path", "worktree_name",
            "status", "started_at", "completed_at", "failure_reason", "state_json"
        }
        assert required.issubset(columns)

    @pytest.mark.asyncio
    async def test_events_has_required_columns(self, db_with_schema):
        """Events table has all required columns."""
        result = await db_with_schema.fetch_all("PRAGMA table_info(events)")
        columns = {row[1] for row in result}

        required = {
            "id", "workflow_id", "sequence", "timestamp",
            "agent", "event_type", "message", "data_json", "correlation_id"
        }
        assert required.issubset(columns)

    @pytest.mark.asyncio
    async def test_unique_active_worktree_constraint(self, db_with_schema):
        """Only one active workflow per worktree is allowed."""
        import aiosqlite

        # Insert first workflow
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
            VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'main', 'in_progress', '{}')
        """)

        # Second workflow in same worktree should fail
        with pytest.raises(aiosqlite.IntegrityError):
            await db_with_schema.execute("""
                INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
                VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'main', 'pending', '{}')
            """)

    @pytest.mark.asyncio
    async def test_completed_workflows_dont_conflict(self, db_with_schema):
        """Completed workflows don't block new workflows in same worktree."""
        # Insert completed workflow
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
            VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'main', 'completed', '{}')
        """)

        # New workflow in same worktree should succeed
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, worktree_name, status, state_json)
            VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'main', 'in_progress', '{}')
        """)

        # Verify both exist
        result = await db_with_schema.fetch_all("SELECT id FROM workflows")
        assert len(result) == 2
