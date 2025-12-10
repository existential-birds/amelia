# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Event models for workflow activity tracking."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """Exhaustive list of workflow event types.

    Events are categorized into:
    - Lifecycle: Start, complete, fail, cancel workflows
    - Stages: Track progress through workflow stages
    - Approval: Human approval flow events
    - Artifacts: File operations
    - Review: Code review cycle
    - Agent messages: Task-level messages and status updates
    - System: Errors and warnings
    """

    # Lifecycle
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


class WorkflowEvent(BaseModel):
    """Event for activity log and real-time updates.

    Events are immutable and append-only. They form the authoritative
    history of workflow execution.

    Attributes:
        id: Unique event identifier (UUID).
        workflow_id: Links to ExecutionState.
        sequence: Monotonic counter per workflow (ensures ordering).
        timestamp: When event occurred.
        agent: Source of event ("architect", "developer", "reviewer", "system").
        event_type: Typed event category.
        message: Human-readable summary.
        data: Optional structured payload (file paths, error details, etc.).
        correlation_id: Links related events (e.g., approval request -> granted).
    """

    id: str = Field(..., description="Unique event identifier")
    workflow_id: str = Field(..., description="Workflow this event belongs to")
    sequence: int = Field(..., ge=1, description="Monotonic sequence number")
    timestamp: datetime = Field(..., description="When event occurred")
    agent: str = Field(..., description="Event source agent")
    event_type: EventType = Field(..., description="Event type category")
    message: str = Field(..., description="Human-readable message")
    data: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured payload",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Links related events for tracing",
    )

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
                    "message": "Creating task plan",
                    "data": {"stage": "planning"},
                }
            ]
        }
    }
