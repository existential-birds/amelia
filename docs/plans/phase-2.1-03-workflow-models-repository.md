# Workflow Models & Repository Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement workflow domain models (EventType, WorkflowEvent, TokenUsage, ExecutionState) and repository with state machine validation.

**Architecture:** Pydantic models for all data structures, repository pattern for database operations, state machine for workflow transitions, event sourcing lite with projection.

**Tech Stack:** Pydantic, aiosqlite

**Depends on:** Plan 2 (Database Foundation)

---

## Task 1: Create EventType and WorkflowEvent Models

**Files:**
- Create: `amelia/server/models/__init__.py`
- Create: `amelia/server/models/events.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/models/test_events.py
"""Tests for event models."""
import pytest
from datetime import datetime, UTC

from amelia.server.models.events import EventType, WorkflowEvent


class TestEventType:
    """Tests for EventType enum."""

    def test_event_type_values_are_strings(self):
        """Event type values are lowercase strings."""
        assert EventType.WORKFLOW_STARTED.value == "workflow_started"
        assert EventType.STAGE_COMPLETED.value == "stage_completed"


class TestWorkflowEvent:
    """Tests for WorkflowEvent model."""

    def test_create_event_with_required_fields(self):
        """Event can be created with required fields."""
        event = WorkflowEvent(
            id="event-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="architect",
            event_type=EventType.STAGE_STARTED,
            message="Starting plan creation",
        )

        assert event.id == "event-123"
        assert event.workflow_id == "wf-456"
        assert event.sequence == 1
        assert event.agent == "architect"
        assert event.event_type == EventType.STAGE_STARTED

    def test_event_optional_fields_default_none(self):
        """Optional fields default to None."""
        event = WorkflowEvent(
            id="event-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        assert event.data is None
        assert event.correlation_id is None

    def test_event_with_data_payload(self):
        """Event can include structured data payload."""
        event = WorkflowEvent(
            id="event-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.FILE_CREATED,
            message="Created file",
            data={"path": "src/main.py", "lines": 100},
        )

        assert event.data["path"] == "src/main.py"
        assert event.data["lines"] == 100

    def test_event_with_correlation_id(self):
        """Event can include correlation ID for tracing."""
        event = WorkflowEvent(
            id="event-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.APPROVAL_GRANTED,
            message="Approved",
            correlation_id="req-789",
        )

        assert event.correlation_id == "req-789"

    def test_event_serialization_to_json(self):
        """Event can be serialized to JSON."""
        event = WorkflowEvent(
            id="event-123",
            workflow_id="wf-456",
            sequence=1,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Started",
        )

        json_str = event.model_dump_json()
        assert "event-123" in json_str
        assert "workflow_started" in json_str

    def test_event_deserialization_from_json(self):
        """Event can be deserialized from JSON."""
        json_str = '''
        {
            "id": "event-123",
            "workflow_id": "wf-456",
            "sequence": 1,
            "timestamp": "2025-01-01T12:00:00",
            "agent": "system",
            "event_type": "workflow_started",
            "message": "Started"
        }
        '''

        event = WorkflowEvent.model_validate_json(json_str)
        assert event.id == "event-123"
        assert event.event_type == EventType.WORKFLOW_STARTED
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_events.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create models package**

```python
# amelia/server/models/__init__.py
"""Domain models for Amelia server."""
from amelia.server.models.events import EventType, WorkflowEvent

__all__ = ["EventType", "WorkflowEvent"]
```

**Step 4: Implement event models**

```python
# amelia/server/models/events.py
"""Event models for workflow activity tracking."""
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Exhaustive list of workflow event types.

    Events are categorized into:
    - Lifecycle: Start, complete, fail, cancel workflows
    - Stages: Track progress through workflow stages
    - Approval: Human approval flow events
    - Artifacts: File operations
    - Review: Code review cycle
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
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_events.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/models/__init__.py amelia/server/models/events.py tests/unit/server/models/test_events.py
git commit -m "feat(models): add EventType enum and WorkflowEvent model"
```

---

## Task 2: Create TokenUsage Model with Cost Calculation

**Files:**
- Create: `amelia/server/models/tokens.py`
- Modify: `amelia/server/models/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/models/test_tokens.py
"""Tests for token usage models."""
import pytest
from datetime import datetime, UTC

