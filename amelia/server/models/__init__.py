"""Domain models for Amelia server.

Provide Pydantic models for API requests, responses, WebSocket messages,
workflow state, and token usage tracking. Define valid state transitions
and serialization formats for all server data.

Exports:
    EventType: Enum of workflow event types.
    WorkflowEvent: Model for workflow state change events.
    CreateWorkflowRequest: Request model for starting a workflow.
    RejectRequest: Request model for rejecting changes.
    ActionResponse: Generic action success response.
    BatchStartResponse: Response from batch start operation.
    CreateWorkflowResponse: Response model for workflow creation.
    ErrorResponse: Standardized error response model.
    TokenSummary: Aggregated token usage summary.
    WorkflowDetailResponse: Detailed workflow state response.
    WorkflowListResponse: List of workflow summaries.
    WorkflowSummary: Brief workflow state for listings.
    WorkflowStatus: Enum of workflow lifecycle states.
    ServerExecutionState: Full server-side workflow state.
    VALID_TRANSITIONS: Mapping of valid state transitions.
    InvalidStateTransitionError: Invalid state transition attempted.
    validate_transition: Validate a state transition.
    TokenUsage: Per-request token usage record.
    MODEL_PRICING: Token pricing by model.
    calculate_token_cost: Calculate cost from token usage.
    BackfillCompleteMessage: WebSocket backfill complete notification.
    BackfillExpiredMessage: WebSocket backfill expired notification.
    ClientMessage: Union of all client WebSocket message types.
    EventMessage: WebSocket event broadcast message.
    PingMessage: WebSocket ping message.
    PongMessage: WebSocket pong message.
    ServerMessage: Union of all server WebSocket message types.
    SubscribeAllMessage: Subscribe to all workflow events.
    SubscribeMessage: Subscribe to specific workflow events.
    UnsubscribeMessage: Unsubscribe from workflow events.
"""

from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.models.requests import CreateWorkflowRequest, RejectRequest
from amelia.server.models.responses import (
    ActionResponse,
    BatchStartResponse,
    CreateWorkflowResponse,
    ErrorResponse,
    WorkflowDetailResponse,
    WorkflowListResponse,
    WorkflowSummary,
)
from amelia.server.models.state import (
    VALID_TRANSITIONS,
    InvalidStateTransitionError,
    ServerExecutionState,
    WorkflowStatus,
    validate_transition,
)
from amelia.server.models.tokens import (
    MODEL_PRICING,
    TokenSummary,
    TokenUsage,
    calculate_token_cost,
)
from amelia.server.models.websocket import (
    BackfillCompleteMessage,
    BackfillExpiredMessage,
    ClientMessage,
    EventMessage,
    PingMessage,
    PongMessage,
    ServerMessage,
    SubscribeAllMessage,
    SubscribeMessage,
    UnsubscribeMessage,
)


__all__ = [
    # Events
    "EventType",
    "WorkflowEvent",
    # Requests
    "CreateWorkflowRequest",
    "RejectRequest",
    # Responses
    "ActionResponse",
    "BatchStartResponse",
    "CreateWorkflowResponse",
    "ErrorResponse",
    "TokenSummary",
    "WorkflowDetailResponse",
    "WorkflowListResponse",
    "WorkflowSummary",
    # State
    "WorkflowStatus",
    "ServerExecutionState",
    "VALID_TRANSITIONS",
    "InvalidStateTransitionError",
    "validate_transition",
    # Tokens
    "TokenUsage",
    "MODEL_PRICING",
    "calculate_token_cost",
    # WebSocket
    "BackfillCompleteMessage",
    "BackfillExpiredMessage",
    "ClientMessage",
    "EventMessage",
    "PingMessage",
    "PongMessage",
    "ServerMessage",
    "SubscribeAllMessage",
    "SubscribeMessage",
    "UnsubscribeMessage",
]
