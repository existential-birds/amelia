"""Pydantic models for brainstorming sessions.

These models support the chat-based brainstorming system where users
collaborate with an AI agent to produce design documents.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


SessionStatus = Literal["active", "ready_for_handoff", "completed", "failed"]


class BrainstormingSession(BaseModel):
    """Tracks a brainstorming chat session.

    Attributes:
        id: Unique session identifier (UUID).
        profile_id: Which profile/project this session belongs to.
        driver_session_id: Claude driver session for conversation continuity.
        status: Current session status.
        topic: Optional initial topic for the session.
        created_at: When the session was created.
        updated_at: When the session was last updated.
    """

    id: str
    profile_id: str
    driver_session_id: str | None = None
    status: SessionStatus
    topic: str | None = None
    created_at: datetime
    updated_at: datetime


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

    type: Literal["text", "tool-call", "tool-result", "reasoning"]
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
        created_at: When the message was created.
    """

    id: str
    session_id: str
    sequence: int
    role: Literal["user", "assistant"]
    content: str
    parts: list[MessagePart] | None = None
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
