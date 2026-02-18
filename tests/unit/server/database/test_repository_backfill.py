"""Tests for repository backfill methods."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from amelia.server.models.events import EventType
from amelia.server.models.state import ServerExecutionState


pytestmark = pytest.mark.integration


class TestEventBackfill:
    """Tests for event backfill functionality."""

    async def test_event_exists_true(
        self, repository, workflow, event_factory
    ) -> None:
        """event_exists() returns True when event exists."""
        event_id = uuid4()
        event = event_factory(
            id=event_id,
            workflow_id=workflow.id,
            timestamp=datetime.now(UTC),
            message="Started",
        )
        await repository.save_event(event)

        assert await repository.event_exists(event_id) is True

    async def test_event_exists_false(
        self, repository, workflow
    ) -> None:
        """event_exists() returns False when event does not exist."""
        assert await repository.event_exists(uuid4()) is False

    async def test_get_events_after_returns_newer_events(self, repository, workflow, event_factory) -> None:
        """get_events_after() returns events with sequence > since_event sequence."""
        # Create sequence of events
        event_ids = []
        for i in range(1, 6):
            evt_id = uuid4()
            event_ids.append(evt_id)
            event = event_factory(
                id=evt_id,
                workflow_id=workflow.id,
                sequence=i,
                timestamp=datetime.now(UTC),
                event_type=EventType.STAGE_STARTED,
                message=f"Event {i}",
            )
            await repository.save_event(event)

        # Get events after event 2 (should return events 3, 4, 5)
        newer_events = await repository.get_events_after(event_ids[1])

        assert len(newer_events) == 3
        assert newer_events[0].id == event_ids[2]
        assert newer_events[1].id == event_ids[3]
        assert newer_events[2].id == event_ids[4]

    async def test_get_events_after_filters_by_workflow(self, repository, event_factory) -> None:
        """get_events_after() only returns events from same workflow."""
        # Create two workflows
        wf1 = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-1",
            worktree_path="/tmp/wf1",
            workflow_status="pending",
            started_at=datetime.now(UTC),
        )
        wf2 = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-2",
            worktree_path="/tmp/wf2",
            workflow_status="pending",
            started_at=datetime.now(UTC),
        )

        await repository.create(wf1)
        await repository.create(wf2)

        # Create events for both workflows
        wf1_evt1_id = uuid4()
        wf1_evt2_id = uuid4()
        await repository.save_event(
            event_factory(
                id=wf1_evt1_id,
                workflow_id=wf1.id,
                sequence=1,
                timestamp=datetime.now(UTC),
                event_type=EventType.STAGE_STARTED,
                message="WF1 Event 1",
            )
        )
        await repository.save_event(
            event_factory(
                id=wf1_evt2_id,
                workflow_id=wf1.id,
                sequence=2,
                timestamp=datetime.now(UTC),
                event_type=EventType.STAGE_STARTED,
                message="WF1 Event 2",
            )
        )
        await repository.save_event(
            event_factory(
                id=uuid4(),
                workflow_id=wf2.id,
                sequence=1,
                timestamp=datetime.now(UTC),
                event_type=EventType.STAGE_STARTED,
                message="WF2 Event 1",
            )
        )

        # Get events after wf1_evt1 should only return wf1 events
        newer_events = await repository.get_events_after(wf1_evt1_id)

        assert len(newer_events) == 1
        assert newer_events[0].id == wf1_evt2_id
        assert newer_events[0].workflow_id == wf1.id

    async def test_get_events_after_raises_when_event_not_found(self, repository) -> None:
        """get_events_after() raises ValueError when event doesn't exist."""
        with pytest.raises(ValueError, match="Event .* not found"):
            await repository.get_events_after(uuid4())