from amelia.server.models.tokens import TokenUsage, MODEL_PRICING, calculate_token_cost


class TestTokenUsage:
    """Tests for TokenUsage model."""

    def test_create_basic_token_usage(self):
        """TokenUsage can be created with required fields."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            input_tokens=1000,
            output_tokens=500,
            timestamp=datetime.now(UTC),
        )

        assert usage.workflow_id == "wf-123"
        assert usage.agent == "architect"
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500

    def test_default_model_is_sonnet(self):
        """Default model is claude-sonnet-4."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            input_tokens=1000,
            output_tokens=500,
            timestamp=datetime.now(UTC),
        )

        assert usage.model == "claude-sonnet-4-20250514"

    def test_cache_tokens_default_zero(self):
        """Cache tokens default to zero."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            input_tokens=1000,
            output_tokens=500,
            timestamp=datetime.now(UTC),
        )

        assert usage.cache_read_tokens == 0
        assert usage.cache_creation_tokens == 0

    def test_token_usage_with_cache(self):
        """TokenUsage can include cache token counts."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="developer",
            input_tokens=2000,
            output_tokens=1000,
            cache_read_tokens=500,
            cache_creation_tokens=100,
            timestamp=datetime.now(UTC),
        )

        assert usage.cache_read_tokens == 500
        assert usage.cache_creation_tokens == 100


class TestModelPricing:
    """Tests for model pricing constants."""

    def test_sonnet_pricing_defined(self):
        """Sonnet pricing is defined."""
        assert "claude-sonnet-4-20250514" in MODEL_PRICING
        sonnet = MODEL_PRICING["claude-sonnet-4-20250514"]
        assert sonnet["input"] == 3.0
        assert sonnet["output"] == 15.0
        assert sonnet["cache_read"] == 0.3
        assert sonnet["cache_write"] == 3.75

    def test_opus_pricing_defined(self):
        """Opus pricing is defined."""
        assert "claude-opus-4-20250514" in MODEL_PRICING
        opus = MODEL_PRICING["claude-opus-4-20250514"]
        assert opus["input"] == 15.0
        assert opus["output"] == 75.0


