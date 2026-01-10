# Queue Workflows Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable users to create workflows in `pending` state and start them later, with optional upfront planning.

**Architecture:** Extend existing `pending` status with a new `planned_at` timestamp to distinguish queue variants. Add `start` and `plan_now` parameters to workflow creation. New `POST /api/workflows/{id}/start` and batch start endpoints. CLI gains `--queue` and `--plan` flags plus new `run` command.

**Tech Stack:** Python 3.12+, Pydantic v2, FastAPI, Typer, React, TypeScript, shadcn/ui, Zustand

---

## Task 1: Add `planned_at` Field to ServerExecutionState

**Files:**
- Modify: `amelia/server/models/state.py:67-149`
- Test: `tests/unit/server/models/test_state.py`

**Step 1: Write the failing test**

Create test file if it doesn't exist:

```python
# tests/unit/server/models/test_state.py
"""Tests for server execution state models."""

from datetime import datetime, timezone

import pytest

from amelia.server.models.state import ServerExecutionState


class TestServerExecutionStatePlannedAt:
    """Tests for planned_at field."""

    def test_planned_at_defaults_to_none(self) -> None:
        """planned_at should default to None for new workflows."""
        state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-1",
            worktree_path="/path/to/repo",
            worktree_name="repo",
        )
        assert state.planned_at is None

    def test_planned_at_can_be_set(self) -> None:
        """planned_at can be set to a datetime."""
        now = datetime.now(timezone.utc)
        state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-1",
            worktree_path="/path/to/repo",
            worktree_name="repo",
            planned_at=now,
        )
        assert state.planned_at == now

    def test_is_planned_property_false_when_no_plan(self) -> None:
        """is_planned should return False when planned_at is None."""
        state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-1",
            worktree_path="/path/to/repo",
            worktree_name="repo",
        )
        assert state.is_planned is False

    def test_is_planned_property_true_when_planned(self) -> None:
        """is_planned should return True when planned_at is set."""
        state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-1",
            worktree_path="/path/to/repo",
            worktree_name="repo",
            planned_at=datetime.now(timezone.utc),
        )
        assert state.is_planned is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_state.py -v`
Expected: FAIL - `planned_at` field not found, `is_planned` property not found

**Step 3: Write minimal implementation**

In `amelia/server/models/state.py`, add to `ServerExecutionState` class (around line 100):

```python
# Add to imports at top if not present
from datetime import datetime

# Add field after completed_at (around line 100)
planned_at: datetime | None = None
"""When the Architect completed planning (if queued with plan)."""

# Add property after existing properties (around line 140)
@property
def is_planned(self) -> bool:
    """Whether this workflow has a pre-generated plan."""
    return self.planned_at is not None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_state.py -v`
Expected: PASS

**Step 5: Run full test suite to check for regressions**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add amelia/server/models/state.py tests/unit/server/models/test_state.py
git commit -m "feat(models): add planned_at field to ServerExecutionState"
```

---

## Task 2: Add Queue Parameters to CreateWorkflowRequest

**Files:**
- Modify: `amelia/server/models/requests.py:67-219`
- Test: `tests/unit/server/models/test_requests.py`

**Step 1: Write the failing tests**

```python
# tests/unit/server/models/test_requests.py
"""Tests for request models."""

import pytest
from pydantic import ValidationError

from amelia.server.models.requests import CreateWorkflowRequest


