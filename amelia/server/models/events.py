"""Event models for workflow activity tracking."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# Sequence number for ephemeral/trace-only events (not persisted, no ordering needed)
EPHEMERAL_SEQUENCE: int = 0


class EventDomain(StrEnum):
    """Domain of event origin."""

    WORKFLOW = "workflow"
    BRAINSTORM = "brainstorm"
    ORACLE = "oracle"
    KNOWLEDGE = "knowledge"


class EventLevel(StrEnum):
    """Event severity level for filtering and retention."""

    INFO = "info"
    WARNING = "warning"
    DEBUG = "debug"
    ERROR = "error"


class EventType(StrEnum):
    """Exhaustive list of workflow event types.

    Events are categorized into lifecycle, stage, approval, artifact,
    review, agent message, and system event types.
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
    BRAINSTORM_ASK_USER = "brainstorm_ask_user"
    BRAINSTORM_MESSAGE_COMPLETE = "brainstorm_message_complete"
    BRAINSTORM_ARTIFACT_CREATED = "brainstorm_artifact_created"
    BRAINSTORM_SESSION_COMPLETED = "brainstorm_session_completed"
    BRAINSTORM_MESSAGE_FAILED = "brainstorm_message_failed"

    # Oracle consultation events
    ORACLE_CONSULTATION_STARTED = "oracle_consultation_started"
    ORACLE_CONSULTATION_THINKING = "oracle_consultation_thinking"
    ORACLE_TOOL_CALL = "oracle_tool_call"
    ORACLE_TOOL_RESULT = "oracle_tool_result"
    ORACLE_CONSULTATION_COMPLETED = "oracle_consultation_completed"
    ORACLE_CONSULTATION_FAILED = "oracle_consultation_failed"

    # Knowledge ingestion
    DOCUMENT_INGESTION_STARTED = "document_ingestion_started"
    DOCUMENT_INGESTION_PROGRESS = "document_ingestion_progress"
    DOCUMENT_INGESTION_COMPLETED = "document_ingestion_completed"
    DOCUMENT_INGESTION_FAILED = "document_ingestion_failed"

    # Plan validation (synchronous extraction and structural checks)
    PLAN_VALIDATED = "plan_validated"
    PLAN_VALIDATION_FAILED = "plan_validation_failed"

    # PR Auto-Fix orchestration
    PR_FIX_QUEUED = "pr_fix_queued"
    PR_FIX_DIVERGED = "pr_fix_diverged"
    PR_FIX_COOLDOWN_STARTED = "pr_fix_cooldown_started"
    PR_FIX_COOLDOWN_RESET = "pr_fix_cooldown_reset"
    PR_FIX_RETRIES_EXHAUSTED = "pr_fix_retries_exhausted"


# Persisted event types (written to workflow log)
PERSISTED_TYPES: frozenset[EventType] = frozenset({
    # Lifecycle
    EventType.WORKFLOW_CREATED,
    EventType.WORKFLOW_STARTED,
    EventType.WORKFLOW_COMPLETED,
    EventType.WORKFLOW_FAILED,
    EventType.WORKFLOW_CANCELLED,
    # Stages
    EventType.STAGE_STARTED,
    EventType.STAGE_COMPLETED,
    # Approval
    EventType.APPROVAL_REQUIRED,
    EventType.APPROVAL_GRANTED,
    EventType.APPROVAL_REJECTED,
    # Artifacts
    EventType.FILE_CREATED,
    EventType.FILE_MODIFIED,
    EventType.FILE_DELETED,
    # Review
    EventType.REVIEW_REQUESTED,
    EventType.REVIEW_COMPLETED,
    EventType.REVISION_REQUESTED,
    # Tasks
    EventType.TASK_STARTED,
    EventType.TASK_COMPLETED,
    EventType.TASK_FAILED,
    # System
    EventType.SYSTEM_ERROR,
    EventType.SYSTEM_WARNING,
    # Oracle
    EventType.ORACLE_CONSULTATION_STARTED,
    EventType.ORACLE_CONSULTATION_COMPLETED,
    EventType.ORACLE_CONSULTATION_FAILED,
    # Brainstorm
    EventType.BRAINSTORM_SESSION_CREATED,
    EventType.BRAINSTORM_SESSION_COMPLETED,
    EventType.BRAINSTORM_ARTIFACT_CREATED,
    EventType.BRAINSTORM_MESSAGE_FAILED,
    # Knowledge ingestion
    EventType.DOCUMENT_INGESTION_STARTED,
    EventType.DOCUMENT_INGESTION_COMPLETED,
    EventType.DOCUMENT_INGESTION_FAILED,
    # Plan validation
    EventType.PLAN_VALIDATED,
    EventType.PLAN_VALIDATION_FAILED,
    # PR Auto-Fix orchestration
    EventType.PR_FIX_QUEUED,
    EventType.PR_FIX_DIVERGED,
    EventType.PR_FIX_COOLDOWN_STARTED,
    EventType.PR_FIX_COOLDOWN_RESET,
    EventType.PR_FIX_RETRIES_EXHAUSTED,
})

