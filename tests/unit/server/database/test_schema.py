# tests/unit/server/database/test_schema.py
"""Tests for database schema constraints."""
import aiosqlite
import pytest

from amelia.server.database.connection import Database


class TestEventsSchema:
    """Tests for events table schema."""

    async def test_events_table_has_level_column(self, db_with_schema: Database) -> None:
        """Events table has level column."""
        columns = await db_with_schema.fetch_all("PRAGMA table_info(events)")
        column_names = [col["name"] for col in columns]
        assert "level" in column_names

    async def test_events_table_has_trace_columns(self, db_with_schema: Database) -> None:
        """Events table has trace-specific columns."""
        columns = await db_with_schema.fetch_all("PRAGMA table_info(events)")
        column_names = [col["name"] for col in columns]
        assert "tool_name" in column_names
        assert "tool_input_json" in column_names
        assert "is_error" in column_names

    async def test_events_level_index_exists(self, db_with_schema: Database) -> None:
        """Events table has index on level column."""
        indexes = await db_with_schema.fetch_all("PRAGMA index_list(events)")
        index_names = [idx["name"] for idx in indexes]
        assert "idx_events_level" in index_names

    async def test_events_table_has_distributed_tracing_columns(
        self, db_with_schema: Database
    ) -> None:
        """Events table has trace_id and parent_id columns."""
        columns = await db_with_schema.fetch_all("PRAGMA table_info(events)")
        column_names = [col["name"] for col in columns]
        assert "trace_id" in column_names
        assert "parent_id" in column_names

    async def test_events_trace_id_index_exists(self, db_with_schema: Database) -> None:
        """Events table has index on trace_id column."""
        indexes = await db_with_schema.fetch_all("PRAGMA index_list(events)")
        index_names = [idx["name"] for idx in indexes]
        assert "idx_events_trace_id" in index_names


class TestWorktreeConstraints:
    """Tests for worktree uniqueness constraints."""

    async def test_unique_constraint_blocks_two_in_progress(self, db_with_schema) -> None:
        """Two in_progress workflows on same worktree should fail."""
        # Insert first in_progress workflow
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status, state_json)
            VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'in_progress', '{}')
        """)

        # Second in_progress workflow in same worktree should fail
        with pytest.raises(aiosqlite.IntegrityError):
            await db_with_schema.execute("""
                INSERT INTO workflows (id, issue_id, worktree_path, status, state_json)
                VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'in_progress', '{}')
            """)

    async def test_pending_workflows_dont_conflict(self, db_with_schema) -> None:
        """Multiple pending workflows on same worktree should be allowed.

        Per queue workflows design: multiple pending workflows per worktree allowed.
        The uniqueness constraint only applies to in_progress/blocked workflows.
        """
        # Insert first pending workflow
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status, state_json)
            VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'pending', '{}')
        """)

        # Second pending workflow in same worktree should succeed
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status, state_json)
            VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'pending', '{}')
        """)

        # Verify both exist
        result = await db_with_schema.fetch_all("SELECT id FROM workflows WHERE status='pending'")
        assert len(result) == 2

    async def test_pending_doesnt_conflict_with_in_progress(self, db_with_schema) -> None:
        """One in_progress + one pending on same worktree should be allowed."""
        # Insert in_progress workflow
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status, state_json)
            VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'in_progress', '{}')
        """)

        # Pending workflow in same worktree should succeed
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status, state_json)
            VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'pending', '{}')
        """)

        # Verify both exist
        result = await db_with_schema.fetch_all("SELECT id FROM workflows")
        assert len(result) == 2

    async def test_completed_workflows_dont_conflict(self, db_with_schema) -> None:
        """Completed workflows don't block new workflows in same worktree."""
        # Insert completed workflow
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status, state_json)
            VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'completed', '{}')
        """)

        # New workflow in same worktree should succeed
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status, state_json)
            VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'in_progress', '{}')
        """)

        # Verify both exist
        result = await db_with_schema.fetch_all("SELECT id FROM workflows")
        assert len(result) == 2
