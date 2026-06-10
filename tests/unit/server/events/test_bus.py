# tests/unit/server/events/test_bus.py
"""Unit tests for EventBus pub/sub."""
import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from amelia.server.events.bus import EventBus
from amelia.server.models import WorkflowEvent


@pytest.fixture
def sample_event(event_factory: Callable[..., WorkflowEvent]) -> WorkflowEvent:
    """Create sample event."""
    return event_factory(
        id=uuid4(),
        workflow_id=uuid4(),
        timestamp=datetime.now(UTC),
        message="Workflow started",
    )


def test_unsubscribe(event_bus: EventBus, sample_event: WorkflowEvent) -> None:
    """Unsubscribed callback should not receive events."""
    received = []

    def callback(event: WorkflowEvent) -> None:
        received.append(event)

    event_bus.subscribe(callback)
    event_bus.unsubscribe(callback)
    event_bus.emit(sample_event)

    assert received == []


def test_emit_single_subscriber(event_bus: EventBus, sample_event: WorkflowEvent) -> None:
    """Emit should call all subscribers."""
    received = []

    def callback(event: WorkflowEvent) -> None:
        received.append(event)

    event_bus.subscribe(callback)
    event_bus.emit(sample_event)

    assert len(received) == 1
    assert received[0] == sample_event


def test_emit_multiple_subscribers(event_bus: EventBus, sample_event: WorkflowEvent) -> None:
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


def test_emit_subscriber_exception(event_bus: EventBus, sample_event: WorkflowEvent) -> None:
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


async def test_broadcast_task_tracking(event_bus: EventBus, sample_event: WorkflowEvent) -> None:
    """Broadcast tasks should be tracked and cleaned up."""
    broadcast_called = asyncio.Event()

    # Create mock connection manager
    mock_manager = AsyncMock()

    async def mock_broadcast(event: WorkflowEvent) -> None:
        broadcast_called.set()

    mock_manager.broadcast = mock_broadcast
    event_bus.set_connection_manager(mock_manager)

    # Emit event - should create a background task
    event_bus.emit(sample_event)

    # Wait for broadcast with timeout instead of arbitrary sleep
    await asyncio.wait_for(broadcast_called.wait(), timeout=1.0)

    # If we get here, broadcast was called with the event


async def test_cleanup_waits_for_broadcast_tasks(event_bus: EventBus, sample_event: WorkflowEvent) -> None:
    """cleanup() should wait for all broadcast tasks to complete."""
    # Create mock connection manager with slow broadcast
    mock_manager = AsyncMock()
    broadcast_completed = False

    async def slow_broadcast(event: WorkflowEvent) -> None:
        nonlocal broadcast_completed
        await asyncio.sleep(0.1)
        broadcast_completed = True

    mock_manager.broadcast = slow_broadcast
    event_bus.set_connection_manager(mock_manager)

    # Emit event
    event_bus.emit(sample_event)

    # Cleanup should wait for broadcast to complete
    await event_bus.cleanup()

    # Broadcast should have completed
    assert broadcast_completed

    # Task set should be cleared
    assert len(event_bus._broadcast_tasks) == 0


def test_ring_buffer_returns_events_after_id(event_factory: Callable[..., WorkflowEvent]) -> None:
    """events_after returns the buffered suffix; evicted ids yield empty."""
    bus = EventBus(buffer_size=3)
    e1, e2, e3, e4 = [event_factory(id=uuid4(), sequence=i) for i in range(1, 5)]
    for e in (e1, e2, e3, e4):
        bus.emit(e)

    assert [e.id for e in bus.events_after(e2.id)] == [e3.id, e4.id]
    # e1 was evicted (maxlen=3) → unknown id → empty, client falls back to full reload
    assert bus.events_after(e1.id) == []


def test_events_after_unknown_id_returns_empty(
    event_bus: EventBus, sample_event: WorkflowEvent
) -> None:
    """An id that was never emitted yields an empty backfill."""
    event_bus.emit(sample_event)

    assert event_bus.events_after(uuid4()) == []


def test_events_after_latest_id_returns_empty(
    event_bus: EventBus, event_factory: Callable[..., WorkflowEvent]
) -> None:
    """No events after the most recent one."""
    e1 = event_factory(id=uuid4(), sequence=1)
    e2 = event_factory(id=uuid4(), sequence=2)
    event_bus.emit(e1)
    event_bus.emit(e2)

    assert event_bus.events_after(e2.id) == []


def test_default_buffer_holds_last_1000_events(
    event_factory: Callable[..., WorkflowEvent],
) -> None:
    """Default buffer keeps exactly the last 1000 events."""
    bus = EventBus()
    events = [event_factory(id=uuid4(), sequence=i) for i in range(1, 1003)]
    for e in events:
        bus.emit(e)

    # First two evicted: 1002 emitted, 1000 kept
    assert bus.events_after(events[0].id) == []
    assert bus.events_after(events[1].id) == []
    # events[2] is the oldest buffered entry → 999 follow it
    assert len(bus.events_after(events[2].id)) == 999


async def test_cleanup_handles_task_exceptions(event_bus: EventBus, sample_event: WorkflowEvent) -> None:
    """cleanup() should handle exceptions in broadcast tasks gracefully."""
    # Create mock connection manager that raises
    mock_manager = AsyncMock()

    async def failing_broadcast(event: WorkflowEvent) -> None:
        raise RuntimeError("Broadcast failed")

    mock_manager.broadcast = failing_broadcast
    event_bus.set_connection_manager(mock_manager)

    # Emit event
    event_bus.emit(sample_event)

    # Cleanup should not raise even though broadcast failed
    await event_bus.cleanup()

    # Task set should be cleared
    assert len(event_bus._broadcast_tasks) == 0


