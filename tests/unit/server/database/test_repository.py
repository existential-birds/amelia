"""Tests for WorkflowRepository."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from amelia.server.database.repository import WorkflowRepository
from amelia.server.models import EventType, WorkflowEvent
from amelia.server.models.state import InvalidStateTransitionError, ServerExecutionState


class TestWorkflowRepository:
    """Tests for WorkflowRepository CRUD operations."""

    @pytest.fixture
    async def repository(self, db_with_schema):
        """WorkflowRepository instance."""
        return WorkflowRepository(db_with_schema)

    @pytest.mark.asyncio
    async def test_create_workflow(self, repository):
        """Can create a workflow."""
        state = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            worktree_name="main",
        )

        await repository.create(state)

        # Verify it was created
        retrieved = await repository.get(state.id)
        assert retrieved is not None
        assert retrieved.issue_id == "ISSUE-123"

    @pytest.mark.asyncio
    async def test_get_by_worktree(self, repository):
        """Can get active workflow by worktree path."""
        state = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            worktree_name="main",
            workflow_status="in_progress",
        )
        await repository.create(state)

        retrieved = await repository.get_by_worktree("/path/to/repo")
        assert retrieved is not None
        assert retrieved.id == state.id

    @pytest.mark.asyncio
    async def test_get_by_worktree_only_active(self, repository):
        """get_by_worktree only returns active workflows."""
        # Create completed workflow
        completed = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-1",
            worktree_path="/path/to/repo",
            worktree_name="main",
            workflow_status="completed",
        )
        await repository.create(completed)

        # No active workflow should be found
        result = await repository.get_by_worktree("/path/to/repo")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_workflow(self, repository):
        """Can update workflow state."""
        state = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            worktree_name="main",
        )
        await repository.create(state)

        # Update status
        state.workflow_status = "in_progress"
        state.started_at = datetime.now(UTC)
        await repository.update(state)

        retrieved = await repository.get(state.id)
        assert retrieved.workflow_status == "in_progress"
        assert retrieved.started_at is not None

    @pytest.mark.asyncio
    async def test_set_status_validates_transition(self, repository):
        """set_status validates state machine transitions."""
        state = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            worktree_name="main",
            workflow_status="pending",
        )
        await repository.create(state)

        # Invalid: pending -> completed (must go through in_progress)
        with pytest.raises(InvalidStateTransitionError):
            await repository.set_status(state.id, "completed")

    @pytest.mark.asyncio
    async def test_set_status_with_failure_reason(self, repository):
        """set_status can set failure reason."""
        state = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            worktree_name="main",
            workflow_status="in_progress",
        )
        await repository.create(state)

        await repository.set_status(state.id, "failed", failure_reason="Something went wrong")

        retrieved = await repository.get(state.id)
        assert retrieved.workflow_status == "failed"
        assert retrieved.failure_reason == "Something went wrong"

    @pytest.mark.asyncio
    async def test_list_active_workflows(self, repository):
        """Can list all active workflows."""
        # Create various workflows
        active1 = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-1",
            worktree_path="/repo1",
            worktree_name="main",
            workflow_status="in_progress",
        )
        active2 = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-2",
            worktree_path="/repo2",
            worktree_name="feat",
            workflow_status="blocked",
        )
        completed = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-3",
            worktree_path="/repo3",
            worktree_name="old",
            workflow_status="completed",
        )

        await repository.create(active1)
        await repository.create(active2)
        await repository.create(completed)

        active = await repository.list_active()
        assert len(active) == 2
        ids = {w.id for w in active}
        assert active1.id in ids
        assert active2.id in ids

    # =========================================================================
    # Event Persistence Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_save_event(self, repository):
        """Should persist event to database."""
        # First create a workflow (required for foreign key)
        state = ServerExecutionState(
            id="wf-1",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            worktree_name="feat-123",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="architect",
            event_type=EventType.STAGE_STARTED,
            message="Planning started",
        )

        await repository.save_event(event)

        # Verify in DB via get_max_event_sequence
        max_seq = await repository.get_max_event_sequence("wf-1")
        assert max_seq == 1

    @pytest.mark.asyncio
    async def test_get_max_event_sequence_with_events(self, repository):
        """Should return max sequence number."""
        # First create a workflow
        state = ServerExecutionState(
            id="wf-1",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            worktree_name="feat-123",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        # Create events with sequences 1, 2, 3
        for seq in [1, 2, 3]:
            event = WorkflowEvent(
                id=f"evt-{seq}",
                workflow_id="wf-1",
                sequence=seq,
                timestamp=datetime.now(UTC),
                agent="system",
                event_type=EventType.WORKFLOW_STARTED,
                message=f"Event {seq}",
            )
            await repository.save_event(event)

        max_seq = await repository.get_max_event_sequence("wf-1")
        assert max_seq == 3
