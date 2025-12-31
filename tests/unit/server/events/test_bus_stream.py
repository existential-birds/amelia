"""Tests for EventBus stream event handling."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from amelia.core.types import StreamEvent, StreamEventType
from amelia.server.events.bus import EventBus
from amelia.server.models.events import WorkflowEvent


@pytest.fixture
def event_bus() -> EventBus:
    """Create EventBus instance."""
    return EventBus()


async def test_emit_stream_broadcasts_to_connection_manager(
    event_bus: EventBus, sample_stream_event: StreamEvent
):
    """emit_stream() should call connection_manager.broadcast_stream()."""
    # Create mock connection manager
    mock_manager = AsyncMock()
    mock_manager.broadcast_stream = AsyncMock()
    event_bus.set_connection_manager(mock_manager)

    # Emit stream event
    event_bus.emit_stream(sample_stream_event)

    # Wait for background tasks to complete
    await event_bus.cleanup()

    # Verify broadcast was called with exact event
    mock_manager.broadcast_stream.assert_awaited_once_with(sample_stream_event)


async def test_emit_stream_does_not_call_subscribers(
    event_bus: EventBus, sample_stream_event: StreamEvent
):
    """emit_stream() should NOT call regular WorkflowEvent subscribers."""
    subscriber_called = False

    def subscriber(event: WorkflowEvent) -> None:
        nonlocal subscriber_called
        subscriber_called = True

    event_bus.subscribe(subscriber)

    # Create mock connection manager
    mock_manager = AsyncMock()
    mock_manager.broadcast_stream = AsyncMock()
    event_bus.set_connection_manager(mock_manager)

    # Emit stream event
    event_bus.emit_stream(sample_stream_event)

    # Wait for all pending broadcast tasks to complete
    await event_bus.cleanup()

    # Regular subscribers should NOT be called for stream events
    assert not subscriber_called


async def test_emit_stream_tracks_broadcast_tasks(
    event_bus: EventBus, sample_stream_event: StreamEvent
):
    """emit_stream() should track broadcast tasks for cleanup."""
    # Create mock connection manager with slow broadcast
    mock_manager = AsyncMock()
    broadcast_started = asyncio.Event()

    async def slow_broadcast_stream(event: StreamEvent) -> None:
        broadcast_started.set()
        await asyncio.sleep(0.1)

    mock_manager.broadcast_stream = slow_broadcast_stream
    event_bus.set_connection_manager(mock_manager)

    # Emit stream event
    event_bus.emit_stream(sample_stream_event)

    # Wait for broadcast to start
    await asyncio.wait_for(broadcast_started.wait(), timeout=1.0)

    # Task should be tracked
    assert len(event_bus._broadcast_tasks) > 0

    # Clean up background task to prevent leaking into other tests
    await asyncio.wait_for(event_bus.cleanup(), timeout=1.0)


async def test_emit_stream_without_connection_manager(
    event_bus: EventBus, sample_stream_event: StreamEvent
):
    """emit_stream() should not raise when connection_manager is None."""
    # No connection manager set
    assert event_bus._connection_manager is None

    # Should not raise
    event_bus.emit_stream(sample_stream_event)

    # No tasks should be created
    assert len(event_bus._broadcast_tasks) == 0


async def test_emit_stream_cleanup_waits_for_tasks(
    event_bus: EventBus, sample_stream_event: StreamEvent
):
    """cleanup() should wait for stream broadcast tasks to complete."""
    # Create mock connection manager with slow broadcast
    mock_manager = AsyncMock()
    broadcast_completed = False

    async def slow_broadcast_stream(event: StreamEvent) -> None:
        nonlocal broadcast_completed
        await asyncio.sleep(0.1)
        broadcast_completed = True

    mock_manager.broadcast_stream = slow_broadcast_stream
    event_bus.set_connection_manager(mock_manager)

    # Emit stream event
    event_bus.emit_stream(sample_stream_event)

    # Cleanup should wait for broadcast to complete
    await event_bus.cleanup()

    # Broadcast should have completed
    assert broadcast_completed

    # Task set should be cleared
    assert len(event_bus._broadcast_tasks) == 0


async def test_emit_stream_handles_broadcast_exception(
    event_bus: EventBus, sample_stream_event: StreamEvent
):
    """emit_stream() should handle broadcast exceptions gracefully."""
    # Create mock connection manager that raises
    mock_manager = AsyncMock()

    async def failing_broadcast_stream(event: StreamEvent) -> None:
        raise RuntimeError("Broadcast failed")

    mock_manager.broadcast_stream = failing_broadcast_stream
    event_bus.set_connection_manager(mock_manager)

    # Emit stream event - should not raise
    event_bus.emit_stream(sample_stream_event)

    # Cleanup should complete without raising despite the broadcast exception
    await event_bus.cleanup()

    # Task tracking should be cleared (exception handled internally)
    assert len(event_bus._broadcast_tasks) == 0


async def test_emit_stream_multiple_events(
    event_bus: EventBus, sample_stream_event: StreamEvent
):
    """emit_stream() should handle multiple stream events correctly."""
    mock_manager = AsyncMock()
    mock_manager.broadcast_stream = AsyncMock()
    event_bus.set_connection_manager(mock_manager)

    # Emit multiple stream events
    event1 = StreamEvent(
        type=StreamEventType.CLAUDE_THINKING,
        content="Event 1",
        timestamp=datetime.now(UTC),
        agent="developer",
        workflow_id="wf-123",
    )
    event2 = StreamEvent(
        type=StreamEventType.CLAUDE_TOOL_CALL,
        content="Event 2",
        timestamp=datetime.now(UTC),
        agent="developer",
        workflow_id="wf-123",
        tool_name="read_file",
    )
    event3 = StreamEvent(
        type=StreamEventType.AGENT_OUTPUT,
        content="Event 3",
        timestamp=datetime.now(UTC),
        agent="developer",
        workflow_id="wf-123",
    )

    event_bus.emit_stream(event1)
    event_bus.emit_stream(event2)
    event_bus.emit_stream(event3)

    # Wait for all broadcasts to complete
    await event_bus.cleanup()

    # Verify all three events were broadcast with correct payloads
    assert mock_manager.broadcast_stream.await_count == 3
    call_args = [call.args[0] for call in mock_manager.broadcast_stream.await_args_list]
    assert event1 in call_args
    assert event2 in call_args
    assert event3 in call_args
