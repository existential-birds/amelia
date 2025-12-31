# tests/unit/server/database/test_schema.py
"""Tests for database schema constraints."""
import aiosqlite
import pytest


class TestWorktreeConstraints:
    """Tests for worktree uniqueness constraints."""

    async def test_unique_active_worktree_constraint(self, db_with_schema):
        """Only one active workflow per worktree is allowed."""
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
