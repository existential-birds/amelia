"""Pydantic models for brainstorming sessions.

These models support the chat-based brainstorming system where users
collaborate with an AI agent to produce design documents.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class SessionStatus(StrEnum):
    """Status for brainstorming sessions."""

    ACTIVE = "active"
    READY_FOR_HANDOFF = "ready_for_handoff"
    COMPLETED = "completed"
    FAILED = "failed"


class MessagePartType(StrEnum):
    """Type of message part in AI SDK UIMessage format."""

    TEXT = "text"
    TOOL_CALL = "tool-call"
    TOOL_RESULT = "tool-result"
    REASONING = "reasoning"


class MessageRole(StrEnum):
    """Role of message sender."""

    USER = "user"
    ASSISTANT = "assistant"


class MessageUsage(BaseModel):
    """Token usage for a single brainstorm message.

    Attributes:
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens generated.
        cost_usd: Calculated cost in USD.
    """

    input_tokens: int
    output_tokens: int
    cost_usd: float


class SessionUsageSummary(BaseModel):
    """Aggregated token usage for a brainstorm session.

    Attributes:
        total_input_tokens: Sum of input tokens across all messages.
        total_output_tokens: Sum of output tokens across all messages.
        total_cost_usd: Sum of costs across all messages.
        message_count: Number of messages with usage data.
    """

    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    message_count: int


class BrainstormingSession(BaseModel):
    """Tracks a brainstorming chat session.

    Attributes:
        id: Unique session identifier (UUID).
        profile_id: Which profile/project this session belongs to.
        driver_session_id: Claude driver session for conversation continuity.
        driver_type: Type of driver used for the session ('cli' or 'api').
        status: Current session status.
        topic: Optional initial topic for the session.
        created_at: When the session was created.
        updated_at: When the session was last updated.
        usage_summary: Aggregated token usage for the session.
    """

    id: str
    profile_id: str
    driver_session_id: str | None = None
    driver_type: str | None = None
    status: SessionStatus
    topic: str | None = None
    created_at: datetime
    updated_at: datetime
    usage_summary: SessionUsageSummary | None = None


class MessagePart(BaseModel):
    """Single part of a message (AI SDK UIMessage compatible).

    Supports text, tool calls, tool results, and reasoning blocks.

    Attributes:
        type: Type of message part.
        text: Text content (for text and reasoning types).
        tool_call_id: Unique ID for tool call/result correlation.
        tool_name: Name of the tool being called.
        args: Arguments passed to the tool.
        result: Result returned from tool execution.
    """

    type: MessagePartType
    text: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    args: dict[str, Any] | None = None
    result: str | None = None


class Message(BaseModel):
    """Single message in a brainstorming session (AI SDK UIMessage compatible).

    Attributes:
        id: Unique message identifier.
        session_id: Session this message belongs to.
        sequence: Order of message within session (1-based).
        role: Who sent the message (user or assistant).
        content: Text content of the message.
        parts: Optional structured parts (tool calls, reasoning, etc.).
        usage: Optional token usage for this message (assistant messages only).
        is_system: Whether this is a system/priming message (not user-authored).
        created_at: When the message was created.
    """

    id: str
    session_id: str
    sequence: int
    role: MessageRole
    content: str
    parts: list[MessagePart] | None = None
    usage: MessageUsage | None = None
    is_system: bool = False
    created_at: datetime


class Artifact(BaseModel):
    """Document produced by a brainstorming session.

    Attributes:
        id: Unique artifact identifier.
        session_id: Session that produced this artifact.
        type: Type of artifact (design, adr, spec, readme, etc.).
        path: File path where artifact is saved.
        title: Optional human-readable title.
        created_at: When the artifact was created.
    """

    id: str
    session_id: str
    type: str
    path: str
    title: str | None = None
    created_at: datetime
