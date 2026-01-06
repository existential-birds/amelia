"""Tests for WorkflowRepository."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from amelia.server.database.repository import WorkflowRepository
from amelia.server.models import EventType
from amelia.server.models.state import InvalidStateTransitionError, ServerExecutionState


class TestWorkflowRepository:
    """Tests for WorkflowRepository CRUD operations."""

    @pytest.fixture
    async def repository(self, db_with_schema):
        """WorkflowRepository instance."""
        return WorkflowRepository(db_with_schema)

    async def test_create_workflow(self, repository) -> None:
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

    async def test_get_by_worktree(self, repository) -> None:
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

    async def test_get_by_worktree_only_active(self, repository) -> None:
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

    async def test_update_workflow(self, repository) -> None:
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

    async def test_set_status_validates_transition(self, repository) -> None:
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

    async def test_set_status_with_failure_reason(self, repository) -> None:
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

    async def test_list_active_workflows(self, repository) -> None:
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

    async def test_save_event(self, repository, make_event) -> None:
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

        event = make_event(
            id="evt-1",
            workflow_id="wf-1",
            timestamp=datetime.now(UTC),
            agent="architect",
            event_type=EventType.STAGE_STARTED,
            message="Planning started",
        )

        await repository.save_event(event)

        # Verify in DB via get_max_event_sequence
        max_seq = await repository.get_max_event_sequence("wf-1")
        assert max_seq == 1

    async def test_get_max_event_sequence_with_events(self, repository, make_event) -> None:
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
            event = make_event(
                id=f"evt-{seq}",
                workflow_id="wf-1",
                sequence=seq,
                timestamp=datetime.now(UTC),
                message=f"Event {seq}",
            )
            await repository.save_event(event)

        max_seq = await repository.get_max_event_sequence("wf-1")
        assert max_seq == 3

    async def test_save_event_with_pydantic_model_in_data(self, repository, make_event) -> None:
        """Should serialize Pydantic models in event data.

        Regression test for: TypeError: Object of type Profile is not JSON serializable
        """
        from amelia.core.types import Profile

        # First create a workflow
        state = ServerExecutionState(
            id="wf-pydantic",
            issue_id="ISSUE-456",
            worktree_path="/path/to/worktree",
            worktree_name="feat-456",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        # Create event with Pydantic model in data
        profile = Profile(name="test", driver="cli:claude", model="sonnet")
        event = make_event(
            id="evt-pydantic",
            workflow_id="wf-pydantic",
            timestamp=datetime.now(UTC),
            agent="architect",
            event_type=EventType.STAGE_COMPLETED,
            message="Stage completed",
            data={
                "stage": "architect_node",
                "output": {
                    "profile": profile,  # Pydantic model, should be serialized
                    "nested": {"another_profile": profile},
                },
            },
        )

        # Should not raise TypeError
        await repository.save_event(event)

        # Verify event was saved
        max_seq = await repository.get_max_event_sequence("wf-pydantic")
        assert max_seq == 1

    async def test_save_event_with_path_in_data(self, repository, make_event) -> None:
        """Should serialize Path objects in event data.

        Regression test for: TypeError: Object of type PosixPath is not JSON serializable
        """
        from pathlib import Path

        # First create a workflow
        state = ServerExecutionState(
            id="wf-path",
            issue_id="ISSUE-789",
            worktree_path="/path/to/worktree",
            worktree_name="feat-789",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        # Create event with Path object in data
        event = make_event(
            id="evt-path",
            workflow_id="wf-path",
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.STAGE_COMPLETED,
            message="Stage completed",
            data={
                "stage": "developer_node",
                "output": {
                    "worktree_path": Path("/foo/bar"),  # PosixPath, should be serialized
                    "nested": {"another_path": Path("/baz/qux")},
                },
            },
        )

        # Should not raise TypeError
        await repository.save_event(event)

        # Verify event was saved
        max_seq = await repository.get_max_event_sequence("wf-path")
        assert max_seq == 1

    async def test_get_recent_events(self, repository, make_event) -> None:
        """Should return recent events for a workflow in chronological order."""
        # Create a workflow
        state = ServerExecutionState(
            id="wf-recent",
            issue_id="ISSUE-789",
            worktree_path="/path/to/worktree",
            worktree_name="feat-789",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        # Create events with sequences 1, 2, 3
        for seq in [1, 2, 3]:
            event = make_event(
                id=f"evt-recent-{seq}",
                workflow_id="wf-recent",
                sequence=seq,
                timestamp=datetime.now(UTC),
                message=f"Event {seq}",
            )
            await repository.save_event(event)

        # Get recent events
        events = await repository.get_recent_events("wf-recent")

        assert len(events) == 3
        # Should be in chronological order (oldest first)
        assert events[0].id == "evt-recent-1"
        assert events[1].id == "evt-recent-2"
        assert events[2].id == "evt-recent-3"

    async def test_get_recent_events_with_limit(self, repository, make_event) -> None:
        """Should respect limit parameter."""
        # Create a workflow
        state = ServerExecutionState(
            id="wf-limited",
            issue_id="ISSUE-LIM",
            worktree_path="/path/to/worktree",
            worktree_name="feat-lim",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        # Create 5 events
        for seq in range(1, 6):
            event = make_event(
                id=f"evt-lim-{seq}",
                workflow_id="wf-limited",
                sequence=seq,
                timestamp=datetime.now(UTC),
                message=f"Event {seq}",
            )
            await repository.save_event(event)

        # Get only 2 most recent events
        events = await repository.get_recent_events("wf-limited", limit=2)

        assert len(events) == 2
        # Should return most recent 2, in chronological order
        assert events[0].id == "evt-lim-4"
        assert events[1].id == "evt-lim-5"

    async def test_get_recent_events_empty(self, repository) -> None:
        """Should return empty list for workflow with no events."""
        # Create a workflow
        state = ServerExecutionState(
            id="wf-empty",
            issue_id="ISSUE-EMPTY",
            worktree_path="/path/to/worktree",
            worktree_name="feat-empty",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        # Get recent events for workflow with no events
        events = await repository.get_recent_events("wf-empty")

        assert len(events) == 0

    @pytest.mark.parametrize("limit", [0, -1, -100])
    async def test_get_recent_events_non_positive_limit(self, repository, limit) -> None:
        """Should return empty list for non-positive limit values."""
        # No need to create workflow - should return early before DB query
        events = await repository.get_recent_events("any-workflow", limit=limit)

        assert events == []
