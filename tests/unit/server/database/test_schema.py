# tests/unit/server/database/test_schema.py
"""Tests for database schema constraints."""
import asyncpg
import pytest

from amelia.server.database.connection import Database


pytestmark = pytest.mark.integration


async def _get_columns(db: Database, table: str) -> list[str]:
    """Get column names for a table from information_schema."""
    rows = await db.fetch_all(
        "SELECT column_name FROM information_schema.columns WHERE table_name = $1 ORDER BY ordinal_position",
        table,
    )
    return [row["column_name"] for row in rows]


async def _get_indexes(db: Database, table: str) -> list[str]:
    """Get index names for a table."""
    rows = await db.fetch_all(
        "SELECT indexname FROM pg_indexes WHERE tablename = $1",
        table,
    )
    return [row["indexname"] for row in rows]


class TestEventsSchema:
    """Tests for workflow_log table schema."""

    async def test_workflow_log_table_has_level_column(self, db_with_schema: Database) -> None:
        """workflow_log table has level column."""
        columns = await _get_columns(db_with_schema, "workflow_log")
        assert "level" in columns

    async def test_workflow_log_table_has_expected_columns(self, db_with_schema: Database) -> None:
        """workflow_log table has the expected columns."""
        columns = await _get_columns(db_with_schema, "workflow_log")
        assert "id" in columns
        assert "workflow_id" in columns
        assert "sequence" in columns
        assert "timestamp" in columns
        assert "event_type" in columns
        assert "level" in columns
        assert "agent" in columns
        assert "message" in columns
        assert "data" in columns
        assert "is_error" in columns

    async def test_workflow_log_errors_index_exists(self, db_with_schema: Database) -> None:
        """workflow_log table has index on errors."""
        indexes = await _get_indexes(db_with_schema, "workflow_log")
        assert "idx_workflow_log_errors" in indexes

    async def test_workflow_log_does_not_have_trace_columns(
        self, db_with_schema: Database
    ) -> None:
        """workflow_log table does NOT have old trace-specific columns."""
        columns = await _get_columns(db_with_schema, "workflow_log")
        assert "tool_name" not in columns
        assert "tool_input_json" not in columns
        assert "trace_id" not in columns
        assert "parent_id" not in columns
        assert "correlation_id" not in columns

    async def test_workflow_log_workflow_sequence_unique(self, db_with_schema: Database) -> None:
        """workflow_log table has unique constraint on (workflow_id, sequence)."""
        indexes = await _get_indexes(db_with_schema, "workflow_log")
        assert "idx_workflow_log_workflow" in indexes


class TestWorkflowsSchema:
    """Tests for workflows table schema."""

    async def test_workflows_table_has_new_columns(self, db_with_schema: Database) -> None:
        """Workflows table has new columns for state_json replacement."""
        columns = await _get_columns(db_with_schema, "workflows")
        assert "workflow_type" in columns
        assert "profile_id" in columns
        assert "plan_cache" in columns
        assert "issue_cache" in columns

    async def test_workflow_type_has_default(self, db_with_schema: Database) -> None:
        """workflow_type column has default value 'full'."""
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-1', '/path', 'pending')
        """)
        row = await db_with_schema.fetch_one(
            "SELECT workflow_type FROM workflows WHERE issue_id = 'ISSUE-1'"
        )
        assert row is not None
        assert row["workflow_type"] == "full"


class TestWorktreeConstraints:
    """Tests for worktree uniqueness constraints."""

    async def test_unique_constraint_blocks_two_in_progress(self, db_with_schema) -> None:
        """Two in_progress workflows on same worktree should fail."""
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-1', '/path/to/worktree', 'in_progress')
        """)
        with pytest.raises(asyncpg.exceptions.UniqueViolationError):
            await db_with_schema.execute("""
                INSERT INTO workflows (id, issue_id, worktree_path, status)
                VALUES (gen_random_uuid(), 'ISSUE-2', '/path/to/worktree', 'in_progress')
            """)

    async def test_pending_workflows_dont_conflict(self, db_with_schema) -> None:
        """Multiple pending workflows on same worktree should be allowed."""
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-1', '/path/to/worktree', 'pending')
        """)
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-2', '/path/to/worktree', 'pending')
        """)
        result = await db_with_schema.fetch_all("SELECT id FROM workflows WHERE status='pending'")
        assert len(result) == 2

    async def test_pending_doesnt_conflict_with_in_progress(self, db_with_schema) -> None:
        """One in_progress + one pending on same worktree should be allowed."""
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-1', '/path/to/worktree', 'in_progress')
        """)
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-2', '/path/to/worktree', 'pending')
        """)
        result = await db_with_schema.fetch_all("SELECT id FROM workflows")
        assert len(result) == 2

    async def test_completed_workflows_dont_conflict(self, db_with_schema) -> None:
        """Completed workflows don't block new workflows in same worktree."""
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-1', '/path/to/worktree', 'completed')
        """)
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-2', '/path/to/worktree', 'in_progress')
        """)
        result = await db_with_schema.fetch_all("SELECT id FROM workflows")
        assert len(result) == 2
