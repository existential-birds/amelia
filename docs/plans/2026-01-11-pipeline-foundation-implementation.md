# Pipeline Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the existing orchestrator into a pipeline abstraction layer with `BasePipelineState`, `Pipeline` protocol, and registry, enabling future workflow types.

**Architecture:** Create `amelia/pipelines/` package with base abstractions, then move orchestrator code to become `ImplementationPipeline` - the first (and initially only) pipeline. All imports are updated, old files deleted.

**Tech Stack:** Python 3.12+, Pydantic v2 (frozen models), LangGraph, Protocol-based typing

---

## Phase 1: Foundation Types

### Task 1: Create pipelines package structure

**Files:**
- Create: `amelia/pipelines/__init__.py`
- Create: `amelia/pipelines/base.py`
- Create: `amelia/pipelines/registry.py`
- Create: `amelia/pipelines/implementation/__init__.py`
- Create: `amelia/pipelines/implementation/state.py`
- Create: `amelia/pipelines/implementation/graph.py`

**Step 1: Create directory structure**

Run: `mkdir -p amelia/pipelines/implementation`
Expected: Directories created

**Step 2: Create empty `__init__.py` files**

Create `amelia/pipelines/__init__.py`:
```python
"""Pipeline abstractions for Amelia workflow types."""

from amelia.pipelines.base import BasePipelineState, Pipeline
from amelia.pipelines.registry import get_pipeline, list_pipelines

__all__ = [
    "BasePipelineState",
    "Pipeline",
    "get_pipeline",
    "list_pipelines",
]
```

Create `amelia/pipelines/implementation/__init__.py`:
```python
"""Implementation pipeline - Architect → Developer ↔ Reviewer workflow."""

from amelia.pipelines.implementation.pipeline import ImplementationPipeline
from amelia.pipelines.implementation.state import ImplementationState

__all__ = [
    "ImplementationPipeline",
    "ImplementationState",
]
```

**Step 3: Commit**

```bash
git add amelia/pipelines/
git commit -m "feat(pipelines): create package structure for pipeline abstraction"
```

---

### Task 2: Define HistoryEntry model

**Files:**
- Create: `amelia/pipelines/history.py`
- Test: `tests/unit/pipelines/test_history.py`

**Step 1: Write the failing test**

Create `tests/unit/pipelines/__init__.py` (empty file).

