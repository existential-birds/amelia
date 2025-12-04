"""Orchestrator service for managing concurrent workflow execution."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from loguru import logger

from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models import ServerExecutionState
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.orchestrator.exceptions import (
    ConcurrencyLimitError,
    WorkflowConflictError,
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
        self._active_tasks: dict[str, asyncio.Task[None]] = {}  # worktree_path -> task
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
            started_at=datetime.now(UTC),
        )
        await self._repository.create(state)

        logger.info(
            "Starting workflow",
            workflow_id=workflow_id,
            issue_id=issue_id,
            worktree_path=worktree_path,
        )

        # Start async task
        task = asyncio.create_task(self._run_workflow(workflow_id, state, profile))
        self._active_tasks[worktree_path] = task

        # Remove from active tasks on completion
        def cleanup_task(_: asyncio.Task[None]) -> None:
            self._active_tasks.pop(worktree_path, None)
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
        # Find workflow ID from active tasks
        if worktree_path not in self._active_tasks:
            return None

        # Search repository for workflow with this worktree_path
        workflows = await self._repository.list_active()
        for workflow in workflows:
            if workflow.worktree_path == worktree_path:
                return workflow

        return None

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
        # Get or create lock for this workflow
        if workflow_id not in self._sequence_locks:
            self._sequence_locks[workflow_id] = asyncio.Lock()

        async with self._sequence_locks[workflow_id]:
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

    async def recover_interrupted_workflows(self) -> None:
        """Recover workflows that were running when server crashed.

        This is a placeholder - full implementation will be added
        when LangGraph integration is complete.
        """
        logger.info("Checking for interrupted workflows...")
        # TODO: Query for workflows with status=in_progress or blocked
        # and mark them as failed with appropriate reason
        logger.info("No interrupted workflows to recover")
