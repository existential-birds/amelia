"""Tests for repository backfill methods."""
from datetime import datetime

import pytest

from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.models.state import ServerExecutionState


@pytest.mark.asyncio
class TestEventBackfill:
    """Tests for event backfill functionality."""

    async def test_event_exists_returns_true_when_exists(self, repository, workflow):
        """event_exists() returns True when event exists."""

        event = WorkflowEvent(
            id="evt-123",
            workflow_id=workflow.id,
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        await repository.save_event(event)

        exists = await repository.event_exists("evt-123")
        assert exists is True

    async def test_event_exists_returns_false_when_not_exists(self, repository):
        """event_exists() returns False when event doesn't exist."""
        exists = await repository.event_exists("evt-nonexistent")
        assert exists is False

    async def test_get_events_after_returns_newer_events(self, repository, workflow):
        """get_events_after() returns events with sequence > since_event sequence."""
        # Create sequence of events
        for i in range(1, 6):
            event = WorkflowEvent(
                id=f"evt-{i}",
                workflow_id=workflow.id,
                sequence=i,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=EventType.STAGE_STARTED,
                message=f"Event {i}",
            )
            await repository.save_event(event)

        # Get events after evt-2 (should return evt-3, evt-4, evt-5)
        newer_events = await repository.get_events_after("evt-2")

        assert len(newer_events) == 3
        assert newer_events[0].id == "evt-3"
        assert newer_events[1].id == "evt-4"
        assert newer_events[2].id == "evt-5"

    async def test_get_events_after_preserves_order(self, repository, workflow):
        """get_events_after() returns events in sequence order."""
        for i in range(1, 11):
            event = WorkflowEvent(
                id=f"evt-{i}",
                workflow_id=workflow.id,
                sequence=i,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=EventType.STAGE_STARTED,
                message=f"Event {i}",
            )
            await repository.save_event(event)

        newer_events = await repository.get_events_after("evt-5")

        # Should be in sequence order
        sequences = [e.sequence for e in newer_events]
        assert sequences == [6, 7, 8, 9, 10]

    async def test_get_events_after_filters_by_workflow(self, repository):
        """get_events_after() only returns events from same workflow."""
        # Create two workflows
        wf1 = ServerExecutionState(
            id="wf-1",
            issue_id="ISSUE-1",
            worktree_path="/tmp/wf1",
            worktree_name="wf1",
            workflow_status="pending",
            started_at=datetime.utcnow(),
        )
        wf2 = ServerExecutionState(
            id="wf-2",
            issue_id="ISSUE-2",
            worktree_path="/tmp/wf2",
            worktree_name="wf2",
            workflow_status="pending",
            started_at=datetime.utcnow(),
        )

        await repository.create(wf1)
        await repository.create(wf2)

        # Events for wf-1
        for i in range(1, 4):
            event = WorkflowEvent(
                id=f"wf1-evt-{i}",
                workflow_id=wf1.id,
                sequence=i,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=EventType.STAGE_STARTED,
                message=f"WF1 Event {i}",
            )
            await repository.save_event(event)

        # Events for wf-2
        for i in range(1, 4):
            event = WorkflowEvent(
                id=f"wf2-evt-{i}",
                workflow_id=wf2.id,
                sequence=i,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=EventType.STAGE_STARTED,
                message=f"WF2 Event {i}",
            )
            await repository.save_event(event)

        # Get events after wf1-evt-1
        newer_events = await repository.get_events_after("wf1-evt-1")

        # Should only return wf-1 events
        assert len(newer_events) == 2
        assert all(e.workflow_id == "wf-1" for e in newer_events)

    async def test_get_events_after_empty_when_latest_event(self, repository, workflow):
        """get_events_after() returns empty list when given latest event."""
        event = WorkflowEvent(
            id="evt-1",
            workflow_id=workflow.id,
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        await repository.save_event(event)

        newer_events = await repository.get_events_after("evt-1")
        assert len(newer_events) == 0

    async def test_get_events_after_raises_when_event_not_found(self, repository):
        """get_events_after() raises ValueError when event doesn't exist."""
        with pytest.raises(ValueError, match="Event .* not found"):
            await repository.get_events_after("evt-nonexistent")
