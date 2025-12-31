# amelia/server/models/websocket.py
"""WebSocket protocol message models."""
from typing import Literal

from pydantic import BaseModel, Field

from amelia.server.models.events import WorkflowEvent


# Client -> Server Messages


class SubscribeMessage(BaseModel):
    """Subscribe to specific workflow events."""

    type: Literal["subscribe"] = "subscribe"
    workflow_id: str = Field(..., description="Workflow to subscribe to")


class UnsubscribeMessage(BaseModel):
    """Unsubscribe from specific workflow events."""

    type: Literal["unsubscribe"] = "unsubscribe"
    workflow_id: str = Field(..., description="Workflow to unsubscribe from")


class SubscribeAllMessage(BaseModel):
    """Subscribe to all workflow events."""

    type: Literal["subscribe_all"] = "subscribe_all"


class PongMessage(BaseModel):
    """Heartbeat response from client."""

    type: Literal["pong"] = "pong"


# Union type for all client messages
ClientMessage = SubscribeMessage | UnsubscribeMessage | SubscribeAllMessage | PongMessage


# Server -> Client Messages


class EventMessage(BaseModel):
    """Event broadcast to client."""

    type: Literal["event"] = "event"
    payload: WorkflowEvent = Field(..., description="The workflow event")


class PingMessage(BaseModel):
    """Heartbeat ping from server."""

    type: Literal["ping"] = "ping"


class BackfillCompleteMessage(BaseModel):
    """Sent after reconnect backfill completes."""

    type: Literal["backfill_complete"] = "backfill_complete"
    count: int = Field(..., description="Number of events backfilled")


class BackfillExpiredMessage(BaseModel):
    """Sent when requested backfill event no longer exists."""

    type: Literal["backfill_expired"] = "backfill_expired"
    message: str = Field(
        ...,
        description="Error message explaining the event was cleaned up",
    )


# Union type for all server messages
ServerMessage = EventMessage | PingMessage | BackfillCompleteMessage | BackfillExpiredMessage
