# tests/unit/server/events/test_bus.py
"""Unit tests for EventBus pub/sub."""
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from amelia.server.events.bus import EventBus
from amelia.server.models import WorkflowEvent


@pytest.fixture
def event_bus() -> EventBus:
    """Create EventBus instance."""
    return EventBus()


@pytest.fixture
def sample_event(make_event) -> WorkflowEvent:
    """Create sample event."""
    return make_event(
        id="evt-1",
        workflow_id="wf-1",
        timestamp=datetime.now(UTC),
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
