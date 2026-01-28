"""Tests for WorkflowRepository migration methods."""

import json
from uuid import uuid4

import pytest

from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository


class TestMigratePlanningToPending:
    """Tests for migrate_planning_to_pending."""

    @pytest.fixture
    async def repository(self, db_with_schema: Database) -> WorkflowRepository:
        """WorkflowRepository instance."""
        return WorkflowRepository(db_with_schema)

    async def _insert_workflow_with_status(
        self, db: Database, workflow_id: str, status: str
    ) -> None:
        """Insert a workflow row with an arbitrary status value.

        Uses raw SQL so we can insert the removed 'planning' status
        that Pydantic validation would reject.
        """
        state = {
            "id": workflow_id,
            "issue_id": "ISSUE-1",
            "worktree_path": f"/tmp/{workflow_id}",
            "workflow_status": status,
        }
        await db.execute(
            """
            INSERT INTO workflows (id, issue_id, worktree_path, status, state_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                "ISSUE-1",
                f"/tmp/{workflow_id}",
                status,
                json.dumps(state),
            ),
        )

    async def test_migrates_planning_status_column(self, repository: WorkflowRepository) -> None:
        """Status column is updated from 'planning' to 'pending'."""
        wf_id = str(uuid4())
        await self._insert_workflow_with_status(repository._db, wf_id, "planning")

        count = await repository.migrate_planning_to_pending()

        assert count == 1
        row = await repository._db.fetch_one(
            "SELECT status FROM workflows WHERE id = ?", (wf_id,)
        )
        assert row is not None
        assert row["status"] == "pending"

    async def test_migrates_state_json_workflow_status(
        self, repository: WorkflowRepository
    ) -> None:
        """workflow_status inside state_json is patched to 'pending'."""
        wf_id = str(uuid4())
        await self._insert_workflow_with_status(repository._db, wf_id, "planning")

        await repository.migrate_planning_to_pending()

        row = await repository._db.fetch_one(
            "SELECT state_json FROM workflows WHERE id = ?", (wf_id,)
        )
        assert row is not None
        state = json.loads(row["state_json"])
        assert state["workflow_status"] == "pending"

    async def test_returns_zero_when_no_planning_rows(
        self, repository: WorkflowRepository
    ) -> None:
        """Returns 0 when there are no rows with 'planning' status."""
        # Insert a normal pending workflow via raw SQL (avoids Pydantic rebuild)
        wf_id = str(uuid4())
        await self._insert_workflow_with_status(repository._db, wf_id, "pending")

        count = await repository.migrate_planning_to_pending()

        assert count == 0

    async def test_does_not_affect_other_statuses(
        self, repository: WorkflowRepository
    ) -> None:
        """Only 'planning' rows are affected; other statuses are untouched."""
        pending_id = str(uuid4())
        in_progress_id = str(uuid4())
        planning_id = str(uuid4())

        await self._insert_workflow_with_status(repository._db, pending_id, "pending")
        await self._insert_workflow_with_status(
            repository._db, in_progress_id, "in_progress"
        )
        await self._insert_workflow_with_status(repository._db, planning_id, "planning")

        count = await repository.migrate_planning_to_pending()

        assert count == 1

        # Verify other rows unchanged
        pending_row = await repository._db.fetch_one(
            "SELECT status FROM workflows WHERE id = ?", (pending_id,)
        )
        assert pending_row is not None
        assert pending_row["status"] == "pending"

        in_progress_row = await repository._db.fetch_one(
            "SELECT status FROM workflows WHERE id = ?", (in_progress_id,)
        )
        assert in_progress_row is not None
        assert in_progress_row["status"] == "in_progress"

    async def test_migrates_multiple_planning_rows(
        self, repository: WorkflowRepository
    ) -> None:
        """All rows with 'planning' status are migrated."""
        ids = [str(uuid4()) for _ in range(3)]
        for wf_id in ids:
            await self._insert_workflow_with_status(repository._db, wf_id, "planning")

        count = await repository.migrate_planning_to_pending()

        assert count == 3
        for wf_id in ids:
            row = await repository._db.fetch_one(
                "SELECT status, state_json FROM workflows WHERE id = ?", (wf_id,)
            )
            assert row is not None
            assert row["status"] == "pending"
            state = json.loads(row["state_json"])
            assert state["workflow_status"] == "pending"