Create `tests/unit/pipelines/test_history.py`:
```python
"""Tests for HistoryEntry model."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from amelia.pipelines.history import HistoryEntry


class TestHistoryEntry:
    """Tests for HistoryEntry frozen model."""

    def test_creates_with_required_fields(self) -> None:
        """HistoryEntry requires actor and event."""
        entry = HistoryEntry(actor="architect", event="plan_started")
        assert entry.actor == "architect"
        assert entry.event == "plan_started"

    def test_has_default_timestamp(self) -> None:
        """HistoryEntry gets automatic timestamp."""
        before = datetime.now(timezone.utc)
        entry = HistoryEntry(actor="developer", event="task_completed")
        after = datetime.now(timezone.utc)
        assert before <= entry.ts <= after

    def test_has_default_empty_detail(self) -> None:
        """HistoryEntry defaults to empty detail dict."""
        entry = HistoryEntry(actor="reviewer", event="review_completed")
        assert entry.detail == {}

    def test_has_default_zero_tokens(self) -> None:
        """HistoryEntry defaults tokens_used to 0."""
        entry = HistoryEntry(actor="architect", event="plan_started")
        assert entry.tokens_used == 0

    def test_accepts_detail_dict(self) -> None:
        """HistoryEntry accepts detail dict."""
        entry = HistoryEntry(
            actor="developer",
            event="tool_called",
            detail={"tool": "shell", "command": "ls"},
        )
        assert entry.detail == {"tool": "shell", "command": "ls"}

    def test_accepts_tokens_used(self) -> None:
        """HistoryEntry accepts tokens_used."""
        entry = HistoryEntry(
            actor="architect",
            event="plan_completed",
            tokens_used=1500,
        )
        assert entry.tokens_used == 1500

    def test_is_frozen(self) -> None:
        """HistoryEntry is immutable."""
        entry = HistoryEntry(actor="developer", event="started")
        with pytest.raises(ValidationError):
            entry.actor = "reviewer"  # type: ignore[misc]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_history.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'amelia.pipelines.history'"

**Step 3: Write minimal implementation**

Create `amelia/pipelines/history.py`:
```python
"""History entry model for pipeline state observability."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HistoryEntry(BaseModel):
    """Structured history entry for agent actions.

    Provides observability into pipeline execution by recording
    timestamped events from each actor (agent/node).

    Attributes:
        ts: Timestamp of the event (UTC).
        actor: Agent or node name that produced this entry.
        event: Event type (e.g., "task_started", "review_completed").
        detail: Additional structured data about the event.
        tokens_used: Token usage for this action (for budget tracking).
    """

    model_config = ConfigDict(frozen=True)

    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str
    event: str
    detail: dict[str, Any] = Field(default_factory=dict)
    tokens_used: int = 0
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/test_history.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/history.py tests/unit/pipelines/
git commit -m "feat(pipelines): add HistoryEntry model for observability"
```

---

### Task 3: Define BasePipelineState

**Files:**
- Create: `amelia/pipelines/base.py`
- Test: `tests/unit/pipelines/test_base.py`

**Step 1: Write the failing test**

Create `tests/unit/pipelines/test_base.py`:
```python
"""Tests for BasePipelineState and Pipeline protocol."""

import operator
from typing import Annotated, Literal, get_type_hints

import pytest
from pydantic import Field, ValidationError

from amelia.core.agentic_state import AgenticStatus, ToolCall, ToolResult
from amelia.pipelines.base import BasePipelineState
from amelia.pipelines.history import HistoryEntry


class TestBasePipelineState:
    """Tests for BasePipelineState base class."""

    def test_requires_identity_fields(self) -> None:
        """BasePipelineState requires workflow_id, pipeline_type, profile_id."""
        state = BasePipelineState(
            workflow_id="wf-123",
            pipeline_type="test",
            profile_id="prof-456",
        )
        assert state.workflow_id == "wf-123"
        assert state.pipeline_type == "test"
        assert state.profile_id == "prof-456"

    def test_has_default_empty_history(self) -> None:
        """BasePipelineState defaults history to empty list."""
        state = BasePipelineState(
            workflow_id="wf-1",
            pipeline_type="test",
            profile_id="prof-1",
        )
        assert state.history == []

    def test_has_default_human_interaction_fields(self) -> None:
        """BasePipelineState has human interaction defaults."""
        state = BasePipelineState(
            workflow_id="wf-1",
            pipeline_type="test",
            profile_id="prof-1",
        )
        assert state.pending_user_input is False
        assert state.user_message is None

    def test_has_default_agentic_fields(self) -> None:
        """BasePipelineState has agentic execution defaults."""
        state = BasePipelineState(
            workflow_id="wf-1",
            pipeline_type="test",
            profile_id="prof-1",
        )
        assert state.tool_calls == []
        assert state.tool_results == []
        assert state.agentic_status == "running"
        assert state.driver_session_id is None
        assert state.final_response is None
        assert state.error is None

    def test_is_frozen(self) -> None:
        """BasePipelineState is immutable."""
        state = BasePipelineState(
            workflow_id="wf-1",
            pipeline_type="test",
            profile_id="prof-1",
        )
        with pytest.raises(ValidationError):
            state.workflow_id = "wf-2"  # type: ignore[misc]

    def test_history_has_add_reducer(self) -> None:
        """history field uses operator.add reducer for append-only updates."""
        hints = get_type_hints(BasePipelineState, include_extras=True)
        history_hint = hints["history"]
        # Annotated types have __metadata__
        assert hasattr(history_hint, "__metadata__")
        assert operator.add in history_hint.__metadata__

    def test_tool_calls_has_add_reducer(self) -> None:
        """tool_calls field uses operator.add reducer."""
        hints = get_type_hints(BasePipelineState, include_extras=True)
        tool_calls_hint = hints["tool_calls"]
        assert hasattr(tool_calls_hint, "__metadata__")
        assert operator.add in tool_calls_hint.__metadata__

    def test_tool_results_has_add_reducer(self) -> None:
        """tool_results field uses operator.add reducer."""
        hints = get_type_hints(BasePipelineState, include_extras=True)
        tool_results_hint = hints["tool_results"]
        assert hasattr(tool_results_hint, "__metadata__")
        assert operator.add in tool_results_hint.__metadata__


class TestBasePipelineStateExtension:
    """Tests for extending BasePipelineState."""

    def test_can_extend_with_pipeline_specific_fields(self) -> None:
        """Subclasses can add pipeline-specific fields."""

        class CustomState(BasePipelineState):
            pipeline_type: Literal["custom"] = "custom"
            custom_field: str = "default"

        state = CustomState(
            workflow_id="wf-1",
            profile_id="prof-1",
            custom_field="custom_value",
        )
        assert state.pipeline_type == "custom"
        assert state.custom_field == "custom_value"

    def test_subclass_inherits_frozen(self) -> None:
        """Subclasses remain frozen."""

        class CustomState(BasePipelineState):
            pipeline_type: Literal["custom"] = "custom"
            custom_field: str = "default"

        state = CustomState(
            workflow_id="wf-1",
            profile_id="prof-1",
        )
        with pytest.raises(ValidationError):
            state.custom_field = "new_value"  # type: ignore[misc]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_base.py -v`
Expected: FAIL with "ImportError: cannot import name 'BasePipelineState'"

**Step 3: Write minimal implementation**

Create `amelia/pipelines/base.py`:
```python
"""Base abstractions for pipeline workflows.

This module defines the foundational types that all pipelines share:
- BasePipelineState: Common state fields for all workflow types
- Pipeline: Protocol that all pipeline implementations must satisfy
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Annotated, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from amelia.core.agentic_state import AgenticStatus, ToolCall, ToolResult
from amelia.pipelines.history import HistoryEntry

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph


