# tests/unit/server/events/test_bus.py
"""Unit tests for EventBus pub/sub."""
from datetime import UTC, datetime

import pytest

from amelia.server.events.bus import EventBus
from amelia.server.models import EventType, WorkflowEvent


@pytest.fixture
def event_bus() -> EventBus:
    """Create EventBus instance."""
    return EventBus()


@pytest.fixture
def sample_event() -> WorkflowEvent:
    """Create sample event."""
    return WorkflowEvent(
        id="evt-1",
        workflow_id="wf-1",
        sequence=1,
        timestamp=datetime.now(UTC),
        agent="system",
        event_type=EventType.WORKFLOW_STARTED,
        message="Workflow started",
    )


def test_eventbus_creation(event_bus: EventBus):
    """EventBus should be created with no subscribers."""
    assert event_bus._subscribers == []


def test_subscribe(event_bus: EventBus):
    """Should allow subscribing with a callback."""
    def callback(event: WorkflowEvent) -> None:
        pass

    event_bus.subscribe(callback)
    assert len(event_bus._subscribers) == 1
    assert event_bus._subscribers[0] == callback


def test_unsubscribe(event_bus: EventBus):
    """Should allow unsubscribing a callback."""
    def callback(event: WorkflowEvent) -> None:
        pass

    event_bus.subscribe(callback)
    event_bus.unsubscribe(callback)
    assert len(event_bus._subscribers) == 0


def test_unsubscribe_nonexistent(event_bus: EventBus):
    """Unsubscribe nonexistent callback should be no-op."""
    def callback(event: WorkflowEvent) -> None:
        pass

    # Should not raise
    event_bus.unsubscribe(callback)
    assert len(event_bus._subscribers) == 0


def test_emit_single_subscriber(event_bus: EventBus, sample_event: WorkflowEvent):
    """Emit should call all subscribers."""
    received = []

    def callback(event: WorkflowEvent) -> None:
        received.append(event)

    event_bus.subscribe(callback)
    event_bus.emit(sample_event)

    assert len(received) == 1
    assert received[0] == sample_event


def test_emit_multiple_subscribers(event_bus: EventBus, sample_event: WorkflowEvent):
    """Emit should call all subscribers."""
    received1 = []
    received2 = []

    def callback1(event: WorkflowEvent) -> None:
        received1.append(event)

    def callback2(event: WorkflowEvent) -> None:
        received2.append(event)

    event_bus.subscribe(callback1)
    event_bus.subscribe(callback2)
    event_bus.emit(sample_event)

    assert len(received1) == 1
    assert len(received2) == 1
    assert received1[0] == sample_event
    assert received2[0] == sample_event


def test_emit_no_subscribers(event_bus: EventBus, sample_event: WorkflowEvent):
    """Emit with no subscribers should not raise."""
    event_bus.emit(sample_event)  # Should not raise


def test_emit_subscriber_exception(event_bus: EventBus, sample_event: WorkflowEvent):
    """Exception in one subscriber should not affect others."""
    received = []

    def failing_callback(event: WorkflowEvent) -> None:
        raise RuntimeError("Test error")

    def successful_callback(event: WorkflowEvent) -> None:
        received.append(event)

    event_bus.subscribe(failing_callback)
    event_bus.subscribe(successful_callback)

    # Emit should log error but continue
    event_bus.emit(sample_event)

    # Second subscriber should still receive event
    assert len(received) == 1
    assert received[0] == sample_event


def test_multiple_events(event_bus: EventBus):
    """Should handle multiple events in sequence."""
    received = []

    def callback(event: WorkflowEvent) -> None:
        received.append(event)

    event_bus.subscribe(callback)

    event1 = WorkflowEvent(
        id="evt-1", workflow_id="wf-1", sequence=1,
        timestamp=datetime.now(UTC), agent="system",
        event_type=EventType.WORKFLOW_STARTED, message="Started",
    )
    event2 = WorkflowEvent(
        id="evt-2", workflow_id="wf-1", sequence=2,
        timestamp=datetime.now(UTC), agent="architect",
        event_type=EventType.STAGE_STARTED, message="Planning",
    )

    event_bus.emit(event1)
    event_bus.emit(event2)

    assert len(received) == 2
    assert received[0] == event1
    assert received[1] == event2
