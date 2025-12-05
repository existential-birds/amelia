"""Orchestrator service for managing concurrent workflow execution."""

import asyncio
import contextlib
from datetime import UTC, datetime
from uuid import uuid4

from loguru import logger

from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.models import ServerExecutionState
from amelia.server.models.events import EventType, WorkflowEvent


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
    ) -> None:
        """Initialize orchestrator service.

        Args:
            event_bus: Event bus for broadcasting workflow events.
            repository: Repository for workflow persistence.
            max_concurrent: Maximum number of concurrent workflows (default: 5).
        """
        self._event_bus = event_bus
        self._repository = repository
        self._max_concurrent = max_concurrent
        self._active_tasks: dict[str, tuple[str, asyncio.Task[None]]] = {}  # worktree_path -> (workflow_id, task)
        self._approval_events: dict[str, asyncio.Event] = {}  # workflow_id -> event
        self._approval_lock = asyncio.Lock()  # Prevents race conditions on approvals
        self._start_lock = asyncio.Lock()  # Prevents race conditions on workflow start
        self._sequence_counters: dict[str, int] = {}  # workflow_id -> next sequence
        self._sequence_locks: dict[str, asyncio.Lock] = {}  # workflow_id -> lock

    async def start_workflow(
        self,
        issue_id: str,
        worktree_path: str,
        worktree_name: str | None = None,
        profile: str | None = None,
        driver: str | None = None,
    ) -> str:
        """Start a new workflow.

        Args:
            issue_id: The issue ID to work on.
            worktree_path: Absolute path to the worktree.
            worktree_name: Human-readable worktree name (optional).
            profile: Optional profile name.
            driver: Optional driver override.

        Returns:
            The workflow ID (UUID).

        Raises:
            WorkflowConflictError: If worktree already has active workflow.
            ConcurrencyLimitError: If at max concurrent workflows.
        """
        async with self._start_lock:
            # Check worktree conflict - workflow_id is cached in tuple
            if worktree_path in self._active_tasks:
                existing_id, _ = self._active_tasks[worktree_path]
                raise WorkflowConflictError(worktree_path, existing_id)

            # Check concurrency limit
            current_count = len(self._active_tasks)
            if current_count >= self._max_concurrent:
                raise ConcurrencyLimitError(self._max_concurrent, current_count)

            # Create workflow record
            workflow_id = str(uuid4())
            state = ServerExecutionState(
                id=workflow_id,
                issue_id=issue_id,
                worktree_path=worktree_path,
                worktree_name=worktree_name or worktree_path.split("/")[-1],
                workflow_status="pending",
                started_at=datetime.now(UTC),
            )
            try:
                await self._repository.create(state)
            except Exception as e:
                # Handle DB constraint violation (e.g., crash recovery scenario)
                if "UNIQUE constraint failed" in str(e):
                    raise WorkflowConflictError(worktree_path, "existing") from e
                raise

            logger.info(
                "Starting workflow",
                workflow_id=workflow_id,
                issue_id=issue_id,
                worktree_path=worktree_path,
            )

            # Start async task
            task = asyncio.create_task(self._run_workflow(workflow_id, state, profile))
            self._active_tasks[worktree_path] = (workflow_id, task)

        # Remove from active tasks on completion
        def cleanup_task(_: asyncio.Task[None]) -> None:
            self._active_tasks.pop(worktree_path, None)
            self._sequence_counters.pop(workflow_id, None)
            self._sequence_locks.pop(workflow_id, None)
            logger.debug(
                "Workflow task completed",
                workflow_id=workflow_id,
                worktree_path=worktree_path,
            )

        task.add_done_callback(cleanup_task)

        return workflow_id

    async def cancel_workflow(
        self,
        workflow_id: str,
        reason: str | None = None,
    ) -> None:
        """Cancel a running workflow.

        Args:
            workflow_id: The workflow to cancel.
            reason: Optional cancellation reason.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateError: If workflow is not in a cancellable state.
        """
        workflow = await self._repository.get(workflow_id)
        if not workflow:
            raise WorkflowNotFoundError(workflow_id)

        # Check if workflow is in a cancellable state (not terminal)
        cancellable_states = {"pending", "in_progress", "blocked"}
        if workflow.workflow_status not in cancellable_states:
            raise InvalidStateError(
                f"Cannot cancel workflow in '{workflow.workflow_status}' state",
                workflow_id=workflow_id,
                current_status=workflow.workflow_status,
            )

        # Cancel the in-memory task if running
        if workflow.worktree_path in self._active_tasks:
            _, task = self._active_tasks[workflow.worktree_path]
            task.cancel()

        # Persist the cancelled status to database
        await self._repository.set_status(workflow_id, "cancelled")

        logger.info(
            "Workflow cancelled",
            workflow_id=workflow_id,
            reason=reason,
        )

    async def cancel_all_workflows(self, timeout: float = 5.0) -> None:
        """Cancel all active workflows gracefully.

        Args:
            timeout: Seconds to wait for each workflow to finish after cancellation.
        """
        for worktree_path in list(self._active_tasks.keys()):
            entry = self._active_tasks.get(worktree_path)
            if entry:
                _, task = entry
                task.cancel()
                with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=timeout)

    def get_active_workflows(self) -> list[str]:
        """Return list of active worktree paths.

        Returns:
            List of worktree paths with active workflows.
        """
        return list(self._active_tasks.keys())

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
        # Use cached workflow_id for O(1) lookup
        entry = self._active_tasks.get(worktree_path)
        if not entry:
            return None

        workflow_id, _ = entry
        return await self._repository.get(workflow_id)

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

    async def _emit(
        self,
        workflow_id: str,
        event_type: EventType,
        message: str,
        agent: str = "system",
        data: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> WorkflowEvent:
        """Emit a workflow event.

        Creates an event with monotonically increasing sequence number,
        persists to repository, and broadcasts via event bus.

        Args:
            workflow_id: The workflow this event belongs to.
            event_type: Type of event.
            message: Human-readable message.
            agent: Source agent (default: "system").
            data: Optional structured payload.
            correlation_id: Optional ID for tracing related events.

        Returns:
            The emitted WorkflowEvent.
        """
        # Get or create lock atomically (setdefault is atomic for dict operations)
        lock = self._sequence_locks.setdefault(workflow_id, asyncio.Lock())

        async with lock:
            # Initialize or get sequence counter
            if workflow_id not in self._sequence_counters:
                max_seq = await self._repository.get_max_event_sequence(workflow_id)
                # Repository returns 0 if no events exist, so max_seq + 1 starts at 1
                self._sequence_counters[workflow_id] = max_seq + 1

            sequence = self._sequence_counters[workflow_id]
            self._sequence_counters[workflow_id] += 1

        event = WorkflowEvent(
            id=str(uuid4()),
            workflow_id=workflow_id,
            sequence=sequence,
            timestamp=datetime.now(UTC),
            agent=agent,
            event_type=event_type,
            message=message,
            data=data,
            correlation_id=correlation_id,
        )

        # Persist and broadcast
        await self._repository.save_event(event)
        self._event_bus.emit(event)

        logger.debug(
            "Event emitted",
            workflow_id=workflow_id,
            event_type=event_type.value,
            sequence=sequence,
        )

        return event

    async def approve_workflow(self, workflow_id: str) -> None:
        """Approve a blocked workflow.

        Args:
            workflow_id: The workflow to approve.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateError: If workflow is not in "blocked" state.
        """
        # Validate workflow exists and get current state
        workflow = await self._repository.get(workflow_id)
        if not workflow:
            raise WorkflowNotFoundError(workflow_id)

        # Validate workflow is in blocked state
        if workflow.workflow_status != "blocked":
            raise InvalidStateError(
                f"Cannot approve workflow in '{workflow.workflow_status}' state",
                workflow_id=workflow_id,
                current_status=workflow.workflow_status,
            )

        async with self._approval_lock:
            # Signal the approval event if it exists
            event = self._approval_events.get(workflow_id)
            if event:
                event.set()
                self._approval_events.pop(workflow_id, None)

            # Update workflow status
            await self._repository.set_status(workflow_id, "in_progress")
            await self._emit(
                workflow_id,
                EventType.APPROVAL_GRANTED,
                "Plan approved",
            )

            logger.info(
                "Workflow approved",
                workflow_id=workflow_id,
            )

    async def reject_workflow(
        self,
        workflow_id: str,
        feedback: str,
    ) -> None:
        """Reject a blocked workflow.

        Args:
            workflow_id: The workflow to reject.
            feedback: Reason for rejection.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateError: If workflow is not in "blocked" state.
        """
        # Validate workflow exists and get current state
        workflow = await self._repository.get(workflow_id)
        if not workflow:
            raise WorkflowNotFoundError(workflow_id)

        # Validate workflow is in blocked state
        if workflow.workflow_status != "blocked":
            raise InvalidStateError(
                f"Cannot reject workflow in '{workflow.workflow_status}' state",
                workflow_id=workflow_id,
                current_status=workflow.workflow_status,
            )

        async with self._approval_lock:
            # Remove approval event if it exists
            self._approval_events.pop(workflow_id, None)

            # Update workflow status to failed with feedback
            await self._repository.set_status(
                workflow_id, "failed", failure_reason=feedback
            )
            await self._emit(
                workflow_id,
                EventType.APPROVAL_REJECTED,
                f"Plan rejected: {feedback}",
            )

            # Cancel the waiting task
            if workflow.worktree_path in self._active_tasks:
                _, task = self._active_tasks[workflow.worktree_path]
                task.cancel()

            logger.info(
                "Workflow rejected",
                workflow_id=workflow_id,
                feedback=feedback,
            )

    async def _wait_for_approval(self, workflow_id: str) -> None:
        """Block until workflow is approved or rejected.

        Sets the workflow status to "blocked" and waits for approval/rejection.

        Args:
            workflow_id: The workflow awaiting approval.
        """
        # Set status to blocked before waiting - required for approve/reject validation
        await self._repository.set_status(workflow_id, "blocked")

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

    async def recover_interrupted_workflows(self) -> None:
        """Recover workflows that were running when server crashed.

        This is a placeholder - full implementation will be added
        when LangGraph integration is complete.
        """
        logger.info("Checking for interrupted workflows...")
        # TODO: Query for workflows with status=in_progress or blocked
        # and mark them as failed with appropriate reason
        logger.info("No interrupted workflows to recover")