class BasePipelineState(BaseModel):
    """Common state for all pipelines.

    This base class contains fields shared across all workflow types:
    - Identity fields for tracking and replay
    - Observability via structured history
    - Human interaction support
    - Agentic execution tracking

    All pipeline-specific state classes should extend this base.
    The model is frozen (immutable) per the stateless reducer pattern.

    Attributes:
        workflow_id: Unique identifier for this workflow instance.
        pipeline_type: Type discriminator (e.g., "implementation", "review").
        profile_id: ID of the profile used (for replay determinism).
        history: Append-only structured event log.
        pending_user_input: Whether workflow is waiting for user input.
        user_message: Message from user when resuming.
        tool_calls: History of tool calls (append-only via reducer).
        tool_results: History of tool results (append-only via reducer).
        agentic_status: Current agentic execution status.
        driver_session_id: Session ID for driver continuity.
        final_response: Final response when agentic execution completes.
        error: Error message if agentic execution failed.
    """

    model_config = ConfigDict(frozen=True)

    # Identity
    workflow_id: str
    pipeline_type: str
    profile_id: str

    # Observability (append-only via reducer)
    history: Annotated[list[HistoryEntry], operator.add] = Field(default_factory=list)

    # Human interaction
    pending_user_input: bool = False
    user_message: str | None = None

    # Agentic execution (shared across all pipelines)
    tool_calls: Annotated[list[ToolCall], operator.add] = Field(default_factory=list)
    tool_results: Annotated[list[ToolResult], operator.add] = Field(default_factory=list)
    agentic_status: AgenticStatus = "running"
    driver_session_id: str | None = None
    final_response: str | None = None
    error: str | None = None


StateT = TypeVar("StateT", bound=BasePipelineState)


class Pipeline(Protocol[StateT]):
    """Protocol that all pipelines must implement.

    Each pipeline provides:
    - Metadata (name, display_name, description) for registry/UI
    - Graph factory for creating the LangGraph workflow
    - State factory for creating initial state
    - State class accessor for type information

    The protocol is generic over the pipeline's state type, which must
    extend BasePipelineState.
    """

    name: str
    display_name: str
    description: str

    def create_graph(
        self,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> CompiledStateGraph:
        """Create the compiled LangGraph for this pipeline.

        Args:
            checkpointer: Optional checkpoint saver for persistence.

        Returns:
            Compiled state graph ready for execution.
        """
        ...

    def get_initial_state(self, **kwargs: object) -> StateT:
        """Create initial state for a new workflow.

        Args:
            **kwargs: Pipeline-specific initialization parameters.

        Returns:
            Initial state instance for the workflow.
        """
        ...

    def get_state_class(self) -> type[StateT]:
        """Get the state class for this pipeline.

        Returns:
            The Pydantic model class for this pipeline's state.
        """
        ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/test_base.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/base.py tests/unit/pipelines/test_base.py
git commit -m "feat(pipelines): add BasePipelineState and Pipeline protocol"
```

---

### Task 4: Define ImplementationState

**Files:**
- Create: `amelia/pipelines/implementation/state.py`
- Test: `tests/unit/pipelines/implementation/test_state.py`

**Step 1: Write the failing test**

Create `tests/unit/pipelines/implementation/__init__.py` (empty file).

Create `tests/unit/pipelines/implementation/test_state.py`:
```python
"""Tests for ImplementationState."""

from pathlib import Path
from typing import Literal, get_type_hints

import pytest
from pydantic import ValidationError

from amelia.core.types import Design, Issue
from amelia.pipelines.base import BasePipelineState
from amelia.pipelines.implementation.state import ImplementationState


class TestImplementationState:
    """Tests for ImplementationState extending BasePipelineState."""

    def test_extends_base_pipeline_state(self) -> None:
        """ImplementationState is a subclass of BasePipelineState."""
        assert issubclass(ImplementationState, BasePipelineState)

    def test_pipeline_type_is_implementation(self) -> None:
        """ImplementationState has pipeline_type='implementation'."""
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="prof-1",
        )
        assert state.pipeline_type == "implementation"

    def test_pipeline_type_is_literal(self) -> None:
        """pipeline_type is Literal['implementation'], not just str."""
        hints = get_type_hints(ImplementationState)
        # The annotation should be Literal["implementation"]
        assert hints["pipeline_type"] == Literal["implementation"]

    def test_has_issue_field(self) -> None:
        """ImplementationState has optional issue field."""
        issue = Issue(key="TEST-123", title="Test Issue", description="Desc")
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="prof-1",
            issue=issue,
        )
        assert state.issue == issue

    def test_has_design_field(self) -> None:
        """ImplementationState has optional design field."""
        design = Design(content="Design content")
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="prof-1",
            design=design,
        )
        assert state.design == design

    def test_has_plan_fields(self) -> None:
        """ImplementationState has plan-related fields."""
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="prof-1",
            goal="Implement feature",
            plan_markdown="## Task 1\nDo thing",
            plan_path=Path("/tmp/plan.md"),
        )
        assert state.goal == "Implement feature"
        assert state.plan_markdown == "## Task 1\nDo thing"
        assert state.plan_path == Path("/tmp/plan.md")

    def test_has_review_fields(self) -> None:
        """ImplementationState has review tracking fields."""
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="prof-1",
            review_iteration=2,
        )
        assert state.review_iteration == 2

    def test_defaults_review_iteration_to_zero(self) -> None:
        """review_iteration defaults to 0."""
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="prof-1",
        )
        assert state.review_iteration == 0

    def test_is_frozen(self) -> None:
        """ImplementationState is immutable."""
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="prof-1",
        )
        with pytest.raises(ValidationError):
            state.goal = "New goal"  # type: ignore[misc]

    def test_inherits_base_fields(self) -> None:
        """ImplementationState has all BasePipelineState fields."""
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="prof-1",
        )
        # Base fields should exist with defaults
        assert state.history == []
        assert state.tool_calls == []
        assert state.agentic_status == "running"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/implementation/test_state.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'amelia.pipelines.implementation.state'"