class TestCostCalculation:
    """Tests for cost calculation function."""

    def test_basic_cost_calculation(self):
        """Basic cost calculation without cache."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            model="claude-sonnet-4-20250514",
            input_tokens=1_000_000,  # 1M tokens
            output_tokens=1_000_000,
            timestamp=datetime.now(UTC),
        )

        cost = calculate_token_cost(usage)
        # Input: 1M * $3/M = $3
        # Output: 1M * $15/M = $15
        # Total: $18
        assert cost == 18.0

    def test_cost_with_cache_reads(self):
        """Cost calculation with cache reads (discounted)."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            model="claude-sonnet-4-20250514",
            input_tokens=1_000_000,
            output_tokens=0,
            cache_read_tokens=500_000,  # Half from cache
            timestamp=datetime.now(UTC),
        )

        cost = calculate_token_cost(usage)
        # Base input: (1M - 500K) * $3/M = $1.50
        # Cache read: 500K * $0.30/M = $0.15
        # Total: $1.65
        assert cost == 1.65

    def test_cost_with_cache_writes(self):
        """Cost calculation with cache creation (premium rate)."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            model="claude-sonnet-4-20250514",
            input_tokens=1_000_000,
            output_tokens=0,
            cache_creation_tokens=100_000,  # 100K cache writes
            timestamp=datetime.now(UTC),
        )

        cost = calculate_token_cost(usage)
        # Base input: 1M * $3/M = $3.00
        # Cache write: 100K * $3.75/M = $0.375
        # Total: $3.375
        assert cost == 3.375

    def test_cost_with_opus_model(self):
        """Cost calculation uses correct model pricing."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            model="claude-opus-4-20250514",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            timestamp=datetime.now(UTC),
        )

        cost = calculate_token_cost(usage)
        # Input: 1M * $15/M = $15
        # Output: 1M * $75/M = $75
        # Total: $90
        assert cost == 90.0

    def test_cost_with_unknown_model_uses_sonnet(self):
        """Unknown models fall back to Sonnet pricing."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            model="unknown-model-2025",
            input_tokens=1_000_000,
            output_tokens=0,
            timestamp=datetime.now(UTC),
        )

        cost = calculate_token_cost(usage)
        # Falls back to Sonnet: 1M * $3/M = $3
        assert cost == 3.0

    def test_cost_rounds_to_micro_dollars(self):
        """Cost is rounded to 6 decimal places (micro-dollars)."""
        usage = TokenUsage(
            workflow_id="wf-123",
            agent="architect",
            model="claude-sonnet-4-20250514",
            input_tokens=1,  # Very small
            output_tokens=1,
            timestamp=datetime.now(UTC),
        )

        cost = calculate_token_cost(usage)
        # Should be a small number with at most 6 decimal places
        assert cost == round(cost, 6)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_tokens.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement token models**

```python
# amelia/server/models/tokens.py
"""Token usage tracking and cost calculation."""
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


# Pricing per million tokens (as of 2025)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-20250514": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.5,      # 90% discount on cached input
        "cache_write": 18.75,   # 25% premium on cache creation
    },
    "claude-sonnet-4-20250514": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
}


class TokenUsage(BaseModel):
    """Token consumption tracking per agent.

    Cache token semantics:
    - input_tokens: Total tokens processed (includes cache_read_tokens)
    - cache_read_tokens: Subset of input_tokens served from prompt cache (cheaper)
    - cache_creation_tokens: Tokens written to cache (billed at higher rate)
    - cost_usd: Calculated as input_cost + output_cost - cache_discount

    Attributes:
        id: Unique identifier.
        workflow_id: Workflow this usage belongs to.
        agent: Agent that consumed tokens.
        model: Model used for cost calculation.
        input_tokens: Total input tokens (includes cache reads).
        output_tokens: Output tokens generated.
        cache_read_tokens: Subset of input from cache (discounted).
        cache_creation_tokens: Tokens written to cache (premium rate).
        cost_usd: Net cost after cache adjustments.
        timestamp: When tokens were consumed.
    """

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier",
    )
    workflow_id: str = Field(..., description="Workflow ID")
    agent: str = Field(..., description="Agent that consumed tokens")
    model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Model used",
    )
    input_tokens: int = Field(..., ge=0, description="Total input tokens")
    output_tokens: int = Field(..., ge=0, description="Output tokens")
    cache_read_tokens: int = Field(
        default=0,
        ge=0,
        description="Input tokens from cache",
    )
    cache_creation_tokens: int = Field(
        default=0,
        ge=0,
        description="Tokens written to cache",
    )
    cost_usd: float | None = Field(
        default=None,
        description="Calculated cost in USD",
    )
    timestamp: datetime = Field(..., description="When consumed")


def calculate_token_cost(usage: TokenUsage) -> float:
    """Calculate USD cost for token usage with cache adjustments.

    Args:
        usage: Token usage record with model and token counts.

    Returns:
        Total cost in USD, rounded to 6 decimal places (micro-dollars).

    Formula:
        cost = (base_input * input_rate) + (cache_read * cache_read_rate)
             + (cache_write * cache_write_rate) + (output * output_rate)

    Where base_input = input_tokens - cache_read_tokens (non-cached input).
    """
    # Default to sonnet pricing if model unknown
    rates = MODEL_PRICING.get(usage.model, MODEL_PRICING["claude-sonnet-4-20250514"])

    # Cache reads are already included in input_tokens, so subtract them
    base_input_tokens = usage.input_tokens - usage.cache_read_tokens

    cost = (
        (base_input_tokens * rates["input"] / 1_000_000)
        + (usage.cache_read_tokens * rates["cache_read"] / 1_000_000)
        + (usage.cache_creation_tokens * rates["cache_write"] / 1_000_000)
        + (usage.output_tokens * rates["output"] / 1_000_000)
    )

    return round(cost, 6)
```

**Step 4: Update models init**

```python
# amelia/server/models/__init__.py
"""Domain models for Amelia server."""
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.models.tokens import MODEL_PRICING, TokenUsage, calculate_token_cost

__all__ = [
    "EventType",
    "WorkflowEvent",
    "TokenUsage",
    "MODEL_PRICING",
    "calculate_token_cost",
]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_tokens.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/models/tokens.py amelia/server/models/__init__.py tests/unit/server/models/test_tokens.py
git commit -m "feat(models): add TokenUsage model with cost calculation"
```

---

## Task 3: Create WorkflowStatus and State Machine

**Files:**
- Create: `amelia/server/models/state.py`
- Modify: `amelia/server/models/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/models/test_state.py
"""Tests for workflow state models."""
import pytest
from datetime import datetime, UTC

from amelia.server.models.state import (
    WorkflowStatus,
    validate_transition,
    InvalidStateTransitionError,
    ServerExecutionState,
)


class TestStateTransitions:
    """Tests for state machine transitions."""

    def test_pending_can_go_to_in_progress(self):
        """pending -> in_progress is valid."""
        validate_transition("pending", "in_progress")  # Should not raise

    def test_pending_can_go_to_cancelled(self):
        """pending -> cancelled is valid."""
        validate_transition("pending", "cancelled")

    def test_pending_cannot_go_to_completed(self):
        """pending -> completed is invalid (must go through in_progress)."""
        with pytest.raises(InvalidStateTransitionError) as exc:
            validate_transition("pending", "completed")

        assert exc.value.current == "pending"
        assert exc.value.target == "completed"

    def test_in_progress_can_go_to_blocked(self):
        """in_progress -> blocked is valid (awaiting approval)."""
        validate_transition("in_progress", "blocked")

    def test_in_progress_can_go_to_completed(self):
        """in_progress -> completed is valid."""
        validate_transition("in_progress", "completed")

    def test_in_progress_can_go_to_failed(self):
        """in_progress -> failed is valid."""
        validate_transition("in_progress", "failed")

    def test_blocked_can_go_to_in_progress(self):
        """blocked -> in_progress is valid (approval granted)."""
        validate_transition("blocked", "in_progress")

    def test_blocked_can_go_to_failed(self):
        """blocked -> failed is valid (approval rejected)."""
        validate_transition("blocked", "failed")

    def test_completed_is_terminal(self):
        """completed is terminal - cannot transition."""
        for target in ["pending", "in_progress", "blocked", "failed", "cancelled"]:
            with pytest.raises(InvalidStateTransitionError):
                validate_transition("completed", target)

    def test_failed_is_terminal(self):
        """failed is terminal - cannot transition."""
        for target in ["pending", "in_progress", "blocked", "completed", "cancelled"]:
            with pytest.raises(InvalidStateTransitionError):
                validate_transition("failed", target)

    def test_cancelled_is_terminal(self):
        """cancelled is terminal - cannot transition."""
        for target in ["pending", "in_progress", "blocked", "completed", "failed"]:
            with pytest.raises(InvalidStateTransitionError):
                validate_transition("cancelled", target)

    def test_same_state_transition_invalid(self):
        """Cannot transition to same state."""
        with pytest.raises(InvalidStateTransitionError):
            validate_transition("in_progress", "in_progress")


class TestServerExecutionState:
    """Tests for ServerExecutionState model."""

    def test_create_with_required_fields(self):
        """ServerExecutionState requires id, issue_id, worktree fields."""
        state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path/to/repo",
            worktree_name="main",
        )

        assert state.id == "wf-123"
        assert state.issue_id == "ISSUE-456"
        assert state.worktree_path == "/path/to/repo"
        assert state.worktree_name == "main"

    def test_default_status_is_pending(self):
        """Default workflow status is pending."""
        state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path/to/repo",
            worktree_name="main",
        )

        assert state.workflow_status == "pending"

    def test_timestamps_default_none(self):
        """Timestamps default to None."""
        state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path/to/repo",
            worktree_name="main",
        )

        assert state.started_at is None
        assert state.completed_at is None

    def test_stage_timestamps_default_empty(self):
        """Stage timestamps default to empty dict."""
        state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path/to/repo",
            worktree_name="main",
        )

        assert state.stage_timestamps == {}

    def test_serialization_to_json(self):
        """State can be serialized to JSON."""
        state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/path/to/repo",
            worktree_name="main",
            workflow_status="in_progress",
            started_at=datetime(2025, 1, 1, 12, 0, 0),
        )

        json_str = state.model_dump_json()
        assert "wf-123" in json_str
        assert "in_progress" in json_str

    def test_deserialization_from_json(self):
        """State can be deserialized from JSON."""
        json_str = '''
        {
            "id": "wf-123",
            "issue_id": "ISSUE-456",
            "worktree_path": "/path/to/repo",
            "worktree_name": "main",
            "workflow_status": "blocked"
        }
        '''

        state = ServerExecutionState.model_validate_json(json_str)
        assert state.id == "wf-123"
        assert state.workflow_status == "blocked"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_state.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement state models**

```python
# amelia/server/models/state.py
"""Workflow state models and state machine validation."""
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


# Type alias for workflow status
WorkflowStatus = Literal[
    "pending",      # Not yet started
    "in_progress",  # Currently executing
    "blocked",      # Awaiting human approval
    "completed",    # Successfully finished
    "failed",       # Error occurred
    "cancelled",    # Explicitly cancelled
]


# State machine validation - prevents invalid transitions
VALID_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    "pending": {"in_progress", "cancelled"},
    "in_progress": {"blocked", "completed", "failed", "cancelled"},
    "blocked": {"in_progress", "failed", "cancelled"},
    "completed": set(),   # Terminal state
    "failed": set(),      # Terminal state
    "cancelled": set(),   # Terminal state
}


class InvalidStateTransitionError(ValueError):
    """Raised when attempting an invalid workflow state transition."""

    def __init__(self, current: WorkflowStatus, target: WorkflowStatus):
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition from '{current}' to '{target}'")


def validate_transition(current: WorkflowStatus, target: WorkflowStatus) -> None:
    """Validate that a state transition is allowed.

    Args:
        current: The current workflow status.
        target: The desired new status.

    Raises:
        InvalidStateTransitionError: If the transition is not allowed.
    """
    if target not in VALID_TRANSITIONS[current]:
        raise InvalidStateTransitionError(current, target)


class ServerExecutionState(BaseModel):
    """Extended ExecutionState for server-side workflow tracking.

    This model extends the core ExecutionState with server-specific fields
    for persistence and tracking.

    Attributes:
        id: Unique workflow identifier (UUID).
        issue_id: Issue being worked on.
        worktree_path: Absolute path to git worktree root.
        worktree_name: Human-readable worktree name (branch or directory).
        workflow_status: Current workflow status.
        started_at: When workflow started.
        completed_at: When workflow ended (success or failure).
        stage_timestamps: When each stage started.
        current_stage: Currently executing stage.
        failure_reason: Error message when status is "failed".
    """

    id: str = Field(..., description="Unique workflow identifier")
    issue_id: str = Field(..., description="Issue being worked on")
    worktree_path: str = Field(..., description="Absolute path to worktree")
    worktree_name: str = Field(..., description="Human-readable worktree name")

    workflow_status: WorkflowStatus = Field(
        default="pending",
        description="Current workflow status",
    )
    started_at: datetime | None = Field(
        default=None,
        description="When workflow started",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="When workflow ended",
    )
    stage_timestamps: dict[str, datetime] = Field(
        default_factory=dict,
        description="When each stage started",
    )
    current_stage: str | None = Field(
        default=None,
        description="Currently executing stage",
    )
    failure_reason: str | None = Field(
        default=None,
        description="Error message when failed",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "wf-123",
                    "issue_id": "ISSUE-456",
                    "worktree_path": "/home/user/project",
                    "worktree_name": "main",
                    "workflow_status": "in_progress",
                    "started_at": "2025-01-01T12:00:00Z",
                    "current_stage": "development",
                }
            ]
        }
    }
```

**Step 4: Update models init**

```python
# amelia/server/models/__init__.py
"""Domain models for Amelia server."""
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.models.state import (
    InvalidStateTransitionError,
    ServerExecutionState,
    VALID_TRANSITIONS,
    WorkflowStatus,
    validate_transition,
)
from amelia.server.models.tokens import MODEL_PRICING, TokenUsage, calculate_token_cost

__all__ = [
    # Events
    "EventType",
    "WorkflowEvent",
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
]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_state.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/models/state.py amelia/server/models/__init__.py tests/unit/server/models/test_state.py
git commit -m "feat(models): add WorkflowStatus and state machine validation"
```

---

## Task 4: Create WorkflowRepository

**Files:**
- Create: `amelia/server/database/repository.py`
- Modify: `amelia/server/database/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/database/test_repository.py
"""Tests for WorkflowRepository."""
import pytest
from datetime import datetime, UTC
from uuid import uuid4

from amelia.server.database.repository import WorkflowRepository
from amelia.server.models.state import ServerExecutionState, InvalidStateTransitionError


class TestWorkflowRepository:
    """Tests for WorkflowRepository CRUD operations."""

    @pytest.fixture
    async def repository(self, db_with_schema):
        """WorkflowRepository instance."""
        return WorkflowRepository(db_with_schema)

    @pytest.mark.asyncio
    async def test_create_workflow(self, repository):
        """Can create a workflow."""
        state = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            worktree_name="main",
        )

        await repository.create(state)

        # Verify it was created
        retrieved = await repository.get(state.id)
        assert retrieved is not None
        assert retrieved.issue_id == "ISSUE-123"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, repository):
        """Getting nonexistent workflow returns None."""
        result = await repository.get("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_worktree(self, repository):
        """Can get active workflow by worktree path."""
        state = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            worktree_name="main",
            workflow_status="in_progress",
        )
        await repository.create(state)

        retrieved = await repository.get_by_worktree("/path/to/repo")
        assert retrieved is not None
        assert retrieved.id == state.id

    @pytest.mark.asyncio
    async def test_get_by_worktree_only_active(self, repository):
        """get_by_worktree only returns active workflows."""
        # Create completed workflow
        completed = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-1",
            worktree_path="/path/to/repo",
            worktree_name="main",
            workflow_status="completed",
        )
        await repository.create(completed)

        # No active workflow should be found
        result = await repository.get_by_worktree("/path/to/repo")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_workflow(self, repository):
        """Can update workflow state."""
        state = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            worktree_name="main",
        )
        await repository.create(state)

        # Update status
        state.workflow_status = "in_progress"
        state.started_at = datetime.now(UTC)
        await repository.update(state)

        retrieved = await repository.get(state.id)
        assert retrieved.workflow_status == "in_progress"
        assert retrieved.started_at is not None

    @pytest.mark.asyncio
    async def test_set_status_validates_transition(self, repository):
        """set_status validates state machine transitions."""
        state = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            worktree_name="main",
            workflow_status="pending",
        )
        await repository.create(state)

        # Invalid: pending -> completed (must go through in_progress)
        with pytest.raises(InvalidStateTransitionError):
            await repository.set_status(state.id, "completed")

    @pytest.mark.asyncio
    async def test_set_status_valid_transition(self, repository):
        """set_status allows valid transitions."""
        state = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            worktree_name="main",
            workflow_status="pending",
        )
        await repository.create(state)

        await repository.set_status(state.id, "in_progress")

        retrieved = await repository.get(state.id)
        assert retrieved.workflow_status == "in_progress"

    @pytest.mark.asyncio
    async def test_set_status_with_failure_reason(self, repository):
        """set_status can set failure reason."""
        state = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            worktree_name="main",
            workflow_status="in_progress",
        )
        await repository.create(state)

        await repository.set_status(state.id, "failed", failure_reason="Something went wrong")

        retrieved = await repository.get(state.id)
        assert retrieved.workflow_status == "failed"
        assert retrieved.failure_reason == "Something went wrong"

    @pytest.mark.asyncio
    async def test_list_active_workflows(self, repository):
        """Can list all active workflows."""
        # Create various workflows
        active1 = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-1",
            worktree_path="/repo1",
            worktree_name="main",
            workflow_status="in_progress",
        )
        active2 = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-2",
            worktree_path="/repo2",
            worktree_name="feat",
            workflow_status="blocked",
        )
        completed = ServerExecutionState(
            id=str(uuid4()),
            issue_id="ISSUE-3",
            worktree_path="/repo3",
            worktree_name="old",
            workflow_status="completed",
        )

        await repository.create(active1)
        await repository.create(active2)
        await repository.create(completed)

        active = await repository.list_active()
        assert len(active) == 2
        ids = {w.id for w in active}
        assert active1.id in ids
        assert active2.id in ids

    @pytest.mark.asyncio
    async def test_count_active_workflows(self, repository):
        """Can count active workflows."""
        for i in range(3):
            state = ServerExecutionState(
                id=str(uuid4()),
                issue_id=f"ISSUE-{i}",
                worktree_path=f"/repo{i}",
                worktree_name=f"wt{i}",
                workflow_status="in_progress",
            )
            await repository.create(state)

        count = await repository.count_active()
        assert count == 3
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_repository.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement WorkflowRepository**

```python
# amelia/server/database/repository.py
"""Repository for workflow persistence operations."""
from datetime import UTC, datetime

from amelia.server.database.connection import Database
from amelia.server.models.state import (
    InvalidStateTransitionError,
    ServerExecutionState,
    WorkflowStatus,
    validate_transition,
)


class WorkflowNotFoundError(Exception):
    """Raised when workflow ID doesn't exist."""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        super().__init__(f"Workflow not found: {workflow_id}")


