"""Tests for repository backfill methods."""
from datetime import UTC, datetime

import pytest

from amelia.server.models.events import EventType
from amelia.server.models.state import ServerExecutionState


class TestEventBackfill:
    """Tests for event backfill functionality."""

    @pytest.mark.parametrize(
        "event_id,should_exist,setup_event",
        [
            ("evt-123", True, True),
            ("evt-nonexistent", False, False),
        ],
        ids=["exists", "not_exists"],
    )
    async def test_event_exists(
        self, repository, workflow, event_id, should_exist, setup_event, make_event
    ) -> None:
        """event_exists() returns correct boolean based on existence."""
        if setup_event:
            event = make_event(
                id=event_id,
                workflow_id=workflow.id,
                timestamp=datetime.now(UTC),
                message="Started",
            )
            await repository.save_event(event)

        assert await repository.event_exists(event_id) == should_exist

    async def test_get_events_after_returns_newer_events(self, repository, workflow, make_event) -> None:
        """get_events_after() returns events with sequence > since_event sequence."""
        # Create sequence of events
        for i in range(1, 6):
            event = make_event(
                id=f"evt-{i}",
                workflow_id=workflow.id,
                sequence=i,
                timestamp=datetime.now(UTC),
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

    async def test_get_events_after_filters_by_workflow(self, repository, make_event) -> None:
        """get_events_after() only returns events from same workflow."""
        # Create two workflows
        wf1 = ServerExecutionState(
            id="wf-1",
            issue_id="ISSUE-1",
            worktree_path="/tmp/wf1",
            worktree_name="wf1",
            workflow_status="pending",
            started_at=datetime.now(UTC),
        )
        wf2 = ServerExecutionState(
            id="wf-2",
            issue_id="ISSUE-2",
            worktree_path="/tmp/wf2",
            worktree_name="wf2",
            workflow_status="pending",
            started_at=datetime.now(UTC),
        )

        await repository.create(wf1)
        await repository.create(wf2)

        # Create events for both workflows
        await repository.save_event(
            make_event(
                id="wf1-evt-1",
                workflow_id=wf1.id,
                sequence=1,
                timestamp=datetime.now(UTC),
                event_type=EventType.STAGE_STARTED,
                message="WF1 Event 1",
            )
        )
        await repository.save_event(
            make_event(
                id="wf1-evt-2",
                workflow_id=wf1.id,
                sequence=2,
                timestamp=datetime.now(UTC),
                event_type=EventType.STAGE_STARTED,
                message="WF1 Event 2",
            )
        )
        await repository.save_event(
            make_event(
                id="wf2-evt-1",
                workflow_id=wf2.id,
                sequence=1,
                timestamp=datetime.now(UTC),
                event_type=EventType.STAGE_STARTED,
                message="WF2 Event 1",
            )
        )

        # Get events after wf1-evt-1 should only return wf-1 events
        newer_events = await repository.get_events_after("wf1-evt-1")

        assert len(newer_events) == 1
        assert newer_events[0].id == "wf1-evt-2"
        assert newer_events[0].workflow_id == "wf-1"

    async def test_get_events_after_raises_when_event_not_found(self, repository) -> None:
        """get_events_after() raises ValueError when event doesn't exist."""
        with pytest.raises(ValueError, match="Event .* not found"):
            await repository.get_events_after("evt-nonexistent")
