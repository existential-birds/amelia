# Event Bus & Orchestrator Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the event bus for real-time event broadcasting and the orchestrator service for concurrent workflow execution with approval gates.

**Architecture:** EventBus pub/sub system for broadcasting WorkflowEvents, OrchestratorService managing concurrent workflows with approval gates, sequence locking for thread-safe event emission, ServerLifecycle for graceful startup/shutdown, LogRetentionService for cleanup, and WorktreeHealthChecker for periodic validation.

**Tech Stack:** Python asyncio, FastAPI dependencies, pytest-asyncio, loguru

**Depends on:**
- Plan 1: Server Foundation (FastAPI app, config)
- Plan 2: Database Foundation (Database, migrations)
- Plan 3: Workflow Models & Repository (WorkflowEvent, WorkflowRepository, ServerExecutionState)

---

## Task 1: Implement EventBus for Pub/Sub

**Files:**
- Create: `amelia/server/events/__init__.py`
- Create: `amelia/server/events/bus.py`
- Create: `tests/unit/server/events/test_bus.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/events/test_bus.py
"""Unit tests for EventBus pub/sub."""
import pytest
from datetime import datetime
from amelia.server.events.bus import EventBus
from amelia.server.models import EventType, WorkflowEvent


@pytest.fixture
def event_bus() -> EventBus:
    """Create EventBus instance."""
    return EventBus()


@pytest.fixture
def sample_event() -> WorkflowEvent:
    """Create sample event."""
    return WorkflowEvent(
        id="evt-1",
        workflow_id="wf-1",
        sequence=1,
        timestamp=datetime.utcnow(),
        agent="system",
        event_type=EventType.WORKFLOW_STARTED,
        message="Workflow started",
    )


def test_eventbus_creation(event_bus: EventBus):
    """EventBus should be created with no subscribers."""
    assert event_bus._subscribers == []


def test_subscribe(event_bus: EventBus):
    """Should allow subscribing with a callback."""
    def callback(event: WorkflowEvent) -> None:
        pass

    event_bus.subscribe(callback)
    assert len(event_bus._subscribers) == 1
    assert event_bus._subscribers[0] == callback


def test_unsubscribe(event_bus: EventBus):
    """Should allow unsubscribing a callback."""
    def callback(event: WorkflowEvent) -> None:
        pass

    event_bus.subscribe(callback)
    event_bus.unsubscribe(callback)
    assert len(event_bus._subscribers) == 0


def test_unsubscribe_nonexistent(event_bus: EventBus):
    """Unsubscribe nonexistent callback should be no-op."""
    def callback(event: WorkflowEvent) -> None:
        pass

    # Should not raise
    event_bus.unsubscribe(callback)
    assert len(event_bus._subscribers) == 0


def test_emit_single_subscriber(event_bus: EventBus, sample_event: WorkflowEvent):
    """Emit should call all subscribers."""
    received = []

    def callback(event: WorkflowEvent) -> None:
        received.append(event)

    event_bus.subscribe(callback)
    event_bus.emit(sample_event)

    assert len(received) == 1
    assert received[0] == sample_event


def test_emit_multiple_subscribers(event_bus: EventBus, sample_event: WorkflowEvent):
    """Emit should call all subscribers."""
    received1 = []
    received2 = []

    def callback1(event: WorkflowEvent) -> None:
        received1.append(event)

    def callback2(event: WorkflowEvent) -> None:
        received2.append(event)

    event_bus.subscribe(callback1)
    event_bus.subscribe(callback2)
    event_bus.emit(sample_event)

    assert len(received1) == 1
    assert len(received2) == 1
    assert received1[0] == sample_event
    assert received2[0] == sample_event


def test_emit_no_subscribers(event_bus: EventBus, sample_event: WorkflowEvent):
    """Emit with no subscribers should not raise."""
    event_bus.emit(sample_event)  # Should not raise


def test_emit_subscriber_exception(event_bus: EventBus, sample_event: WorkflowEvent):
    """Exception in one subscriber should not affect others."""
    received = []

    def failing_callback(event: WorkflowEvent) -> None:
        raise RuntimeError("Test error")

    def successful_callback(event: WorkflowEvent) -> None:
        received.append(event)

    event_bus.subscribe(failing_callback)
    event_bus.subscribe(successful_callback)

    # Emit should log error but continue
    event_bus.emit(sample_event)

    # Second subscriber should still receive event
    assert len(received) == 1
    assert received[0] == sample_event


def test_multiple_events(event_bus: EventBus):
    """Should handle multiple events in sequence."""
    received = []

    def callback(event: WorkflowEvent) -> None:
        received.append(event)

    event_bus.subscribe(callback)

    event1 = WorkflowEvent(
        id="evt-1", workflow_id="wf-1", sequence=1,
        timestamp=datetime.utcnow(), agent="system",
        event_type=EventType.WORKFLOW_STARTED, message="Started",
    )
    event2 = WorkflowEvent(
        id="evt-2", workflow_id="wf-1", sequence=2,
        timestamp=datetime.utcnow(), agent="architect",
        event_type=EventType.STAGE_STARTED, message="Planning",
    )

    event_bus.emit(event1)
    event_bus.emit(event2)

    assert len(received) == 2
    assert received[0] == event1
    assert received[1] == event2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/events/test_bus.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement EventBus**

```python
# amelia/server/events/__init__.py
"""Event system for real-time workflow updates."""
from amelia.server.events.bus import EventBus

__all__ = ["EventBus"]
```

```python
# amelia/server/events/bus.py
"""Event bus for pub/sub broadcasting of workflow events."""
from typing import Callable
from loguru import logger
from amelia.server.models import WorkflowEvent


EventCallback = Callable[[WorkflowEvent], None]


class EventBus:
    """Synchronous pub/sub event bus for broadcasting workflow events.

    Thread-safe for single-threaded asyncio event loop.
    Subscribers are called synchronously in order of subscription.

    Example:
        >>> bus = EventBus()
        >>> def print_event(event: WorkflowEvent) -> None:
        ...     print(f"Event: {event.message}")
        >>> bus.subscribe(print_event)
        >>> bus.emit(event)  # Calls print_event(event)
    """

    def __init__(self) -> None:
        """Initialize empty event bus."""
        self._subscribers: list[EventCallback] = []

    def subscribe(self, callback: EventCallback) -> None:
        """Subscribe to all workflow events.

        Args:
            callback: Function to call when events are emitted.
                Will be called synchronously with each emitted event.
        """
        self._subscribers.append(callback)
        logger.debug(
            "EventBus subscriber added",
            callback=callback.__name__,
            total_subscribers=len(self._subscribers),
        )

    def unsubscribe(self, callback: EventCallback) -> None:
        """Unsubscribe from workflow events.

        Args:
            callback: The callback to remove.
        """
        try:
            self._subscribers.remove(callback)
            logger.debug(
                "EventBus subscriber removed",
                callback=callback.__name__,
                total_subscribers=len(self._subscribers),
            )
        except ValueError:
            # Callback not in list - no-op
            pass

    def emit(self, event: WorkflowEvent) -> None:
        """Emit event to all subscribers.

        Subscribers are called synchronously in subscription order.
        If a subscriber raises an exception, it is logged and other
        subscribers continue to receive the event.

        Args:
            event: The workflow event to broadcast.
        """
        for callback in self._subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.error(
                    "EventBus subscriber error",
                    callback=callback.__name__,
                    error=str(e),
                    event_id=event.id,
                    event_type=event.event_type,
                )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/events/test_bus.py -v`
Expected: PASS

**Step 5: Run linting and type checking**

Run: `uv run ruff check amelia/server/events && uv run mypy amelia/server/events`
Expected: No errors

**Step 6: Commit**

```bash
git add amelia/server/events/ tests/unit/server/events/
git commit -m "feat(events): implement EventBus for pub/sub broadcasting"
```

---

## Task 2: Add Orchestrator Custom Exceptions

**Files:**
- Create: `amelia/server/orchestrator/__init__.py`
- Create: `amelia/server/orchestrator/exceptions.py`
- Create: `tests/unit/server/orchestrator/test_exceptions.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/orchestrator/test_exceptions.py
"""Unit tests for orchestrator exceptions."""
import pytest
from amelia.server.orchestrator.exceptions import (
    WorkflowConflictError,
    ConcurrencyLimitError,
)