class WorkflowRepository:
    """Repository for workflow CRUD operations.

    Handles persistence and retrieval of workflow state,
    with state machine validation on status transitions.
    """

    def __init__(self, db: Database):
        """Initialize repository.

        Args:
            db: Database connection.
        """
        self._db = db

    async def create(self, state: ServerExecutionState) -> None:
        """Create a new workflow.

        Args:
            state: Initial workflow state.
        """
        await self._db.execute(
            """
            INSERT INTO workflows (
                id, issue_id, worktree_path, worktree_name,
                status, started_at, completed_at, failure_reason, state_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.id,
                state.issue_id,
                state.worktree_path,
                state.worktree_name,
                state.workflow_status,
                state.started_at,
                state.completed_at,
                state.failure_reason,
                state.model_dump_json(),
            ),
        )

    async def get(self, workflow_id: str) -> ServerExecutionState | None:
        """Get workflow by ID.

        Args:
            workflow_id: Workflow identifier.

        Returns:
            Workflow state or None if not found.
        """
        row = await self._db.fetch_one(
            "SELECT state_json FROM workflows WHERE id = ?",
            (workflow_id,),
        )
        if row is None:
            return None
        return ServerExecutionState.model_validate_json(row[0])

    async def get_by_worktree(
        self,
        worktree_path: str,
    ) -> ServerExecutionState | None:
        """Get active workflow for a worktree.

        Args:
            worktree_path: Worktree path to check.

        Returns:
            Active workflow or None if no active workflow.
        """
        row = await self._db.fetch_one(
            """
            SELECT state_json FROM workflows
            WHERE worktree_path = ?
            AND status IN ('pending', 'in_progress', 'blocked')
            """,
            (worktree_path,),
        )
        if row is None:
            return None
        return ServerExecutionState.model_validate_json(row[0])

    async def update(self, state: ServerExecutionState) -> None:
        """Update workflow state.

        Args:
            state: Updated workflow state.
        """
        await self._db.execute(
            """
            UPDATE workflows SET
                status = ?,
                started_at = ?,
                completed_at = ?,
                failure_reason = ?,
                state_json = ?
            WHERE id = ?
            """,
            (
                state.workflow_status,
                state.started_at,
                state.completed_at,
                state.failure_reason,
                state.model_dump_json(),
                state.id,
            ),
        )

    async def set_status(
        self,
        workflow_id: str,
        new_status: WorkflowStatus,
        failure_reason: str | None = None,
    ) -> None:
        """Update workflow status with state machine validation.

        Args:
            workflow_id: Workflow to update.
            new_status: Target status.
            failure_reason: Optional failure reason (for failed status).

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateTransitionError: If transition is invalid.
        """
        workflow = await self.get(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(workflow_id)

        validate_transition(workflow.workflow_status, new_status)

        # Set completed_at for terminal states
        completed_at = None
        if new_status in ("completed", "failed", "cancelled"):
            completed_at = datetime.now(UTC)

        await self._db.execute(
            """
            UPDATE workflows SET
                status = ?,
                completed_at = ?,
                failure_reason = ?,
                state_json = json_set(state_json,
                    '$.workflow_status', ?,
                    '$.completed_at', ?,
                    '$.failure_reason', ?
                )
            WHERE id = ?
            """,
            (
                new_status,
                completed_at.isoformat() if completed_at else None,
                failure_reason,
                new_status,
                completed_at.isoformat() if completed_at else None,
                failure_reason,
                workflow_id,
            ),
        )

    async def list_active(self) -> list[ServerExecutionState]:
        """List all active workflows.

        Returns:
            List of active workflows (pending, in_progress, blocked).
        """
        rows = await self._db.fetch_all(
            """
            SELECT state_json FROM workflows
            WHERE status IN ('pending', 'in_progress', 'blocked')
            ORDER BY started_at DESC
            """
        )
        return [ServerExecutionState.model_validate_json(row[0]) for row in rows]

    async def count_active(self) -> int:
        """Count active workflows.

        Returns:
            Number of active workflows.
        """
        count = await self._db.fetch_scalar(
            """
            SELECT COUNT(*) FROM workflows
            WHERE status IN ('pending', 'in_progress', 'blocked')
            """
        )
        return count if count is not None else 0

    async def find_by_status(
        self,
        statuses: list[WorkflowStatus],
    ) -> list[ServerExecutionState]:
        """Find workflows by status.

        Args:
            statuses: List of statuses to match.

        Returns:
            List of matching workflows.
        """
        placeholders = ",".join("?" for _ in statuses)
        rows = await self._db.fetch_all(
            f"""
            SELECT state_json FROM workflows
            WHERE status IN ({placeholders})
            """,
            statuses,
        )
        return [ServerExecutionState.model_validate_json(row[0]) for row in rows]
```

**Step 4: Add fetch_scalar to Database**

First, add the `fetch_scalar()` method to the Database class:

```python
# Add to amelia/server/database/connection.py in the Database class

async def fetch_scalar(self, query: str, params: tuple = ()) -> Any:
    """Fetch a single scalar value (first column of first row).

    Args:
        query: SQL query to execute.
        params: Query parameters.

    Returns:
        Single value or None if no result.
    """
    row = await self.fetch_one(query, params)
    return row[0] if row else None
```

**Step 5: Update database package init**

```python
# amelia/server/database/__init__.py
"""Database package for Amelia server."""
from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowNotFoundError, WorkflowRepository

__all__ = [
    "Database",
    "WorkflowRepository",
    "WorkflowNotFoundError",
]
```

**Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_repository.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/server/database/repository.py amelia/server/database/__init__.py tests/unit/server/database/test_repository.py
git commit -m "feat(database): add WorkflowRepository with state machine validation"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] `uv run pytest tests/unit/server/models/ -v` - All model tests pass
- [ ] `uv run pytest tests/unit/server/database/test_repository.py -v` - Repository tests pass
- [ ] `uv run ruff check amelia/server/models amelia/server/database` - No linting errors
- [ ] `uv run mypy amelia/server/models amelia/server/database` - No type errors

```python
# Quick verification in Python REPL
from datetime import datetime, UTC
from amelia.server.models import (
    EventType, WorkflowEvent, TokenUsage, calculate_token_cost,
    ServerExecutionState, validate_transition
)

# Event creation
event = WorkflowEvent(
    id="test", workflow_id="wf-1", sequence=1,
    timestamp=datetime.now(UTC), agent="system",
    event_type=EventType.WORKFLOW_STARTED, message="Test"
)

# State machine
validate_transition("pending", "in_progress")  # OK
validate_transition("pending", "completed")     # Raises InvalidStateTransitionError
```

---

## Summary

This plan creates the domain models and repository:

| Component | File | Purpose |
|-----------|------|---------|
| EventType | `amelia/server/models/events.py` | Enum of all event types |
| WorkflowEvent | `amelia/server/models/events.py` | Event model for activity log |
| TokenUsage | `amelia/server/models/tokens.py` | Token consumption tracking |
| Cost Calculation | `amelia/server/models/tokens.py` | USD cost from token counts |
| WorkflowStatus | `amelia/server/models/state.py` | Status type alias |
| State Machine | `amelia/server/models/state.py` | Transition validation |
| ServerExecutionState | `amelia/server/models/state.py` | Extended workflow state |
| WorkflowRepository | `amelia/server/database/repository.py` | CRUD with validation |

**Next PR:** REST API Workflow Endpoints (Plan 4)