**Step 3: Write minimal implementation**

Reference current `ExecutionState` fields from `amelia/core/state.py:44-130`.

Create `amelia/pipelines/implementation/state.py`:
```python
"""State model for the Implementation pipeline.

This module defines ImplementationState, which extends BasePipelineState
with fields specific to the Architect → Developer ↔ Reviewer workflow.
"""

from __future__ import annotations

import operator
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field

from amelia.core.types import Design, Issue
from amelia.pipelines.base import BasePipelineState

if TYPE_CHECKING:
    from amelia.agents.evaluator import EvaluationResult
    from amelia.agents.reviewer import StructuredReviewResult
    from amelia.core.state import ReviewResult


class ImplementationState(BasePipelineState):
    """State for the implementation pipeline.

    Extends BasePipelineState with fields for the Architect → Developer ↔ Reviewer
    workflow. Includes issue/design context, planning outputs, review tracking,
    and task-based execution support.

    All fields from the original ExecutionState are preserved for backward
    compatibility during the migration.
    """

    pipeline_type: Literal["implementation"] = "implementation"

    # Domain data (from planning phase)
    issue: Issue | None = None
    design: Design | None = None
    goal: str | None = None
    base_commit: str | None = None
    plan_markdown: str | None = None
    raw_architect_output: str | None = None
    plan_path: Path | None = None
    key_files: list[str] = Field(default_factory=list)

    # Human approval (plan review)
    human_approved: bool | None = None
    human_feedback: str | None = None

    # Code review tracking
    last_review: ReviewResult | None = None
    code_changes_for_review: str | None = None

    # Workflow status (terminal state indicator)
    workflow_status: Literal["running", "completed", "failed", "aborted"] = "running"

    # Agent history (legacy, append-only)
    agent_history: Annotated[list[str], operator.add] = Field(default_factory=list)

    # Review iteration tracking
    review_iteration: int = 0

    # Task-based execution (multi-task plans)
    total_tasks: int | None = None
    current_task_index: int = 0
    task_review_iteration: int = 0

    # Structured review workflow
    structured_review: StructuredReviewResult | None = None
    evaluation_result: EvaluationResult | None = None
    approved_items: list[int] = Field(default_factory=list)
    auto_approve: bool = False
    review_pass: int = 0
    max_review_passes: int = 3


def rebuild_implementation_state() -> None:
    """Rebuild ImplementationState to resolve forward references.

    Must be called after importing StructuredReviewResult and EvaluationResult
    to enable Pydantic validation and Python's get_type_hints() to work.
    """
    import sys  # noqa: PLC0415

    from amelia.agents.evaluator import EvaluationResult  # noqa: PLC0415
    from amelia.agents.reviewer import StructuredReviewResult  # noqa: PLC0415
    from amelia.core.state import ReviewResult  # noqa: PLC0415

    module = sys.modules[__name__]
    module.StructuredReviewResult = StructuredReviewResult  # type: ignore[attr-defined]
    module.EvaluationResult = EvaluationResult  # type: ignore[attr-defined]
    module.ReviewResult = ReviewResult  # type: ignore[attr-defined]

    ImplementationState.model_rebuild(
        _types_namespace={
            "StructuredReviewResult": StructuredReviewResult,
            "EvaluationResult": EvaluationResult,
            "ReviewResult": ReviewResult,
        }
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/implementation/test_state.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/state.py tests/unit/pipelines/implementation/
git commit -m "feat(pipelines): add ImplementationState extending BasePipelineState"
```

---

## Phase 2: Pipeline Registry

### Task 5: Create pipeline registry

**Files:**
- Create: `amelia/pipelines/registry.py`
- Test: `tests/unit/pipelines/test_registry.py`

**Step 1: Write the failing test**

