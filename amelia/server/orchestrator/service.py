"""Orchestrator service for managing concurrent workflow execution."""

import asyncio
import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from httpx import TimeoutException
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.state import CompiledStateGraph
from loguru import logger
from pydantic import ValidationError

from amelia.core.orchestrator import create_orchestrator_graph, create_review_graph
from amelia.core.state import ExecutionState
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
    "evaluation_node",
})

# Exceptions that warrant retry
TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    asyncio.TimeoutError,
    TimeoutException,
    ConnectionError,
)


async def get_git_head(cwd: str | None) -> str | None:
    """Get current git HEAD commit SHA.

    Args:
        cwd: Working directory for git command.

    Returns:
        Current HEAD commit SHA or None if not a git repo.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode().strip()
    except (FileNotFoundError, OSError):
        pass
    return None


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
        checkpoint_path: str = "~/.amelia/checkpoints.db",
    ) -> None:
        """Initialize orchestrator service.

        Args:
            event_bus: Event bus for broadcasting workflow events.
            repository: Repository for workflow persistence.
            max_concurrent: Maximum number of concurrent workflows (default: 5).
            checkpoint_path: Path to checkpoint database file.
        """
        self._event_bus = event_bus
        self._repository = repository
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

    async def _resolve_prompts(self, workflow_id: str) -> dict[str, str]:
        """Resolve all prompts for a workflow.

        Uses PromptResolver to get current active prompts, falling back to
        defaults when no custom version exists. Records which versions are
        used by the workflow for audit purposes.

        Args:
            workflow_id: The workflow identifier for recording prompt usage.

        Returns:
            Dictionary mapping prompt_id to prompt content.
        """
        from amelia.agents.prompts.resolver import PromptResolver  # noqa: PLC0415
        from amelia.server.database.prompt_repository import PromptRepository  # noqa: PLC0415

        try:
            prompt_repo = PromptRepository(self._repository.db)
            resolver = PromptResolver(prompt_repo)
            resolved_prompts = await resolver.get_all_active()
            prompts = {pid: rp.content for pid, rp in resolved_prompts.items()}

            # Record which versions the workflow uses (best-effort)
            await resolver.record_for_workflow(workflow_id)

            return prompts
        except Exception as e:
            # Log but don't fail workflow - prompts will fall back to defaults
            logger.warning(
                "Failed to resolve prompts, using defaults",
                workflow_id=workflow_id,
                error=str(e),
            )
            return {}

    async def _get_profile_or_fail(
        self,
        workflow_id: str,
        profile_id: str,
        worktree_path: str,
    ) -> Profile | None:
        """Look up profile by ID from worktree settings.

        Settings are loaded from the worktree's settings.amelia.yaml file.
        There is no fallback - each worktree must have its own settings.

        Args:
            workflow_id: Workflow ID for logging and status updates.
            profile_id: Profile ID to look up in settings.
            worktree_path: Worktree path to load settings from (required).

        Returns:
            Profile if found, None if not found (after setting workflow to failed).
        """
        try:
            settings = self._load_settings_for_worktree(worktree_path)
        except ValidationError as e:
            logger.error(
                "Invalid settings file in worktree",
                workflow_id=workflow_id,
                worktree_path=worktree_path,
                error=str(e),
            )
            await self._repository.set_status(
                workflow_id, "failed", failure_reason=f"Invalid settings.amelia.yaml in {worktree_path}: {e}"
            )
            return None
        if settings is None:
            logger.error(
                "No settings file found in worktree",
                workflow_id=workflow_id,
                worktree_path=worktree_path,
            )
            await self._repository.set_status(
                workflow_id, "failed", failure_reason=f"No settings.amelia.yaml in {worktree_path}"
            )
            return None

        if profile_id not in settings.profiles:
            logger.error("Profile not found", workflow_id=workflow_id, profile_id=profile_id)
            await self._repository.set_status(
                workflow_id, "failed", failure_reason=f"Profile '{profile_id}' not found"
            )
            return None

        profile = settings.profiles[profile_id]

        # Ensure working_dir is set to worktree_path for git operations
        # Create a copy to avoid mutating the shared settings profile
        if profile.working_dir is None:
            profile = profile.model_copy(update={"working_dir": worktree_path})

        return profile

    def _resolve_safe_worktree_path(self, worktree_path: str) -> Path | None:
        """Resolve and validate a worktree path to prevent path traversal attacks.

        Normalizes the path by expanding ~ and resolving to an absolute path,
        then validates that the resulting path is a directory.

        Args:
            worktree_path: Path to the worktree directory.

        Returns:
            Resolved absolute Path if valid, None if validation fails.
        """
        try:
            # Normalize path: expand ~ and resolve to absolute canonical path
            # This prevents path traversal attacks like "../../../etc"
            resolved = Path(worktree_path).expanduser().resolve()

            # Validate the resolved path is a directory
            if not resolved.is_dir():
                logger.warning(
                    "Worktree path is not a directory",
                    worktree_path=worktree_path,
                    resolved_path=str(resolved),
                )
                return None

            return resolved
        except (OSError, ValueError) as e:
            logger.warning(
                "Failed to resolve worktree path",
                worktree_path=worktree_path,
                error=str(e),
            )
            return None

    def _load_settings_for_worktree(self, worktree_path: str) -> Settings | None:
        """Load settings from a worktree directory.

        Attempts to load settings.amelia.yaml from the worktree directory.
        Returns None on any error (file not found, invalid YAML, validation error)
        to allow graceful fallback to server settings.

        Args:
            worktree_path: Absolute path to the worktree directory.

        Returns:
            Settings if successfully loaded, None otherwise.
        """
        # Resolve and validate the worktree path to prevent path traversal
        resolved_worktree = self._resolve_safe_worktree_path(worktree_path)
        if resolved_worktree is None:
            return None

        settings_path = resolved_worktree / "settings.amelia.yaml"

        # Verify the settings path is still within the worktree directory
        # (prevents path traversal via symlinks)
        try:
            settings_path.resolve().relative_to(resolved_worktree)
        except ValueError:
            logger.warning(
                "Settings path escapes worktree directory",
                worktree_path=worktree_path,
                settings_path=str(settings_path),
            )
            return None

        if not settings_path.exists():
            logger.debug(
                "No settings file in worktree",
                worktree_path=worktree_path,
            )
            return None

        try:
            with settings_path.open() as f:
                data = yaml.safe_load(f)
            return Settings(**data)
        except yaml.YAMLError as e:
            logger.warning(
                "Invalid YAML in worktree settings",
                worktree_path=worktree_path,
                error=str(e),
            )
            return None
        except ValidationError:
            # Let Pydantic validation errors propagate so callers can show
            # the actual validation error (e.g., missing required fields)
            # instead of a misleading "file not found" message
            raise
        except Exception as e:
            logger.warning(
                "Failed to load worktree settings",
                worktree_path=worktree_path,
                error=str(e),
            )
            return None

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

            # Load settings from worktree (required - no fallback)
            try:
                settings = self._load_settings_for_worktree(worktree_path)
            except ValidationError as e:
                raise ValueError(
                    f"Invalid settings.amelia.yaml in {worktree_path}: {e}"
                ) from e
            if settings is None:
                raise ValueError(
                    f"No settings.amelia.yaml found in {worktree_path}. "
                    "Each worktree must have its own settings file."
                )

            # Load the profile (use provided profile name or active profile as fallback)
            profile_name = profile or settings.active_profile
            if profile_name not in settings.profiles:
                raise ValueError(f"Profile '{profile_name}' not found in settings")
            loaded_profile = settings.profiles[profile_name]

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

            # Get current HEAD to track changes from workflow start
            base_commit = await get_git_head(worktree_path)

            # Initialize ExecutionState with profile_id, issue, and base commit
            execution_state = ExecutionState(
                profile_id=loaded_profile.name,
                issue=issue,
                base_commit=base_commit,
            )

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

            # Load settings from worktree (required - no fallback)
            try:
                settings = self._load_settings_for_worktree(worktree_path)
            except ValidationError as e:
                raise ValueError(
                    f"Invalid settings.amelia.yaml in {worktree_path}: {e}"
                ) from e
            if settings is None:
                raise ValueError(
                    f"No settings.amelia.yaml found in {worktree_path}. "
                    "Each worktree must have its own settings file."
                )

            # Load profile
            profile_name = profile or settings.active_profile
            if profile_name not in settings.profiles:
                raise ValueError(f"Profile '{profile_name}' not found in settings")
            loaded_profile = settings.profiles[profile_name]
            if loaded_profile.working_dir is None:
                loaded_profile = loaded_profile.model_copy(update={"working_dir": worktree_path})

            # Create dummy issue for review context
            dummy_issue = Issue(
                id="LOCAL-REVIEW",
                title="Local Code Review",
                description="Review local uncommitted changes."
            )

            # Get current HEAD for tracking (even though diff is provided)
            base_commit = await get_git_head(worktree_path)

            # Initialize ExecutionState with diff content
            execution_state = ExecutionState(
                profile_id=loaded_profile.name,
                issue=dummy_issue,
                code_changes_for_review=diff_content,
                base_commit=base_commit,
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

        # Get profile from settings using profile_id (with worktree_path fallback)
        profile = await self._get_profile_or_fail(
            workflow_id, state.execution_state.profile_id, state.worktree_path
        )
        if profile is None:
            return

        # Resolve prompts before starting workflow
        prompts = await self._resolve_prompts(workflow_id)

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
                    "repository": self._repository,
                    "prompts": prompts,
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

        # Get profile from settings using profile_id (with worktree_path fallback)
        profile = await self._get_profile_or_fail(
            workflow_id, state.execution_state.profile_id, state.worktree_path
        )
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

        # Get profile from settings using profile_id (with worktree_path fallback)
        profile = await self._get_profile_or_fail(
            workflow_id, state.execution_state.profile_id, state.worktree_path
        )
        if profile is None:
            return

        # Resolve prompts before starting workflow
        prompts = await self._resolve_prompts(workflow_id)

        async with AsyncSqliteSaver.from_conn_string(
            str(self._checkpoint_path)
        ) as checkpointer:
            # Determine interrupt settings based on auto_approve
            auto_approve = state.execution_state.auto_approve or profile.auto_approve_reviews
            interrupt_before: list[str] | None = [] if auto_approve else None  # None = use defaults

            # Use dedicated review graph for review workflows
            graph = create_review_graph(
                checkpoint_saver=checkpointer,
                interrupt_before=interrupt_before,
            )

            # Create stream emitter and pass it via config
            stream_emitter = self._create_stream_emitter()
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "stream_emitter": stream_emitter,
                    "profile": profile,
                    "repository": self._repository,
                    "prompts": prompts,
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
                # Ensure auto_approve is set from profile if not already in state
                if profile.auto_approve_reviews and not initial_state.get("auto_approve"):
                    initial_state["auto_approve"] = True

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

        # Get profile from settings using profile_id (with worktree_path fallback)
        if workflow.execution_state is None:
            logger.error("No execution_state in workflow", workflow_id=workflow_id)
            return
        profile = await self._get_profile_or_fail(
            workflow_id, workflow.execution_state.profile_id, workflow.worktree_path
        )
        if profile is None:
            return

        # Resolve prompts for workflow resume
        prompts = await self._resolve_prompts(workflow_id)

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
                    "repository": self._repository,
                    "prompts": prompts,
                }
            }

            # Update state with approval decision
            await graph.aupdate_state(config, {"human_approved": True})

            # Diagnostic: Log checkpoint state before resuming
            checkpoint_state = await graph.aget_state(config)
            if checkpoint_state and checkpoint_state.values:
                has_goal = checkpoint_state.values.get("goal") is not None
                has_plan = checkpoint_state.values.get("plan_markdown") is not None
                logger.debug(
                    "Checkpoint state before resume",
                    workflow_id=workflow_id,
                    has_goal=has_goal,
                    has_plan=has_plan,
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
                    # In agentic mode, no interrupts expected after initial approval
                    if "__interrupt__" in chunk:
                        state = await graph.aget_state(config)
                        next_nodes = state.next if state else []
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

        # Get profile from settings using profile_id (with worktree_path fallback)
        if workflow.execution_state is None:
            logger.error("No execution_state in workflow", workflow_id=workflow_id)
            return
        profile = await self._get_profile_or_fail(
            workflow_id, workflow.execution_state.profile_id, workflow.worktree_path
        )
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
                    "repository": self._repository,
                }
            }

            await graph.aupdate_state(config, {"human_approved": False})

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
        elif node_name == "evaluation_node":
            await self._emit_evaluator_messages(workflow_id, output)

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
        # In agentic mode, architect sets goal and generates markdown plan
        goal = output.get("goal")
        plan_markdown = output.get("plan_markdown")

        if goal:
            await self._emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                f"Goal: {goal}",
                agent="architect",
                data={"goal": goal, "has_plan": plan_markdown is not None},
            )

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
        # In agentic mode, developer works autonomously with tool calls
        # Emit status updates based on agentic state
        status = output.get("agentic_status")
        final_response = output.get("final_response")

        if status == "completed" and final_response:
            await self._emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                "Development complete",
                agent="developer",
                data={"status": status},
            )
        elif status == "failed":
            error = output.get("error", "Unknown error")
            await self._emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                f"Development failed: {error}",
                agent="developer",
                data={"status": status, "error": error},
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
        if not last_review:
            return

        # Node returns ReviewResult Pydantic model directly
        approved = last_review.approved
        severity = last_review.severity
        comment_count = len(last_review.comments) if last_review.comments else 0

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

    async def _emit_evaluator_messages(
        self,
        workflow_id: str,
        output: dict[str, Any],
    ) -> None:
        """Emit messages for evaluator node output.

        Args:
            workflow_id: The workflow ID.
            output: State updates from the evaluator node.
        """
        evaluation_result = output.get("evaluation_result")
        if not evaluation_result:
            return

        # Node returns EvaluationResult Pydantic model directly
        to_implement = len(evaluation_result.items_to_implement)
        rejected = len(evaluation_result.items_rejected)
        deferred = len(evaluation_result.items_deferred)
        clarify = len(evaluation_result.items_needing_clarification)

        summary_parts = []
        if to_implement:
            summary_parts.append(f"{to_implement} to implement")
        if rejected:
            summary_parts.append(f"{rejected} rejected")
        if deferred:
            summary_parts.append(f"{deferred} deferred")
        if clarify:
            summary_parts.append(f"{clarify} need clarification")

        message = f"Evaluation: {', '.join(summary_parts)}" if summary_parts else "Evaluation complete"

        await self._emit(
            workflow_id,
            EventType.AGENT_MESSAGE,
            message,
            agent="evaluator",
            data={
                "to_implement": to_implement,
                "rejected": rejected,
                "deferred": deferred,
                "needs_clarification": clarify,
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

            # Check for goal and plan_markdown from agentic execution
            goal = checkpoint_state.values.get("goal")
            plan_markdown = checkpoint_state.values.get("plan_markdown")
            if goal is None and plan_markdown is None:
                logger.debug("No goal or plan_markdown in checkpoint yet", workflow_id=workflow_id)
                return

            # Fetch ServerExecutionState
            state = await self._repository.get(workflow_id)
            if state is None or state.execution_state is None:
                logger.warning(
                    "Cannot sync plan - workflow or execution_state not found",
                    workflow_id=workflow_id,
                )
                return

            # Build update dict with goal and plan_markdown
            update_dict: dict[str, Any] = {}
            if goal is not None:
                update_dict["goal"] = goal
            if plan_markdown is not None:
                update_dict["plan_markdown"] = plan_markdown

            if not update_dict:
                return

            # Update the execution_state with synced fields
            # ExecutionState is frozen, so we use model_copy to create an updated instance
            state.execution_state = state.execution_state.model_copy(update=update_dict)

            # Save back to repository
            await self._repository.update(state)
            logger.debug("Synced plan to ServerExecutionState", workflow_id=workflow_id)

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