def test_workflow_conflict_error():
    """WorkflowConflictError should have custom message."""
    error = WorkflowConflictError("/path/to/worktree")
    assert "already active" in str(error).lower()
    assert "/path/to/worktree" in str(error)


def test_concurrency_limit_error():
    """ConcurrencyLimitError should have custom message."""
    error = ConcurrencyLimitError(5)
    assert "maximum" in str(error).lower()
    assert "5" in str(error)
    assert error.max_concurrent == 5
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_exceptions.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement exceptions**

```python
# amelia/server/orchestrator/__init__.py
"""Orchestrator service for managing concurrent workflow execution."""
from amelia.server.orchestrator.exceptions import (
    ConcurrencyLimitError,
    WorkflowConflictError,
)

__all__ = [
    "ConcurrencyLimitError",
    "WorkflowConflictError",
]
```

```python
# amelia/server/orchestrator/exceptions.py
"""Custom exceptions for orchestrator service."""


class WorkflowConflictError(ValueError):
    """Raised when attempting to start a workflow in a worktree that already has an active workflow."""

    def __init__(self, worktree_path: str):
        """Initialize error.

        Args:
            worktree_path: The path to the conflicting worktree.
        """
        self.worktree_path = worktree_path
        super().__init__(f"Workflow already active in worktree: {worktree_path}")


class ConcurrencyLimitError(ValueError):
    """Raised when attempting to start a workflow beyond the concurrency limit."""

    def __init__(self, max_concurrent: int):
        """Initialize error.

        Args:
            max_concurrent: The maximum number of concurrent workflows allowed.
        """
        self.max_concurrent = max_concurrent
        super().__init__(
            f"Maximum {max_concurrent} concurrent workflows already running"
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_exceptions.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/orchestrator/ tests/unit/server/orchestrator/test_exceptions.py
git commit -m "feat(orchestrator): add custom exceptions"
```

---

## Task 3: Implement OrchestratorService Core

**Files:**
- Create: `amelia/server/orchestrator/service.py`
- Create: `tests/unit/server/orchestrator/test_service.py`
- Modify: `amelia/server/orchestrator/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/orchestrator/test_service.py
"""Unit tests for OrchestratorService."""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from amelia.server.orchestrator.service import OrchestratorService
from amelia.server.orchestrator.exceptions import (
    WorkflowConflictError,
    ConcurrencyLimitError,
)
from amelia.server.models import EventType, WorkflowEvent, ServerExecutionState
from amelia.server.events.bus import EventBus
from amelia.server.database.repository import WorkflowRepository


@pytest.fixture
def mock_event_bus() -> EventBus:
    """Create mock event bus."""
    return EventBus()


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create mock repository."""
    repo = AsyncMock(spec=WorkflowRepository)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.set_status = AsyncMock()
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    repo.get = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def orchestrator(
    mock_event_bus: EventBus,
    mock_repository: AsyncMock,
) -> OrchestratorService:
    """Create orchestrator service."""
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        max_concurrent=5,
    )


def test_orchestrator_initialization(orchestrator: OrchestratorService):
    """OrchestratorService should initialize with empty state."""
    assert orchestrator._max_concurrent == 5
    assert len(orchestrator._active_tasks) == 0
    assert len(orchestrator._approval_events) == 0
    assert len(orchestrator._sequence_counters) == 0
    assert len(orchestrator._sequence_locks) == 0


def test_get_active_workflows_empty(orchestrator: OrchestratorService):
    """Should return empty list when no active workflows."""
    assert orchestrator.get_active_workflows() == []


@pytest.mark.asyncio
async def test_start_workflow_success(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Should start workflow and return workflow ID."""
    with patch.object(orchestrator, '_run_workflow', new=AsyncMock()) as mock_run:
        workflow_id = await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            worktree_name="feat-123",
        )

        assert workflow_id  # Should return a UUID
        assert "/path/to/worktree" in orchestrator._active_tasks
        mock_repository.create.assert_called_once()

        # Verify state creation
        call_args = mock_repository.create.call_args
        state = call_args[0][0]
        assert state.id == workflow_id
        assert state.issue_id == "ISSUE-123"
        assert state.worktree_path == "/path/to/worktree"
        assert state.worktree_name == "feat-123"
        assert state.workflow_status == "pending"


@pytest.mark.asyncio
async def test_start_workflow_conflict(
    orchestrator: OrchestratorService,
):
    """Should raise WorkflowConflictError when worktree already active."""
    # Create a fake task to simulate active workflow
    orchestrator._active_tasks["/path/to/worktree"] = asyncio.create_task(
        asyncio.sleep(1)
    )

    with pytest.raises(WorkflowConflictError) as exc_info:
        await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            worktree_name="feat-123",
        )

    assert "/path/to/worktree" in str(exc_info.value)

    # Cleanup
    orchestrator._active_tasks["/path/to/worktree"].cancel()


@pytest.mark.asyncio
async def test_start_workflow_concurrency_limit(
    orchestrator: OrchestratorService,
):
    """Should raise ConcurrencyLimitError when at max concurrent."""
    # Fill up to max concurrent
    for i in range(5):
        orchestrator._active_tasks[f"/path/to/worktree{i}"] = asyncio.create_task(
            asyncio.sleep(1)
        )

    with pytest.raises(ConcurrencyLimitError) as exc_info:
        await orchestrator.start_workflow(
            issue_id="ISSUE-123",
            worktree_path="/path/to/new",
            worktree_name="feat-new",
        )

    assert exc_info.value.max_concurrent == 5

    # Cleanup
    for task in orchestrator._active_tasks.values():
        task.cancel()


@pytest.mark.asyncio
async def test_cancel_workflow(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Should cancel running workflow task."""
    # Create mock workflow state
    mock_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        worktree_name="feat-123",
        workflow_status="in_progress",
        started_at=datetime.utcnow(),
    )
    mock_repository.get.return_value = mock_state

    # Create a fake running task
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/path/to/worktree"] = task

    await orchestrator.cancel_workflow("wf-1")

    # Task should be cancelled
    assert task.cancelled()


@pytest.mark.asyncio
async def test_cancel_workflow_not_running(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Cancel non-running workflow should be no-op."""
    mock_repository.get.return_value = None

    # Should not raise
    await orchestrator.cancel_workflow("nonexistent")


def test_get_active_workflows(orchestrator: OrchestratorService):
    """Should return list of active worktree paths."""
    orchestrator._active_tasks["/path/1"] = MagicMock()
    orchestrator._active_tasks["/path/2"] = MagicMock()

    active = orchestrator.get_active_workflows()
    assert set(active) == {"/path/1", "/path/2"}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement OrchestratorService core**

```python
# amelia/server/orchestrator/service.py
"""Orchestrator service for managing concurrent workflow execution."""
import asyncio
from datetime import datetime
from uuid import uuid4
from loguru import logger
from amelia.server.models import EventType, ServerExecutionState
from amelia.server.events.bus import EventBus
from amelia.server.database.repository import WorkflowRepository
from amelia.server.orchestrator.exceptions import (
    WorkflowConflictError,
    ConcurrencyLimitError,
)