_ERROR_TYPES: frozenset[EventType] = frozenset({
    EventType.WORKFLOW_FAILED,
    EventType.TASK_FAILED,
    EventType.SYSTEM_ERROR,
    EventType.ORACLE_CONSULTATION_FAILED,
    EventType.DOCUMENT_INGESTION_FAILED,
    EventType.PLAN_VALIDATION_FAILED,
    EventType.BRAINSTORM_MESSAGE_FAILED,
    EventType.PR_FIX_RETRIES_EXHAUSTED,
})

_WARNING_TYPES: frozenset[EventType] = frozenset({
    EventType.SYSTEM_WARNING,
    EventType.PR_FIX_DIVERGED,
})

_INFO_TYPES: frozenset[EventType] = frozenset({
    EventType.WORKFLOW_CREATED,
    EventType.WORKFLOW_STARTED,
    EventType.WORKFLOW_COMPLETED,
    EventType.WORKFLOW_CANCELLED,
    EventType.STAGE_STARTED,
    EventType.STAGE_COMPLETED,
    EventType.APPROVAL_REQUIRED,
    EventType.APPROVAL_GRANTED,
    EventType.APPROVAL_REJECTED,
    EventType.REVIEW_COMPLETED,
    EventType.ORACLE_CONSULTATION_STARTED,
    EventType.ORACLE_CONSULTATION_COMPLETED,
    EventType.DOCUMENT_INGESTION_STARTED,
    EventType.DOCUMENT_INGESTION_COMPLETED,
    EventType.PR_FIX_QUEUED,
    EventType.PR_FIX_COOLDOWN_STARTED,
    EventType.PR_FIX_COOLDOWN_RESET,
})


def get_event_level(event_type: EventType) -> EventLevel:
    """Get the level for an event type.

    Args:
        event_type: The event type to classify.

    Returns:
        EventLevel for the given event type.
    """
    if event_type in _ERROR_TYPES:
        return EventLevel.ERROR
    if event_type in _WARNING_TYPES:
        return EventLevel.WARNING
    if event_type in _INFO_TYPES:
        return EventLevel.INFO
    return EventLevel.DEBUG


class WorkflowEvent(BaseModel):
    """Event for activity log and real-time updates.

    Events are immutable and append-only. They form the authoritative
    history of workflow execution.
    """

    id: uuid.UUID = Field(..., description="Unique event identifier")
    domain: EventDomain = Field(
        default=EventDomain.WORKFLOW,
        description="Event domain (workflow or brainstorm)",
    )
    workflow_id: uuid.UUID = Field(..., description="Workflow this event belongs to")
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
    session_id: uuid.UUID | None = Field(
        default=None,
        description="Per-consultation session ID (independent from workflow_id)",
    )
    correlation_id: uuid.UUID | None = Field(
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
    trace_id: uuid.UUID | None = Field(
        default=None,
        description="Distributed trace ID (flows through all events in a workflow execution)",
    )
    parent_id: uuid.UUID | None = Field(
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