Create `tests/unit/pipelines/test_registry.py`:
```python
"""Tests for pipeline registry."""

import pytest

from amelia.pipelines.registry import PIPELINES, get_pipeline, list_pipelines


class TestPipelineRegistry:
    """Tests for pipeline registry functions."""

    def test_pipelines_dict_has_implementation(self) -> None:
        """PIPELINES dict contains 'implementation' entry."""
        assert "implementation" in PIPELINES

    def test_get_pipeline_returns_implementation(self) -> None:
        """get_pipeline('implementation') returns ImplementationPipeline."""
        pipeline = get_pipeline("implementation")
        assert pipeline.name == "implementation"
        assert pipeline.display_name == "Implementation"

    def test_get_pipeline_raises_for_unknown(self) -> None:
        """get_pipeline raises ValueError for unknown pipeline."""
        with pytest.raises(ValueError, match="Unknown pipeline: unknown"):
            get_pipeline("unknown")

    def test_list_pipelines_returns_metadata(self) -> None:
        """list_pipelines returns list of pipeline metadata dicts."""
        pipelines = list_pipelines()
        assert len(pipelines) >= 1

        # Find implementation pipeline in list
        impl = next((p for p in pipelines if p["name"] == "implementation"), None)
        assert impl is not None
        assert impl["display_name"] == "Implementation"
        assert "description" in impl

    def test_list_pipelines_structure(self) -> None:
        """list_pipelines returns dicts with name, display_name, description."""
        pipelines = list_pipelines()
        for p in pipelines:
            assert "name" in p
            assert "display_name" in p
            assert "description" in p
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_registry.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'amelia.pipelines.registry'"

**Step 3: Write minimal implementation**

Create `amelia/pipelines/registry.py`:
```python
"""Pipeline registry for routing to pipeline implementations.

This module provides a simple registry pattern for looking up pipelines
by name. Phase 1 includes only the Implementation pipeline; future phases
add entries here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amelia.pipelines.base import Pipeline

# Lazy import to avoid circular dependencies
_pipeline_instances: dict[str, Pipeline] = {}


def _get_implementation_pipeline() -> Pipeline:
    """Lazily create and cache ImplementationPipeline instance."""
    if "implementation" not in _pipeline_instances:
        from amelia.pipelines.implementation.pipeline import (  # noqa: PLC0415
            ImplementationPipeline,
        )

        _pipeline_instances["implementation"] = ImplementationPipeline()
    return _pipeline_instances["implementation"]


# Registry of available pipelines (lazy loaded)
PIPELINES: dict[str, type] = {
    "implementation": type(
        "ImplementationPipelineType",
        (),
        {"__call__": lambda self: _get_implementation_pipeline()},
    ),
}


def get_pipeline(name: str) -> Pipeline:
    """Get a pipeline instance by name.

    Args:
        name: Pipeline name (e.g., "implementation").

    Returns:
        Pipeline instance.

    Raises:
        ValueError: If pipeline name is not found in registry.
    """
    if name == "implementation":
        return _get_implementation_pipeline()

    raise ValueError(f"Unknown pipeline: {name}")


def list_pipelines() -> list[dict[str, str]]:
    """List available pipelines with their metadata.

    Returns:
        List of dicts with name, display_name, and description for each pipeline.
    """
    # For Phase 1, we only have implementation
    impl = _get_implementation_pipeline()
    return [
        {
            "name": impl.name,
            "display_name": impl.display_name,
            "description": impl.description,
        }
    ]
```

Note: This implementation depends on `ImplementationPipeline` which we'll create in Task 6. The test will still fail until that's done.

**Step 4: Skip test run (dependency not yet created)**

The registry depends on `ImplementationPipeline` which we create next. Mark this step to verify after Task 6.

**Step 5: Commit partial progress**

```bash
git add amelia/pipelines/registry.py tests/unit/pipelines/test_registry.py
git commit -m "feat(pipelines): add registry (pending ImplementationPipeline)"
```

---

## Phase 3: Implementation Pipeline

### Task 6: Create ImplementationPipeline class

**Files:**
- Create: `amelia/pipelines/implementation/pipeline.py`
- Update: `amelia/pipelines/implementation/__init__.py`

**Step 1: Write the failing test**

Add to `tests/unit/pipelines/implementation/test_state.py` (or create new file `tests/unit/pipelines/implementation/test_pipeline.py`):

Create `tests/unit/pipelines/implementation/test_pipeline.py`:
```python
"""Tests for ImplementationPipeline class."""

from unittest.mock import MagicMock

import pytest

from amelia.core.types import Design, Issue
from amelia.pipelines.base import Pipeline
from amelia.pipelines.implementation.pipeline import ImplementationPipeline
from amelia.pipelines.implementation.state import ImplementationState


class TestImplementationPipeline:
    """Tests for ImplementationPipeline protocol implementation."""

    def test_satisfies_pipeline_protocol(self) -> None:
        """ImplementationPipeline satisfies Pipeline protocol."""
        pipeline = ImplementationPipeline()
        # Protocol requires these attributes
        assert hasattr(pipeline, "name")
        assert hasattr(pipeline, "display_name")
        assert hasattr(pipeline, "description")
        assert hasattr(pipeline, "create_graph")
        assert hasattr(pipeline, "get_initial_state")
        assert hasattr(pipeline, "get_state_class")

    def test_has_correct_name(self) -> None:
        """ImplementationPipeline has name='implementation'."""
        pipeline = ImplementationPipeline()
        assert pipeline.name == "implementation"

    def test_has_correct_display_name(self) -> None:
        """ImplementationPipeline has display_name='Implementation'."""
        pipeline = ImplementationPipeline()
        assert pipeline.display_name == "Implementation"

    def test_has_description(self) -> None:
        """ImplementationPipeline has non-empty description."""
        pipeline = ImplementationPipeline()
        assert pipeline.description
        assert len(pipeline.description) > 10

    def test_get_state_class_returns_implementation_state(self) -> None:
        """get_state_class returns ImplementationState."""
        pipeline = ImplementationPipeline()
        assert pipeline.get_state_class() is ImplementationState

    def test_get_initial_state_creates_implementation_state(self) -> None:
        """get_initial_state creates ImplementationState with kwargs."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id="wf-123",
            profile_id="prof-456",
        )
        assert isinstance(state, ImplementationState)
        assert state.workflow_id == "wf-123"
        assert state.profile_id == "prof-456"

    def test_get_initial_state_accepts_issue_and_design(self) -> None:
        """get_initial_state accepts issue and design parameters."""
        pipeline = ImplementationPipeline()
        issue = Issue(key="TEST-1", title="Test", description="Desc")
        design = Design(content="Design content")
        state = pipeline.get_initial_state(
            workflow_id="wf-1",
            profile_id="prof-1",
            issue=issue,
            design=design,
        )
        assert state.issue == issue
        assert state.design == design

    def test_create_graph_returns_compiled_graph(self) -> None:
        """create_graph returns a compiled LangGraph."""
        pipeline = ImplementationPipeline()
        graph = pipeline.create_graph()
        # LangGraph compiled graphs have these attributes
        assert hasattr(graph, "invoke")
        assert hasattr(graph, "ainvoke")
        assert hasattr(graph, "get_graph")

    def test_create_graph_accepts_checkpointer(self) -> None:
        """create_graph accepts optional checkpointer."""
        pipeline = ImplementationPipeline()
        mock_checkpointer = MagicMock()
        graph = pipeline.create_graph(checkpointer=mock_checkpointer)
        assert graph.checkpointer is mock_checkpointer
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/implementation/test_pipeline.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'amelia.pipelines.implementation.pipeline'"