class OrchestratorService:
    """Manages concurrent workflow executions across worktrees.

    Enforces one workflow per worktree and a global concurrency limit.
    Provides approval gate mechanism for blocked workflows.
    Thread-safe for asyncio event loop.
    """

    def __init__(
        self,
        event_bus: EventBus,
        repository: WorkflowRepository,
        max_concurrent: int = 5,
    ):
        """Initialize orchestrator service.

        Args:
            event_bus: Event bus for broadcasting workflow events.
            repository: Repository for workflow persistence.
            max_concurrent: Maximum number of concurrent workflows (default: 5).
        """
        self._event_bus = event_bus
        self._repository = repository
        self._max_concurrent = max_concurrent
        self._active_tasks: dict[str, asyncio.Task] = {}  # worktree_path -> task
        self._approval_events: dict[str, asyncio.Event] = {}  # workflow_id -> event
        self._approval_lock = asyncio.Lock()  # Prevents race conditions on approvals
        self._sequence_counters: dict[str, int] = {}  # workflow_id -> next sequence
        self._sequence_locks: dict[str, asyncio.Lock] = {}  # workflow_id -> lock

    async def start_workflow(
        self,
        issue_id: str,
        worktree_path: str,
        worktree_name: str,
        profile: str | None = None,
    ) -> str:
        """Start a new workflow.

        Args:
            issue_id: The issue ID to work on.
            worktree_path: Absolute path to the worktree.
            worktree_name: Human-readable worktree name.
            profile: Optional profile name.

        Returns:
            The workflow ID (UUID).

        Raises:
            WorkflowConflictError: If worktree already has active workflow.
            ConcurrencyLimitError: If at max concurrent workflows.
        """
        # Check worktree conflict
        if worktree_path in self._active_tasks:
            raise WorkflowConflictError(worktree_path)

        # Check concurrency limit
        if len(self._active_tasks) >= self._max_concurrent:
            raise ConcurrencyLimitError(self._max_concurrent)

        # Create workflow record
        workflow_id = str(uuid4())
        state = ServerExecutionState(
            id=workflow_id,
            issue_id=issue_id,
            worktree_path=worktree_path,
            worktree_name=worktree_name,
            workflow_status="pending",
            started_at=datetime.utcnow(),
        )
        await self._repository.create(state)

        logger.info(
            "Starting workflow",
            workflow_id=workflow_id,
            issue_id=issue_id,
            worktree_path=worktree_path,
        )

        # Start async task
        task = asyncio.create_task(
            self._run_workflow(workflow_id, state, profile)
        )
        self._active_tasks[worktree_path] = task

        # Remove from active tasks on completion
        def cleanup_task(_: asyncio.Task) -> None:
            self._active_tasks.pop(worktree_path, None)
            # Clean up workflow tracking data to prevent memory leaks
            self._sequence_counters.pop(workflow_id, None)
            self._sequence_locks.pop(workflow_id, None)
            logger.debug(
                "Workflow task completed",
                workflow_id=workflow_id,
                worktree_path=worktree_path,
            )

        task.add_done_callback(cleanup_task)

        return workflow_id

    async def cancel_workflow(self, workflow_id: str) -> None:
        """Cancel a running workflow.

        Args:
            workflow_id: The workflow to cancel.
        """
        workflow = await self._repository.get(workflow_id)
        if workflow and workflow.worktree_path in self._active_tasks:
            task = self._active_tasks[workflow.worktree_path]
            task.cancel()
            logger.info("Workflow cancelled", workflow_id=workflow_id)

    def get_active_workflows(self) -> list[str]:
        """Return list of active worktree paths.

        Returns:
            List of worktree paths with active workflows.
        """
        return list(self._active_tasks.keys())

    async def cancel_all_workflows(self, timeout: float = 5.0) -> None:
        """Cancel all running workflows.

        Used during server shutdown to cleanly cancel active workflows.
        Encapsulates access to _active_tasks for proper separation of concerns.

        Args:
            timeout: Seconds to wait for each task to cancel.
        """
        for worktree_path in list(self._active_tasks.keys()):
            task = self._active_tasks.get(worktree_path)
            if task:
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=timeout)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

    async def _run_workflow(
        self,
        workflow_id: str,
        initial_state: ServerExecutionState,
        profile: str | None,
    ) -> None:
        """Execute workflow with event emission.

        This is a placeholder for the actual LangGraph execution.
        Will be implemented in a future task.

        Args:
            workflow_id: The workflow ID.
            initial_state: Initial execution state.
            profile: Optional profile name.
        """
        # Placeholder - will be implemented with LangGraph integration
        logger.warning(
            "Workflow execution not yet implemented",
            workflow_id=workflow_id,
        )
        await asyncio.sleep(0)  # Prevent immediate completion in tests
```

**Step 4: Update __init__.py**

```python
# amelia/server/orchestrator/__init__.py
"""Orchestrator service for managing concurrent workflow execution."""
from amelia.server.orchestrator.exceptions import (
    ConcurrencyLimitError,
    WorkflowConflictError,
)
from amelia.server.orchestrator.service import OrchestratorService

__all__ = [
    "ConcurrencyLimitError",
    "OrchestratorService",
    "WorkflowConflictError",
]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py -v`
Expected: PASS

**Step 6: Run linting and type checking**

Run: `uv run ruff check amelia/server/orchestrator && uv run mypy amelia/server/orchestrator`
Expected: No errors

**Step 7: Commit**

```bash
git add amelia/server/orchestrator/ tests/unit/server/orchestrator/test_service.py
git commit -m "feat(orchestrator): implement OrchestratorService core with concurrency control"
```

---

## Task 4: Implement Event Emission with Sequence Locking

**Files:**
- Modify: `amelia/server/orchestrator/service.py`
- Modify: `tests/unit/server/orchestrator/test_service.py`
- Modify: `amelia/server/database/repository.py`
- Modify: `tests/unit/server/database/test_repository.py`

**Step 1: Write the failing test**

Add to `tests/unit/server/orchestrator/test_service.py`:

```python
@pytest.mark.asyncio
async def test_emit_event(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
):
    """Should emit event with sequence number and persist to DB."""
    received = []
    mock_event_bus.subscribe(lambda e: received.append(e))

    await orchestrator._emit(
        workflow_id="wf-1",
        event_type=EventType.WORKFLOW_STARTED,
        message="Test message",
    )

    # Should persist to DB
    mock_repository.save_event.assert_called_once()
    saved_event = mock_repository.save_event.call_args[0][0]
    assert saved_event.workflow_id == "wf-1"
    assert saved_event.event_type == EventType.WORKFLOW_STARTED
    assert saved_event.message == "Test message"
    assert saved_event.sequence == 1
    assert saved_event.agent == "system"

    # Should broadcast to event bus
    assert len(received) == 1
    assert received[0] == saved_event


