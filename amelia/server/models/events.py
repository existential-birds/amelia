"""Event models for workflow activity tracking."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventDomain(StrEnum):
    """Domain of event origin.

    Attributes:
        WORKFLOW: Standard workflow events (orchestrator, agents).
        BRAINSTORM: Brainstorming session events (chat streaming).
        ORACLE: Oracle consultation events.
    """

    WORKFLOW = "workflow"
    BRAINSTORM = "brainstorm"
    ORACLE = "oracle"


class EventLevel(StrEnum):
    """Event severity level for filtering and retention.

    Attributes:
        INFO: High-level workflow events (lifecycle, stages, approvals).
        DEBUG: Operational details (tasks, files, messages).
        TRACE: Verbose execution trace (thinking, tool calls).
    """

    INFO = "info"
    DEBUG = "debug"
    TRACE = "trace"


class EventType(StrEnum):
    """Exhaustive list of workflow event types.

    Events are categorized into lifecycle, stage, approval, artifact,
    review, agent message, and system event types.

    Attributes:
        WORKFLOW_STARTED: Workflow execution has begun.
        WORKFLOW_COMPLETED: Workflow finished successfully.
        WORKFLOW_FAILED: Workflow terminated due to error.
        WORKFLOW_CANCELLED: Workflow was cancelled by user.
        STAGE_STARTED: A workflow stage has begun.
        STAGE_COMPLETED: A workflow stage has finished.
        APPROVAL_REQUIRED: Human approval is needed to proceed.
        APPROVAL_GRANTED: Human approved the pending action.
        APPROVAL_REJECTED: Human rejected the pending action.
        FILE_CREATED: A new file was created.
        FILE_MODIFIED: An existing file was modified.
        FILE_DELETED: A file was deleted.
        REVIEW_REQUESTED: Code review has been requested.
        REVIEW_COMPLETED: Code review has been completed.
        REVISION_REQUESTED: Reviewer requested changes.
        AGENT_MESSAGE: Message from an agent.
        TASK_STARTED: An agent task has begun.
        TASK_COMPLETED: An agent task has finished.
        TASK_FAILED: An agent task has failed.
        SYSTEM_ERROR: System-level error occurred.
        SYSTEM_WARNING: System-level warning issued.
        STREAM: Ephemeral streaming event (not persisted).
    """

    # Lifecycle
    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"

    # Stages
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"

    # Approval
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"

    # Artifacts
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"

    # Review cycle
    REVIEW_REQUESTED = "review_requested"
    REVIEW_COMPLETED = "review_completed"
    REVISION_REQUESTED = "revision_requested"

    # Agent messages (replaces in-state message accumulation)
    AGENT_MESSAGE = "agent_message"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    # System
    SYSTEM_ERROR = "system_error"
    SYSTEM_WARNING = "system_warning"

    # Streaming (ephemeral, not persisted)
    STREAM = "stream"

    # Stream event types (trace level)
    CLAUDE_THINKING = "claude_thinking"
    CLAUDE_TOOL_CALL = "claude_tool_call"
    CLAUDE_TOOL_RESULT = "claude_tool_result"
    AGENT_OUTPUT = "agent_output"

    # Brainstorming (chat-based design sessions)
    BRAINSTORM_SESSION_CREATED = "brainstorm_session_created"
    BRAINSTORM_REASONING = "brainstorm_reasoning"
    BRAINSTORM_TOOL_CALL = "brainstorm_tool_call"
    BRAINSTORM_TOOL_RESULT = "brainstorm_tool_result"
    BRAINSTORM_TEXT = "brainstorm_text"
    BRAINSTORM_MESSAGE_COMPLETE = "brainstorm_message_complete"
    BRAINSTORM_ARTIFACT_CREATED = "brainstorm_artifact_created"
    BRAINSTORM_SESSION_COMPLETED = "brainstorm_session_completed"

    # Oracle consultation events
    ORACLE_CONSULTATION_STARTED = "oracle_consultation_started"
    ORACLE_CONSULTATION_THINKING = "oracle_consultation_thinking"
    ORACLE_TOOL_CALL = "oracle_tool_call"
    ORACLE_TOOL_RESULT = "oracle_tool_result"
    ORACLE_CONSULTATION_COMPLETED = "oracle_consultation_completed"
    ORACLE_CONSULTATION_FAILED = "oracle_consultation_failed"


# Event type to level mapping
_INFO_TYPES: frozenset[EventType] = frozenset({
    EventType.WORKFLOW_CREATED,
    EventType.WORKFLOW_STARTED,
    EventType.WORKFLOW_COMPLETED,
    EventType.WORKFLOW_FAILED,
    EventType.WORKFLOW_CANCELLED,
    EventType.STAGE_STARTED,
    EventType.STAGE_COMPLETED,
    EventType.APPROVAL_REQUIRED,
    EventType.APPROVAL_GRANTED,
    EventType.APPROVAL_REJECTED,
    EventType.REVIEW_COMPLETED,
    EventType.ORACLE_CONSULTATION_STARTED,
    EventType.ORACLE_CONSULTATION_COMPLETED,
    EventType.ORACLE_CONSULTATION_FAILED,
})

_TRACE_TYPES: frozenset[EventType] = frozenset({
    EventType.CLAUDE_THINKING,
    EventType.CLAUDE_TOOL_CALL,
    EventType.CLAUDE_TOOL_RESULT,
    EventType.AGENT_OUTPUT,
    EventType.ORACLE_CONSULTATION_THINKING,
    EventType.ORACLE_TOOL_CALL,
    EventType.ORACLE_TOOL_RESULT,
})


def get_event_level(event_type: EventType) -> EventLevel:
    """Get the level for an event type.

    Args:
        event_type: The event type to classify.

    Returns:
        EventLevel for the given event type.
    """
    if event_type in _INFO_TYPES:
        return EventLevel.INFO
    if event_type in _TRACE_TYPES:
        return EventLevel.TRACE
    return EventLevel.DEBUG


class WorkflowEvent(BaseModel):
    """Event for activity log and real-time updates.

    Events are immutable and append-only. They form the authoritative
    history of workflow execution.

    Attributes:
        id: Unique event identifier (UUID).
        domain: Event domain (workflow or brainstorm).
        workflow_id: Links to ExecutionState.
        sequence: Monotonic counter per workflow (ensures ordering).
        timestamp: When event occurred.
        agent: Source of event ("architect", "developer", "reviewer", "system").
        event_type: Typed event category.
        level: Event severity level (info, debug, trace).
        message: Human-readable summary.
        data: Optional structured payload (file paths, error details, etc.).
        session_id: Per-consultation session ID (independent from workflow_id).
        correlation_id: Links related events (e.g., approval request -> granted).
        tool_name: Tool name for trace events (optional).
        tool_input: Tool input parameters for trace events (optional).
        is_error: Whether trace event represents an error (default False).
        trace_id: Distributed trace ID (flows through all events in a workflow execution).
        parent_id: Parent event ID for causal chain (e.g., tool_call -> tool_result).
    """

    id: str = Field(..., description="Unique event identifier")
    domain: EventDomain = Field(
        default=EventDomain.WORKFLOW,
        description="Event domain (workflow or brainstorm)",
    )
    workflow_id: str = Field(..., description="Workflow this event belongs to")
    sequence: int = Field(..., ge=0, description="Monotonic sequence number (0 for trace-only events)")
    timestamp: datetime = Field(..., description="When event occurred")
    agent: str = Field(..., description="Event source agent")
    event_type: EventType = Field(..., description="Event type category")
    level: EventLevel | None = Field(default=None, description="Event severity level")
    message: str = Field(..., description="Human-readable message")
    data: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured payload",
    )
    session_id: str | None = Field(
        default=None,
        description="Per-consultation session ID (independent from workflow_id)",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Links related events for tracing",
    )
    # Trace-specific fields
    tool_name: str | None = Field(
        default=None,
        description="Tool name for trace events",
    )
    tool_input: dict[str, Any] | None = Field(
        default=None,
        description="Tool input parameters for trace events",
    )
    is_error: bool = Field(
        default=False,
        description="Whether trace event represents an error",
    )
    model: str | None = Field(
        default=None,
        description="LLM model name for trace events",
    )
    # Distributed tracing fields (OTel-compatible)
    trace_id: str | None = Field(
        default=None,
        description="Distributed trace ID (flows through all events in a workflow execution)",
    )
    parent_id: str | None = Field(
        default=None,
        description="Parent event ID for causal chain (e.g., tool_call -> tool_result)",
    )

    def model_post_init(self, __context: Any) -> None:
        """Set level from event_type if not provided."""
        if self.level is None:
            object.__setattr__(self, "level", get_event_level(self.event_type))

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "evt-123",
                    "workflow_id": "wf-456",
                    "sequence": 1,
                    "timestamp": "2025-01-01T12:00:00Z",
                    "agent": "architect",
                    "event_type": "stage_started",
                    "level": "info",
                    "message": "Creating task plan",
                    "data": {"stage": "planning"},
                }
            ]
        }
    }