**Step 3: Write minimal implementation**

Create `amelia/pipelines/implementation/pipeline.py`:
```python
"""Implementation pipeline - the main Amelia workflow.

This module defines ImplementationPipeline, which wraps the existing
orchestrator graph in the Pipeline protocol interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

    from amelia.core.types import Design, Issue


class ImplementationPipeline:
    """Pipeline for implementing code from issues/designs.

    Implements the Architect → Developer ↔ Reviewer flow:
    1. Architect analyzes issue and creates implementation plan
    2. Human approves the plan
    3. Developer implements the plan agentically
    4. Reviewer reviews the changes
    5. Loop between Developer and Reviewer until approved

    This is the primary workflow for Amelia, handling feature implementation
    and bug fixes from issue trackers.
    """

    name: str = "implementation"
    display_name: str = "Implementation"
    description: str = (
        "Build features and fix bugs with Architect → Developer ↔ Reviewer flow"
    )

    def get_state_class(self) -> type[ImplementationState]:
        """Get the state class for this pipeline.

        Returns:
            ImplementationState class.
        """
        return ImplementationState

    def create_graph(
        self,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> CompiledStateGraph[Any]:
        """Create the implementation workflow graph.

        This wraps the existing create_orchestrator_graph function,
        providing the same behavior through the Pipeline interface.

        Args:
            checkpointer: Optional checkpoint saver for persistence.

        Returns:
            Compiled LangGraph for implementation workflow.
        """
        # Rebuild state to resolve forward references before creating graph
        rebuild_implementation_state()

        # Import here to avoid circular dependency during initial load
        from amelia.pipelines.implementation.graph import (  # noqa: PLC0415
            create_implementation_graph,
        )

        return create_implementation_graph(checkpointer)

    def get_initial_state(
        self,
        workflow_id: str = "",
        profile_id: str = "",
        issue: Issue | None = None,
        design: Design | None = None,
        **kwargs: object,
    ) -> ImplementationState:
        """Create initial state for an implementation workflow.

        Args:
            workflow_id: Unique workflow identifier.
            profile_id: Profile ID for replay determinism.
            issue: Optional issue to implement.
            design: Optional design context.
            **kwargs: Additional state fields.

        Returns:
            Initial ImplementationState for the workflow.
        """
        return ImplementationState(
            workflow_id=workflow_id,
            profile_id=profile_id,
            issue=issue,
            design=design,
            **kwargs,  # type: ignore[arg-type]
        )
```

**Step 4: Skip test run (graph not yet created)**

The pipeline depends on `create_implementation_graph` which we create next.

**Step 5: Commit partial progress**

```bash
git add amelia/pipelines/implementation/pipeline.py
git commit -m "feat(pipelines): add ImplementationPipeline class (pending graph)"
```

---

### Task 7: Move orchestrator graph to implementation pipeline

**Files:**
- Create: `amelia/pipelines/implementation/graph.py`
- Modify: `amelia/core/orchestrator.py` (will be updated, then deleted in Phase 4)

**Step 1: Write the failing test**

