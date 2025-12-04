"""Orchestrator service for managing concurrent workflow execution."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from loguru import logger

from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models import ServerExecutionState
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
