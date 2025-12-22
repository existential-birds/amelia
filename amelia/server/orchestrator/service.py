# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Orchestrator service for managing concurrent workflow execution."""

import asyncio
import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from httpx import TimeoutException
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from amelia.core.orchestrator import create_orchestrator_graph, create_review_graph
from amelia.core.state import ExecutionPlan, ExecutionState
from amelia.core.types import Issue, Profile, Settings, StreamEmitter, StreamEvent
from amelia.ext import WorkflowEventType as ExtWorkflowEventType
from amelia.ext.exceptions import PolicyDeniedError
from amelia.ext.hooks import (
    check_policy_workflow_start,
    emit_workflow_event,
    flush_exporters,
)
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    InvalidWorktreeError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.models import ServerExecutionState
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.trackers.factory import create_tracker


# Nodes that emit stage events
STAGE_NODES: frozenset[str] = frozenset({
    "architect_node",
    "human_approval_node",
    "developer_node",
    "reviewer_node",
})

# Exceptions that warrant retry
TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    asyncio.TimeoutError,
    TimeoutException,
    ConnectionError,
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
        settings: Settings,
        max_concurrent: int = 5,
        checkpoint_path: str = "~/.amelia/checkpoints.db",
    ) -> None:
        """Initialize orchestrator service.

        Args:
            event_bus: Event bus for broadcasting workflow events.
            repository: Repository for workflow persistence.
            settings: Application settings for profile management.
            max_concurrent: Maximum number of concurrent workflows (default: 5).
            checkpoint_path: Path to checkpoint database file.
        """
        self._event_bus = event_bus
        self._repository = repository
        self._settings = settings
        self._max_concurrent = max_concurrent
        # Expand ~ and resolve path, ensure parent directory exists
        expanded_path = Path(checkpoint_path).expanduser().resolve()
        expanded_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpoint_path = str(expanded_path)
        self._active_tasks: dict[str, tuple[str, asyncio.Task[None]]] = {}  # worktree_path -> (workflow_id, task)
        self._approval_events: dict[str, asyncio.Event] = {}  # workflow_id -> event
        self._approval_lock = asyncio.Lock()  # Prevents race conditions on approvals
        self._start_lock = asyncio.Lock()  # Prevents race conditions on workflow start
        self._sequence_counters: dict[str, int] = {}  # workflow_id -> next sequence
        self._sequence_locks: dict[str, asyncio.Lock] = {}  # workflow_id -> lock
        self._last_task_statuses: dict[str, dict[str, str]] = {}  # workflow_id -> {task_id -> status}

    def _create_server_graph(
        self,
        checkpointer: BaseCheckpointSaver[Any],
    ) -> CompiledStateGraph[Any]:
        """Create graph with server-mode interrupt configuration.

        Args:
            checkpointer: Checkpoint saver for persistence.

        Returns:
            Compiled LangGraph with interrupts before all human-input nodes.
        """
        return create_orchestrator_graph(
            checkpoint_saver=checkpointer,
            interrupt_before=[
                "human_approval_node",
                "batch_approval_node",
                "blocker_resolution_node",
            ],
        )

    def _create_stream_emitter(self) -> StreamEmitter:
        """Create a stream emitter callback for broadcasting events.

        Stream events are broadcast via WebSocket but NOT persisted to the database.
        Each StreamEvent already contains its own workflow_id, so the emitter
        doesn't need workflow context.

        Returns:
            Async callback that broadcasts StreamEvent via WebSocket.
        """
        async def emit(event: StreamEvent) -> None:
            self._event_bus.emit_stream(event)

        return emit

    async def _get_profile_or_fail(self, workflow_id: str, profile_id: str) -> Profile | None:
        """Look up profile by ID and handle missing profile consistently.

        Args:
            workflow_id: Workflow ID for logging and status updates.
            profile_id: Profile ID to look up in settings.

        Returns:
            Profile if found, None if not found (after setting workflow to failed).
        """
        if profile_id not in self._settings.profiles:
            logger.error("Profile not found", workflow_id=workflow_id, profile_id=profile_id)
            await self._repository.set_status(
                workflow_id, "failed", failure_reason=f"Profile '{profile_id}' not found"
            )
            return None
        return self._settings.profiles[profile_id]

    async def start_workflow(
        self,
        issue_id: str,
        worktree_path: str,
        worktree_name: str | None = None,
        profile: str | None = None,
        driver: str | None = None,
        plan_only: bool = False,
    ) -> str:
        """Start a new workflow.

        Args:
            issue_id: The issue ID to work on.
            worktree_path: Absolute path to the worktree.
            worktree_name: Human-readable worktree name (optional).
            profile: Optional profile name.
            driver: Optional driver override.
            plan_only: If True, stop after planning and save markdown without executing.

        Returns:
            The workflow ID (UUID).

        Raises:
            InvalidWorktreeError: If worktree path doesn't exist or is not a git repo.
            WorkflowConflictError: If worktree already has active workflow.
            ConcurrencyLimitError: If at max concurrent workflows.
        """
        # Validate worktree before acquiring lock (fast-fail)
        worktree = Path(worktree_path)
        if not worktree.exists():
            raise InvalidWorktreeError(worktree_path, "directory does not exist")
        if not worktree.is_dir():
            raise InvalidWorktreeError(worktree_path, "path is not a directory")
        git_path = worktree / ".git"
        if not git_path.exists():
            raise InvalidWorktreeError(worktree_path, "not a git repository (.git missing)")

        async with self._start_lock:
            # Check worktree conflict - workflow_id is cached in tuple
            if worktree_path in self._active_tasks:
                existing_id, _ = self._active_tasks[worktree_path]
                raise WorkflowConflictError(worktree_path, existing_id)

            # Check concurrency limit
            current_count = len(self._active_tasks)
            if current_count >= self._max_concurrent:
                raise ConcurrencyLimitError(self._max_concurrent, current_count)

            # Create workflow ID early for policy check
            workflow_id = str(uuid4())

            # Load the profile (use provided profile name or active profile as fallback)
            profile_name = profile or self._settings.active_profile
            if profile_name not in self._settings.profiles:
                raise ValueError(f"Profile '{profile_name}' not found in settings")
            loaded_profile = self._settings.profiles[profile_name]

            # Check policy hooks before starting workflow
            # This allows Enterprise to enforce rate limits, quotas, etc.
            allowed, hook_name = await check_policy_workflow_start(
                workflow_id=workflow_id,
                profile=loaded_profile,
                issue_id=issue_id,
            )
            if not allowed:
                logger.warning(
                    "Workflow start denied by policy hook",
                    workflow_id=workflow_id,
                    issue_id=issue_id,
                    hook_name=hook_name,
                )
                raise PolicyDeniedError(
                    reason="Workflow start denied by policy",
                    hook_name=hook_name,
                )

            # Ensure working_dir is set to worktree_path for git operations
            # Create a copy to avoid mutating the shared settings profile
            if loaded_profile.working_dir is None:
                loaded_profile = loaded_profile.model_copy(
                    update={"working_dir": worktree_path}
                )

            # Fetch issue from tracker (pass worktree_path so gh CLI uses correct repo)
            tracker = create_tracker(loaded_profile)
            issue = tracker.get_issue(issue_id, cwd=worktree_path)

            # Initialize ExecutionState with profile_id and issue
            execution_state = ExecutionState(profile_id=loaded_profile.name, issue=issue, plan_only=plan_only)

            state = ServerExecutionState(
                id=workflow_id,
                issue_id=issue_id,
                worktree_path=worktree_path,
                worktree_name=worktree_name or worktree_path.split("/")[-1],
                execution_state=execution_state,
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

            # Start async task with retry wrapper for transient failures
            task = asyncio.create_task(self._run_workflow_with_retry(workflow_id, state))
            self._active_tasks[worktree_path] = (workflow_id, task)

        # Remove from active tasks on completion
        def cleanup_task(_: asyncio.Task[None]) -> None:
            """Clean up resources when workflow task completes.

            Args:
                _: The completed asyncio Task (unused).
            """
            self._active_tasks.pop(worktree_path, None)
            self._sequence_counters.pop(workflow_id, None)
            self._sequence_locks.pop(workflow_id, None)
            self._last_task_statuses.pop(workflow_id, None)
            logger.debug(
                "Workflow task completed",
                workflow_id=workflow_id,
                worktree_path=worktree_path,
            )

        task.add_done_callback(cleanup_task)

        return workflow_id

    async def start_review_workflow(
        self,
        diff_content: str,
        worktree_path: str,
        worktree_name: str | None = None,
        profile: str | None = None,
    ) -> str:
        """Start a review-fix workflow.

        Args:
            diff_content: The git diff to review.
            worktree_path: Path for conflict detection (typically cwd).
            worktree_name: Optional human-readable name.
            profile: Optional profile name.

        Returns:
            The workflow ID (UUID).

        Raises:
            WorkflowConflictError: If worktree already has active workflow.
            ConcurrencyLimitError: If at max concurrent workflows.
        """
        # Validate worktree exists (for conflict detection, not git ops)
        worktree = Path(worktree_path)
        if not worktree.exists() or not worktree.is_dir():
            raise InvalidWorktreeError(worktree_path, "directory does not exist")

        async with self._start_lock:
            # Same conflict and concurrency checks as start_workflow
            if worktree_path in self._active_tasks:
                existing_id, _ = self._active_tasks[worktree_path]
                raise WorkflowConflictError(worktree_path, existing_id)

            if len(self._active_tasks) >= self._max_concurrent:
                raise ConcurrencyLimitError(self._max_concurrent, len(self._active_tasks))

            workflow_id = str(uuid4())

            # Load profile
            profile_name = profile or self._settings.active_profile
            loaded_profile = self._settings.profiles[profile_name]
            if loaded_profile.working_dir is None:
                loaded_profile = loaded_profile.model_copy(update={"working_dir": worktree_path})

            # Create dummy issue for review context
            dummy_issue = Issue(
                id="LOCAL-REVIEW",
                title="Local Code Review",
                description="Review local uncommitted changes."
            )

            # Initialize ExecutionState with diff content
            execution_state = ExecutionState(
                profile_id=loaded_profile.name,
                issue=dummy_issue,
                code_changes_for_review=diff_content,
                review_iteration=0,
            )

            # Create server state with workflow_type="review"
            state = ServerExecutionState(
                id=workflow_id,
                issue_id="LOCAL-REVIEW",
                worktree_path=worktree_path,
                worktree_name=worktree_name or "local-review",
                workflow_type="review",
                execution_state=execution_state,
                workflow_status="pending",
                started_at=datetime.now(UTC),
            )

            await self._repository.create(state)

            # Start with review graph instead of full graph
            task = asyncio.create_task(self._run_review_workflow(workflow_id, state))
            self._active_tasks[worktree_path] = (workflow_id, task)

        # Same cleanup callback as start_workflow
        def cleanup_task(_: asyncio.Task[None]) -> None:
            """Clean up resources when workflow task completes.

            Args:
                _: The completed asyncio Task (unused).
            """
            self._active_tasks.pop(worktree_path, None)
            self._sequence_counters.pop(workflow_id, None)
            self._sequence_locks.pop(workflow_id, None)
            self._last_task_statuses.pop(workflow_id, None)
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

        # Emit extension hook for cancellation
        await emit_workflow_event(
            ExtWorkflowEventType.CANCELLED,
            workflow_id=workflow_id,
            metadata={"reason": reason} if reason else None,
        )

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

        # Flush any buffered audit events during graceful shutdown
        await flush_exporters()

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
        state: ServerExecutionState,
    ) -> None:
        """Execute workflow via LangGraph with interrupt support.

        Args:
            workflow_id: The workflow ID.
            state: Server execution state with embedded core state.

        Note:
            When GraphInterrupt is raised, the workflow is paused at the
            human_approval_node. Status is set to "blocked" and an
            APPROVAL_REQUIRED event is emitted. The workflow resumes when
            approve_workflow() is called.
        """
        if state.execution_state is None:
            logger.error("No execution_state in ServerExecutionState", workflow_id=workflow_id)
            await self._repository.set_status(
                workflow_id, "failed", failure_reason="Missing execution state"
            )
            return

        # Get profile from settings using profile_id
        profile = await self._get_profile_or_fail(workflow_id, state.execution_state.profile_id)
        if profile is None:
            return

        async with AsyncSqliteSaver.from_conn_string(
            str(self._checkpoint_path)
        ) as checkpointer:
            # CRITICAL: Pass interrupt_before to enable server-mode approval
            graph = self._create_server_graph(checkpointer)

            # Create stream emitter and pass it via config
            stream_emitter = self._create_stream_emitter()
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "stream_emitter": stream_emitter,
                    "profile": profile,
                }
            }

            await self._emit(
                workflow_id,
                EventType.WORKFLOW_STARTED,
                "Workflow execution started",
                data={"issue_id": state.issue_id},
            )

            # Emit extension hook for audit/analytics (fire-and-forget, errors logged)
            await emit_workflow_event(
                ExtWorkflowEventType.STARTED,
                workflow_id=workflow_id,
                metadata={"issue_id": state.issue_id},
            )

            try:
                await self._repository.set_status(workflow_id, "in_progress")

                was_interrupted = False
                # Use astream with stream_mode="updates" to detect interrupts
                # astream_events does NOT surface __interrupt__ events
                # Convert Pydantic model to JSON-serializable dict for checkpointing.
                # LangGraph's AsyncSqliteSaver uses json.dumps() internally,
                # which fails on Pydantic BaseModel objects.
                initial_state = state.execution_state.model_dump(mode="json")

                async for chunk in graph.astream(
                    initial_state,
                    config=config,
                    stream_mode="updates",
                ):
                    # Check for interrupt signal from LangGraph
                    if "__interrupt__" in chunk:
                        was_interrupted = True
                        logger.info(
                            "Workflow paused for human approval",
                            workflow_id=workflow_id,
                            interrupt_data=chunk["__interrupt__"],
                        )
                        # Sync plan from LangGraph checkpoint to ServerExecutionState
                        # so it's available via REST API while blocked
                        await self._sync_plan_from_checkpoint(workflow_id, graph, config)
                        await self._emit(
                            workflow_id,
                            EventType.APPROVAL_REQUIRED,
                            "Plan ready for review - awaiting human approval",
                            data={"paused_at": "human_approval_node"},
                        )
                        # Emit extension hook for approval gate
                        await emit_workflow_event(
                            ExtWorkflowEventType.APPROVAL_REQUESTED,
                            workflow_id=workflow_id,
                            stage="human_approval_node",
                        )
                        await self._repository.set_status(workflow_id, "blocked")
                        # Emit PAUSED event for workflow being blocked
                        await emit_workflow_event(
                            ExtWorkflowEventType.PAUSED,
                            workflow_id=workflow_id,
                            stage="human_approval_node",
                        )
                        break
                    # Emit stage events for each node that completes
                    await self._handle_stream_chunk(workflow_id, chunk)

                if not was_interrupted:
                    # Workflow completed without interruption (no human approval needed).
                    # Note: A separate COMPLETED emission exists in approve_workflow() for
                    # workflows that resume after human approval. These are mutually exclusive
                    # code paths - only one COMPLETED event is ever emitted per workflow.
                    await self._emit(
                        workflow_id,
                        EventType.WORKFLOW_COMPLETED,
                        "Workflow completed successfully",
                        data={"final_stage": state.current_stage},
                    )
                    await emit_workflow_event(
                        ExtWorkflowEventType.COMPLETED,
                        workflow_id=workflow_id,
                        stage=state.current_stage,
                    )
                    await self._repository.set_status(workflow_id, "completed")

            except Exception:
                # Let exceptions propagate to _run_workflow_with_retry for retry logic
                # and proper failure event emission
                raise

    async def _run_workflow_with_retry(
        self,
        workflow_id: str,
        state: ServerExecutionState,
    ) -> None:
        """Execute workflow with automatic retry for transient failures.

        Args:
            workflow_id: The workflow ID.
            state: Server execution state.
        """
        if state.execution_state is None:
            await self._repository.set_status(
                workflow_id, "failed", failure_reason="Missing execution state"
            )
            return

        # Get profile from settings using profile_id
        profile = await self._get_profile_or_fail(workflow_id, state.execution_state.profile_id)
        if profile is None:
            return
        retry_config = profile.retry
        attempt = 0

        while attempt <= retry_config.max_retries:
            try:
                await self._run_workflow(workflow_id, state)
                # Success - reset error tracking if needed
                # Re-fetch state to avoid overwriting changes from _sync_plan_from_checkpoint
                if state.consecutive_errors > 0:
                    fresh_state = await self._repository.get(workflow_id)
                    if fresh_state is not None:
                        fresh_state.consecutive_errors = 0
                        fresh_state.last_error_context = None
                        await self._repository.update(fresh_state)
                return  # Success

            except TRANSIENT_EXCEPTIONS as e:
                attempt += 1
                # Re-fetch state to avoid overwriting changes from _sync_plan_from_checkpoint
                fresh_state = await self._repository.get(workflow_id)
                if fresh_state is not None:
                    fresh_state.consecutive_errors = attempt
                    fresh_state.last_error_context = f"{type(e).__name__}: {str(e)}"
                    await self._repository.update(fresh_state)

                if attempt > retry_config.max_retries:
                    logger.exception("Workflow failed after retries exhausted", workflow_id=workflow_id)
                    await self._emit(
                        workflow_id,
                        EventType.WORKFLOW_FAILED,
                        f"Workflow failed after {attempt} attempts: {e!s}",
                        data={"error": str(e), "attempts": attempt},
                    )
                    # Emit extension hook for failure
                    await emit_workflow_event(
                        ExtWorkflowEventType.FAILED,
                        workflow_id=workflow_id,
                        metadata={"error": str(e), "attempts": attempt},
                    )
                    await self._repository.set_status(
                        workflow_id,
                        "failed",
                        failure_reason=f"Failed after {attempt} attempts: {e}",
                    )
                    raise

                delay = min(
                    retry_config.base_delay * (2 ** (attempt - 1)),
                    retry_config.max_delay,
                )
                logger.warning(
                    f"Transient error (attempt {attempt}/{retry_config.max_retries}), "
                    f"retrying in {delay}s",
                    workflow_id=workflow_id,
                    error=str(e),
                )
                await asyncio.sleep(delay)

            except Exception as e:
                # Non-transient error - fail immediately
                # Re-fetch state to avoid overwriting changes from _sync_plan_from_checkpoint
                fresh_state = await self._repository.get(workflow_id)
                if fresh_state is not None:
                    fresh_state.consecutive_errors = attempt + 1
                    fresh_state.last_error_context = f"{type(e).__name__}: {str(e)}"
                    await self._repository.update(fresh_state)

                logger.exception("Workflow failed with non-transient error", workflow_id=workflow_id)
                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Workflow failed: {e!s}",
                    data={"error": str(e), "error_type": "non-transient"},
                )
                # Emit extension hook for failure
                await emit_workflow_event(
                    ExtWorkflowEventType.FAILED,
                    workflow_id=workflow_id,
                    metadata={"error": str(e), "error_type": "non-transient"},
                )
                await self._repository.set_status(
                    workflow_id, "failed", failure_reason=str(e)
                )
                raise

    async def _run_review_workflow(
        self,
        workflow_id: str,
        state: ServerExecutionState,
    ) -> None:
        """Run the review-fix workflow graph.

        Similar to _run_workflow but uses review graph and no approval pauses.
        The graph runs autonomously until approved or max iterations reached.

        Args:
            workflow_id: The workflow ID.
            state: Server execution state with embedded core state.
        """
        if state.execution_state is None:
            logger.error("No execution_state in ServerExecutionState", workflow_id=workflow_id)
            await self._repository.set_status(
                workflow_id, "failed", failure_reason="Missing execution state"
            )
            return

        # Get profile from settings using profile_id
        profile = await self._get_profile_or_fail(workflow_id, state.execution_state.profile_id)
        if profile is None:
            return

        async with AsyncSqliteSaver.from_conn_string(
            str(self._checkpoint_path)
        ) as checkpointer:
            # Create review graph (no interrupt_before - runs autonomously)
            graph = create_review_graph(checkpointer)

            # Create stream emitter and pass it via config
            stream_emitter = self._create_stream_emitter()
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "stream_emitter": stream_emitter,
                    "profile": profile,
                }
            }

            await self._emit(
                workflow_id,
                EventType.WORKFLOW_STARTED,
                "Review workflow started",
                data={"issue_id": state.issue_id, "workflow_type": "review"},
            )

            try:
                await self._repository.set_status(workflow_id, "in_progress")

                # Convert Pydantic model to JSON-serializable dict for checkpointing
                initial_state = state.execution_state.model_dump(mode="json")

                async for chunk in graph.astream(
                    initial_state,
                    config=config,
                    stream_mode="updates",
                ):
                    # No interrupt handling - review graph runs autonomously
                    # Emit stage events for each node that completes
                    await self._handle_stream_chunk(workflow_id, chunk)

                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_COMPLETED,
                    "Review workflow completed",
                    data={"final_stage": state.current_stage},
                )
                await self._repository.set_status(workflow_id, "completed")

            except Exception as e:
                logger.exception("Review workflow failed", workflow_id=workflow_id)
                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Review workflow failed: {e}",
                    data={"error": str(e)},
                )
                await self._repository.set_status(
                    workflow_id, "failed", failure_reason=str(e)
                )

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
        """Approve a blocked workflow and resume LangGraph execution.

        Args:
            workflow_id: The workflow to approve.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateError: If workflow is not in "blocked" state.
        """
        workflow = await self._repository.get(workflow_id)
        if not workflow:
            raise WorkflowNotFoundError(workflow_id)

        if workflow.workflow_status != "blocked":
            raise InvalidStateError(
                f"Cannot approve workflow in '{workflow.workflow_status}' state",
                workflow_id=workflow_id,
                current_status=workflow.workflow_status,
            )

        # Emit RESUMED event for workflow being unblocked
        await emit_workflow_event(
            ExtWorkflowEventType.RESUMED,
            workflow_id=workflow_id,
        )

        async with self._approval_lock:
            # Signal the approval event if it exists (for legacy flow)
            event = self._approval_events.get(workflow_id)
            if event:
                event.set()
                self._approval_events.pop(workflow_id, None)

            await self._emit(
                workflow_id,
                EventType.APPROVAL_GRANTED,
                "Plan approved",
            )
            # Emit extension hook for approval
            await emit_workflow_event(
                ExtWorkflowEventType.APPROVAL_GRANTED,
                workflow_id=workflow_id,
            )

            logger.info("Workflow approved", workflow_id=workflow_id)

        # Get profile from settings using profile_id
        if workflow.execution_state is None:
            logger.error("No execution_state in workflow", workflow_id=workflow_id)
            return
        profile = await self._get_profile_or_fail(workflow_id, workflow.execution_state.profile_id)
        if profile is None:
            return

        # Resume LangGraph execution with updated state
        async with AsyncSqliteSaver.from_conn_string(
            str(self._checkpoint_path)
        ) as checkpointer:
            graph = self._create_server_graph(checkpointer)

            # Create stream emitter and pass it via config
            stream_emitter = self._create_stream_emitter()
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "stream_emitter": stream_emitter,
                    "profile": profile,
                }
            }

            # Update state with approval decision
            await graph.aupdate_state(config, {"human_approved": True})

            # Diagnostic: Log checkpoint state before resuming
            checkpoint_state = await graph.aget_state(config)
            if checkpoint_state and checkpoint_state.values:
                has_plan = checkpoint_state.values.get("execution_plan") is not None
                logger.debug(
                    "Checkpoint state before resume",
                    workflow_id=workflow_id,
                    has_execution_plan=has_plan,
                    human_approved=checkpoint_state.values.get("human_approved"),
                    next_nodes=checkpoint_state.next if checkpoint_state.next else None,
                )
            else:
                logger.warning(
                    "No checkpoint state available before resume",
                    workflow_id=workflow_id,
                )

            # Update status to in_progress before resuming
            await self._repository.set_status(workflow_id, "in_progress")

            # Resume execution from checkpoint
            try:
                was_interrupted = False
                async for chunk in graph.astream(
                    None,  # Resume from checkpoint, no new input needed
                    config=config,
                    stream_mode="updates",
                ):
                    # Check for interrupt after resuming (e.g., blocker or batch approval)
                    if "__interrupt__" in chunk:
                        # Get checkpoint state to determine which node triggered interrupt
                        state = await graph.aget_state(config)
                        next_nodes = state.next if state else []

                        logger.info(
                            "Interrupt detected after approval",
                            workflow_id=workflow_id,
                            next_nodes=next_nodes,
                            interrupt_data=chunk["__interrupt__"],
                        )

                        # Handle blocker_resolution_node interrupt
                        if "blocker_resolution_node" in next_nodes:
                            was_interrupted = True
                            # Sync state and emit blocker event
                            await self._sync_plan_from_checkpoint(
                                workflow_id, graph, config
                            )
                            # Get blocker details from state
                            current_blocker = (
                                state.values.get("current_blocker")
                                if state and state.values
                                else None
                            )
                            await self._emit(
                                workflow_id,
                                EventType.APPROVAL_REQUIRED,
                                "Developer blocked - awaiting human intervention",
                                data={
                                    "paused_at": "blocker_resolution_node",
                                    "blocker": current_blocker,
                                },
                            )
                            await self._repository.set_status(workflow_id, "blocked")
                            break
                        # Handle batch_approval_node interrupt
                        elif "batch_approval_node" in next_nodes:
                            was_interrupted = True
                            await self._sync_plan_from_checkpoint(
                                workflow_id, graph, config
                            )
                            await self._emit(
                                workflow_id,
                                EventType.APPROVAL_REQUIRED,
                                "Batch complete - awaiting approval to continue",
                                data={"paused_at": "batch_approval_node"},
                            )
                            await self._repository.set_status(workflow_id, "blocked")
                            break
                        else:
                            # Truly unexpected interrupt - log and continue
                            logger.warning(
                                "Unexpected interrupt after approval",
                                workflow_id=workflow_id,
                                next_nodes=next_nodes,
                            )
                            continue
                    await self._handle_stream_chunk(workflow_id, chunk)

                if not was_interrupted:
                    # Workflow completed after human approval.
                    # Note: A separate COMPLETED emission exists in _run_workflow() for
                    # workflows that complete without interruption. These are mutually exclusive
                    # code paths - only one COMPLETED event is ever emitted per workflow.
                    await self._emit(
                        workflow_id,
                        EventType.WORKFLOW_COMPLETED,
                        "Workflow completed successfully",
                    )
                    await emit_workflow_event(
                        ExtWorkflowEventType.COMPLETED,
                        workflow_id=workflow_id,
                    )
                    await self._repository.set_status(workflow_id, "completed")

            except Exception as e:
                logger.exception("Workflow failed after approval", workflow_id=workflow_id)
                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Workflow failed: {e!s}",
                    data={"error": str(e)},
                )
                # Emit extension hook for failure
                await emit_workflow_event(
                    ExtWorkflowEventType.FAILED,
                    workflow_id=workflow_id,
                    metadata={"error": str(e)},
                )
                await self._repository.set_status(
                    workflow_id, "failed", failure_reason=str(e)
                )
                raise

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
            # Emit extension hook for rejection
            await emit_workflow_event(
                ExtWorkflowEventType.APPROVAL_DENIED,
                workflow_id=workflow_id,
                metadata={"feedback": feedback},
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

        # Get profile from settings using profile_id
        if workflow.execution_state is None:
            logger.error("No execution_state in workflow", workflow_id=workflow_id)
            return
        profile = await self._get_profile_or_fail(workflow_id, workflow.execution_state.profile_id)
        if profile is None:
            return

        # Update LangGraph state to record rejection
        async with AsyncSqliteSaver.from_conn_string(
            str(self._checkpoint_path)
        ) as checkpointer:
            graph = self._create_server_graph(checkpointer)

            config: RunnableConfig = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "profile": profile,
                }
            }

            await graph.aupdate_state(config, {"human_approved": False})

    async def resolve_blocker(
        self,
        workflow_id: str,
        action: Literal["skip", "retry", "abort", "abort_revert", "fix"],
        feedback: str | None = None,
    ) -> None:
        """Resolve a blocker and resume LangGraph execution.

        Maps the action to the appropriate blocker_resolution value and resumes
        the graph from blocker_resolution_node.

        Args:
            workflow_id: The workflow with a blocker to resolve.
            action: Resolution action (skip, retry, abort, abort_revert, fix).
            feedback: Optional feedback or fix instruction (required for 'fix').

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateError: If workflow is not in "blocked" state.
        """
        workflow = await self._repository.get(workflow_id)
        if not workflow:
            raise WorkflowNotFoundError(workflow_id)

        if workflow.workflow_status != "blocked":
            raise InvalidStateError(
                f"Cannot resolve blocker for workflow in '{workflow.workflow_status}' state",
                workflow_id=workflow_id,
                current_status=workflow.workflow_status,
            )

        # Map action to blocker_resolution value
        # See blocker_resolution_node in orchestrator.py for handling:
        # - "skip" → Skip step and continue
        # - "abort" → Abort workflow (keep changes)
        # - "abort_revert" → Abort workflow and revert changes
        # - Any other string (including empty for retry) → Fix instruction/retry
        resolution_map = {
            "skip": "skip",
            "abort": "abort",
            "abort_revert": "abort_revert",
            "retry": "",  # Empty string signals retry without fix instruction
            "fix": feedback or "",  # Fix instruction text
        }
        blocker_resolution = resolution_map.get(action, "")

        async with self._approval_lock:
            await self._emit(
                workflow_id,
                EventType.APPROVAL_GRANTED,
                f"Blocker resolved: {action}",
                data={"action": action, "feedback": feedback},
            )
            logger.info(
                "Blocker resolution submitted",
                workflow_id=workflow_id,
                action=action,
                resolution=blocker_resolution,
            )

        # Get profile from settings using profile_id
        if workflow.execution_state is None:
            logger.error("No execution_state in workflow", workflow_id=workflow_id)
            return
        profile = await self._get_profile_or_fail(workflow_id, workflow.execution_state.profile_id)
        if profile is None:
            return

        # Resume LangGraph execution with blocker_resolution set
        async with AsyncSqliteSaver.from_conn_string(
            str(self._checkpoint_path)
        ) as checkpointer:
            graph = self._create_server_graph(checkpointer)

            stream_emitter = self._create_stream_emitter()
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "stream_emitter": stream_emitter,
                    "profile": profile,
                }
            }

            # Update state with blocker resolution
            await graph.aupdate_state(config, {"blocker_resolution": blocker_resolution})

            # Diagnostic logging
            checkpoint_state = await graph.aget_state(config)
            if checkpoint_state and checkpoint_state.values:
                logger.debug(
                    "Checkpoint state before blocker resume",
                    workflow_id=workflow_id,
                    blocker_resolution=checkpoint_state.values.get("blocker_resolution"),
                    next_nodes=checkpoint_state.next if checkpoint_state.next else None,
                )

            await self._repository.set_status(workflow_id, "in_progress")

            try:
                was_interrupted = False
                async for chunk in graph.astream(
                    None,
                    config=config,
                    stream_mode="updates",
                ):
                    # Check for new interrupt (e.g., another blocker or batch approval)
                    if "__interrupt__" in chunk:
                        state = await graph.aget_state(config)
                        next_nodes = state.next if state else []

                        logger.info(
                            "Interrupt detected after blocker resolution",
                            workflow_id=workflow_id,
                            next_nodes=next_nodes,
                        )

                        if "blocker_resolution_node" in next_nodes:
                            was_interrupted = True
                            await self._sync_plan_from_checkpoint(
                                workflow_id, graph, config
                            )
                            current_blocker = (
                                state.values.get("current_blocker")
                                if state and state.values
                                else None
                            )
                            await self._emit(
                                workflow_id,
                                EventType.APPROVAL_REQUIRED,
                                "Developer blocked - awaiting human intervention",
                                data={
                                    "paused_at": "blocker_resolution_node",
                                    "blocker": current_blocker,
                                },
                            )
                            await self._repository.set_status(workflow_id, "blocked")
                            break
                        elif "batch_approval_node" in next_nodes:
                            was_interrupted = True
                            await self._sync_plan_from_checkpoint(
                                workflow_id, graph, config
                            )
                            await self._emit(
                                workflow_id,
                                EventType.APPROVAL_REQUIRED,
                                "Batch complete - awaiting approval to continue",
                                data={"paused_at": "batch_approval_node"},
                            )
                            await self._repository.set_status(workflow_id, "blocked")
                            break
                        elif "human_approval_node" in next_nodes:
                            was_interrupted = True
                            await self._sync_plan_from_checkpoint(
                                workflow_id, graph, config
                            )
                            await self._emit(
                                workflow_id,
                                EventType.APPROVAL_REQUIRED,
                                "Plan ready for review - awaiting human approval",
                                data={"paused_at": "human_approval_node"},
                            )
                            await self._repository.set_status(workflow_id, "blocked")
                            break
                        else:
                            logger.warning(
                                "Unexpected interrupt after blocker resolution",
                                workflow_id=workflow_id,
                                next_nodes=next_nodes,
                            )
                            continue
                    await self._handle_stream_chunk(workflow_id, chunk)

                if not was_interrupted:
                    await self._emit(
                        workflow_id,
                        EventType.WORKFLOW_COMPLETED,
                        "Workflow completed successfully",
                    )
                    await self._repository.set_status(workflow_id, "completed")

            except Exception as e:
                logger.exception(
                    "Workflow failed after blocker resolution", workflow_id=workflow_id
                )
                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Workflow failed: {e!s}",
                    data={"error": str(e)},
                )
                await self._repository.set_status(
                    workflow_id, "failed", failure_reason=str(e)
                )
                raise

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

    async def _handle_graph_event(
        self,
        workflow_id: str,
        event: dict[str, object],
    ) -> None:
        """Translate LangGraph events to WorkflowEvents and emit.

        Args:
            workflow_id: The workflow this event belongs to.
            event: LangGraph event dictionary.
        """
        event_type = event.get("event")
        node_name = event.get("name")

        if not isinstance(node_name, str):
            return

        if event_type == "on_chain_start":
            if node_name in STAGE_NODES:
                await self._emit(
                    workflow_id,
                    EventType.STAGE_STARTED,
                    f"Starting {node_name}",
                    data={"stage": node_name},
                )

        elif event_type == "on_chain_end":
            if node_name in STAGE_NODES:
                await self._emit(
                    workflow_id,
                    EventType.STAGE_COMPLETED,
                    f"Completed {node_name}",
                    data={"stage": node_name, "output": event.get("data")},
                )

        elif event_type == "on_chain_error":
            error_data = event.get("data", {})
            error_msg = "Unknown error"
            if isinstance(error_data, dict):
                error_msg = str(error_data.get("error", "Unknown error"))
            await self._emit(
                workflow_id,
                EventType.SYSTEM_ERROR,
                f"Error in {node_name}: {error_msg}",
                data={"stage": node_name, "error": error_msg},
            )

    async def _handle_stream_chunk(
        self,
        workflow_id: str,
        chunk: dict[str, Any],
    ) -> None:
        """Handle a chunk from astream(stream_mode='updates').

        With stream_mode='updates', each chunk maps node names to their
        state updates. We emit STAGE_STARTED before and STAGE_COMPLETED
        after each node that's in STAGE_NODES.

        Additionally emits AGENT_MESSAGE and task lifecycle events (TASK_STARTED,
        TASK_COMPLETED, TASK_FAILED) based on node output.

        Args:
            workflow_id: The workflow this chunk belongs to.
            chunk: Dict mapping node names to state updates.
        """
        for node_name, output in chunk.items():
            if node_name in STAGE_NODES:
                # Update current_stage in workflow state
                state = await self._repository.get(workflow_id)
                if state is not None:
                    state.current_stage = node_name
                    await self._repository.update(state)

                # Emit both started and completed for each node update
                # (astream "updates" mode gives us the result after completion)
                await self._emit(
                    workflow_id,
                    EventType.STAGE_STARTED,
                    f"Starting {node_name}",
                    data={"stage": node_name},
                )

                # Emit agent-specific messages based on node
                await self._emit_agent_messages(workflow_id, node_name, output)

                await self._emit(
                    workflow_id,
                    EventType.STAGE_COMPLETED,
                    f"Completed {node_name}",
                    data={"stage": node_name, "output": output},
                )

    async def _emit_agent_messages(
        self,
        workflow_id: str,
        node_name: str,
        output: dict[str, Any],
    ) -> None:
        """Emit detailed agent messages based on node output.

        Args:
            workflow_id: The workflow ID.
            node_name: Name of the node that produced this output.
            output: State updates from the node.
        """
        if node_name == "architect_node":
            await self._emit_architect_messages(workflow_id, output)
        elif node_name == "developer_node":
            await self._emit_developer_messages(workflow_id, output)
        elif node_name == "reviewer_node":
            await self._emit_reviewer_messages(workflow_id, output)

    async def _emit_architect_messages(
        self,
        workflow_id: str,
        output: dict[str, Any],
    ) -> None:
        """Emit messages for architect node output.

        Args:
            workflow_id: The workflow ID.
            output: State updates from the architect node.
        """
        execution_plan = output.get("execution_plan")
        if not execution_plan:
            return

        # Handle both Pydantic model and dict representations
        # LangGraph may pass either depending on serialization context
        if isinstance(execution_plan, dict):
            batches = execution_plan.get("batches", [])
        elif hasattr(execution_plan, "batches"):
            # Pydantic model - convert to list for consistent handling
            batches = list(execution_plan.batches)
        else:
            return

        # Count total steps across all batches
        total_steps = 0
        for batch in batches:
            if isinstance(batch, dict):
                total_steps += len(batch.get("steps", []))
            elif hasattr(batch, "steps"):
                total_steps += len(batch.steps)

        await self._emit(
            workflow_id,
            EventType.AGENT_MESSAGE,
            f"Generated plan with {len(batches)} batches, {total_steps} steps",
            agent="architect",
            data={"batch_count": len(batches), "step_count": total_steps},
        )

        # Initialize step status tracking for this workflow
        if workflow_id not in self._last_task_statuses:
            self._last_task_statuses[workflow_id] = {}

        for batch in batches:
            # Get steps from either dict or Pydantic model
            if isinstance(batch, dict):
                steps = batch.get("steps", [])
            elif hasattr(batch, "steps"):
                steps = batch.steps
            else:
                continue

            for step in steps:
                # Get step_id from either dict or Pydantic model
                if isinstance(step, dict):
                    step_id = step.get("id")
                elif hasattr(step, "id"):
                    step_id = step.id
                else:
                    continue

                if step_id:
                    # Steps don't have status initially, mark as pending
                    self._last_task_statuses[workflow_id][step_id] = "pending"

    async def _emit_developer_messages(
        self,
        workflow_id: str,
        output: dict[str, Any],
    ) -> None:
        """Emit messages for developer node output.

        Args:
            workflow_id: The workflow ID.
            output: State updates from the developer node.
        """
        # Check for batch results from new execution model
        batch_results = output.get("batch_results")
        developer_status = output.get("developer_status")
        current_batch_index = output.get("current_batch_index")

        if batch_results and isinstance(batch_results, list):
            for result in batch_results:
                if not isinstance(result, dict):
                    continue

                batch_num = result.get("batch_number", 0)
                # Field is 'completed_steps' in BatchResult model, not 'step_results'
                completed_steps = result.get("completed_steps", [])

                # Emit events for each step result
                for step_result in completed_steps:
                    if not isinstance(step_result, dict):
                        continue

                    step_id = step_result.get("step_id")
                    # StepResult uses 'status' field with values like "completed", "failed", "skipped"
                    status = step_result.get("status")
                    # StepResult uses 'error' field, not 'error_message'
                    error = step_result.get("error")

                    if not step_id:
                        continue

                    if status == "completed":
                        await self._emit(
                            workflow_id,
                            EventType.TASK_COMPLETED,
                            f"Completed step: {step_id}",
                            agent="developer",
                            data={"step_id": step_id, "batch_number": batch_num},
                        )
                    elif status == "failed" and error:
                        await self._emit(
                            workflow_id,
                            EventType.TASK_FAILED,
                            f"Step failed: {step_id} - {error}",
                            agent="developer",
                            data={"step_id": step_id, "batch_number": batch_num, "error": error},
                        )
                    elif status == "skipped":
                        await self._emit(
                            workflow_id,
                            EventType.AGENT_MESSAGE,
                            f"Step skipped: {step_id}",
                            agent="developer",
                            data={"step_id": step_id, "batch_number": batch_num, "status": "skipped"},
                        )

        # Emit status updates based on developer_status
        if developer_status == "batch_complete":
            await self._emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                f"Batch {current_batch_index} complete, awaiting review",
                agent="developer",
                data={"batch_index": current_batch_index, "status": developer_status},
            )
        elif developer_status == "all_done":
            await self._emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                "All batches complete",
                agent="developer",
                data={"status": developer_status},
            )
        elif developer_status == "blocked":
            # Get blocker details from output
            current_blocker = output.get("current_blocker")
            blocker_data: dict[str, Any] = {"status": developer_status}

            if current_blocker and isinstance(current_blocker, dict):
                step_id = current_blocker.get("step_id", "unknown")
                step_desc = current_blocker.get("step_description", "")
                blocker_type = current_blocker.get("blocker_type", "unknown")
                context = current_blocker.get("context", "")

                # Build detailed message
                message_parts = [f"Developer blocked at step '{step_id}'"]
                if blocker_type:
                    message_parts.append(f"({blocker_type})")
                if step_desc:
                    message_parts.append(f": {step_desc}")
                message = " ".join(message_parts)

                # Include blocker details in event data
                blocker_data["blocker"] = {
                    "step_id": step_id,
                    "step_description": step_desc,
                    "blocker_type": blocker_type,
                    "context": context,
                }

                # Log detailed blocker info
                logger.warning(
                    "Developer execution blocked",
                    workflow_id=workflow_id,
                    step_id=step_id,
                    step_description=step_desc,
                    blocker_type=blocker_type,
                    context=context[:200] if context else None,
                )
            else:
                message = "Developer blocked, needs human intervention"
                logger.warning(
                    "Developer blocked without blocker details",
                    workflow_id=workflow_id,
                )

            await self._emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                message,
                agent="developer",
                data=blocker_data,
            )

    async def _emit_reviewer_messages(
        self,
        workflow_id: str,
        output: dict[str, Any],
    ) -> None:
        """Emit messages for reviewer node output.

        Args:
            workflow_id: The workflow ID.
            output: State updates from the reviewer node.
        """
        last_review = output.get("last_review")
        if last_review and isinstance(last_review, dict):
            approved = last_review.get("approved", False)
            severity = last_review.get("severity", "unknown")
            comment_count = len(last_review.get("comments", []))

            await self._emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                f"Review {'approved' if approved else 'requested changes'} "
                f"({severity} severity, {comment_count} comments)",
                agent="reviewer",
                data={
                    "approved": approved,
                    "severity": severity,
                    "comment_count": comment_count,
                },
            )

    async def _sync_plan_from_checkpoint(
        self,
        workflow_id: str,
        graph: CompiledStateGraph[Any],
        config: RunnableConfig,
    ) -> None:
        """Sync plan from LangGraph checkpoint to ServerExecutionState.

        Uses LangGraph's get_state() API to fetch the current checkpoint state,
        ensuring the plan is available via REST API when workflow is blocked.

        Args:
            workflow_id: The workflow ID.
            graph: The compiled LangGraph instance.
            config: The RunnableConfig with thread_id.
        """
        try:
            # Fetch current checkpoint state from LangGraph
            checkpoint_state = await graph.aget_state(config)
            if checkpoint_state is None or checkpoint_state.values is None:
                logger.warning(
                    "Cannot sync plan - no checkpoint state",
                    workflow_id=workflow_id,
                )
                return

            execution_plan_dict = checkpoint_state.values.get("execution_plan")
            if execution_plan_dict is None:
                logger.debug("No execution_plan in checkpoint yet", workflow_id=workflow_id)
                return

            # Fetch ServerExecutionState
            state = await self._repository.get(workflow_id)
            if state is None or state.execution_state is None:
                logger.warning(
                    "Cannot sync execution_plan - workflow or execution_state not found",
                    workflow_id=workflow_id,
                )
                return

            # Parse the execution_plan dict into an ExecutionPlan
            execution_plan = ExecutionPlan.model_validate(execution_plan_dict)

            # Update the execution_state with the execution_plan
            # ExecutionState is frozen, so we use model_copy to create an updated instance
            state.execution_state = state.execution_state.model_copy(
                update={"execution_plan": execution_plan}
            )

            # Save back to repository
            await self._repository.update(state)
            logger.debug("Synced execution_plan to ServerExecutionState", workflow_id=workflow_id)

        except Exception as e:
            # Log but don't fail the workflow - plan sync is best-effort
            logger.warning(
                "Failed to sync plan from checkpoint",
                workflow_id=workflow_id,
                error=str(e),
            )


    async def recover_interrupted_workflows(self) -> None:
        """Recover workflows that were running when server crashed.

        Scans for workflows in non-terminal states (in_progress, blocked) and marks
        them as failed with an appropriate reason. This prevents stale workflows from
        persisting after server restarts.

        Note:
            This is a placeholder - full implementation will be added when LangGraph
            integration is complete.
        """
        logger.info("Checking for interrupted workflows...")
        # TODO: Query for workflows with status=in_progress or blocked
        # and mark them as failed with appropriate reason
        logger.info("No interrupted workflows to recover")
