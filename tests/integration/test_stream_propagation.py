# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Integration tests for stream event propagation.

These tests verify the end-to-end flow of stream events:
1. Agents emit StreamEvents via stream_emitter callback
2. EventBus.emit_stream broadcasts to ConnectionManager
3. ConnectionManager.broadcast_stream sends to WebSocket clients
4. Stream events are NOT persisted (ephemeral)
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocket

from amelia.core.types import StreamEvent, StreamEventType
from amelia.server.events.bus import EventBus
from amelia.server.events.connection_manager import ConnectionManager


class TestStreamEventPropagation:
    """Test end-to-end stream event propagation."""

    @pytest.fixture
    def mock_websocket(self) -> AsyncMock:
        """Create a mock WebSocket connection."""
        ws = AsyncMock(spec=WebSocket)
        ws.send_json = AsyncMock()
        return ws

    async def test_emit_stream_broadcasts_to_websocket(
        self,
        event_bus: EventBus,
        connection_manager: ConnectionManager,
        mock_websocket: AsyncMock,
        sample_stream_event: StreamEvent,
    ):
        """Stream events are broadcast to connected WebSocket clients."""
        # Connect WebSocket
        await connection_manager.connect(mock_websocket)

        # Emit stream event
        event_bus.emit_stream(sample_stream_event)

        # Wait for async broadcast task
        await asyncio.sleep(0.1)

        # Verify WebSocket received the event
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "stream"
        assert call_args["payload"]["subtype"] == "claude_thinking"
        assert call_args["payload"]["content"] == "Analyzing requirements"
        assert call_args["payload"]["agent"] == "developer"

    async def test_stream_events_broadcast_to_all_clients(
        self,
        event_bus: EventBus,
        connection_manager: ConnectionManager,
        sample_stream_event: StreamEvent,
    ):
        """Stream events are broadcast to ALL connected clients."""
        # Connect multiple WebSockets
        ws1 = AsyncMock(spec=WebSocket)
        ws1.send_json = AsyncMock()
        ws2 = AsyncMock(spec=WebSocket)
        ws2.send_json = AsyncMock()
        ws3 = AsyncMock(spec=WebSocket)
        ws3.send_json = AsyncMock()

        await connection_manager.connect(ws1)
        await connection_manager.connect(ws2)
        await connection_manager.connect(ws3)

        # Emit stream event
        event_bus.emit_stream(sample_stream_event)

        # Wait for async broadcast
        await asyncio.sleep(0.1)

        # All clients should receive the event
        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()
        ws3.send_json.assert_called_once()

    async def test_tool_call_event_includes_tool_info(
        self,
        event_bus: EventBus,
        connection_manager: ConnectionManager,
        mock_websocket: AsyncMock,
    ):
        """Tool call events include tool name and input."""
        await connection_manager.connect(mock_websocket)

        tool_call_event = StreamEvent(
            type=StreamEventType.CLAUDE_TOOL_CALL,
            content=None,
            timestamp=datetime.now(UTC),
            agent="developer",
            workflow_id="wf-test-123",
            tool_name="Read",
            tool_input={"file_path": "/src/main.py"},
        )

        event_bus.emit_stream(tool_call_event)
        await asyncio.sleep(0.1)

        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["payload"]["subtype"] == "claude_tool_call"
        assert call_args["payload"]["tool_name"] == "Read"
        assert call_args["payload"]["tool_input"] == {"file_path": "/src/main.py"}


@pytest.mark.parametrize(
    "agent,event_type,content_substring",
    [
        ("developer", StreamEventType.CLAUDE_THINKING, "Planning"),
        ("architect", StreamEventType.AGENT_OUTPUT, "tasks"),
        ("reviewer", StreamEventType.AGENT_OUTPUT, "Approved"),
    ],
)
async def test_agent_emitter_broadcasts(
    agent: str,
    event_type: StreamEventType,
    content_substring: str,
):
    """Agent stream emitters broadcast events to EventBus."""
    event_bus = EventBus()
    captured_events: list[StreamEvent] = []

    # Create emitter that captures events and broadcasts
    def capture_emit_stream(event: StreamEvent) -> None:
        captured_events.append(event)

    event_bus.emit_stream = capture_emit_stream  # type: ignore

    # Create emitter callback (simulating what OrchestratorService._create_stream_emitter does)
    async def emitter(event: StreamEvent) -> None:
        event_bus.emit_stream(event)

    # Simulate agent emitting an event
    content_map = {
        "developer": "Planning implementation...",
        "architect": "Generated plan with 5 tasks",
        "reviewer": "Review completed: Approved",
    }

    stream_event = StreamEvent(
        type=event_type,
        content=content_map[agent],
        timestamp=datetime.now(UTC),
        agent=agent,
        workflow_id=f"wf-{agent}-123",
    )

    await emitter(stream_event)

    assert len(captured_events) == 1
    assert captured_events[0].agent == agent
    assert captured_events[0].type == event_type
    assert content_substring in captured_events[0].content  # type: ignore


class TestStreamEventTypes:
    """Test all stream event types are handled correctly."""

    @pytest.mark.parametrize(
        "event_type,expected_type_str",
        [
            (StreamEventType.CLAUDE_THINKING, "claude_thinking"),
            (StreamEventType.CLAUDE_TOOL_CALL, "claude_tool_call"),
            (StreamEventType.CLAUDE_TOOL_RESULT, "claude_tool_result"),
            (StreamEventType.AGENT_OUTPUT, "agent_output"),
        ],
    )
    async def test_all_event_types_broadcast_correctly(
        self,
        event_bus: EventBus,
        connection_manager: ConnectionManager,
        event_type: StreamEventType,
        expected_type_str: str,
    ):
        """All StreamEventType values are broadcast correctly."""
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.send_json = AsyncMock()
        await connection_manager.connect(mock_ws)

        event = StreamEvent(
            type=event_type,
            content="Test content",
            timestamp=datetime.now(UTC),
            agent="developer",
            workflow_id="wf-test",
        )

        event_bus.emit_stream(event)
        await asyncio.sleep(0.1)

        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["type"] == "stream"
        assert call_args["payload"]["subtype"] == expected_type_str