class TestCreateWorkflowRequestQueueParams:
    """Tests for queue-related parameters."""

    def test_start_defaults_to_true(self) -> None:
        """start should default to True for backward compatibility."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
        )
        assert request.start is True

    def test_plan_now_defaults_to_false(self) -> None:
        """plan_now should default to False."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
        )
        assert request.plan_now is False

    def test_queue_mode_start_false(self) -> None:
        """Setting start=False queues without immediate execution."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
        )
        assert request.start is False
        assert request.plan_now is False

    def test_queue_with_plan_mode(self) -> None:
        """Setting start=False, plan_now=True runs Architect then queues."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
            plan_now=True,
        )
        assert request.start is False
        assert request.plan_now is True

    def test_plan_now_ignored_when_start_true(self) -> None:
        """plan_now is ignored when start=True (immediate execution)."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=True,
            plan_now=True,
        )
        # Should be valid - plan_now is simply ignored
        assert request.start is True
        assert request.plan_now is True  # Stored but not used
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_requests.py::TestCreateWorkflowRequestQueueParams -v`
Expected: FAIL - `start` and `plan_now` fields not found

**Step 3: Write minimal implementation**

In `amelia/server/models/requests.py`, add to `CreateWorkflowRequest` class (around line 85):

```python
# Add after task_description field (around line 85)
start: bool = True
"""Whether to start the workflow immediately. False = queue without starting."""

plan_now: bool = False
"""If not starting, whether to run Architect immediately. Ignored if start=True."""
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_requests.py::TestCreateWorkflowRequestQueueParams -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add amelia/server/models/requests.py tests/unit/server/models/test_requests.py
git commit -m "feat(models): add start and plan_now params to CreateWorkflowRequest"
```

---

## Task 3: Add BatchStartRequest Model

**Files:**
- Modify: `amelia/server/models/requests.py`
- Test: `tests/unit/server/models/test_requests.py`

**Step 1: Write the failing tests**

Add to `tests/unit/server/models/test_requests.py`:

```python
from amelia.server.models.requests import BatchStartRequest


class TestBatchStartRequest:
    """Tests for BatchStartRequest model."""

    def test_empty_request_valid(self) -> None:
        """Empty request means start all pending workflows."""
        request = BatchStartRequest()
        assert request.workflow_ids is None
        assert request.worktree_path is None

    def test_specific_workflow_ids(self) -> None:
        """Can specify exact workflow IDs to start."""
        request = BatchStartRequest(workflow_ids=["wf-1", "wf-2", "wf-3"])
        assert request.workflow_ids == ["wf-1", "wf-2", "wf-3"]

    def test_filter_by_worktree(self) -> None:
        """Can filter by worktree path."""
        request = BatchStartRequest(worktree_path="/path/to/repo")
        assert request.worktree_path == "/path/to/repo"

    def test_combined_filter(self) -> None:
        """Can combine workflow IDs and worktree filter."""
        request = BatchStartRequest(
            workflow_ids=["wf-1", "wf-2"],
            worktree_path="/path/to/repo",
        )
        assert request.workflow_ids == ["wf-1", "wf-2"]
        assert request.worktree_path == "/path/to/repo"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_requests.py::TestBatchStartRequest -v`
Expected: FAIL - `BatchStartRequest` not found

**Step 3: Write minimal implementation**

In `amelia/server/models/requests.py`, add new class after `RejectRequest` (around line 255):

```python
class BatchStartRequest(BaseModel):
    """Request to start multiple pending workflows."""

    workflow_ids: list[str] | None = None
    """Specific workflow IDs to start, or None for all pending."""

    worktree_path: str | None = None
    """Filter by worktree path."""
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_requests.py::TestBatchStartRequest -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/requests.py tests/unit/server/models/test_requests.py
git commit -m "feat(models): add BatchStartRequest model"
```

---

## Task 4: Add BatchStartResponse Model

**Files:**
- Modify: `amelia/server/models/responses.py` (or create if needed)
- Test: `tests/unit/server/models/test_responses.py`

**Step 1: Check if responses.py exists and read it**

If file doesn't exist, create it. Otherwise, add to existing file.

**Step 2: Write the failing tests**

```python
# tests/unit/server/models/test_responses.py
"""Tests for response models."""

import pytest

from amelia.server.models.responses import BatchStartResponse


class TestBatchStartResponse:
    """Tests for BatchStartResponse model."""

    def test_all_started_success(self) -> None:
        """Response with all workflows started successfully."""
        response = BatchStartResponse(
            started=["wf-1", "wf-2", "wf-3"],
            errors={},
        )
        assert response.started == ["wf-1", "wf-2", "wf-3"]
        assert response.errors == {}

    def test_partial_success(self) -> None:
        """Response with some workflows started, some failed."""
        response = BatchStartResponse(
            started=["wf-1"],
            errors={
                "wf-2": "Worktree already has active workflow",
                "wf-3": "Workflow not found",
            },
        )
        assert response.started == ["wf-1"]
        assert len(response.errors) == 2
        assert "wf-2" in response.errors

    def test_all_failed(self) -> None:
        """Response when all workflows fail to start."""
        response = BatchStartResponse(
            started=[],
            errors={"wf-1": "Error 1", "wf-2": "Error 2"},
        )
        assert response.started == []
        assert len(response.errors) == 2

    def test_empty_response(self) -> None:
        """Response when no workflows to start."""
        response = BatchStartResponse(started=[], errors={})
        assert response.started == []
        assert response.errors == {}
```

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_responses.py -v`
Expected: FAIL - Module or class not found

**Step 4: Write minimal implementation**

Create or modify `amelia/server/models/responses.py`:

```python
"""Response models for API endpoints."""

from pydantic import BaseModel


class BatchStartResponse(BaseModel):
    """Response from batch start operation."""

    started: list[str]
    """Workflow IDs that were successfully started."""

    errors: dict[str, str]
    """Map of workflow_id to error message for failures."""
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_responses.py -v`
Expected: PASS

**Step 6: Update `__init__.py` exports if needed**

Check `amelia/server/models/__init__.py` and add `BatchStartResponse` export.

**Step 7: Commit**

```bash
git add amelia/server/models/responses.py tests/unit/server/models/test_responses.py amelia/server/models/__init__.py
git commit -m "feat(models): add BatchStartResponse model"
```

---

## Task 5: Implement `queue_workflow` Method in Orchestrator

**Files:**
- Modify: `amelia/server/orchestrator/service.py:337-512`
- Test: `tests/unit/server/orchestrator/test_service.py`

**Step 1: Write the failing tests**

```python
# tests/unit/server/orchestrator/test_queue_workflow.py
"""Tests for queue_workflow orchestrator method."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Create a mock event bus."""
    bus = MagicMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create a mock repository."""
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    repo.list_active = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def orchestrator(mock_event_bus: MagicMock, mock_repository: MagicMock) -> OrchestratorService:
    """Create orchestrator with mocked dependencies."""
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        max_concurrent=5,
    )


class TestQueueWorkflow:
    """Tests for queue_workflow method."""

    @pytest.mark.asyncio
    async def test_queue_workflow_creates_pending_state(
        self, orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """queue_workflow creates workflow in pending state without starting."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
            plan_now=False,
        )

        workflow_id = await orchestrator.queue_workflow(request)

        assert workflow_id.startswith("wf-")
        mock_repository.save.assert_called_once()
        saved_state: ServerExecutionState = mock_repository.save.call_args[0][0]
        assert saved_state.workflow_status == "pending"
        assert saved_state.started_at is None
        assert saved_state.planned_at is None

    @pytest.mark.asyncio
    async def test_queue_workflow_does_not_spawn_task(
        self, orchestrator: OrchestratorService
    ) -> None:
        """queue_workflow should not spawn an execution task."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
        )

        await orchestrator.queue_workflow(request)

        # No active tasks should be spawned
        assert len(orchestrator._active_tasks) == 0

    @pytest.mark.asyncio
    async def test_queue_workflow_allows_multiple_pending_per_worktree(
        self, orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """Multiple pending workflows allowed on same worktree."""
        # First workflow
        mock_repository.list_active.return_value = []
        request1 = CreateWorkflowRequest(
            issue_id="ISSUE-1",
            worktree_path="/path/to/repo",
            start=False,
        )
        await orchestrator.queue_workflow(request1)

        # Simulate first workflow exists as pending
        mock_repository.list_active.return_value = [
            ServerExecutionState(
                id="wf-1",
                issue_id="ISSUE-1",
                worktree_path="/path/to/repo",
                worktree_name="repo",
                workflow_status="pending",
            )
        ]

        # Second workflow on same worktree should succeed
        request2 = CreateWorkflowRequest(
            issue_id="ISSUE-2",
            worktree_path="/path/to/repo",
            start=False,
        )
        workflow_id = await orchestrator.queue_workflow(request2)
        assert workflow_id is not None

    @pytest.mark.asyncio
    async def test_queue_workflow_emits_created_event(
        self, orchestrator: OrchestratorService, mock_event_bus: MagicMock
    ) -> None:
        """queue_workflow should emit workflow_created event."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
        )

        await orchestrator.queue_workflow(request)

        mock_event_bus.emit.assert_called()
        # Check event type in call args
        event = mock_event_bus.emit.call_args[0][0]
        assert event.event_type == "workflow_created"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_queue_workflow.py -v`
Expected: FAIL - `queue_workflow` method not found

**Step 3: Write minimal implementation**

In `amelia/server/orchestrator/service.py`, add method after `start_workflow` (around line 515):

```python
async def queue_workflow(self, request: CreateWorkflowRequest) -> str:
    """
    Queue a workflow without starting it.

    Creates a workflow in pending state. Multiple pending workflows
    can exist for the same worktree.

    Args:
        request: Workflow creation request with start=False

    Returns:
        The workflow ID

    Raises:
        ValueError: If worktree doesn't exist or isn't a git repo
    """
    # Validate worktree exists and is git repo
    worktree_path = Path(request.worktree_path)
    if not worktree_path.exists():
        raise ValueError(f"Worktree path does not exist: {request.worktree_path}")
    if not (worktree_path / ".git").exists() and not worktree_path.joinpath(".git").is_file():
        raise ValueError(f"Not a git repository: {request.worktree_path}")

    # Generate workflow ID
    workflow_id = f"wf-{uuid.uuid4().hex[:12]}"

    # Determine worktree name
    worktree_name = request.worktree_name or worktree_path.name

    # Create state in pending without starting
    state = ServerExecutionState(
        id=workflow_id,
        issue_id=request.issue_id,
        worktree_path=str(worktree_path.resolve()),
        worktree_name=worktree_name,
        workflow_status="pending",
        # No started_at - workflow hasn't started
        # No planned_at - not planned yet
    )

    # Save to database
    await self._repository.save(state)

    # Emit created event
    await self._event_bus.emit(
        WorkflowEvent(
            workflow_id=workflow_id,
            event_type="workflow_created",
            timestamp=datetime.now(timezone.utc),
            message=f"Workflow queued for {request.issue_id}",
            data={"issue_id": request.issue_id, "queued": True},
        )
    )

    logger.info(
        "Workflow queued",
        workflow_id=workflow_id,
        issue_id=request.issue_id,
        worktree=worktree_name,
    )

    return workflow_id
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_queue_workflow.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/orchestrator/test_queue_workflow.py
git commit -m "feat(orchestrator): add queue_workflow method"
```

---

## Task 6: Implement `queue_and_plan_workflow` Method

**Files:**
- Modify: `amelia/server/orchestrator/service.py`
- Test: `tests/unit/server/orchestrator/test_queue_and_plan.py`

**Step 1: Write the failing tests**

```python
# tests/unit/server/orchestrator/test_queue_and_plan.py
"""Tests for queue_and_plan_workflow orchestrator method."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import ExecutionState, Issue, Profile
from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService


@pytest.fixture
def mock_event_bus() -> MagicMock:
    bus = MagicMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def mock_repository() -> MagicMock:
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def mock_architect() -> MagicMock:
    architect = MagicMock()
    architect.plan = AsyncMock(return_value=ExecutionState(
        issue=Issue(id="ISSUE-123", title="Test", description="Test desc"),
        plan="# Plan\n\n1. Do thing\n2. Do other thing",
    ))
    return architect


@pytest.fixture
def orchestrator(
    mock_event_bus: MagicMock,
    mock_repository: MagicMock,
) -> OrchestratorService:
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        max_concurrent=5,
    )


class TestQueueAndPlanWorkflow:
    """Tests for queue_and_plan_workflow method."""

    @pytest.mark.asyncio
    async def test_queue_and_plan_runs_architect(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        mock_architect: MagicMock,
    ) -> None:
        """queue_and_plan_workflow runs Architect and stores plan."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
            plan_now=True,
        )

        with patch.object(orchestrator, "_create_architect", return_value=mock_architect):
            workflow_id = await orchestrator.queue_and_plan_workflow(request)

        mock_architect.plan.assert_called_once()

        # Check state was saved with plan and planned_at
        saved_state = mock_repository.save.call_args[0][0]
        assert saved_state.workflow_status == "pending"
        assert saved_state.planned_at is not None
        assert saved_state.execution_state.plan is not None

    @pytest.mark.asyncio
    async def test_queue_and_plan_stays_pending(
        self,
        orchestrator: OrchestratorService,
        mock_architect: MagicMock,
    ) -> None:
        """Workflow remains pending after planning (not started)."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
            plan_now=True,
        )

        with patch.object(orchestrator, "_create_architect", return_value=mock_architect):
            await orchestrator.queue_and_plan_workflow(request)

        # No active task spawned
        assert len(orchestrator._active_tasks) == 0

    @pytest.mark.asyncio
    async def test_queue_and_plan_failure_marks_failed(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """If Architect fails, workflow is marked failed."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
            plan_now=True,
        )

        failing_architect = MagicMock()
        failing_architect.plan = AsyncMock(side_effect=Exception("LLM API error"))

        with patch.object(orchestrator, "_create_architect", return_value=failing_architect):
            workflow_id = await orchestrator.queue_and_plan_workflow(request)

        # Should be marked failed with reason
        update_call = mock_repository.update.call_args
        assert update_call is not None
        updated_state = update_call[0][0]
        assert updated_state.workflow_status == "failed"
        assert "LLM API error" in updated_state.failure_reason
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_queue_and_plan.py -v`
Expected: FAIL - `queue_and_plan_workflow` method not found

**Step 3: Write minimal implementation**

In `amelia/server/orchestrator/service.py`, add after `queue_workflow`:

```python
async def queue_and_plan_workflow(self, request: CreateWorkflowRequest) -> str:
    """
    Queue a workflow and run Architect to generate plan.

    Creates workflow, runs Architect to generate plan, stores plan,
    then leaves workflow in pending state for manual start.

    Args:
        request: Workflow creation request with start=False, plan_now=True

    Returns:
        The workflow ID

    Raises:
        ValueError: If worktree doesn't exist or isn't a git repo
    """
    # Validate worktree
    worktree_path = Path(request.worktree_path)
    if not worktree_path.exists():
        raise ValueError(f"Worktree path does not exist: {request.worktree_path}")

    # Generate workflow ID
    workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
    worktree_name = request.worktree_name or worktree_path.name

    # Create initial state
    state = ServerExecutionState(
        id=workflow_id,
        issue_id=request.issue_id,
        worktree_path=str(worktree_path.resolve()),
        worktree_name=worktree_name,
        workflow_status="pending",
    )

    await self._repository.save(state)

    await self._event_bus.emit(
        WorkflowEvent(
            workflow_id=workflow_id,
            event_type="workflow_created",
            timestamp=datetime.now(timezone.utc),
            message=f"Workflow queued for {request.issue_id}, planning...",
            data={"issue_id": request.issue_id, "queued": True, "planning": True},
        )
    )

    # Run Architect to generate plan
    try:
        architect = self._create_architect(request.profile)

        # Fetch issue details
        issue = await self._fetch_issue(request.issue_id, request.profile)

        execution_state = await architect.plan(issue, str(worktree_path))

        # Update state with plan
        state.execution_state = execution_state
        state.planned_at = datetime.now(timezone.utc)
        await self._repository.update(state)

        await self._event_bus.emit(
            WorkflowEvent(
                workflow_id=workflow_id,
                event_type="plan_completed",
                timestamp=datetime.now(timezone.utc),
                message="Plan generated, workflow queued",
                data={"plan_ready": True},
            )
        )

        logger.info(
            "Workflow queued with plan",
            workflow_id=workflow_id,
            issue_id=request.issue_id,
        )

    except Exception as e:
        # Mark workflow as failed
        state.workflow_status = "failed"
        state.failure_reason = f"Planning failed: {e}"
        await self._repository.update(state)

        await self._event_bus.emit(
            WorkflowEvent(
                workflow_id=workflow_id,
                event_type="workflow_failed",
                timestamp=datetime.now(timezone.utc),
                message=f"Planning failed: {e}",
                level="error",
            )
        )

        logger.error(
            "Queue and plan failed",
            workflow_id=workflow_id,
            error=str(e),
        )

    return workflow_id
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_queue_and_plan.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/orchestrator/test_queue_and_plan.py
git commit -m "feat(orchestrator): add queue_and_plan_workflow method"
```

---

## Task 7: Implement `start_pending_workflow` Method

**Files:**
- Modify: `amelia/server/orchestrator/service.py`
- Test: `tests/unit/server/orchestrator/test_start_pending.py`

**Step 1: Write the failing tests**

```python
# tests/unit/server/orchestrator/test_start_pending.py
"""Tests for start_pending_workflow orchestrator method."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.exceptions import (
    WorkflowNotFoundError,
    WorkflowStateError,
    WorktreeConflictError,
)
from amelia.server.orchestrator.service import OrchestratorService


@pytest.fixture
def mock_event_bus() -> MagicMock:
    bus = MagicMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def mock_repository() -> MagicMock:
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.get = AsyncMock()
    repo.update = AsyncMock()
    repo.list_active = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def pending_workflow() -> ServerExecutionState:
    return ServerExecutionState(
        id="wf-pending123",
        issue_id="ISSUE-123",
        worktree_path="/path/to/repo",
        worktree_name="repo",
        workflow_status="pending",
    )


@pytest.fixture
def orchestrator(mock_event_bus: MagicMock, mock_repository: MagicMock) -> OrchestratorService:
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        max_concurrent=5,
    )


class TestStartPendingWorkflow:
    """Tests for start_pending_workflow method."""

    @pytest.mark.asyncio
    async def test_start_pending_workflow_success(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        pending_workflow: ServerExecutionState,
    ) -> None:
        """Successfully start a pending workflow."""
        mock_repository.get.return_value = pending_workflow

        with patch.object(orchestrator, "_run_workflow_with_retry", new_callable=AsyncMock):
            await orchestrator.start_pending_workflow("wf-pending123")

        # Workflow should be updated to in_progress
        update_call = mock_repository.update.call_args
        updated_state = update_call[0][0]
        assert updated_state.workflow_status == "in_progress"
        assert updated_state.started_at is not None

    @pytest.mark.asyncio
    async def test_start_pending_not_found(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Raise error when workflow not found."""
        mock_repository.get.return_value = None

        with pytest.raises(WorkflowNotFoundError):
            await orchestrator.start_pending_workflow("wf-nonexistent")

    @pytest.mark.asyncio
    async def test_start_pending_wrong_state(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Raise error when workflow not in pending state."""
        in_progress = ServerExecutionState(
            id="wf-running",
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            worktree_name="repo",
            workflow_status="in_progress",
        )
        mock_repository.get.return_value = in_progress

        with pytest.raises(WorkflowStateError):
            await orchestrator.start_pending_workflow("wf-running")

    @pytest.mark.asyncio
    async def test_start_pending_worktree_conflict(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        pending_workflow: ServerExecutionState,
    ) -> None:
        """Raise error when worktree has active workflow."""
        mock_repository.get.return_value = pending_workflow

        # Another workflow is active on same worktree
        active_workflow = ServerExecutionState(
            id="wf-active",
            issue_id="ISSUE-999",
            worktree_path="/path/to/repo",
            worktree_name="repo",
            workflow_status="in_progress",
        )
        mock_repository.list_active.return_value = [active_workflow]

        with pytest.raises(WorktreeConflictError):
            await orchestrator.start_pending_workflow("wf-pending123")

    @pytest.mark.asyncio
    async def test_start_pending_spawns_task(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
        pending_workflow: ServerExecutionState,
    ) -> None:
        """Starting pending workflow spawns execution task."""
        mock_repository.get.return_value = pending_workflow

        with patch.object(
            orchestrator, "_run_workflow_with_retry", new_callable=AsyncMock
        ) as mock_run:
            await orchestrator.start_pending_workflow("wf-pending123")

        # Task should be tracked
        assert "/path/to/repo" in orchestrator._active_tasks
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_start_pending.py -v`
Expected: FAIL - `start_pending_workflow` method not found, exception classes not found

**Step 3: Create exception classes if needed**

Check `amelia/server/orchestrator/exceptions.py` (create if doesn't exist):

```python
"""Orchestrator exceptions."""


class OrchestratorError(Exception):
    """Base exception for orchestrator errors."""


class WorkflowNotFoundError(OrchestratorError):
    """Workflow not found."""


class WorkflowStateError(OrchestratorError):
    """Workflow is in wrong state for operation."""


class WorktreeConflictError(OrchestratorError):
    """Worktree already has an active workflow."""


class ConcurrencyLimitError(OrchestratorError):
    """Maximum concurrent workflows reached."""
```

**Step 4: Write minimal implementation**

In `amelia/server/orchestrator/service.py`, add after `queue_and_plan_workflow`:

```python
async def start_pending_workflow(self, workflow_id: str) -> None:
    """
    Start a pending workflow.

    Args:
        workflow_id: ID of the pending workflow to start

    Raises:
        WorkflowNotFoundError: Workflow doesn't exist
        WorkflowStateError: Workflow is not in pending state
        WorktreeConflictError: Worktree already has active workflow
        ConcurrencyLimitError: Max concurrent workflows reached
    """
    # Get workflow
    state = await self._repository.get(workflow_id)
    if state is None:
        raise WorkflowNotFoundError(f"Workflow not found: {workflow_id}")

    # Verify pending state
    if state.workflow_status != "pending":
        raise WorkflowStateError(
            f"Workflow {workflow_id} is {state.workflow_status}, expected pending"
        )

    # Check worktree conflict - only one in_progress/blocked per worktree
    active_workflows = await self._repository.list_active()
    for active in active_workflows:
        if (
            active.worktree_path == state.worktree_path
            and active.workflow_status in ("in_progress", "blocked")
            and active.id != workflow_id
        ):
            raise WorktreeConflictError(
                f"Worktree {state.worktree_path} already has active workflow: {active.id}"
            )

    # Check concurrency limit
    in_progress_count = sum(
        1 for w in active_workflows if w.workflow_status == "in_progress"
    )
    if in_progress_count >= self._max_concurrent:
        raise ConcurrencyLimitError(
            f"Maximum concurrent workflows ({self._max_concurrent}) reached"
        )

    # Update state to in_progress
    state.workflow_status = "in_progress"
    state.started_at = datetime.now(timezone.utc)
    await self._repository.update(state)

    # Emit started event
    await self._event_bus.emit(
        WorkflowEvent(
            workflow_id=workflow_id,
            event_type="workflow_started",
            timestamp=datetime.now(timezone.utc),
            message=f"Workflow started for {state.issue_id}",
        )
    )

    # Spawn execution task
    task = asyncio.create_task(
        self._run_workflow_with_retry(state)
    )
    self._active_tasks[state.worktree_path] = (workflow_id, task)

    logger.info(
        "Started pending workflow",
        workflow_id=workflow_id,
        issue_id=state.issue_id,
    )
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_start_pending.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/orchestrator/service.py amelia/server/orchestrator/exceptions.py tests/unit/server/orchestrator/test_start_pending.py
git commit -m "feat(orchestrator): add start_pending_workflow method"
```

---

## Task 8: Implement `start_batch_workflows` Method

**Files:**
- Modify: `amelia/server/orchestrator/service.py`
- Test: `tests/unit/server/orchestrator/test_start_batch.py`

**Step 1: Write the failing tests**

```python
# tests/unit/server/orchestrator/test_start_batch.py
"""Tests for start_batch_workflows orchestrator method."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.models.requests import BatchStartRequest
from amelia.server.models.responses import BatchStartResponse
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService


@pytest.fixture
def mock_event_bus() -> MagicMock:
    bus = MagicMock()
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def mock_repository() -> MagicMock:
    repo = MagicMock()
    repo.list_pending = AsyncMock(return_value=[])
    repo.get = AsyncMock()
    return repo


@pytest.fixture
def orchestrator(mock_event_bus: MagicMock, mock_repository: MagicMock) -> OrchestratorService:
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        max_concurrent=5,
    )


