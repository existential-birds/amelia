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


def test_unsubscribe(event_bus: EventBus, sample_event: WorkflowEvent):
    """Unsubscribed callback should not receive events."""
    received = []

    def callback(event: WorkflowEvent) -> None:
        received.append(event)

    event_bus.subscribe(callback)
    event_bus.unsubscribe(callback)
    event_bus.emit(sample_event)

    assert received == []


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