@pytest.mark.asyncio
async def test_emit_sequence_increment(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Sequence numbers should increment per workflow."""
    await orchestrator._emit("wf-1", EventType.WORKFLOW_STARTED, "Event 1")
    await orchestrator._emit("wf-1", EventType.STAGE_STARTED, "Event 2")
    await orchestrator._emit("wf-1", EventType.STAGE_COMPLETED, "Event 3")

    # Check sequences
    calls = mock_repository.save_event.call_args_list
    assert calls[0][0][0].sequence == 1
    assert calls[1][0][0].sequence == 2
    assert calls[2][0][0].sequence == 3


@pytest.mark.asyncio
async def test_emit_different_workflows(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Different workflows should have independent sequence counters."""
    await orchestrator._emit("wf-1", EventType.WORKFLOW_STARTED, "WF1 Event 1")
    await orchestrator._emit("wf-2", EventType.WORKFLOW_STARTED, "WF2 Event 1")
    await orchestrator._emit("wf-1", EventType.STAGE_STARTED, "WF1 Event 2")

    calls = mock_repository.save_event.call_args_list
    # wf-1 sequences: 1, 2
    assert calls[0][0][0].workflow_id == "wf-1"
    assert calls[0][0][0].sequence == 1
    assert calls[2][0][0].workflow_id == "wf-1"
    assert calls[2][0][0].sequence == 2
    # wf-2 sequences: 1
    assert calls[1][0][0].workflow_id == "wf-2"
    assert calls[1][0][0].sequence == 1


@pytest.mark.asyncio
async def test_emit_with_correlation_id(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Should propagate correlation_id to event."""
    await orchestrator._emit(
        workflow_id="wf-1",
        event_type=EventType.APPROVAL_GRANTED,
        message="Approved",
        correlation_id="corr-123",
    )

    saved_event = mock_repository.save_event.call_args[0][0]
    assert saved_event.correlation_id == "corr-123"


@pytest.mark.asyncio
async def test_emit_with_data(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Should include structured data in event."""
    data = {"stage": "architect", "tasks": 5}

    await orchestrator._emit(
        workflow_id="wf-1",
        event_type=EventType.STAGE_STARTED,
        message="Planning started",
        data=data,
    )

    saved_event = mock_repository.save_event.call_args[0][0]
    assert saved_event.data == data


@pytest.mark.asyncio
async def test_emit_concurrent_same_workflow(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Concurrent emits for same workflow should have unique sequences."""
    # Simulate concurrent emits
    await asyncio.gather(
        orchestrator._emit("wf-1", EventType.FILE_CREATED, "File 1"),
        orchestrator._emit("wf-1", EventType.FILE_CREATED, "File 2"),
        orchestrator._emit("wf-1", EventType.FILE_CREATED, "File 3"),
    )

    calls = mock_repository.save_event.call_args_list
    sequences = [call[0][0].sequence for call in calls]

    # All sequences should be unique
    assert len(set(sequences)) == 3
    assert set(sequences) == {1, 2, 3}


@pytest.mark.asyncio
async def test_emit_resumes_from_db_max_sequence(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """First emit should query DB for max sequence."""
    mock_repository.get_max_event_sequence.return_value = 42

    await orchestrator._emit("wf-1", EventType.WORKFLOW_STARTED, "Resume")

    # Should query DB once
    mock_repository.get_max_event_sequence.assert_called_once_with("wf-1")

    # Next sequence should be 43
    saved_event = mock_repository.save_event.call_args[0][0]
    assert saved_event.sequence == 43
```

Add tests to the `TestWorkflowRepository` class in `tests/unit/server/database/test_repository.py`:

```python
    # Add these methods to the existing TestWorkflowRepository class

    async def test_save_event(self, repository: WorkflowRepository):
        """Should persist event to database."""
        # First create a workflow (required for foreign key)
        state = ServerExecutionState(
            id="wf-1",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            worktree_name="feat-123",
            workflow_status="in_progress",
            started_at=datetime.utcnow(),
        )
        await repository.create(state)

        event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="architect",
            event_type=EventType.STAGE_STARTED,
            message="Planning started",
        )

        await repository.save_event(event)

        # Verify in DB via get_max_event_sequence
        max_seq = await repository.get_max_event_sequence("wf-1")
        assert max_seq == 1

    async def test_save_event_with_data(self, repository: WorkflowRepository):
        """Should persist event with structured data."""
        # First create a workflow
        state = ServerExecutionState(
            id="wf-1",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            worktree_name="feat-123",
            workflow_status="in_progress",
            started_at=datetime.utcnow(),
        )
        await repository.create(state)

        event = WorkflowEvent(
            id="evt-1",
            workflow_id="wf-1",
            sequence=1,
            timestamp=datetime.utcnow(),
            agent="developer",
            event_type=EventType.FILE_CREATED,
            message="Created file",
            data={"file_path": "/path/to/file.py", "lines": 42},
        )

        await repository.save_event(event)

        # Verify event was saved (data_json column)
        max_seq = await repository.get_max_event_sequence("wf-1")
        assert max_seq == 1

    async def test_get_max_event_sequence_no_events(
        self, repository: WorkflowRepository
    ):
        """Should return None when no events exist."""
        max_seq = await repository.get_max_event_sequence("wf-nonexistent")
        assert max_seq is None

    async def test_get_max_event_sequence_with_events(
        self, repository: WorkflowRepository
    ):
        """Should return max sequence number."""
        # First create a workflow
        state = ServerExecutionState(
            id="wf-1",
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            worktree_name="feat-123",
            workflow_status="in_progress",
            started_at=datetime.utcnow(),
        )
        await repository.create(state)

        # Create events with different sequences
        for seq in [1, 3, 2, 5, 4]:
            event = WorkflowEvent(
                id=f"evt-{seq}",
                workflow_id="wf-1",
                sequence=seq,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=EventType.WORKFLOW_STARTED,
                message=f"Event {seq}",
            )
            await repository.save_event(event)

        max_seq = await repository.get_max_event_sequence("wf-1")
        assert max_seq == 5
```

Also add the required imports at the top of `tests/unit/server/database/test_repository.py`:

```python
from amelia.server.models import EventType, WorkflowEvent
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py::test_emit_event -v`
Expected: FAIL with AttributeError (_emit method not found)

**Step 3: Add get_max_event_sequence to repository**

Add to `amelia/server/database/repository.py`:

```python
    async def save_event(self, event: WorkflowEvent) -> None:
        """Persist workflow event to database.

        Args:
            event: The event to persist.
        """
        import json

        await self._db.execute(
            """
            INSERT INTO events (
                id, workflow_id, sequence, timestamp, agent,
                event_type, message, data_json, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.workflow_id,
                event.sequence,
                event.timestamp.isoformat(),
                event.agent,
                event.event_type.value,
                event.message,
                json.dumps(event.data) if event.data else None,
                event.correlation_id,
            ),
        )

    async def get_max_event_sequence(self, workflow_id: str) -> int | None:
        """Get maximum event sequence number for a workflow.

        Args:
            workflow_id: The workflow ID.

        Returns:
            Maximum sequence number, or None if no events exist.
        """
        return await self._db.fetch_scalar(
            "SELECT MAX(sequence) FROM events WHERE workflow_id = ?",
            (workflow_id,),
        )
```

**Step 4: Implement _emit method**

Add to `amelia/server/orchestrator/service.py`:

```python
    async def _emit(
        self,
        workflow_id: str,
        event_type: EventType,
        message: str,
        data: dict | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Emit a workflow event with write-ahead persistence.

        Events are persisted to database BEFORE being broadcast to subscribers.
        This ensures no events are lost if server crashes between emit and broadcast.

        Thread-safe: Uses per-workflow lock to prevent sequence number collisions
        when multiple events are emitted concurrently for the same workflow.

        Args:
            workflow_id: The workflow this event belongs to.
            event_type: Type of event being emitted.
            message: Human-readable description.
            data: Optional structured payload.
            correlation_id: Optional ID for tracing related events.
        """
        from amelia.server.models import WorkflowEvent

        # Get or create lock for this workflow's sequence counter
        if workflow_id not in self._sequence_locks:
            self._sequence_locks[workflow_id] = asyncio.Lock()

        async with self._sequence_locks[workflow_id]:
            # Get next sequence number for this workflow
            if workflow_id not in self._sequence_counters:
                # On first event, query DB for max sequence
                max_seq = await self._repository.get_max_event_sequence(workflow_id)
                self._sequence_counters[workflow_id] = max_seq if max_seq else 0

            self._sequence_counters[workflow_id] += 1
            sequence = self._sequence_counters[workflow_id]

            event = WorkflowEvent(
                id=str(uuid4()),
                workflow_id=workflow_id,
                sequence=sequence,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=event_type,
                message=message,
                data=data,
                correlation_id=correlation_id,
            )

            # Write-ahead: persist to DB first
            await self._repository.save_event(event)

        # Broadcast outside the lock to avoid holding it during I/O
        self._event_bus.emit(event)

        logger.debug(
            "Event emitted",
            workflow_id=workflow_id,
            event_type=event_type.value,
            sequence=sequence,
        )
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py -v`
Run: `uv run pytest tests/unit/server/database/test_repository.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/orchestrator/service.py amelia/server/database/repository.py tests/
git commit -m "feat(orchestrator): implement event emission with sequence locking"
```

---

## Task 5: Implement Approval Flow

**Files:**
- Modify: `amelia/server/orchestrator/service.py`
- Modify: `tests/unit/server/orchestrator/test_service.py`

**Step 1: Write the failing test**

Add to `tests/unit/server/orchestrator/test_service.py`:

```python
@pytest.mark.asyncio
async def test_wait_for_approval(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
):
    """Should block until approval is granted."""
    received_events = []
    mock_event_bus.subscribe(lambda e: received_events.append(e))

    # Start waiting in background
    wait_task = asyncio.create_task(
        orchestrator._wait_for_approval("wf-1")
    )

    # Give it a moment to start waiting
    await asyncio.sleep(0.01)

    # Should be blocked
    assert not wait_task.done()

    # Should have created approval event
    assert "wf-1" in orchestrator._approval_events

    # Should have emitted APPROVAL_REQUIRED
    approval_required = [e for e in received_events if e.event_type == EventType.APPROVAL_REQUIRED]
    assert len(approval_required) == 1

    # Simulate approval
    orchestrator._approval_events["wf-1"].set()

    # Should complete
    await asyncio.wait_for(wait_task, timeout=1.0)
    assert wait_task.done()


@pytest.mark.asyncio
async def test_approve_workflow_success(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
):
    """Should approve blocked workflow."""
    received_events = []
    mock_event_bus.subscribe(lambda e: received_events.append(e))

    # Simulate workflow waiting for approval
    orchestrator._approval_events["wf-1"] = asyncio.Event()

    success = await orchestrator.approve_workflow("wf-1", correlation_id="corr-123")

    assert success is True

    # Should remove from approval events
    assert "wf-1" not in orchestrator._approval_events

    # Should update status
    mock_repository.set_status.assert_called_once_with("wf-1", "in_progress")

    # Should emit APPROVAL_GRANTED
    approval_granted = [e for e in received_events if e.event_type == EventType.APPROVAL_GRANTED]
    assert len(approval_granted) == 1
    assert approval_granted[0].correlation_id == "corr-123"


@pytest.mark.asyncio
async def test_approve_workflow_not_blocked(
    orchestrator: OrchestratorService,
):
    """Approve non-blocked workflow should return False."""
    success = await orchestrator.approve_workflow("wf-1")
    assert success is False


@pytest.mark.asyncio
async def test_approve_workflow_race_condition(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Concurrent approvals should be idempotent."""
    orchestrator._approval_events["wf-1"] = asyncio.Event()

    # Simulate concurrent approvals
    results = await asyncio.gather(
        orchestrator.approve_workflow("wf-1"),
        orchestrator.approve_workflow("wf-1"),
    )

    # Only one should succeed
    assert results.count(True) == 1
    assert results.count(False) == 1


@pytest.mark.asyncio
async def test_reject_workflow_success(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
    mock_event_bus: EventBus,
):
    """Should reject blocked workflow."""
    received_events = []
    mock_event_bus.subscribe(lambda e: received_events.append(e))

    # Create mock workflow and task
    mock_state = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/path/to/worktree",
        worktree_name="feat-123",
        workflow_status="blocked",
        started_at=datetime.utcnow(),
    )
    mock_repository.get.return_value = mock_state

    # Create fake task
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/path/to/worktree"] = task
    orchestrator._approval_events["wf-1"] = asyncio.Event()

    success = await orchestrator.reject_workflow("wf-1", feedback="Plan too complex")

    assert success is True

    # Should update status to failed
    mock_repository.set_status.assert_called_once_with(
        "wf-1", "failed", failure_reason="Plan too complex"
    )

    # Should cancel task
    assert task.cancelled()

    # Should emit APPROVAL_REJECTED
    approval_rejected = [e for e in received_events if e.event_type == EventType.APPROVAL_REJECTED]
    assert len(approval_rejected) == 1
    assert "rejected" in approval_rejected[0].message.lower()


@pytest.mark.asyncio
async def test_reject_workflow_not_blocked(
    orchestrator: OrchestratorService,
):
    """Reject non-blocked workflow should return False."""
    success = await orchestrator.reject_workflow("wf-1", feedback="Nope")
    assert success is False
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py::test_wait_for_approval -v`
Expected: FAIL with AttributeError

**Step 3: Implement approval flow methods**

Add to `amelia/server/orchestrator/service.py`:

```python
    async def approve_workflow(
        self,
        workflow_id: str,
        correlation_id: str | None = None,
    ) -> bool:
        """Approve a blocked workflow.

        Args:
            workflow_id: The workflow to approve.
            correlation_id: Optional ID for tracing this action.

        Returns:
            True if approval was processed, False if already handled or not blocked.

        Thread-safe: Uses atomic pop to prevent race conditions when multiple
        clients approve simultaneously.
        """
        async with self._approval_lock:
            # Atomic check-and-remove prevents duplicate approvals
            event = self._approval_events.pop(workflow_id, None)
            if not event:
                # Already approved, rejected, or not blocked
                return False

            await self._repository.set_status(workflow_id, "in_progress")
            await self._emit(
                workflow_id,
                EventType.APPROVAL_GRANTED,
                "Plan approved",
                correlation_id=correlation_id,
            )
            event.set()

            logger.info(
                "Workflow approved",
                workflow_id=workflow_id,
                correlation_id=correlation_id,
            )
            return True

    async def reject_workflow(
        self,
        workflow_id: str,
        feedback: str,
    ) -> bool:
        """Reject a blocked workflow.

        Args:
            workflow_id: The workflow to reject.
            feedback: Reason for rejection.

        Returns:
            True if rejection was processed, False if already handled or not blocked.

        Thread-safe: Uses atomic pop to prevent race conditions.
        """
        async with self._approval_lock:
            # Atomic check-and-remove prevents duplicate rejections
            event = self._approval_events.pop(workflow_id, None)
            if not event:
                # Already approved, rejected, or not blocked
                return False

            await self._repository.set_status(
                workflow_id, "failed", failure_reason=feedback
            )
            await self._emit(
                workflow_id,
                EventType.APPROVAL_REJECTED,
                f"Plan rejected: {feedback}",
            )

            # Cancel the waiting task
            workflow = await self._repository.get(workflow_id)
            if workflow and workflow.worktree_path in self._active_tasks:
                self._active_tasks[workflow.worktree_path].cancel()

            logger.info(
                "Workflow rejected",
                workflow_id=workflow_id,
                feedback=feedback,
            )
            return True

    async def _wait_for_approval(self, workflow_id: str) -> None:
        """Block until workflow is approved or rejected.

        Args:
            workflow_id: The workflow awaiting approval.
        """
        event = asyncio.Event()
        self._approval_events[workflow_id] = event
        await self._emit(
            workflow_id,
            EventType.APPROVAL_REQUIRED,
            "Awaiting plan approval",
        )

        logger.info("Workflow awaiting approval", workflow_id=workflow_id)

        try:
            await event.wait()
        finally:
            # Cleanup - event should already be removed by approve/reject
            self._approval_events.pop(workflow_id, None)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/orchestrator/test_service.py
git commit -m "feat(orchestrator): implement approval flow with race condition safety"
```

---

## Task 6: Implement LogRetentionService

**Files:**
- Create: `amelia/server/lifecycle/__init__.py`
- Create: `amelia/server/lifecycle/retention.py`
- Create: `tests/unit/server/lifecycle/test_retention.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/lifecycle/test_retention.py
"""Unit tests for LogRetentionService."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from pydantic import BaseModel
from amelia.server.lifecycle.retention import LogRetentionService, CleanupResult


class MockConfig(BaseModel):
    """Mock server config."""
    log_retention_days: int = 30
    log_retention_max_events: int = 100_000


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create mock database."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=0)
    return db


@pytest.fixture
def config() -> MockConfig:
    """Create config."""
    return MockConfig()


@pytest.fixture
def retention_service(mock_db: AsyncMock, config: MockConfig) -> LogRetentionService:
    """Create retention service."""
    return LogRetentionService(db=mock_db, config=config)


@pytest.mark.asyncio
async def test_cleanup_on_shutdown(
    retention_service: LogRetentionService,
    mock_db: AsyncMock,
):
    """Should delete old events and workflows."""
    mock_db.execute.side_effect = [50, 5]  # events deleted, workflows deleted

    result = await retention_service.cleanup_on_shutdown()

    assert result.events_deleted == 50
    assert result.workflows_deleted == 5
    assert mock_db.execute.call_count == 2


@pytest.mark.asyncio
async def test_cleanup_uses_retention_days(
    retention_service: LogRetentionService,
    mock_db: AsyncMock,
    config: MockConfig,
):
    """Should use configured retention_days."""
    config.log_retention_days = 90
    retention_service = LogRetentionService(db=mock_db, config=config)

    await retention_service.cleanup_on_shutdown()

    # Verify cutoff date calculation
    # Check first SQL call has appropriate WHERE clause
    sql_call = mock_db.execute.call_args_list[0][0][0]
    assert "WHERE" in sql_call


@pytest.mark.asyncio
async def test_cleanup_deletes_by_status(
    retention_service: LogRetentionService,
    mock_db: AsyncMock,
):
    """Should only delete from completed/failed/cancelled workflows."""
    await retention_service.cleanup_on_shutdown()

    # Check SQL includes status filter
    sql_call = mock_db.execute.call_args_list[0][0][0]
    assert "workflow_id IN" in sql_call
    assert "SELECT id FROM workflows" in sql_call


def test_cleanup_result():
    """CleanupResult should be instantiable."""
    result = CleanupResult(events_deleted=10, workflows_deleted=2)
    assert result.events_deleted == 10
    assert result.workflows_deleted == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/lifecycle/test_retention.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement LogRetentionService**

```python
# amelia/server/lifecycle/__init__.py
"""Server lifecycle management."""
from amelia.server.lifecycle.retention import CleanupResult, LogRetentionService

__all__ = ["CleanupResult", "LogRetentionService"]
```

```python
# amelia/server/lifecycle/retention.py
"""Log retention service for cleaning up old workflow data."""
from datetime import datetime, timedelta
from pydantic import BaseModel
from loguru import logger
from amelia.server.database.connection import Database


class CleanupResult(BaseModel):
    """Result of cleanup operation."""
    events_deleted: int
    workflows_deleted: int


class LogRetentionService:
    """Manages event log cleanup on server shutdown.

    Cleanup runs only during graceful shutdown to:
    - Avoid runtime performance impact
    - Ensure cleanup completes before server exits
    - Keep implementation simple (no background tasks)
    """

    def __init__(self, db: Database, config) -> None:
        """Initialize retention service.

        Args:
            db: Database connection.
            config: Server configuration with retention settings.
        """
        self._db = db
        self._config = config

    async def cleanup_on_shutdown(self) -> CleanupResult:
        """Execute retention policy cleanup during server shutdown.

        Deletes:
        1. Events from workflows completed/failed/cancelled more than
           retention_days ago
        2. Workflows with no remaining events

        Returns:
            CleanupResult with counts of deleted records.
        """
        logger.info(
            "Running log retention cleanup",
            retention_days=self._config.log_retention_days,
            max_events=self._config.log_retention_max_events,
        )

        cutoff_date = datetime.utcnow() - timedelta(
            days=self._config.log_retention_days
        )

        # Delete old events from completed/failed/cancelled workflows
        events_deleted = await self._db.execute(
            """
            DELETE FROM events
            WHERE workflow_id IN (
                SELECT id FROM workflows
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_at < ?
            )
            """,
            (cutoff_date.isoformat(),),
        )

        # Delete workflows with no remaining events
        workflows_deleted = await self._db.execute(
            """
            DELETE FROM workflows
            WHERE id NOT IN (SELECT DISTINCT workflow_id FROM events)
            AND status IN ('completed', 'failed', 'cancelled')
            """
        )

        logger.info(
            "Cleanup complete",
            events_deleted=events_deleted,
            workflows_deleted=workflows_deleted,
        )

        return CleanupResult(
            events_deleted=events_deleted,
            workflows_deleted=workflows_deleted,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/lifecycle/test_retention.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/lifecycle/ tests/unit/server/lifecycle/
git commit -m "feat(lifecycle): implement LogRetentionService for cleanup"
```

---

## Task 7: Implement ServerLifecycle

**Files:**
- Create: `amelia/server/lifecycle/server.py`
- Create: `tests/unit/server/lifecycle/test_server.py`
- Modify: `amelia/server/lifecycle/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/lifecycle/test_server.py
"""Unit tests for ServerLifecycle."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from amelia.server.lifecycle.server import ServerLifecycle
from amelia.server.lifecycle.retention import CleanupResult


@pytest.fixture
def mock_orchestrator() -> AsyncMock:
    """Create mock orchestrator."""
    orch = AsyncMock()
    orch.recover_interrupted_workflows = AsyncMock()
    orch.get_active_workflows = MagicMock(return_value=[])
    orch._active_tasks = {}
    return orch


@pytest.fixture
def mock_retention() -> AsyncMock:
    """Create mock retention service."""
    retention = AsyncMock()
    retention.cleanup_on_shutdown = AsyncMock(
        return_value=CleanupResult(events_deleted=10, workflows_deleted=2)
    )
    return retention


@pytest.fixture
def lifecycle(
    mock_orchestrator: AsyncMock,
    mock_retention: AsyncMock,
) -> ServerLifecycle:
    """Create server lifecycle."""
    return ServerLifecycle(
        orchestrator=mock_orchestrator,
        log_retention=mock_retention,
    )


def test_lifecycle_initialization(lifecycle: ServerLifecycle):
    """ServerLifecycle should initialize with not shutting down."""
    assert lifecycle.is_shutting_down is False


@pytest.mark.asyncio
async def test_startup(lifecycle: ServerLifecycle, mock_orchestrator: AsyncMock):
    """Startup should call recover_interrupted_workflows."""
    await lifecycle.startup()

    mock_orchestrator.recover_interrupted_workflows.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_no_active_workflows(
    lifecycle: ServerLifecycle,
    mock_orchestrator: AsyncMock,
    mock_retention: AsyncMock,
):
    """Shutdown with no active workflows should cleanup immediately."""
    mock_orchestrator.get_active_workflows.return_value = []

    await lifecycle.shutdown()

    assert lifecycle.is_shutting_down is True
    mock_retention.cleanup_on_shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_waits_for_workflows(
    lifecycle: ServerLifecycle,
    mock_orchestrator: AsyncMock,
):
    """Shutdown should wait for active workflows to complete."""
    # Simulate workflow that completes after 0.1s
    active_paths = ["/path/to/worktree"]
    call_count = 0

    def get_active():
        nonlocal call_count
        call_count += 1
        if call_count > 2:
            return []
        return active_paths

    mock_orchestrator.get_active_workflows = get_active

    await lifecycle.shutdown()

    assert lifecycle.is_shutting_down is True
    assert call_count > 1  # Should have checked multiple times


@pytest.mark.asyncio
async def test_shutdown_timeout_cancels_workflows(
    lifecycle: ServerLifecycle,
    mock_orchestrator: AsyncMock,
):
    """Shutdown timeout should cancel remaining workflows."""
    # Create mock task that never completes
    mock_task = AsyncMock()
    mock_task.cancel = MagicMock()
    mock_task.cancelled = MagicMock(return_value=True)

    mock_orchestrator.get_active_workflows.return_value = ["/path/to/worktree"]
    mock_orchestrator._active_tasks = {"/path/to/worktree": mock_task}

    # Use short timeout for test
    lifecycle._shutdown_timeout = 0.1

    await lifecycle.shutdown()

    # Should have cancelled the task
    mock_task.cancel.assert_called()


def test_is_shutting_down_property(lifecycle: ServerLifecycle):
    """is_shutting_down should reflect internal state."""
    assert lifecycle.is_shutting_down is False

    lifecycle._shutting_down = True
    assert lifecycle.is_shutting_down is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/lifecycle/test_server.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement ServerLifecycle**

```python
# amelia/server/lifecycle/server.py
"""Server lifecycle management for startup and shutdown."""
import asyncio
from loguru import logger
from amelia.server.orchestrator.service import OrchestratorService
from amelia.server.lifecycle.retention import LogRetentionService


class ServerLifecycle:
    """Manages server startup and graceful shutdown.

    Coordinates:
    - Workflow recovery on startup
    - Graceful workflow completion on shutdown
    - Log retention cleanup
    - Connection cleanup
    """

    def __init__(
        self,
        orchestrator: OrchestratorService,
        log_retention: LogRetentionService,
        shutdown_timeout: int = 30,
    ) -> None:
        """Initialize lifecycle manager.

        Args:
            orchestrator: Orchestrator service instance.
            log_retention: Log retention service instance.
            shutdown_timeout: Seconds to wait for workflows before cancelling.
        """
        self._orchestrator = orchestrator
        self._log_retention = log_retention
        self._shutting_down = False
        self._shutdown_timeout = shutdown_timeout

    @property
    def is_shutting_down(self) -> bool:
        """Check if server is shutting down.

        Returns:
            True if shutdown has been initiated.
        """
        return self._shutting_down

    async def startup(self) -> None:
        """Execute startup sequence.

        Recovers any workflows that were interrupted by server crash.
        """
        logger.info("Server starting up...")
        await self._orchestrator.recover_interrupted_workflows()
        logger.info("Server startup complete")

    async def shutdown(self) -> None:
        """Execute graceful shutdown sequence.

        Steps:
        1. Set shutting_down flag (middleware rejects new workflows)
        2. Wait for active workflows to complete (with timeout)
        3. Cancel remaining workflows
        4. Run log retention cleanup
        5. Close connections (handled by caller)
        """
        self._shutting_down = True
        logger.info("Server shutting down...")

        # Wait for blocked workflows with timeout
        active = self._orchestrator.get_active_workflows()
        if active:
            logger.info(f"Waiting for {len(active)} active workflows...")
            try:
                await asyncio.wait_for(
                    self._wait_for_workflows_to_finish(),
                    timeout=self._shutdown_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("Shutdown timeout - cancelling remaining workflows")

        # Cancel any still-running workflows
        # Uses OrchestratorService.cancel_all_workflows() for proper encapsulation
        # instead of accessing _active_tasks directly
        await self._orchestrator.cancel_all_workflows(timeout=5.0)

        # Persist final state (already done via repository on each update)
        logger.info("Final state persisted to database")

        # Run log retention cleanup
        cleanup_result = await self._log_retention.cleanup_on_shutdown()
        logger.info(
            "Cleanup complete",
            events_deleted=cleanup_result.events_deleted,
            workflows_deleted=cleanup_result.workflows_deleted,
        )

        logger.info("Server shutdown complete")

    async def _wait_for_workflows_to_finish(self) -> None:
        """Wait for all active workflows to complete."""
        while self._orchestrator.get_active_workflows():
            await asyncio.sleep(1)
```

**Step 4: Update __init__.py**

```python
# amelia/server/lifecycle/__init__.py
"""Server lifecycle management."""
from amelia.server.lifecycle.retention import CleanupResult, LogRetentionService
from amelia.server.lifecycle.server import ServerLifecycle

__all__ = ["CleanupResult", "LogRetentionService", "ServerLifecycle"]
```

**Step 5: Add recover_interrupted_workflows stub to OrchestratorService**

Add to `amelia/server/orchestrator/service.py`:

```python
    async def recover_interrupted_workflows(self) -> None:
        """Recover workflows that were running when server crashed.

        This is a placeholder - full implementation will be added
        when LangGraph integration is complete.
        """
        logger.info("Checking for interrupted workflows...")
        # TODO: Query for workflows with status=in_progress or blocked
        # and mark them as failed with appropriate reason
        logger.info("No interrupted workflows to recover")
```

**Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/lifecycle/test_server.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/server/lifecycle/ amelia/server/orchestrator/service.py tests/unit/server/lifecycle/
git commit -m "feat(lifecycle): implement ServerLifecycle for graceful startup/shutdown"
```

---

## Task 8: Implement WorktreeHealthChecker

**Files:**
- Create: `amelia/server/lifecycle/health_checker.py`
- Create: `tests/unit/server/lifecycle/test_health_checker.py`
- Modify: `amelia/server/lifecycle/__init__.py`

**Step 1: Write the failing test**

```python
# tests/unit/server/lifecycle/test_health_checker.py
"""Unit tests for WorktreeHealthChecker."""
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from amelia.server.lifecycle.health_checker import WorktreeHealthChecker
from amelia.server.models import ServerExecutionState
from datetime import datetime


@pytest.fixture
def mock_orchestrator() -> AsyncMock:
    """Create mock orchestrator."""
    orch = AsyncMock()
    orch.get_active_workflows = MagicMock(return_value=[])
    orch.get_workflow_by_worktree = AsyncMock(return_value=None)
    orch.cancel_workflow = AsyncMock()
    return orch


@pytest.fixture
def health_checker(mock_orchestrator: AsyncMock) -> WorktreeHealthChecker:
    """Create health checker."""
    return WorktreeHealthChecker(
        orchestrator=mock_orchestrator,
        check_interval=0.1,  # Short interval for tests
    )


@pytest.mark.asyncio
async def test_start_and_stop(health_checker: WorktreeHealthChecker):
    """Should start and stop check loop."""
    await health_checker.start()
    assert health_checker._task is not None
    assert not health_checker._task.done()

    await health_checker.stop()
    assert health_checker._task.cancelled() or health_checker._task.done()


@pytest.mark.asyncio
async def test_check_healthy_worktree(
    health_checker: WorktreeHealthChecker,
    mock_orchestrator: AsyncMock,
    tmp_path: Path,
):
    """Healthy worktree should not trigger cancellation."""
    # Create fake worktree
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    (worktree_path / ".git").touch()

    mock_orchestrator.get_active_workflows.return_value = [str(worktree_path)]

    await health_checker._check_all_worktrees()

    # Should not cancel
    mock_orchestrator.cancel_workflow.assert_not_called()


@pytest.mark.asyncio
async def test_check_deleted_worktree(
    health_checker: WorktreeHealthChecker,
    mock_orchestrator: AsyncMock,
):
    """Deleted worktree should trigger cancellation."""
    # Mock workflow
    mock_workflow = ServerExecutionState(
        id="wf-1",
        issue_id="ISSUE-123",
        worktree_path="/nonexistent/path",
        worktree_name="deleted",
        workflow_status="in_progress",
        started_at=datetime.utcnow(),
    )
    mock_orchestrator.get_active_workflows.return_value = ["/nonexistent/path"]
    mock_orchestrator.get_workflow_by_worktree.return_value = mock_workflow

    await health_checker._check_all_worktrees()

    # Should cancel workflow
    mock_orchestrator.cancel_workflow.assert_called_once()
    call_args = mock_orchestrator.cancel_workflow.call_args
    assert call_args[0][0] == "wf-1"


@pytest.mark.asyncio
async def test_is_worktree_healthy_directory_exists(
    health_checker: WorktreeHealthChecker,
    tmp_path: Path,
):
    """Should return True for valid worktree directory."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    (worktree_path / ".git").touch()

    is_healthy = await health_checker._is_worktree_healthy(str(worktree_path))
    assert is_healthy is True


@pytest.mark.asyncio
async def test_is_worktree_healthy_no_directory(
    health_checker: WorktreeHealthChecker,
):
    """Should return False for nonexistent directory."""
    is_healthy = await health_checker._is_worktree_healthy("/nonexistent")
    assert is_healthy is False


@pytest.mark.asyncio
async def test_is_worktree_healthy_no_git(
    health_checker: WorktreeHealthChecker,
    tmp_path: Path,
):
    """Should return False if .git missing."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    # No .git file/dir

    is_healthy = await health_checker._is_worktree_healthy(str(worktree_path))
    assert is_healthy is False


@pytest.mark.asyncio
async def test_is_worktree_healthy_git_directory(
    health_checker: WorktreeHealthChecker,
    tmp_path: Path,
):
    """Should return True for main repo with .git directory."""
    worktree_path = tmp_path / "main"
    worktree_path.mkdir()
    (worktree_path / ".git").mkdir()

    is_healthy = await health_checker._is_worktree_healthy(str(worktree_path))
    assert is_healthy is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/lifecycle/test_health_checker.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Implement WorktreeHealthChecker**

```python
# amelia/server/lifecycle/health_checker.py
"""Worktree health checker for periodic validation."""
import asyncio
from pathlib import Path
from loguru import logger
from amelia.server.orchestrator.service import OrchestratorService


class WorktreeHealthChecker:
    """Periodically validates worktree health for active workflows.

    Checks that worktree directories still exist and are valid git repositories.
    If a worktree is deleted while a workflow is running, cancels the workflow.
    """

    def __init__(
        self,
        orchestrator: OrchestratorService,
        check_interval: float = 30.0,
    ) -> None:
        """Initialize health checker.

        Args:
            orchestrator: Orchestrator service instance.
            check_interval: Seconds between health checks (default: 30).
        """
        self._orchestrator = orchestrator
        self._check_interval = check_interval
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the health check loop."""
        self._task = asyncio.create_task(self._check_loop())
        logger.info(
            "WorktreeHealthChecker started",
            interval=self._check_interval,
        )

    async def stop(self) -> None:
        """Stop the health check loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("WorktreeHealthChecker stopped")

    async def _check_loop(self) -> None:
        """Periodically check all active worktrees."""
        while True:
            await asyncio.sleep(self._check_interval)
            await self._check_all_worktrees()

    async def _check_all_worktrees(self) -> None:
        """Check health of all active workflow worktrees."""
        for worktree_path in self._orchestrator.get_active_workflows():
            if not await self._is_worktree_healthy(worktree_path):
                workflow = await self._orchestrator.get_workflow_by_worktree(
                    worktree_path
                )
                if workflow:
                    logger.warning(
                        "Worktree deleted - cancelling workflow",
                        worktree_path=worktree_path,
                        workflow_id=workflow.id,
                    )
                    await self._orchestrator.cancel_workflow(
                        workflow.id,
                        reason="Worktree directory no longer exists",
                    )

    def _check_worktree_sync(self, path: Path) -> bool:
        """Synchronous helper to check if worktree is valid.

        Performs all Path operations synchronously. Called via asyncio.to_thread()
        to prevent blocking the event loop on slow/network filesystems.

        Args:
            path: Path object to check.

        Returns:
            True if worktree is healthy, False otherwise.
        """
        if not path.exists():
            return False

        if not path.is_dir():
            return False

        # Check .git exists (file for worktrees, dir for main repo)
        git_path = path / ".git"
        return git_path.exists()

    async def _is_worktree_healthy(self, worktree_path: str) -> bool:
        """Check if worktree directory still exists and is valid.

        Uses asyncio.to_thread() to avoid blocking the event loop on filesystem I/O,
        which can be slow on network filesystems or when many files exist.

        Args:
            worktree_path: Absolute path to worktree.

        Returns:
            True if worktree is healthy, False otherwise.
        """
        path = Path(worktree_path)
        # Run sync Path operations in thread pool to prevent blocking event loop
        return await asyncio.to_thread(self._check_worktree_sync, path)
```

**Step 4: Add get_workflow_by_worktree stub to OrchestratorService**

Add to `amelia/server/orchestrator/service.py`:

```python
    async def get_workflow_by_worktree(
        self,
        worktree_path: str,
    ) -> ServerExecutionState | None:
        """Get workflow by worktree path.

        Args:
            worktree_path: The worktree path.

        Returns:
            Workflow state if found, None otherwise.
        """
        # Find workflow ID from active tasks
        if worktree_path not in self._active_tasks:
            return None

        # Search repository for workflow with this worktree_path
        # This requires adding a query method to repository
        workflows = await self._repository.list_active()
        for workflow in workflows:
            if workflow.worktree_path == worktree_path:
                return workflow

        return None
```

Update cancel_workflow signature:

```python
    async def cancel_workflow(
        self,
        workflow_id: str,
        reason: str | None = None,
    ) -> None:
        """Cancel a running workflow.

        Args:
            workflow_id: The workflow to cancel.
            reason: Optional cancellation reason.
        """
        workflow = await self._repository.get(workflow_id)
        if workflow and workflow.worktree_path in self._active_tasks:
            task = self._active_tasks[workflow.worktree_path]
            task.cancel()
            logger.info(
                "Workflow cancelled",
                workflow_id=workflow_id,
                reason=reason,
            )
```

**Step 5: Update __init__.py**

```python
# amelia/server/lifecycle/__init__.py
"""Server lifecycle management."""
from amelia.server.lifecycle.health_checker import WorktreeHealthChecker
from amelia.server.lifecycle.retention import CleanupResult, LogRetentionService
from amelia.server.lifecycle.server import ServerLifecycle

__all__ = [
    "CleanupResult",
    "LogRetentionService",
    "ServerLifecycle",
    "WorktreeHealthChecker",
]
```

**Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/lifecycle/test_health_checker.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/server/lifecycle/ amelia/server/orchestrator/service.py tests/unit/server/lifecycle/
git commit -m "feat(lifecycle): implement WorktreeHealthChecker for periodic validation"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] `uv run pytest tests/unit/server/events/ -v` - EventBus tests pass
- [ ] `uv run pytest tests/unit/server/orchestrator/ -v` - OrchestratorService tests pass
- [ ] `uv run pytest tests/unit/server/lifecycle/ -v` - Lifecycle service tests pass
- [ ] `uv run ruff check amelia/server/events amelia/server/orchestrator amelia/server/lifecycle` - No linting errors
- [ ] `uv run mypy amelia/server/events amelia/server/orchestrator amelia/server/lifecycle` - No type errors

**Integration verification in Python REPL:**

```python
from amelia.server.events.bus import EventBus
from amelia.server.orchestrator import OrchestratorService
from amelia.server.lifecycle import ServerLifecycle, LogRetentionService, WorktreeHealthChecker
from amelia.server.models import EventType, WorkflowEvent
from datetime import datetime

# EventBus
bus = EventBus()
def print_event(e): print(f"Event: {e.message}")
bus.subscribe(print_event)
event = WorkflowEvent(
    id="1", workflow_id="w1", sequence=1,
    timestamp=datetime.utcnow(), agent="system",
    event_type=EventType.WORKFLOW_STARTED, message="Test"
)
bus.emit(event)  # Should print "Event: Test"

# OrchestratorService (requires async)
# orchestrator = OrchestratorService(bus, repo, max_concurrent=5)
# workflow_id = await orchestrator.start_workflow(...)
```

---

## Summary

This plan implements the event bus and orchestrator service:

| Component | File | Purpose |
|-----------|------|---------|
| EventBus | `amelia/server/events/bus.py` | Pub/sub for broadcasting events |
| OrchestratorService | `amelia/server/orchestrator/service.py` | Concurrent workflow execution |
| Event Emission | `OrchestratorService._emit()` | Thread-safe event emission with sequences |
| Approval Flow | `approve_workflow()`, `reject_workflow()` | Approval gate mechanism |
| LogRetentionService | `amelia/server/lifecycle/retention.py` | Cleanup on shutdown |
| ServerLifecycle | `amelia/server/lifecycle/server.py` | Graceful startup/shutdown |
| WorktreeHealthChecker | `amelia/server/lifecycle/health_checker.py` | Periodic worktree validation |

**Key Features:**
- Thread-safe event emission with per-workflow sequence locking
- Concurrency control (max_concurrent, worktree isolation)
- Approval gate with race condition safety
- Graceful shutdown with timeout and cancellation
- Automatic cleanup of deleted worktrees

**Next Plan:** WebSocket Endpoint & Connection Manager (Plan 6)