class TestStartBatchWorkflows:
    """Tests for start_batch_workflows method."""

    @pytest.mark.asyncio
    async def test_start_batch_all_pending(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Start all pending workflows when no filter specified."""
        pending = [
            ServerExecutionState(
                id="wf-1", issue_id="ISSUE-1",
                worktree_path="/repo1", worktree_name="repo1",
                workflow_status="pending",
            ),
            ServerExecutionState(
                id="wf-2", issue_id="ISSUE-2",
                worktree_path="/repo2", worktree_name="repo2",
                workflow_status="pending",
            ),
        ]
        mock_repository.list_pending.return_value = pending

        with patch.object(
            orchestrator, "start_pending_workflow", new_callable=AsyncMock
        ) as mock_start:
            request = BatchStartRequest()
            response = await orchestrator.start_batch_workflows(request)

        assert len(response.started) == 2
        assert response.errors == {}

    @pytest.mark.asyncio
    async def test_start_batch_specific_ids(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Start only specified workflow IDs."""
        mock_repository.get.side_effect = lambda id: ServerExecutionState(
            id=id, issue_id=f"ISSUE-{id}",
            worktree_path=f"/repo/{id}", worktree_name=id,
            workflow_status="pending",
        )

        with patch.object(
            orchestrator, "start_pending_workflow", new_callable=AsyncMock
        ):
            request = BatchStartRequest(workflow_ids=["wf-1", "wf-2"])
            response = await orchestrator.start_batch_workflows(request)

        assert response.started == ["wf-1", "wf-2"]

    @pytest.mark.asyncio
    async def test_start_batch_filter_by_worktree(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Filter pending workflows by worktree path."""
        pending = [
            ServerExecutionState(
                id="wf-1", issue_id="ISSUE-1",
                worktree_path="/repo/a", worktree_name="a",
                workflow_status="pending",
            ),
            ServerExecutionState(
                id="wf-2", issue_id="ISSUE-2",
                worktree_path="/repo/b", worktree_name="b",
                workflow_status="pending",
            ),
        ]
        mock_repository.list_pending.return_value = pending

        with patch.object(
            orchestrator, "start_pending_workflow", new_callable=AsyncMock
        ):
            request = BatchStartRequest(worktree_path="/repo/a")
            response = await orchestrator.start_batch_workflows(request)

        assert response.started == ["wf-1"]

    @pytest.mark.asyncio
    async def test_start_batch_partial_failure(
        self,
        orchestrator: OrchestratorService,
        mock_repository: MagicMock,
    ) -> None:
        """Handle partial failures gracefully."""
        pending = [
            ServerExecutionState(
                id="wf-1", issue_id="ISSUE-1",
                worktree_path="/repo", worktree_name="repo",
                workflow_status="pending",
            ),
            ServerExecutionState(
                id="wf-2", issue_id="ISSUE-2",
                worktree_path="/repo", worktree_name="repo",
                workflow_status="pending",
            ),
        ]
        mock_repository.list_pending.return_value = pending

        # First succeeds, second fails due to worktree conflict
        call_count = 0
        async def mock_start(wf_id: str) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                from amelia.server.orchestrator.exceptions import WorktreeConflictError
                raise WorktreeConflictError("Worktree has active workflow")

        with patch.object(orchestrator, "start_pending_workflow", side_effect=mock_start):
            request = BatchStartRequest()
            response = await orchestrator.start_batch_workflows(request)

        assert response.started == ["wf-1"]
        assert "wf-2" in response.errors
        assert "active workflow" in response.errors["wf-2"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_start_batch.py -v`
Expected: FAIL - `start_batch_workflows` method not found

**Step 3: Write minimal implementation**

In `amelia/server/orchestrator/service.py`, add after `start_pending_workflow`:

```python
async def start_batch_workflows(self, request: BatchStartRequest) -> BatchStartResponse:
    """
    Start multiple pending workflows.

    Starts workflows sequentially, respecting concurrency limits.
    Partial success is possible.

    Args:
        request: Batch start parameters

    Returns:
        BatchStartResponse with started IDs and errors
    """
    started: list[str] = []
    errors: dict[str, str] = {}

    # Get workflows to start
    if request.workflow_ids:
        # Specific IDs requested
        workflow_ids = request.workflow_ids
    else:
        # Get all pending, optionally filtered by worktree
        pending = await self._repository.list_pending()
        if request.worktree_path:
            pending = [w for w in pending if w.worktree_path == request.worktree_path]
        workflow_ids = [w.id for w in pending]

    # Start each workflow sequentially
    for workflow_id in workflow_ids:
        try:
            await self.start_pending_workflow(workflow_id)
            started.append(workflow_id)
        except Exception as e:
            errors[workflow_id] = str(e)
            logger.warning(
                "Failed to start workflow in batch",
                workflow_id=workflow_id,
                error=str(e),
            )

    logger.info(
        "Batch start completed",
        started_count=len(started),
        error_count=len(errors),
    )

    return BatchStartResponse(started=started, errors=errors)
```

**Step 4: Add `list_pending` method to repository if needed**

Check if repository has `list_pending` method, add if missing.

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_start_batch.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/orchestrator/test_start_batch.py
git commit -m "feat(orchestrator): add start_batch_workflows method"
```

---

## Task 9: Modify `POST /workflows` Route

**Files:**
- Modify: `amelia/server/routes/workflows.py:44-79`
- Test: `tests/unit/server/routes/test_workflows.py`

**Step 1: Write the failing tests**

```python
# tests/unit/server/routes/test_workflows_queue.py
"""Tests for queue-related workflow endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.routes.workflows import router


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    orch = MagicMock()
    orch.start_workflow = AsyncMock(return_value="wf-started")
    orch.queue_workflow = AsyncMock(return_value="wf-queued")
    orch.queue_and_plan_workflow = AsyncMock(return_value="wf-planned")
    return orch


@pytest.fixture
def client(mock_orchestrator: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.orchestrator = mock_orchestrator
    return TestClient(app)


class TestCreateWorkflowQueue:
    """Tests for POST /workflows with queue parameters."""

    def test_default_starts_immediately(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Default behavior (start=True) starts workflow immediately."""
        response = client.post(
            "/workflows",
            json={"issue_id": "ISSUE-123", "worktree_path": "/repo"},
        )

        assert response.status_code == 201
        mock_orchestrator.start_workflow.assert_called_once()

    def test_queue_without_plan(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """start=False queues without planning."""
        response = client.post(
            "/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/repo",
                "start": False,
            },
        )

        assert response.status_code == 201
        mock_orchestrator.queue_workflow.assert_called_once()
        mock_orchestrator.start_workflow.assert_not_called()

    def test_queue_with_plan(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """start=False, plan_now=True runs Architect then queues."""
        response = client.post(
            "/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/repo",
                "start": False,
                "plan_now": True,
            },
        )

        assert response.status_code == 201
        mock_orchestrator.queue_and_plan_workflow.assert_called_once()

    def test_plan_now_ignored_when_start_true(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """plan_now is ignored when start=True."""
        response = client.post(
            "/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/repo",
                "start": True,
                "plan_now": True,
            },
        )

        assert response.status_code == 201
        mock_orchestrator.start_workflow.assert_called_once()
        mock_orchestrator.queue_and_plan_workflow.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_workflows_queue.py -v`
Expected: FAIL - routes don't handle queue parameters

**Step 3: Modify the route implementation**

In `amelia/server/routes/workflows.py`, modify the `POST /workflows` handler (around line 44):

```python
@router.post("/workflows", status_code=201)
async def create_workflow(
    request: CreateWorkflowRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> dict[str, str]:
    """
    Create a new workflow.

    Behavior depends on start and plan_now parameters:
    - start=True (default): Start workflow immediately
    - start=False, plan_now=False: Queue without planning
    - start=False, plan_now=True: Run Architect, then queue
    """
    if request.start:
        # Immediate execution (existing behavior)
        workflow_id = await orchestrator.start_workflow(request)
    elif request.plan_now:
        # Queue with planning
        workflow_id = await orchestrator.queue_and_plan_workflow(request)
    else:
        # Queue without planning
        workflow_id = await orchestrator.queue_workflow(request)

    return {"workflow_id": workflow_id}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_workflows_queue.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/workflows.py tests/unit/server/routes/test_workflows_queue.py
git commit -m "feat(api): modify POST /workflows to support queue parameters"
```

---

## Task 10: Add `POST /workflows/{id}/start` Endpoint

**Files:**
- Modify: `amelia/server/routes/workflows.py`
- Test: `tests/unit/server/routes/test_workflows_queue.py`

**Step 1: Write the failing tests**

Add to `tests/unit/server/routes/test_workflows_queue.py`:

```python
from amelia.server.orchestrator.exceptions import (
    WorkflowNotFoundError,
    WorkflowStateError,
    WorktreeConflictError,
)


class TestStartWorkflowEndpoint:
    """Tests for POST /workflows/{id}/start endpoint."""

    def test_start_pending_workflow_success(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Successfully start a pending workflow."""
        mock_orchestrator.start_pending_workflow = AsyncMock()

        response = client.post("/workflows/wf-123/start")

        assert response.status_code == 202
        mock_orchestrator.start_pending_workflow.assert_called_once_with("wf-123")

    def test_start_workflow_not_found(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Return 404 when workflow not found."""
        mock_orchestrator.start_pending_workflow = AsyncMock(
            side_effect=WorkflowNotFoundError("Not found")
        )

        response = client.post("/workflows/wf-nonexistent/start")

        assert response.status_code == 404

    def test_start_workflow_wrong_state(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Return 409 when workflow not pending."""
        mock_orchestrator.start_pending_workflow = AsyncMock(
            side_effect=WorkflowStateError("Not pending")
        )

        response = client.post("/workflows/wf-running/start")

        assert response.status_code == 409

    def test_start_workflow_worktree_conflict(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Return 409 when worktree has active workflow."""
        mock_orchestrator.start_pending_workflow = AsyncMock(
            side_effect=WorktreeConflictError("Worktree busy")
        )

        response = client.post("/workflows/wf-123/start")

        assert response.status_code == 409
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_workflows_queue.py::TestStartWorkflowEndpoint -v`
Expected: FAIL - endpoint not found (404 for all)

**Step 3: Write minimal implementation**

In `amelia/server/routes/workflows.py`, add new endpoint:

```python
@router.post("/workflows/{workflow_id}/start", status_code=202)
async def start_workflow(
    workflow_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> dict[str, str]:
    """
    Start a pending workflow.

    Returns:
        202 Accepted with workflow_id

    Raises:
        404: Workflow not found
        409: Workflow not pending, or worktree has active workflow
    """
    try:
        await orchestrator.start_pending_workflow(workflow_id)
        return {"workflow_id": workflow_id, "status": "started"}
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    except (WorkflowStateError, WorktreeConflictError) as e:
        raise HTTPException(status_code=409, detail=str(e))
```

Add imports at top:

```python
from amelia.server.orchestrator.exceptions import (
    WorkflowNotFoundError,
    WorkflowStateError,
    WorktreeConflictError,
)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_workflows_queue.py::TestStartWorkflowEndpoint -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/workflows.py tests/unit/server/routes/test_workflows_queue.py
git commit -m "feat(api): add POST /workflows/{id}/start endpoint"
```

---

## Task 11: Add `POST /workflows/start-batch` Endpoint

**Files:**
- Modify: `amelia/server/routes/workflows.py`
- Test: `tests/unit/server/routes/test_workflows_queue.py`

**Step 1: Write the failing tests**

Add to `tests/unit/server/routes/test_workflows_queue.py`:

```python
from amelia.server.models.requests import BatchStartRequest
from amelia.server.models.responses import BatchStartResponse


class TestBatchStartEndpoint:
    """Tests for POST /workflows/start-batch endpoint."""

    def test_batch_start_all(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Start all pending workflows."""
        mock_orchestrator.start_batch_workflows = AsyncMock(
            return_value=BatchStartResponse(
                started=["wf-1", "wf-2"],
                errors={},
            )
        )

        response = client.post("/workflows/start-batch", json={})

        assert response.status_code == 200
        data = response.json()
        assert data["started"] == ["wf-1", "wf-2"]
        assert data["errors"] == {}

    def test_batch_start_specific_ids(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Start specific workflow IDs."""
        mock_orchestrator.start_batch_workflows = AsyncMock(
            return_value=BatchStartResponse(started=["wf-1"], errors={})
        )

        response = client.post(
            "/workflows/start-batch",
            json={"workflow_ids": ["wf-1"]},
        )

        assert response.status_code == 200
        call_args = mock_orchestrator.start_batch_workflows.call_args[0][0]
        assert call_args.workflow_ids == ["wf-1"]

    def test_batch_start_partial_failure(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Handle partial failures."""
        mock_orchestrator.start_batch_workflows = AsyncMock(
            return_value=BatchStartResponse(
                started=["wf-1"],
                errors={"wf-2": "Worktree conflict"},
            )
        )

        response = client.post("/workflows/start-batch", json={})

        assert response.status_code == 200
        data = response.json()
        assert data["started"] == ["wf-1"]
        assert data["errors"]["wf-2"] == "Worktree conflict"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_workflows_queue.py::TestBatchStartEndpoint -v`
Expected: FAIL - endpoint not found

**Step 3: Write minimal implementation**

In `amelia/server/routes/workflows.py`, add new endpoint:

```python
@router.post("/workflows/start-batch")
async def start_batch(
    request: BatchStartRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> BatchStartResponse:
    """
    Start multiple pending workflows.

    Starts workflows sequentially, respecting concurrency limits.
    Partial success is possible.

    Returns:
        BatchStartResponse with started IDs and errors
    """
    return await orchestrator.start_batch_workflows(request)
```

Add import:

```python
from amelia.server.models.requests import BatchStartRequest
from amelia.server.models.responses import BatchStartResponse
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_workflows_queue.py::TestBatchStartEndpoint -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/workflows.py tests/unit/server/routes/test_workflows_queue.py
git commit -m "feat(api): add POST /workflows/start-batch endpoint"
```

---

## Task 12: Add `--queue` and `--plan` Flags to CLI `start` Command

**Files:**
- Modify: `amelia/client/cli.py:92-147`
- Test: `tests/unit/client/test_cli.py`

**Step 1: Write the failing tests**

```python
# tests/unit/client/test_cli_queue.py
"""Tests for CLI queue-related commands."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from amelia.client.cli import app


runner = CliRunner()


class TestStartCommandQueue:
    """Tests for start command with queue flags."""

    def test_start_default_immediate(self) -> None:
        """Default start without flags starts immediately."""
        with patch("amelia.client.cli.get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.create_workflow = AsyncMock(
                return_value={"workflow_id": "wf-123"}
            )
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)

            result = runner.invoke(app, ["start", "ISSUE-123"])

            assert result.exit_code == 0
            call_kwargs = mock_client.create_workflow.call_args[1]
            assert call_kwargs.get("start", True) is True

    def test_start_with_queue_flag(self) -> None:
        """--queue flag queues without starting."""
        with patch("amelia.client.cli.get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.create_workflow = AsyncMock(
                return_value={"workflow_id": "wf-123"}
            )
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)

            result = runner.invoke(app, ["start", "ISSUE-123", "--queue"])

            assert result.exit_code == 0
            call_kwargs = mock_client.create_workflow.call_args[1]
            assert call_kwargs["start"] is False
            assert call_kwargs.get("plan_now", False) is False

    def test_start_with_queue_and_plan_flags(self) -> None:
        """--queue --plan flags queue with planning."""
        with patch("amelia.client.cli.get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.create_workflow = AsyncMock(
                return_value={"workflow_id": "wf-123"}
            )
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)

            result = runner.invoke(app, ["start", "ISSUE-123", "--queue", "--plan"])

            assert result.exit_code == 0
            call_kwargs = mock_client.create_workflow.call_args[1]
            assert call_kwargs["start"] is False
            assert call_kwargs["plan_now"] is True

    def test_plan_without_queue_is_error(self) -> None:
        """--plan without --queue should error."""
        result = runner.invoke(app, ["start", "ISSUE-123", "--plan"])

        assert result.exit_code != 0
        assert "--queue" in result.output or "queue" in result.output.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_cli_queue.py::TestStartCommandQueue -v`
Expected: FAIL - flags not recognized

**Step 3: Modify CLI implementation**

In `amelia/client/cli.py`, modify the `start_command` function (around line 92):

```python
@app.command("start")
def start_command(
    issue_id: Annotated[str, typer.Argument(help="Issue ID to work on")],
    profile: Annotated[str | None, typer.Option("-p", "--profile", help="Profile name")] = None,
    title: Annotated[str | None, typer.Option("--title", help="Task title (noop tracker)")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Task description")] = None,
    queue: Annotated[bool, typer.Option("--queue", help="Queue workflow without starting")] = False,
    plan: Annotated[bool, typer.Option("--plan", help="Run Architect before queueing (requires --queue)")] = False,
) -> None:
    """Start a workflow for an issue."""
    # Validate flags
    if plan and not queue:
        console.print("[red]Error:[/red] --plan requires --queue flag")
        raise typer.Exit(1)

    worktree_context = get_worktree_context()

    with get_client() as client:
        result = asyncio.run(
            client.create_workflow(
                issue_id=issue_id,
                worktree_path=worktree_context.path,
                worktree_name=worktree_context.name,
                profile=profile,
                task_title=title,
                task_description=description,
                start=not queue,
                plan_now=plan,
            )
        )

    workflow_id = result["workflow_id"]

    if queue:
        if plan:
            console.print(f"[green]Workflow queued with plan:[/green] {workflow_id}")
        else:
            console.print(f"[green]Workflow queued:[/green] {workflow_id}")
    else:
        console.print(f"[green]Workflow started:[/green] {workflow_id}")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/client/test_cli_queue.py::TestStartCommandQueue -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/client/cli.py tests/unit/client/test_cli_queue.py
git commit -m "feat(cli): add --queue and --plan flags to start command"
```

---

## Task 13: Add `amelia run` CLI Command

**Files:**
- Modify: `amelia/client/cli.py`
- Test: `tests/unit/client/test_cli_queue.py`

**Step 1: Write the failing tests**

Add to `tests/unit/client/test_cli_queue.py`:

```python
class TestRunCommand:
    """Tests for run command."""

    def test_run_specific_workflow(self) -> None:
        """Run a specific workflow by ID."""
        with patch("amelia.client.cli.get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.start_workflow = AsyncMock(return_value={"status": "started"})
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)

            result = runner.invoke(app, ["run", "wf-123"])

            assert result.exit_code == 0
            mock_client.start_workflow.assert_called_once_with("wf-123")

    def test_run_all_pending(self) -> None:
        """Run all pending workflows with --all flag."""
        with patch("amelia.client.cli.get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.start_batch = AsyncMock(
                return_value={"started": ["wf-1", "wf-2"], "errors": {}}
            )
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)

            result = runner.invoke(app, ["run", "--all"])

            assert result.exit_code == 0
            mock_client.start_batch.assert_called_once()

    def test_run_all_with_worktree_filter(self) -> None:
        """Run all pending with worktree filter."""
        with patch("amelia.client.cli.get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.start_batch = AsyncMock(
                return_value={"started": ["wf-1"], "errors": {}}
            )
            mock_get.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)

            result = runner.invoke(app, ["run", "--all", "--worktree", "/path/to/repo"])

            assert result.exit_code == 0
            call_kwargs = mock_client.start_batch.call_args[1]
            assert call_kwargs["worktree_path"] == "/path/to/repo"

    def test_run_requires_id_or_all(self) -> None:
        """run command requires either workflow ID or --all flag."""
        result = runner.invoke(app, ["run"])

        assert result.exit_code != 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_cli_queue.py::TestRunCommand -v`
Expected: FAIL - run command not found

**Step 3: Write minimal implementation**

In `amelia/client/cli.py`, add new command:

```python
@app.command("run")
def run_command(
    workflow_id: Annotated[str | None, typer.Argument(help="Workflow ID to start")] = None,
    all_pending: Annotated[bool, typer.Option("--all", help="Start all pending workflows")] = False,
    worktree: Annotated[str | None, typer.Option("--worktree", help="Filter by worktree path")] = None,
) -> None:
    """Start pending workflow(s)."""
    if not workflow_id and not all_pending:
        console.print("[red]Error:[/red] Provide workflow ID or use --all flag")
        raise typer.Exit(1)

    with get_client() as client:
        if workflow_id:
            # Start specific workflow
            result = asyncio.run(client.start_workflow(workflow_id))
            console.print(f"[green]Started workflow:[/green] {workflow_id}")
        else:
            # Batch start
            result = asyncio.run(
                client.start_batch(
                    workflow_ids=None,
                    worktree_path=worktree,
                )
            )
            started = result.get("started", [])
            errors = result.get("errors", {})

            if started:
                console.print(f"[green]Started {len(started)} workflow(s):[/green]")
                for wf_id in started:
                    console.print(f"  - {wf_id}")

            if errors:
                console.print(f"[yellow]Failed to start {len(errors)} workflow(s):[/yellow]")
                for wf_id, error in errors.items():
                    console.print(f"  - {wf_id}: {error}")

            if not started and not errors:
                console.print("[dim]No pending workflows to start[/dim]")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/client/test_cli_queue.py::TestRunCommand -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/client/cli.py tests/unit/client/test_cli_queue.py
git commit -m "feat(cli): add run command for starting pending workflows"
```

---

## Task 14: Update Dashboard Types

**Files:**
- Modify: `dashboard/src/types/index.ts`
- Test: `dashboard/src/types/__tests__/index.test.ts`

**Step 1: Write the failing tests**

```typescript
// dashboard/src/types/__tests__/index.test.ts
import { describe, it, expect } from 'vitest';
import type { CreateWorkflowRequest, BatchStartRequest, BatchStartResponse } from '../index';

describe('CreateWorkflowRequest', () => {
  it('should allow start and plan_now fields', () => {
    const request: CreateWorkflowRequest = {
      issue_id: 'ISSUE-123',
      worktree_path: '/path/to/repo',
      start: false,
      plan_now: true,
    };
    expect(request.start).toBe(false);
    expect(request.plan_now).toBe(true);
  });

  it('should have optional start defaulting to true semantically', () => {
    const request: CreateWorkflowRequest = {
      issue_id: 'ISSUE-123',
      worktree_path: '/path/to/repo',
    };
    // Fields are optional in TypeScript
    expect(request.start).toBeUndefined();
  });
});

describe('BatchStartRequest', () => {
  it('should allow empty request', () => {
    const request: BatchStartRequest = {};
    expect(request.workflow_ids).toBeUndefined();
    expect(request.worktree_path).toBeUndefined();
  });

  it('should allow workflow_ids list', () => {
    const request: BatchStartRequest = {
      workflow_ids: ['wf-1', 'wf-2'],
    };
    expect(request.workflow_ids).toHaveLength(2);
  });

  it('should allow worktree_path filter', () => {
    const request: BatchStartRequest = {
      worktree_path: '/path/to/repo',
    };
    expect(request.worktree_path).toBe('/path/to/repo');
  });
});

describe('BatchStartResponse', () => {
  it('should have started and errors fields', () => {
    const response: BatchStartResponse = {
      started: ['wf-1', 'wf-2'],
      errors: { 'wf-3': 'Worktree conflict' },
    };
    expect(response.started).toHaveLength(2);
    expect(response.errors['wf-3']).toBe('Worktree conflict');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/types/__tests__/index.test.ts`
Expected: FAIL - types not found

**Step 3: Write minimal implementation**

In `dashboard/src/types/index.ts`, add/modify types:

```typescript
// Add to CreateWorkflowRequest (around line 419)
export interface CreateWorkflowRequest {
  issue_id: string;
  worktree_path: string;
  worktree_name?: string;
  profile?: string;
  driver?: string;
  task_title?: string;
  task_description?: string;
  start?: boolean;      // Default: true - whether to start immediately
  plan_now?: boolean;   // Default: false - if not starting, run Architect first
}

// Add new types
export interface BatchStartRequest {
  workflow_ids?: string[];
  worktree_path?: string;
}

export interface BatchStartResponse {
  started: string[];
  errors: Record<string, string>;
}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/types/__tests__/index.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/types/index.ts dashboard/src/types/__tests__/index.test.ts
git commit -m "feat(dashboard): add queue workflow types"
```

---

## Task 15: Update Dashboard API Client

**Files:**
- Modify: `dashboard/src/api/client.ts`
- Test: `dashboard/src/api/__tests__/client.test.ts`

**Step 1: Write the failing tests**

```typescript
// dashboard/src/api/__tests__/client.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../client';

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('apiClient queue methods', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  describe('startWorkflow', () => {
    it('should POST to /workflows/{id}/start', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ workflow_id: 'wf-123', status: 'started' }),
      });

      const result = await apiClient.startWorkflow('wf-123');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/workflows/wf-123/start'),
        expect.objectContaining({ method: 'POST' })
      );
      expect(result.workflow_id).toBe('wf-123');
    });
  });

  describe('startBatch', () => {
    it('should POST to /workflows/start-batch', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ started: ['wf-1', 'wf-2'], errors: {} }),
      });

      const result = await apiClient.startBatch({});

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/workflows/start-batch'),
        expect.objectContaining({ method: 'POST' })
      );
      expect(result.started).toHaveLength(2);
    });

    it('should pass workflow_ids and worktree_path', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ started: ['wf-1'], errors: {} }),
      });

      await apiClient.startBatch({
        workflow_ids: ['wf-1'],
        worktree_path: '/repo',
      });

      const callBody = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(callBody.workflow_ids).toEqual(['wf-1']);
      expect(callBody.worktree_path).toBe('/repo');
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/api/__tests__/client.test.ts`
Expected: FAIL - methods not found

**Step 3: Write minimal implementation**

In `dashboard/src/api/client.ts`, add methods:

```typescript
import type { BatchStartRequest, BatchStartResponse } from '../types';

// Add to apiClient object
export const apiClient = {
  // ... existing methods ...

  /**
   * Start a pending workflow.
   */
  async startWorkflow(workflowId: string): Promise<{ workflow_id: string; status: string }> {
    const response = await fetchWithTimeout(`${API_BASE}/api/workflows/${workflowId}/start`, {
      method: 'POST',
    });
    return handleResponse(response);
  },

  /**
   * Start multiple pending workflows.
   */
  async startBatch(request: BatchStartRequest): Promise<BatchStartResponse> {
    const response = await fetchWithTimeout(`${API_BASE}/api/workflows/start-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    return handleResponse(response);
  },
};
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/api/__tests__/client.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/api/client.ts dashboard/src/api/__tests__/client.test.ts
git commit -m "feat(dashboard): add startWorkflow and startBatch API methods"
```

---

## Task 16: Update QuickShotModal with Queue Buttons

**Files:**
- Modify: `dashboard/src/components/QuickShotModal.tsx`
- Test: `dashboard/src/components/__tests__/QuickShotModal.test.tsx`

**Step 1: Write the failing tests**

```typescript
// dashboard/src/components/__tests__/QuickShotModal.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QuickShotModal } from '../QuickShotModal';

describe('QuickShotModal queue buttons', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onSubmit: vi.fn(),
  };

  it('should render Queue button', () => {
    render(<QuickShotModal {...defaultProps} />);
    expect(screen.getByRole('button', { name: /queue/i })).toBeInTheDocument();
  });

  it('should render Plan & Queue button', () => {
    render(<QuickShotModal {...defaultProps} />);
    expect(screen.getByRole('button', { name: /plan.*queue/i })).toBeInTheDocument();
  });

  it('should render Start button as primary', () => {
    render(<QuickShotModal {...defaultProps} />);
    const startButton = screen.getByRole('button', { name: /^start$/i });
    expect(startButton).toBeInTheDocument();
    // Primary style check (implementation-specific)
  });

  it('should call onSubmit with start=false for Queue button', async () => {
    const onSubmit = vi.fn();
    render(<QuickShotModal {...defaultProps} onSubmit={onSubmit} />);

    // Fill required fields first
    fireEvent.change(screen.getByLabelText(/issue/i), { target: { value: 'ISSUE-123' } });
    fireEvent.change(screen.getByLabelText(/worktree/i), { target: { value: '/repo' } });

    fireEvent.click(screen.getByRole('button', { name: /^queue$/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        start: false,
        plan_now: false,
      })
    );
  });

  it('should call onSubmit with plan_now=true for Plan & Queue button', async () => {
    const onSubmit = vi.fn();
    render(<QuickShotModal {...defaultProps} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText(/issue/i), { target: { value: 'ISSUE-123' } });
    fireEvent.change(screen.getByLabelText(/worktree/i), { target: { value: '/repo' } });

    fireEvent.click(screen.getByRole('button', { name: /plan.*queue/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        start: false,
        plan_now: true,
      })
    );
  });

  it('should call onSubmit with start=true for Start button', async () => {
    const onSubmit = vi.fn();
    render(<QuickShotModal {...defaultProps} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText(/issue/i), { target: { value: 'ISSUE-123' } });
    fireEvent.change(screen.getByLabelText(/worktree/i), { target: { value: '/repo' } });

    fireEvent.click(screen.getByRole('button', { name: /^start$/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        start: true,
      })
    );
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/components/__tests__/QuickShotModal.test.tsx`
Expected: FAIL - buttons not found

**Step 3: Modify QuickShotModal implementation**

In `dashboard/src/components/QuickShotModal.tsx`, modify the footer section:

```tsx
// Update form submission to accept action type
const handleSubmit = (action: 'start' | 'queue' | 'plan_queue') => {
  return form.handleSubmit((data) => {
    onSubmit({
      ...data,
      start: action === 'start',
      plan_now: action === 'plan_queue',
    });
  });
};

// Update footer buttons
<DialogFooter className="flex gap-2">
  <Button variant="ghost" onClick={onClose}>
    Cancel
  </Button>
  <Button
    variant="secondary"
    onClick={handleSubmit('queue')}
    disabled={!form.formState.isValid}
  >
    Queue
  </Button>
  <Button
    variant="secondary"
    onClick={handleSubmit('plan_queue')}
    disabled={!form.formState.isValid}
  >
    Plan & Queue
  </Button>
  <Button
    variant="default"
    onClick={handleSubmit('start')}
    disabled={!form.formState.isValid}
  >
    Start
  </Button>
</DialogFooter>
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/components/__tests__/QuickShotModal.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/QuickShotModal.tsx dashboard/src/components/__tests__/QuickShotModal.test.tsx
git commit -m "feat(dashboard): add Queue and Plan & Queue buttons to QuickShotModal"
```

---

## Task 17: Update WorkflowsPage for Pending Workflow Actions

**Files:**
- Modify: `dashboard/src/pages/WorkflowsPage.tsx`
- Test: `dashboard/src/pages/__tests__/WorkflowsPage.test.tsx`

**Step 1: Write the failing tests**

```typescript
// dashboard/src/pages/__tests__/WorkflowsPage.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WorkflowsPage } from '../WorkflowsPage';

// Mock dependencies
vi.mock('../api/client', () => ({
  apiClient: {
    getWorkflows: vi.fn().mockResolvedValue([]),
    startWorkflow: vi.fn().mockResolvedValue({}),
    cancelWorkflow: vi.fn().mockResolvedValue({}),
  },
}));

describe('WorkflowsPage pending workflow actions', () => {
  const pendingWorkflow = {
    id: 'wf-pending',
    issue_id: 'ISSUE-123',
    worktree_name: 'repo',
    workflow_status: 'pending' as const,
    created_at: new Date().toISOString(),
  };

  it('should show Start button for pending workflows', async () => {
    vi.mocked(apiClient.getWorkflows).mockResolvedValueOnce([pendingWorkflow]);

    render(<WorkflowsPage />);

    // Wait for workflows to load
    const startButton = await screen.findByRole('button', { name: /start/i });
    expect(startButton).toBeInTheDocument();
  });

  it('should show Cancel button for pending workflows', async () => {
    vi.mocked(apiClient.getWorkflows).mockResolvedValueOnce([pendingWorkflow]);

    render(<WorkflowsPage />);

    const cancelButton = await screen.findByRole('button', { name: /cancel/i });
    expect(cancelButton).toBeInTheDocument();
  });

  it('should call startWorkflow when Start clicked', async () => {
    vi.mocked(apiClient.getWorkflows).mockResolvedValueOnce([pendingWorkflow]);
    const startMock = vi.mocked(apiClient.startWorkflow);

    render(<WorkflowsPage />);

    const startButton = await screen.findByRole('button', { name: /start/i });
    fireEvent.click(startButton);

    expect(startMock).toHaveBeenCalledWith('wf-pending');
  });

  it('should show "queued X ago" for pending workflows', async () => {
    vi.mocked(apiClient.getWorkflows).mockResolvedValueOnce([pendingWorkflow]);

    render(<WorkflowsPage />);

    const queuedText = await screen.findByText(/queued/i);
    expect(queuedText).toBeInTheDocument();
  });

  it('should show plan status indicator for pending workflows', async () => {
    const plannedWorkflow = {
      ...pendingWorkflow,
      planned_at: new Date().toISOString(),
    };
    vi.mocked(apiClient.getWorkflows).mockResolvedValueOnce([plannedWorkflow]);

    render(<WorkflowsPage />);

    const planIndicator = await screen.findByText(/plan ready/i);
    expect(planIndicator).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test src/pages/__tests__/WorkflowsPage.test.tsx`
Expected: FAIL - buttons and indicators not found

**Step 3: Modify WorkflowsPage implementation**

In `dashboard/src/pages/WorkflowsPage.tsx`, update the JobQueue section to handle pending workflows:

```tsx
// Add to JobQueue row rendering for pending workflows
{workflow.workflow_status === 'pending' && (
  <div className="flex items-center gap-2">
    <span className="text-muted-foreground text-sm">
      queued {formatRelativeTime(workflow.created_at)}
    </span>
    <span className="text-xs">
      {workflow.planned_at ? (
        <Badge variant="outline">Plan ready</Badge>
      ) : (
        <Badge variant="secondary">No plan</Badge>
      )}
    </span>
    <div className="flex gap-1">
      <Button
        size="sm"
        variant="default"
        onClick={() => handleStartWorkflow(workflow.id)}
      >
        Start
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => handleCancelWorkflow(workflow.id)}
      >
        Cancel
      </Button>
    </div>
  </div>
)}

// Add handlers
const handleStartWorkflow = async (workflowId: string) => {
  try {
    await apiClient.startWorkflow(workflowId);
    toast.success('Workflow started');
    revalidate();
  } catch (error) {
    toast.error('Failed to start workflow');
  }
};
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/pages/__tests__/WorkflowsPage.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/pages/WorkflowsPage.tsx dashboard/src/pages/__tests__/WorkflowsPage.test.tsx
git commit -m "feat(dashboard): add Start/Cancel actions for pending workflows"
```

---

## Task 18: Update StatusBadge for Queued State

**Files:**
- Modify: `dashboard/src/components/StatusBadge.tsx`
- Test: `dashboard/src/components/__tests__/StatusBadge.test.tsx`

**Step 1: Write the failing tests**

```typescript
// dashboard/src/components/__tests__/StatusBadge.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from '../StatusBadge';

describe('StatusBadge queued styling', () => {
  it('should display "Queued" label for pending status', () => {
    render(<StatusBadge status="pending" />);
    expect(screen.getByText('Queued')).toBeInTheDocument();
  });

  it('should have muted styling for queued status', () => {
    render(<StatusBadge status="pending" />);
    const badge = screen.getByText('Queued');
    // Check for muted/secondary variant class
    expect(badge.className).toMatch(/muted|secondary/);
  });
});
```

**Step 2: Run test to verify current state**

Run: `cd dashboard && pnpm test src/components/__tests__/StatusBadge.test.tsx`
Expected: May pass if already showing "Queued" for pending, otherwise FAIL

**Step 3: Modify StatusBadge if needed**

In `dashboard/src/components/StatusBadge.tsx`, update the label mapping:

```typescript
const statusLabels: Record<WorkflowStatus, string> = {
  pending: 'Queued',  // Changed from 'Pending' to 'Queued'
  in_progress: 'Running',
  blocked: 'Blocked',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
};
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test src/components/__tests__/StatusBadge.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/StatusBadge.tsx dashboard/src/components/__tests__/StatusBadge.test.tsx
git commit -m "feat(dashboard): update StatusBadge to show 'Queued' for pending"
```

---

## Task 19: Integration Tests for Queue Workflow Flow

**Files:**
- Create: `tests/integration/test_queue_workflow_flow.py`

**Step 1: Write integration tests**

```python
# tests/integration/test_queue_workflow_flow.py
"""Integration tests for queue workflow flow."""

import pytest
from httpx import AsyncClient

from amelia.server.app import create_app


@pytest.fixture
async def app():
    """Create test app."""
    return create_app()


@pytest.fixture
async def client(app):
    """Create test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


class TestQueueWorkflowFlow:
    """Integration tests for complete queue workflow flow."""

    @pytest.mark.asyncio
    async def test_queue_then_start_workflow(self, client: AsyncClient) -> None:
        """Queue a workflow, then start it."""
        # Queue without starting
        create_response = await client.post(
            "/api/workflows",
            json={
                "issue_id": "ISSUE-123",
                "worktree_path": "/tmp/test-repo",
                "start": False,
            },
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["workflow_id"]

        # Verify it's pending
        get_response = await client.get(f"/api/workflows/{workflow_id}")
        assert get_response.status_code == 200
        assert get_response.json()["workflow_status"] == "pending"

        # Start it
        start_response = await client.post(f"/api/workflows/{workflow_id}/start")
        assert start_response.status_code == 202

        # Verify it's in_progress
        get_response = await client.get(f"/api/workflows/{workflow_id}")
        assert get_response.json()["workflow_status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_batch_start_multiple_workflows(self, client: AsyncClient) -> None:
        """Queue multiple workflows and batch start them."""
        # Queue two workflows
        ids = []
        for i in range(2):
            response = await client.post(
                "/api/workflows",
                json={
                    "issue_id": f"ISSUE-{i}",
                    "worktree_path": f"/tmp/test-repo-{i}",
                    "start": False,
                },
            )
            ids.append(response.json()["workflow_id"])

        # Batch start
        batch_response = await client.post(
            "/api/workflows/start-batch",
            json={"workflow_ids": ids},
        )
        assert batch_response.status_code == 200
        result = batch_response.json()
        assert len(result["started"]) == 2
        assert result["errors"] == {}
```

**Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_queue_workflow_flow.py -v`
Expected: PASS (after all previous tasks complete)

**Step 3: Commit**

```bash
git add tests/integration/test_queue_workflow_flow.py
git commit -m "test(integration): add queue workflow flow tests"
```

---

## Task 20: Run Full Test Suite and Fix Issues

**Step 1: Run Python tests**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All PASS

**Step 2: Run type checking**

Run: `uv run mypy amelia`
Expected: No errors

**Step 3: Run linting**

Run: `uv run ruff check amelia tests`
Expected: No errors

**Step 4: Run dashboard tests**

Run: `cd dashboard && pnpm test:run`
Expected: All PASS

**Step 5: Run dashboard type check**

Run: `cd dashboard && pnpm type-check`
Expected: No errors

**Step 6: Run dashboard lint**

Run: `cd dashboard && pnpm lint`
Expected: No errors

**Step 7: Fix any issues found**

Address any failing tests, type errors, or lint warnings.

**Step 8: Final commit**

```bash
git add -A
git commit -m "chore: fix issues from full test suite run"
```

---

## Summary

This plan implements the Queue Workflows feature in 20 bite-sized tasks:

1. **Tasks 1-4**: Add models (`planned_at`, `start`/`plan_now` params, `BatchStartRequest`, `BatchStartResponse`)
2. **Tasks 5-8**: Add orchestrator methods (`queue_workflow`, `queue_and_plan_workflow`, `start_pending_workflow`, `start_batch_workflows`)
3. **Tasks 9-11**: Add API endpoints (modify POST /workflows, add POST /start, POST /start-batch)
4. **Tasks 12-13**: Add CLI commands (`--queue`/`--plan` flags, new `run` command)
5. **Tasks 14-18**: Update dashboard (types, API client, QuickShotModal, WorkflowsPage, StatusBadge)
6. **Tasks 19-20**: Integration tests and full suite verification

Each task follows TDD with explicit test-first steps, exact file paths, complete code, and commit points.