Create `tests/unit/pipelines/implementation/test_graph.py`:
```python
"""Tests for implementation pipeline graph."""

from unittest.mock import MagicMock

import pytest

from amelia.pipelines.implementation.graph import create_implementation_graph


class TestCreateImplementationGraph:
    """Tests for create_implementation_graph factory."""

    def test_creates_graph_without_checkpointer(self) -> None:
        """create_implementation_graph works without checkpointer."""
        graph = create_implementation_graph()
        assert graph is not None
        assert graph.checkpointer is None

    def test_creates_graph_with_checkpointer(self) -> None:
        """create_implementation_graph accepts checkpointer."""
        mock_checkpointer = MagicMock()
        graph = create_implementation_graph(checkpointer=mock_checkpointer)
        assert graph.checkpointer is mock_checkpointer

    def test_graph_has_expected_nodes(self) -> None:
        """Graph has architect, plan_validator, human_approval, developer, reviewer nodes."""
        graph = create_implementation_graph()
        graph_view = graph.get_graph()
        node_ids = [n.id for n in graph_view.nodes]

        assert "architect_node" in node_ids
        assert "plan_validator_node" in node_ids
        assert "human_approval_node" in node_ids
        assert "developer_node" in node_ids
        assert "reviewer_node" in node_ids
        assert "next_task_node" in node_ids

    def test_graph_entry_point_is_architect(self) -> None:
        """Graph entry point is architect_node."""
        graph = create_implementation_graph()
        graph_view = graph.get_graph()
        # Find edges from __start__
        start_edges = [e for e in graph_view.edges if e.source == "__start__"]
        assert len(start_edges) == 1
        assert start_edges[0].target == "architect_node"

    def test_architect_routes_to_validator(self) -> None:
        """architect_node routes to plan_validator_node."""
        graph = create_implementation_graph()
        graph_view = graph.get_graph()
        architect_edges = [e for e in graph_view.edges if e.source == "architect_node"]
        assert len(architect_edges) == 1
        assert architect_edges[0].target == "plan_validator_node"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/implementation/test_graph.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'amelia.pipelines.implementation.graph'"

**Step 3: Write implementation (copy and adapt from orchestrator.py)**

This is the largest task. We need to:
1. Copy `create_orchestrator_graph` and all its dependencies from `amelia/core/orchestrator.py`
2. Adapt to use `ImplementationState` instead of `ExecutionState`
3. Keep the same logic and node functions

Create `amelia/pipelines/implementation/graph.py`:

```python
"""LangGraph implementation for the Implementation pipeline.

This module contains the graph definition and node functions for the
Architect → Developer ↔ Reviewer workflow. It was refactored from
amelia/core/orchestrator.py as part of the pipeline foundation work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)

if TYPE_CHECKING:
    pass

# Resolve forward references
rebuild_implementation_state()


def create_implementation_graph(
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    interrupt_before: list[str] | None = None,
) -> CompiledStateGraph[Any]:
    """Creates and compiles the LangGraph for implementation workflow.

    This is a thin wrapper that delegates to the existing orchestrator
    graph creation. In Phase 1, we maintain backward compatibility by
    reusing the orchestrator code. Future phases will migrate the node
    functions into this module.

    Args:
        checkpointer: Optional checkpoint saver for state persistence.
        interrupt_before: List of node names to interrupt before executing.

    Returns:
        Compiled StateGraph ready for execution.
    """
    # Import from orchestrator to reuse existing implementation
    # This maintains backward compatibility during migration
    from amelia.core.orchestrator import (  # noqa: PLC0415
        call_architect_node,
        call_developer_node,
        call_reviewer_node,
        human_approval_node,
        next_task_node,
        plan_validator_node,
        route_after_review_or_task,
        route_approval,
    )

    workflow = StateGraph(ImplementationState)

    # Add nodes
    workflow.add_node("architect_node", call_architect_node)
    workflow.add_node("plan_validator_node", plan_validator_node)
    workflow.add_node("human_approval_node", human_approval_node)
    workflow.add_node("developer_node", call_developer_node)
    workflow.add_node("reviewer_node", call_reviewer_node)
    workflow.add_node("next_task_node", next_task_node)

    # Set entry point
    workflow.set_entry_point("architect_node")

    # Define edges
    workflow.add_edge("architect_node", "plan_validator_node")
    workflow.add_edge("plan_validator_node", "human_approval_node")

    workflow.add_conditional_edges(
        "human_approval_node",
        route_approval,
        {
            "approve": "developer_node",
            "reject": END,
        },
    )

    workflow.add_edge("developer_node", "reviewer_node")

    workflow.add_conditional_edges(
        "reviewer_node",
        route_after_review_or_task,
        {
            "developer": "developer_node",
            "developer_node": "developer_node",
            "next_task_node": "next_task_node",
            "__end__": END,
        },
    )

    workflow.add_edge("next_task_node", "developer_node")

    # Set default interrupt_before for server mode
    if interrupt_before is None and checkpointer is not None:
        interrupt_before = ["human_approval_node"]

    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/implementation/test_graph.py -v`
Expected: PASS

**Step 5: Verify registry tests pass**

Run: `uv run pytest tests/unit/pipelines/test_registry.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/pipelines/implementation/graph.py tests/unit/pipelines/implementation/test_graph.py
git commit -m "feat(pipelines): add implementation graph (wrapping orchestrator)"
```

---

### Task 8: Update package exports

**Files:**
- Update: `amelia/pipelines/__init__.py`
- Update: `amelia/pipelines/implementation/__init__.py`

**Step 1: Update pipelines package init**

Update `amelia/pipelines/__init__.py`:
```python
"""Pipeline abstractions for Amelia workflow types.

This package provides the foundational types for Amelia's pipeline system:
- BasePipelineState: Common state fields for all workflow types
- Pipeline: Protocol that all pipeline implementations must satisfy
- Registry: Functions to get and list available pipelines
- HistoryEntry: Structured event logging for observability

