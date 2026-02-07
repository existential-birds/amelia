# tests/unit/server/database/test_schema.py
"""Tests for database schema constraints."""
import aiosqlite
import pytest

from amelia.server.database.connection import Database


class TestEventsSchema:
    """Tests for workflow_log table schema."""

    async def test_workflow_log_table_has_level_column(self, db_with_schema: Database) -> None:
        """workflow_log table has level column."""
        columns = await db_with_schema.fetch_all("PRAGMA table_info(workflow_log)")
        column_names = [col["name"] for col in columns]
        assert "level" in column_names

    async def test_workflow_log_table_has_expected_columns(self, db_with_schema: Database) -> None:
        """workflow_log table has the expected columns."""
        columns = await db_with_schema.fetch_all("PRAGMA table_info(workflow_log)")
        column_names = [col["name"] for col in columns]
        assert "id" in column_names
        assert "workflow_id" in column_names
        assert "sequence" in column_names
        assert "timestamp" in column_names
        assert "event_type" in column_names
        assert "level" in column_names
        assert "agent" in column_names
        assert "message" in column_names
        assert "data_json" in column_names
        assert "is_error" in column_names

    async def test_workflow_log_errors_index_exists(self, db_with_schema: Database) -> None:
        """workflow_log table has index on errors."""
        indexes = await db_with_schema.fetch_all("PRAGMA index_list(workflow_log)")
        index_names = [idx["name"] for idx in indexes]
        assert "idx_workflow_log_errors" in index_names

    async def test_workflow_log_does_not_have_trace_columns(
        self, db_with_schema: Database
    ) -> None:
        """workflow_log table does NOT have old trace-specific columns."""
        columns = await db_with_schema.fetch_all("PRAGMA table_info(workflow_log)")
        column_names = [col["name"] for col in columns]
        assert "tool_name" not in column_names
        assert "tool_input_json" not in column_names
        assert "trace_id" not in column_names
        assert "parent_id" not in column_names
        assert "correlation_id" not in column_names

    async def test_workflow_log_workflow_sequence_index_exists(self, db_with_schema: Database) -> None:
        """workflow_log table has unique index on (workflow_id, sequence)."""
        indexes = await db_with_schema.fetch_all("PRAGMA index_list(workflow_log)")
        index_names = [idx["name"] for idx in indexes]
        assert "idx_workflow_log_workflow_sequence" in index_names


class TestWorkflowsSchema:
    """Tests for workflows table schema."""

    async def test_workflows_table_has_new_columns(self, db_with_schema: Database) -> None:
        """Workflows table has new columns for state_json replacement."""
        columns = await db_with_schema.fetch_all("PRAGMA table_info(workflows)")
        column_names = [col["name"] for col in columns]

        # New columns added in Phase 1
        assert "workflow_type" in column_names
        assert "profile_id" in column_names
        assert "plan_cache" in column_names
        assert "issue_cache" in column_names

    async def test_workflow_type_has_default(self, db_with_schema: Database) -> None:
        """workflow_type column has default value 'full'."""
        # Insert without specifying workflow_type
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES ('test-id', 'ISSUE-1', '/path', 'pending')
        """)

        row = await db_with_schema.fetch_one(
            "SELECT workflow_type FROM workflows WHERE id = 'test-id'"
        )
        assert row is not None
        assert row["workflow_type"] == "full"


class TestWorktreeConstraints:
    """Tests for worktree uniqueness constraints."""

    async def test_unique_constraint_blocks_two_in_progress(self, db_with_schema) -> None:
        """Two in_progress workflows on same worktree should fail."""
        # Insert first in_progress workflow
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'in_progress')
        """)

        # Second in_progress workflow in same worktree should fail
        with pytest.raises(aiosqlite.IntegrityError):
            await db_with_schema.execute("""
                INSERT INTO workflows (id, issue_id, worktree_path, status)
                VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'in_progress')
            """)

    async def test_pending_workflows_dont_conflict(self, db_with_schema) -> None:
        """Multiple pending workflows on same worktree should be allowed.

        Per queue workflows design: multiple pending workflows per worktree allowed.
        The uniqueness constraint only applies to in_progress/blocked workflows.
        """
        # Insert first pending workflow
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'pending')
        """)

        # Second pending workflow in same worktree should succeed
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'pending')
        """)

        # Verify both exist
        result = await db_with_schema.fetch_all("SELECT id FROM workflows WHERE status='pending'")
        assert len(result) == 2

    async def test_pending_doesnt_conflict_with_in_progress(self, db_with_schema) -> None:
        """One in_progress + one pending on same worktree should be allowed."""
        # Insert in_progress workflow
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'in_progress')
        """)

        # Pending workflow in same worktree should succeed
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'pending')
        """)

        # Verify both exist
        result = await db_with_schema.fetch_all("SELECT id FROM workflows")
        assert len(result) == 2

    async def test_completed_workflows_dont_conflict(self, db_with_schema) -> None:
        """Completed workflows don't block new workflows in same worktree."""
        # Insert completed workflow
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES ('id1', 'ISSUE-1', '/path/to/worktree', 'completed')
        """)

        # New workflow in same worktree should succeed
        await db_with_schema.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES ('id2', 'ISSUE-2', '/path/to/worktree', 'in_progress')
        """)

        # Verify both exist
        result = await db_with_schema.fetch_all("SELECT id FROM workflows")
        assert len(result) == 2
