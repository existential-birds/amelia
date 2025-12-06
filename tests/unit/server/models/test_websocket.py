# tests/unit/server/models/test_websocket.py
"""Tests for WebSocket protocol message models."""
import pytest
from datetime import datetime


class TestClientMessages:
    """Tests for client-to-server message models."""

    def test_subscribe_message(self):
        """Subscribe message has workflow_id."""
        from amelia.server.models.websocket import SubscribeMessage

        msg = SubscribeMessage(workflow_id="wf-123")

        assert msg.type == "subscribe"
        assert msg.workflow_id == "wf-123"

    def test_unsubscribe_message(self):
        """Unsubscribe message has workflow_id."""
        from amelia.server.models.websocket import UnsubscribeMessage

        msg = UnsubscribeMessage(workflow_id="wf-456")

        assert msg.type == "unsubscribe"
        assert msg.workflow_id == "wf-456"

    def test_subscribe_all_message(self):
        """Subscribe all message has no workflow_id."""
        from amelia.server.models.websocket import SubscribeAllMessage

        msg = SubscribeAllMessage()

        assert msg.type == "subscribe_all"

    def test_pong_message(self):
        """Pong message is heartbeat response."""
        from amelia.server.models.websocket import PongMessage

        msg = PongMessage()

        assert msg.type == "pong"

    def test_client_message_serialization(self):
        """Client messages serialize to JSON correctly."""
        from amelia.server.models.websocket import SubscribeMessage

        msg = SubscribeMessage(workflow_id="wf-123")
        json_data = msg.model_dump()

        assert json_data["type"] == "subscribe"
        assert json_data["workflow_id"] == "wf-123"


class TestServerMessages:
    """Tests for server-to-client message models."""

    def test_event_message(self):
        """Event message wraps WorkflowEvent."""
        from amelia.server.models.websocket import EventMessage
        from amelia.server.models.events import WorkflowEvent, EventType

        event = WorkflowEvent(
            id="evt-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        msg = EventMessage(payload=event)

        assert msg.type == "event"
        assert msg.payload.id == "evt-123"
        assert msg.payload.workflow_id == "wf-456"

    def test_ping_message(self):
        """Ping message is heartbeat."""
        from amelia.server.models.websocket import PingMessage

        msg = PingMessage()

        assert msg.type == "ping"

    def test_backfill_complete_message(self):
        """Backfill complete includes event count."""
        from amelia.server.models.websocket import BackfillCompleteMessage

        msg = BackfillCompleteMessage(count=15)

        assert msg.type == "backfill_complete"
        assert msg.count == 15

    def test_backfill_expired_message(self):
        """Backfill expired includes error message."""
        from amelia.server.models.websocket import BackfillExpiredMessage

        msg = BackfillExpiredMessage(
            message="Requested event no longer exists. Full refresh required."
        )

        assert msg.type == "backfill_expired"
        assert "no longer exists" in msg.message

    def test_server_message_serialization(self):
        """Server messages serialize to JSON correctly."""
        from amelia.server.models.websocket import PingMessage

        msg = PingMessage()
        json_data = msg.model_dump()

        assert json_data["type"] == "ping"
