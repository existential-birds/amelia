# tests/integration/server/database/test_schema.py
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


class TestDroppedTables:
    """Guards that the dead stores stay dropped — trajectories are the only run history."""

    @pytest.mark.parametrize("table", ["workflow_log", "token_usage"])
    async def test_dead_store_table_does_not_exist(
        self, test_db: Database, table: str
    ) -> None:
        row = await test_db.fetch_one(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)",
            table,
        )
        assert row is not None
        assert row[0] is False, f"Table {table} should have been dropped"


class TestWorkflowsSchema:
    """Tests for workflows table schema."""

    async def test_workflows_table_has_new_columns(self, test_db: Database) -> None:
        """Workflows table has new columns for state_json replacement."""
        columns = await _get_columns(test_db, "workflows")
        assert "workflow_type" in columns
        assert "profile_id" in columns
        assert "plan_cache" in columns
        assert "issue_cache" in columns

    async def test_workflow_type_has_default(self, test_db: Database) -> None:
        """workflow_type column has default value 'full'."""
        await test_db.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-1', '/path', 'pending')
        """)
        row = await test_db.fetch_one(
            "SELECT workflow_type FROM workflows WHERE issue_id = 'ISSUE-1'"
        )
        assert row is not None
        assert row["workflow_type"] == "full"


class TestWorktreeConstraints:
    """Tests for worktree uniqueness constraints."""

    async def test_unique_constraint_blocks_two_in_progress(self, test_db) -> None:
        """Two in_progress workflows on same worktree should fail."""
        await test_db.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-1', '/path/to/worktree', 'in_progress')
        """)
        with pytest.raises(asyncpg.exceptions.UniqueViolationError):
            await test_db.execute("""
                INSERT INTO workflows (id, issue_id, worktree_path, status)
                VALUES (gen_random_uuid(), 'ISSUE-2', '/path/to/worktree', 'in_progress')
            """)

    async def test_pending_workflows_dont_conflict(self, test_db) -> None:
        """Multiple pending workflows on same worktree should be allowed."""
        await test_db.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-1', '/path/to/worktree', 'pending')
        """)
        await test_db.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-2', '/path/to/worktree', 'pending')
        """)
        result = await test_db.fetch_all("SELECT id FROM workflows WHERE status='pending'")
        assert len(result) == 2

    async def test_pending_doesnt_conflict_with_in_progress(self, test_db) -> None:
        """One in_progress + one pending on same worktree should be allowed."""
        await test_db.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-1', '/path/to/worktree', 'in_progress')
        """)
        await test_db.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-2', '/path/to/worktree', 'pending')
        """)
        result = await test_db.fetch_all("SELECT id FROM workflows")
        assert len(result) == 2

    async def test_completed_workflows_dont_conflict(self, test_db) -> None:
        """Completed workflows don't block new workflows in same worktree."""
        await test_db.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-1', '/path/to/worktree', 'completed')
        """)
        await test_db.execute("""
            INSERT INTO workflows (id, issue_id, worktree_path, status)
            VALUES (gen_random_uuid(), 'ISSUE-2', '/path/to/worktree', 'in_progress')
        """)
        result = await test_db.fetch_all("SELECT id FROM workflows")
        assert len(result) == 2