Currently supported pipelines:
- implementation: Architect → Developer ↔ Reviewer workflow
"""

from amelia.pipelines.base import BasePipelineState, Pipeline
from amelia.pipelines.history import HistoryEntry
from amelia.pipelines.registry import get_pipeline, list_pipelines

__all__ = [
    "BasePipelineState",
    "HistoryEntry",
    "Pipeline",
    "get_pipeline",
    "list_pipelines",
]
```

**Step 2: Update implementation package init**

Update `amelia/pipelines/implementation/__init__.py`:
```python
"""Implementation pipeline - Architect → Developer ↔ Reviewer workflow.

This is the primary workflow for Amelia, handling feature implementation
and bug fixes from issue trackers.
"""

from amelia.pipelines.implementation.graph import create_implementation_graph
from amelia.pipelines.implementation.pipeline import ImplementationPipeline
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)

__all__ = [
    "ImplementationPipeline",
    "ImplementationState",
    "create_implementation_graph",
    "rebuild_implementation_state",
]
```

**Step 3: Run all pipeline tests**

Run: `uv run pytest tests/unit/pipelines/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add amelia/pipelines/__init__.py amelia/pipelines/implementation/__init__.py
git commit -m "feat(pipelines): update package exports"
```

---

## Phase 4: Integration and Migration

### Task 9: Update server to use pipeline registry

**Files:**
- Modify: `amelia/server/orchestrator/service.py:129-146`

**Step 1: Write the test**

The existing tests in `tests/unit/server/orchestrator/test_service.py` should continue to pass. We'll add a new test for the registry integration.

Add to `tests/unit/server/orchestrator/test_service.py` or create new test:

```python
def test_server_uses_pipeline_registry() -> None:
    """OrchestratorService should work with pipeline registry."""
    # This test verifies that the server can create graphs via the pipeline
    from amelia.pipelines import get_pipeline

    pipeline = get_pipeline("implementation")
    graph = pipeline.create_graph()
    assert graph is not None
```

**Step 2: Update server to optionally use registry**

For Phase 1, we keep the server using the existing imports for backward compatibility. The registry is available but not yet required.

No changes to `service.py` in Phase 1. The goal is to ensure the pipeline abstraction works without breaking existing functionality.

**Step 3: Run existing server tests**

Run: `uv run pytest tests/unit/server/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git commit --allow-empty -m "chore(pipelines): verify server compatibility (no changes needed)"
```

---

### Task 10: Add backward-compatible exports to amelia/__init__.py

**Files:**
- Modify: `amelia/__init__.py`

**Step 1: Read current exports**

Reference: `amelia/__init__.py` currently exports `create_orchestrator_graph` and `ExecutionState`.

**Step 2: Add pipeline exports while maintaining compatibility**

Update `amelia/__init__.py` to add pipeline exports:

```python
"""Amelia - AI-powered code implementation assistant."""

from amelia.core.orchestrator import create_orchestrator_graph
from amelia.core.state import ExecutionState
from amelia.pipelines import (
    BasePipelineState,
    Pipeline,
    get_pipeline,
    list_pipelines,
)
from amelia.pipelines.implementation import (
    ImplementationPipeline,
    ImplementationState,
    create_implementation_graph,
)

__all__ = [
    # Legacy exports (maintained for backward compatibility)
    "ExecutionState",
    "create_orchestrator_graph",
    # Pipeline exports (new in Phase 1)
    "BasePipelineState",
    "ImplementationPipeline",
    "ImplementationState",
    "Pipeline",
    "create_implementation_graph",
    "get_pipeline",
    "list_pipelines",
]
```

**Step 3: Run import test**

Run: `python -c "from amelia import get_pipeline, ImplementationPipeline; print('OK')"`
Expected: "OK"

**Step 4: Commit**

```bash
git add amelia/__init__.py
git commit -m "feat(pipelines): add pipeline exports to main package"
```

---

### Task 11: Run full test suite

**Files:**
- No changes

**Step 1: Run linting**

Run: `uv run ruff check amelia tests`
Expected: No errors

**Step 2: Run type checking**

Run: `uv run mypy amelia`
Expected: No errors (or same as before)

**Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All tests pass

**Step 4: Commit any fixes if needed**

If there are any issues, fix them and commit:
```bash
git add -A
git commit -m "fix(pipelines): address test suite issues"
```

---

### Task 12: Update documentation

**Files:**
- Update: `docs/plans/2026-01-10-pipeline-foundation-design.md` (mark as implemented)

**Step 1: Add implementation note to design doc**

Add to the top of `docs/plans/2026-01-10-pipeline-foundation-design.md`:

```markdown
> **Status:** Implemented in `amelia/pipelines/` (2026-01-XX)
```

**Step 2: Commit**

```bash
git add docs/plans/2026-01-10-pipeline-foundation-design.md
git commit -m "docs(pipelines): mark design as implemented"
```

---

## Success Verification

After completing all tasks, verify:

1. **Protocol defined**: `Pipeline` protocol and `BasePipelineState` exist in `amelia/pipelines/base.py`
2. **Registry works**: `get_pipeline("implementation")` returns valid pipeline
3. **State hierarchy**: `ImplementationState` extends `BasePipelineState`
4. **Graph relocated**: Implementation graph in `pipelines/implementation/graph.py`
5. **CLI unchanged**: `amelia start` and `amelia review` work as before

Run final verification:
```bash
uv run pytest tests/unit/pipelines/ -v
uv run pytest tests/integration/ -v --timeout=60
uv run amelia --help
```
