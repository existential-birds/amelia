"""Orchestrator service for managing concurrent workflow execution."""

import asyncio
import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
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
from amelia.core.types import (
    Issue,
    Profile,
    Settings,
)
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
from amelia.server.models.requests import BatchStartRequest, CreateWorkflowRequest
from amelia.server.models.responses import BatchStartResponse
from amelia.trackers.factory import create_tracker


if TYPE_CHECKING:
    from amelia.agents.architect import Architect


# Nodes that emit stage events
STAGE_NODES: frozenset[str] = frozenset({
    "architect_node",
    "plan_validator_node",
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
        self._planning_tasks: dict[str, asyncio.Task[None]] = {}  # workflow_id -> planning task
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

        # ALWAYS set working_dir to worktree_path for agent execution
        # This ensures agents run in the correct directory regardless of settings
        # Create a copy to avoid mutating the shared settings profile
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

    async def _prepare_workflow_state(
        self,
        worktree_path: str,
        issue_id: str,
        profile_name: str | None = None,
        task_title: str | None = None,
        task_description: str | None = None,
    ) -> tuple[str, Profile, ExecutionState]:
        """Prepare common state needed to create or start a workflow.

        Centralizes the common initialization logic for settings loading,
        profile resolution, issue fetching, and ExecutionState creation
        shared across queue_workflow, start_workflow, and queue_and_plan_workflow.

        Args:
            worktree_path: Resolved worktree path (already validated).
            issue_id: The issue ID to work on.
            profile_name: Optional profile name (defaults to active profile).
            task_title: Optional task title for noop tracker.
            task_description: Optional task description (defaults to task_title).

        Returns:
            Tuple of (resolved_path, profile, execution_state).

        Raises:
            ValueError: If settings are invalid, profile not found, or task_title
                used with non-noop tracker.
        """
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
        resolved_profile_name = profile_name or settings.active_profile
        if resolved_profile_name not in settings.profiles:
            raise ValueError(f"Profile '{resolved_profile_name}' not found in settings")
        profile = settings.profiles[resolved_profile_name]

        # ALWAYS set working_dir to worktree_path for agent execution
        profile = profile.model_copy(update={"working_dir": worktree_path})

        # Fetch issue from tracker (or construct from task_title)
        if task_title is not None:
            # Validate that tracker is noop when using task_title
            if profile.tracker not in ("noop", "none"):
                raise ValueError(
                    f"task_title can only be used with noop tracker, "
                    f"but profile '{profile.name}' uses tracker '{profile.tracker}'"
                )
            issue = Issue(
                id=issue_id,
                title=task_title,
                description=task_description or task_title,
            )
        else:
            # Fetch issue from tracker
            tracker = create_tracker(profile)
            issue = tracker.get_issue(issue_id, cwd=worktree_path)

        # Get current HEAD to track changes
        base_commit = await get_git_head(worktree_path)

        # Create ExecutionState with all required fields
        execution_state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            base_commit=base_commit,
        )

        return worktree_path, profile, execution_state

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

    def _validate_worktree_path(self, worktree_path: str) -> Path:
        """Validate and resolve worktree path securely.

        Resolves the path to its canonical form, removing any path traversal
        sequences (../) and following symlinks. Then validates the resolved
        path exists and is a git repository.

        Args:
            worktree_path: User-provided worktree path to validate.

        Returns:
            Resolved, validated Path object.

        Raises:
            InvalidWorktreeError: If path doesn't exist, isn't a directory,
                or isn't a git repository.
        """
        # Expand ~ and resolve to canonical form FIRST - this prevents path
        # traversal attacks by converting paths like "/safe/../unsafe" to their
        # real location
        try:
            worktree = Path(worktree_path).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as e:
            raise InvalidWorktreeError(worktree_path, f"invalid path: {e}") from e

        # Now validate the RESOLVED path
        if not worktree.exists():
            raise InvalidWorktreeError(str(worktree), "directory does not exist")
        if not worktree.is_dir():
            raise InvalidWorktreeError(str(worktree), "path is not a directory")
        git_path = worktree / ".git"
        if not git_path.exists():
            raise InvalidWorktreeError(str(worktree), "not a git repository (.git missing)")

        return worktree

    async def start_workflow(
        self,
        issue_id: str,
        worktree_path: str,
        profile: str | None = None,
        driver: str | None = None,
        task_title: str | None = None,
        task_description: str | None = None,
    ) -> str:
        """Start a new workflow.

        Args:
            issue_id: The issue ID to work on.
            worktree_path: Absolute path to the worktree.
            profile: Optional profile name.
            driver: Optional driver override.
            task_title: Optional task title for direct Issue construction (noop tracker only).
            task_description: Optional task description (defaults to task_title if not provided).

        Returns:
            The workflow ID (UUID).

        Raises:
            InvalidWorktreeError: If worktree path doesn't exist or is not a git repo.
            WorkflowConflictError: If worktree already has active workflow.
            ConcurrencyLimitError: If at max concurrent workflows.
            ValueError: If task_title is provided but tracker is not noop.
        """
        # Validate and resolve worktree before acquiring lock (fast-fail)
        worktree = self._validate_worktree_path(worktree_path)
        resolved_path = str(worktree)

        async with self._start_lock:
            # Check worktree conflict - workflow_id is cached in tuple
            # Use resolved path for consistent comparison
            if resolved_path in self._active_tasks:
                existing_id, _ = self._active_tasks[resolved_path]
                raise WorkflowConflictError(resolved_path, existing_id)

            # Check concurrency limit
            current_count = len(self._active_tasks)
            if current_count >= self._max_concurrent:
                raise ConcurrencyLimitError(self._max_concurrent, current_count)

            # Create workflow ID early for policy check
            workflow_id = str(uuid4())

            # Load settings from worktree (required - no fallback)
            try:
                settings = self._load_settings_for_worktree(resolved_path)
            except ValidationError as e:
                raise ValueError(
                    f"Invalid settings.amelia.yaml in {resolved_path}: {e}"
                ) from e
            if settings is None:
                raise ValueError(
                    f"No settings.amelia.yaml found in {resolved_path}. "
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

            # Prepare issue and execution state using the helper
            # (settings/profile loading done above for policy check)
            _, loaded_profile, execution_state = await self._prepare_workflow_state(
                worktree_path=resolved_path,
                issue_id=issue_id,
                profile_name=profile,
                task_title=task_title,
                task_description=task_description,
            )

            state = ServerExecutionState(
                id=workflow_id,
                issue_id=issue_id,
                worktree_path=resolved_path,
                execution_state=execution_state,
                workflow_status="pending",
                started_at=datetime.now(UTC),
            )
            try:
                await self._repository.create(state)
            except Exception as e:
                # Handle DB constraint violation (e.g., crash recovery scenario)
                if "UNIQUE constraint failed" in str(e):
                    raise WorkflowConflictError(resolved_path, "existing") from e
                raise

            logger.info(
                "Starting workflow",
                workflow_id=workflow_id,
                issue_id=issue_id,
                worktree_path=resolved_path,
            )

            # Start async task with retry wrapper for transient failures
            task = asyncio.create_task(self._run_workflow_with_retry(workflow_id, state))
            self._active_tasks[resolved_path] = (workflow_id, task)

        # Remove from active tasks on completion
        def cleanup_task(_: asyncio.Task[None]) -> None:
            """Clean up resources when workflow task completes.

            Args:
                _: The completed asyncio Task (unused).
            """
            self._active_tasks.pop(resolved_path, None)
            self._sequence_counters.pop(workflow_id, None)
            self._sequence_locks.pop(workflow_id, None)
            self._approval_events.pop(workflow_id, None)
            logger.debug(
                "Workflow task completed",
                workflow_id=workflow_id,
                worktree_path=resolved_path,
            )

        task.add_done_callback(cleanup_task)

        return workflow_id

    async def queue_workflow(self, request: CreateWorkflowRequest) -> str:
        """Queue a workflow without starting it.

        Creates a workflow in pending state with execution_state populated
        so it can be started later. Multiple pending workflows can exist
        for the same worktree (unlike running workflows).

        Args:
            request: Workflow creation request with start=False.

        Returns:
            The workflow ID (UUID format).

        Raises:
            InvalidWorktreeError: If worktree doesn't exist or isn't a git repo.
            ValueError: If settings are invalid or profile not found.
        """
        # Validate and resolve worktree path securely
        worktree = self._validate_worktree_path(request.worktree_path)
        resolved_path = str(worktree)

        # Prepare common workflow state (settings, profile, issue, execution_state)
        resolved_path, profile, execution_state = await self._prepare_workflow_state(
            worktree_path=resolved_path,
            issue_id=request.issue_id,
            profile_name=request.profile,
            task_title=request.task_title,
            task_description=request.task_description,
        )

        # Generate workflow ID
        workflow_id = str(uuid4())

        # Create ServerExecutionState in pending status (not started)
        state = ServerExecutionState(
            id=workflow_id,
            issue_id=request.issue_id,
            worktree_path=resolved_path,
            execution_state=execution_state,
            workflow_status="pending",
            # No started_at - workflow hasn't started
            # No planned_at - not planned yet
        )

        # Save to database
        await self._repository.create(state)

        # Emit created event
        await self._emit(
            workflow_id,
            EventType.WORKFLOW_CREATED,
            f"Workflow queued for {request.issue_id}",
            data={"issue_id": request.issue_id, "queued": True},
        )

        logger.info(
            "Workflow queued",
            workflow_id=workflow_id,
            issue_id=request.issue_id,
            worktree_path=resolved_path,
        )

        return workflow_id

    async def start_review_workflow(
        self,
        diff_content: str,
        worktree_path: str,
        profile: str | None = None,
    ) -> str:
        """Start a review-fix workflow.

        Args:
            diff_content: The git diff to review.
            worktree_path: Path for conflict detection (typically cwd).
            profile: Optional profile name.

        Returns:
            The workflow ID (UUID).

        Raises:
            WorkflowConflictError: If worktree already has active workflow.
            ConcurrencyLimitError: If at max concurrent workflows.
        """
        # Validate and resolve worktree path securely
        # Note: review workflow doesn't require .git, so we do minimal validation
        try:
            worktree = Path(worktree_path).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as e:
            raise InvalidWorktreeError(worktree_path, f"invalid path: {e}") from e
        if not worktree.exists() or not worktree.is_dir():
            raise InvalidWorktreeError(str(worktree), "directory does not exist")
        resolved_path = str(worktree)

        async with self._start_lock:
            # Same conflict and concurrency checks as start_workflow
            if resolved_path in self._active_tasks:
                existing_id, _ = self._active_tasks[resolved_path]
                raise WorkflowConflictError(resolved_path, existing_id)

            if len(self._active_tasks) >= self._max_concurrent:
                raise ConcurrencyLimitError(self._max_concurrent, len(self._active_tasks))

            workflow_id = str(uuid4())

            # Load settings from worktree (required - no fallback)
            try:
                settings = self._load_settings_for_worktree(resolved_path)
            except ValidationError as e:
                raise ValueError(
                    f"Invalid settings.amelia.yaml in {resolved_path}: {e}"
                ) from e
            if settings is None:
                raise ValueError(
                    f"No settings.amelia.yaml found in {resolved_path}. "
                    "Each worktree must have its own settings file."
                )

            # Load profile
            profile_name = profile or settings.active_profile
            if profile_name not in settings.profiles:
                raise ValueError(f"Profile '{profile_name}' not found in settings")
            loaded_profile = settings.profiles[profile_name]
            # ALWAYS set working_dir to resolved_path for agent execution
            loaded_profile = loaded_profile.model_copy(update={"working_dir": resolved_path})

            # Create dummy issue for review context
            dummy_issue = Issue(
                id="LOCAL-REVIEW",
                title="Local Code Review",
                description="Review local uncommitted changes."
            )

            # Get current HEAD for tracking (even though diff is provided)
            base_commit = await get_git_head(resolved_path)

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
                worktree_path=resolved_path,
                workflow_type="review",
                execution_state=execution_state,
                workflow_status="pending",
                started_at=datetime.now(UTC),
            )

            await self._repository.create(state)

            # Start with review graph instead of full graph
            task = asyncio.create_task(self._run_review_workflow(workflow_id, state))
            self._active_tasks[resolved_path] = (workflow_id, task)

        # Same cleanup callback as start_workflow
        def cleanup_task(_: asyncio.Task[None]) -> None:
            """Clean up resources when workflow task completes.

            Args:
                _: The completed asyncio Task (unused).
            """
            self._active_tasks.pop(resolved_path, None)
            self._sequence_counters.pop(workflow_id, None)
            self._sequence_locks.pop(workflow_id, None)
            self._approval_events.pop(workflow_id, None)
            logger.debug(
                "Workflow task completed",
                workflow_id=workflow_id,
                worktree_path=resolved_path,
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

        # Cancel any active planning tasks
        for _workflow_id, task in list(self._planning_tasks.items()):
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

            # Pass event_bus via config
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "event_bus": self._event_bus,
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

                # BUG FIX (#199): Check if checkpoint exists before starting.
                # If we have an existing checkpoint, pass None to resume from it.
                # If no checkpoint, pass initial_state to start fresh.
                # This prevents the infinite loop bug where retries would restart
                # the workflow from review_iteration=0 instead of resuming.
                checkpoint_state = await graph.aget_state(config)
                if checkpoint_state is not None and checkpoint_state.values:
                    # Checkpoint exists - resume from it
                    logger.debug(
                        "Resuming workflow from existing checkpoint",
                        workflow_id=workflow_id,
                        checkpoint_keys=list(checkpoint_state.values.keys())[:5],
                    )
                    input_state = None
                else:
                    # No checkpoint - start fresh with initial state
                    # Convert Pydantic model to JSON-serializable dict for checkpointing.
                    # LangGraph's AsyncSqliteSaver uses json.dumps() internally,
                    # which fails on Pydantic BaseModel objects.
                    input_state = state.execution_state.model_dump(mode="json")
                    logger.debug(
                        "Starting workflow fresh (no checkpoint)",
                        workflow_id=workflow_id,
                    )

                async for chunk in graph.astream(
                    input_state,
                    config=config,
                    stream_mode=["updates", "tasks"],
                ):
                    # Combined mode returns (mode, data) tuples
                    # Cast for type checker - astream with list mode returns tuples
                    chunk_tuple = cast(tuple[str, Any], chunk)
                    if self._is_interrupt_chunk(chunk_tuple):
                        was_interrupted = True
                        mode, data = chunk_tuple
                        interrupt_data = data.get("__interrupt__") if isinstance(data, dict) else None
                        logger.info(
                            "Workflow paused for human approval",
                            workflow_id=workflow_id,
                            interrupt_data=interrupt_data,
                        )
                        # Sync plan from LangGraph checkpoint to ServerExecutionState
                        # so it's available via REST API while blocked
                        await self._sync_plan_from_checkpoint(workflow_id, graph, config)
                        await self._emit(
                            workflow_id,
                            EventType.APPROVAL_REQUIRED,
                            "Plan ready for review - awaiting human approval",
                            agent="human_approval",
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
                    # Handle combined mode chunk
                    await self._handle_combined_stream_chunk(workflow_id, chunk_tuple)

                if not was_interrupted:
                    # Workflow completed without interruption (no human approval needed).
                    # Note: A separate COMPLETED emission exists in approve_workflow() for
                    # workflows that resume after human approval. These are mutually exclusive
                    # code paths - only one COMPLETED event is ever emitted per workflow.
                    # Fetch fresh state from DB to get accurate current_stage
                    # (the local state variable is stale - _handle_stream_chunk updates DB)
                    fresh_state = await self._repository.get(workflow_id)
                    final_stage = fresh_state.current_stage if fresh_state else None
                    await self._emit(
                        workflow_id,
                        EventType.WORKFLOW_COMPLETED,
                        "Workflow completed successfully",
                        data={"final_stage": final_stage},
                    )
                    await emit_workflow_event(
                        ExtWorkflowEventType.COMPLETED,
                        workflow_id=workflow_id,
                        stage=final_stage,
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
                    "Transient error, retrying",
                    workflow_id=workflow_id,
                    attempt=attempt,
                    max_retries=retry_config.max_retries,
                    delay=delay,
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

            # Pass event_bus via config
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "event_bus": self._event_bus,
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
                    stream_mode=["updates", "tasks"],
                ):
                    # Combined mode returns (mode, data) tuples
                    # Cast for type checker - astream with list mode returns tuples
                    chunk_tuple = cast(tuple[str, Any], chunk)
                    # No interrupt handling - review graph runs autonomously
                    # But we still need to check for unexpected interrupts
                    if self._is_interrupt_chunk(chunk_tuple):
                        mode, data = chunk_tuple
                        logger.warning(
                            "Unexpected interrupt in review workflow",
                            workflow_id=workflow_id,
                        )
                        continue
                    # Emit stage events for each node
                    await self._handle_combined_stream_chunk(workflow_id, chunk_tuple)

                # Fetch fresh state from DB to get accurate current_stage
                # (the local state variable is stale - _handle_stream_chunk updates DB)
                fresh_state = await self._repository.get(workflow_id)
                final_stage = fresh_state.current_stage if fresh_state else None
                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_COMPLETED,
                    "Review workflow completed",
                    data={"final_stage": final_stage},
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
                agent="human_approval",
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

            # Pass event_bus via config
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "event_bus": self._event_bus,
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
                async for chunk in graph.astream(
                    None,  # Resume from checkpoint, no new input needed
                    config=config,
                    stream_mode=["updates", "tasks"],
                ):
                    # Combined mode returns (mode, data) tuples
                    # Cast for type checker - astream with list mode returns tuples
                    chunk_tuple = cast(tuple[str, Any], chunk)
                    # In agentic mode, no interrupts expected after initial approval
                    if self._is_interrupt_chunk(chunk_tuple):
                        _, data = chunk_tuple
                        state = await graph.aget_state(config)
                        next_nodes = state.next if state else []
                        logger.warning(
                            "Unexpected interrupt after approval",
                            workflow_id=workflow_id,
                            next_nodes=next_nodes,
                        )
                        continue
                    await self._handle_combined_stream_chunk(workflow_id, chunk_tuple)

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
                    agent=node_name.removesuffix("_node"),
                    data={"stage": node_name},
                )

        elif event_type == "on_chain_end":
            if node_name in STAGE_NODES:
                await self._emit(
                    workflow_id,
                    EventType.STAGE_COMPLETED,
                    f"Completed {node_name}",
                    agent=node_name.removesuffix("_node"),
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
        """Handle an updates chunk from astream(stream_mode=['updates', 'tasks']).

        With combined stream mode, updates chunks map node names to their
        state updates. We emit STAGE_COMPLETED after each node that's in
        STAGE_NODES.

        Note: STAGE_STARTED events are emitted by _handle_tasks_event when
        task events arrive from the tasks stream mode.

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

                # Emit agent-specific messages based on node
                await self._emit_agent_messages(workflow_id, node_name, output)

                # Emit STAGE_COMPLETED for the current node
                await self._emit(
                    workflow_id,
                    EventType.STAGE_COMPLETED,
                    f"Completed {node_name}",
                    agent=node_name.removesuffix("_node"),
                    data={"stage": node_name, "output": output},
                )

    async def _handle_tasks_event(
        self,
        workflow_id: str,
        task_data: dict[str, Any],
    ) -> None:
        """Handle a task event from stream_mode='tasks'.

        LangGraph emits two types of task events:
        - Task START: {id, name, input, triggers} - when node begins
        - Task RESULT: {id, name, error, result, interrupts} - when node completes

        We only process START events for STAGE_STARTED. Result events are
        ignored since STAGE_COMPLETED is handled via "updates" mode.

        Args:
            workflow_id: The workflow this task belongs to.
            task_data: Task event data from LangGraph.
        """
        # Ignore task result events - only process task start events
        if "input" not in task_data:
            return

        node_name = task_data.get("name", "")
        if node_name in STAGE_NODES:
            await self._emit(
                workflow_id,
                EventType.STAGE_STARTED,
                f"Starting {node_name}",
                agent=node_name.removesuffix("_node"),
                data={"stage": node_name},
            )

    async def _handle_combined_stream_chunk(
        self,
        workflow_id: str,
        chunk: tuple[str, Any],
    ) -> None:
        """Handle a chunk from stream_mode=['updates', 'tasks'].

        Combined stream mode emits tuples of (mode, data). We route each
        to the appropriate handler.

        Args:
            workflow_id: The workflow this chunk belongs to.
            chunk: Tuple of (mode_name, data).
        """
        mode, data = chunk
        if mode == "tasks":
            await self._handle_tasks_event(workflow_id, data)
        elif mode == "updates":
            # Interrupts handled by caller via _is_interrupt_chunk check
            if "__interrupt__" in data:
                return
            await self._handle_stream_chunk(workflow_id, data)

    def _is_interrupt_chunk(self, chunk: tuple[str, Any] | dict[str, Any]) -> bool:
        """Check if a stream chunk represents an interrupt.

        Works with both combined mode (tuple) and single mode (dict).

        Args:
            chunk: Stream chunk from astream().

        Returns:
            True if this chunk contains an interrupt signal.
        """
        if isinstance(chunk, tuple):
            mode, data = chunk
            if mode == "updates" and isinstance(data, dict):
                return "__interrupt__" in data
            return False
        # Single mode (dict)
        return "__interrupt__" in chunk

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
        elif node_name == "plan_validator_node":
            await self._emit_validator_messages(workflow_id, output)
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

    async def _emit_validator_messages(
        self,
        workflow_id: str,
        output: dict[str, Any],
    ) -> None:
        """Emit messages for plan validator node output.

        Args:
            workflow_id: The workflow ID.
            output: State updates from the validator node.
        """
        goal = output.get("goal")
        key_files = output.get("key_files", [])

        if goal:
            await self._emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                f"Plan validated: {goal}",
                agent="plan_validator",
                data={"goal": goal, "key_files_count": len(key_files)},
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
        issue_count = len(last_review.comments) if last_review.comments else 0

        await self._emit(
            workflow_id,
            EventType.AGENT_MESSAGE,
            f"Review {'approved' if approved else 'requested changes'} "
            f"({severity} severity, {issue_count} issues)",
            agent="reviewer",
            data={
                "approved": approved,
                "severity": severity,
                "issue_count": issue_count,
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
            raw_architect_output = checkpoint_state.values.get("raw_architect_output")

            # Log checkpoint values for debugging
            logger.info(
                "Syncing plan from checkpoint",
                workflow_id=workflow_id,
                has_goal=goal is not None,
                goal_preview=goal[:100] if goal else None,
                has_plan_markdown=plan_markdown is not None,
                plan_markdown_length=len(plan_markdown) if plan_markdown else 0,
                has_raw_output=raw_architect_output is not None,
            )

            if goal is None and plan_markdown is None:
                logger.warning(
                    "No goal or plan_markdown in checkpoint - architect may not have completed",
                    workflow_id=workflow_id,
                    checkpoint_keys=list(checkpoint_state.values.keys()) if checkpoint_state.values else [],
                )
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

    def _create_architect_for_planning(
        self,
        profile: Profile,
        prompts: dict[str, str] | None = None,
    ) -> "Architect":
        """Create an Architect instance for plan generation.

        Args:
            profile: Profile with driver configuration.
            prompts: Optional custom prompts for the architect.

        Returns:
            Configured Architect instance.
        """
        from amelia.agents.architect import Architect  # noqa: PLC0415
        from amelia.drivers.factory import get_driver  # noqa: PLC0415

        driver = get_driver(profile.driver, model=profile.model)
        return Architect(driver=driver, event_bus=self._event_bus, prompts=prompts)

    async def _run_planning_task(
        self,
        workflow_id: str,
        state: ServerExecutionState,
        execution_state: ExecutionState,
        profile: Profile,
    ) -> None:
        """Background task to run Architect and generate plan.

        Updates the workflow with the generated plan or marks it as failed
        if planning fails.

        Args:
            workflow_id: The workflow ID being planned.
            state: The server execution state to update.
            execution_state: The execution state for the architect.
            profile: The profile with driver configuration.
        """
        # Resolve prompts for architect
        prompts = await self._resolve_prompts(workflow_id)

        try:
            architect = self._create_architect_for_planning(profile, prompts)

            # Run architect and collect the final state
            final_state: ExecutionState | None = None
            async for updated_state, event in architect.plan(
                state=execution_state,
                profile=profile,
                workflow_id=workflow_id,
            ):
                final_state = updated_state
                # Emit events from architect as they come
                if event:
                    self._event_bus.emit(event)

            if final_state is not None:
                # Re-fetch the latest state to avoid clobbering concurrent updates
                # (e.g., if start_pending_workflow set started_at)
                fresh = await self._repository.get(workflow_id)
                if fresh is None:
                    logger.warning(
                        "Workflow deleted during planning",
                        workflow_id=workflow_id,
                    )
                    return

                # Only update if workflow is still pending - avoid overwriting
                # status/started_at if the workflow was started concurrently
                if fresh.workflow_status != "pending":
                    logger.info(
                        "Planning finished but workflow is no longer pending; skipping plan write",
                        workflow_id=workflow_id,
                        workflow_status=fresh.workflow_status,
                    )
                    return

                # Update state with plan on the fresh snapshot
                fresh.execution_state = final_state
                fresh.planned_at = datetime.now(UTC)
                await self._repository.update(fresh)

                await self._emit(
                    workflow_id,
                    EventType.STAGE_COMPLETED,
                    "Plan generated, workflow queued for execution",
                    agent="architect",
                    data={
                        "plan_ready": True,
                        "goal": final_state.goal,
                    },
                )

                logger.info(
                    "Workflow queued with plan",
                    workflow_id=workflow_id,
                    issue_id=fresh.issue_id,
                    goal=final_state.goal[:100] if final_state.goal else None,
                )
            else:
                # Architect didn't yield any state (shouldn't happen)
                logger.warning(
                    "Architect completed without yielding state",
                    workflow_id=workflow_id,
                )

        except asyncio.CancelledError:
            # Don't treat cancellation (e.g., during shutdown) as a failure
            logger.info("Planning task cancelled", workflow_id=workflow_id)
            raise
        except Exception as e:
            # Mark workflow as failed using fresh state
            try:
                fresh = await self._repository.get(workflow_id)
                if fresh is not None and fresh.workflow_status == "pending":
                    fresh.workflow_status = "failed"
                    fresh.failure_reason = f"Planning failed: {e}"
                    await self._repository.update(fresh)
            except Exception as update_err:
                logger.error(
                    "Failed to mark workflow as failed",
                    workflow_id=workflow_id,
                    error=str(update_err),
                )

            await self._emit(
                workflow_id,
                EventType.WORKFLOW_FAILED,
                f"Planning failed: {e}",
                data={"error": str(e)},
            )

            logger.error(
                "Planning task failed",
                workflow_id=workflow_id,
                error=str(e),
            )

    async def queue_and_plan_workflow(
        self,
        request: CreateWorkflowRequest,
    ) -> str:
        """Queue a workflow and run Architect to generate plan.

        Creates workflow, runs Architect to generate plan, stores plan,
        then leaves workflow in pending state for manual start.

        Args:
            request: Workflow creation request with start=False, plan_now=True.

        Returns:
            The workflow ID.

        Raises:
            InvalidWorktreeError: If worktree doesn't exist or isn't a git repo.
            ValueError: If settings are invalid or profile not found.
        """
        # Validate and resolve worktree path securely
        worktree = self._validate_worktree_path(request.worktree_path)
        resolved_path = str(worktree)

        # Prepare common workflow state (settings, profile, issue, execution_state)
        resolved_path, profile, execution_state = await self._prepare_workflow_state(
            worktree_path=resolved_path,
            issue_id=request.issue_id,
            profile_name=request.profile,
            task_title=request.task_title,
            task_description=request.task_description,
        )

        # Generate workflow ID
        workflow_id = str(uuid4())

        # Create ServerExecutionState in pending status (not started)
        state = ServerExecutionState(
            id=workflow_id,
            issue_id=request.issue_id,
            worktree_path=resolved_path,
            execution_state=execution_state,
            workflow_status="pending",
            # Note: started_at is None - workflow hasn't started yet
        )

        # Save initial state
        await self._repository.create(state)

        # Emit workflow created event
        await self._emit(
            workflow_id,
            EventType.WORKFLOW_CREATED,
            f"Workflow queued for {request.issue_id}, planning...",
            data={"issue_id": request.issue_id, "queued": True, "planning": True},
        )

        logger.info(
            "Workflow queued, spawning planning task",
            workflow_id=workflow_id,
            issue_id=request.issue_id,
            worktree_path=resolved_path,
        )

        # Spawn planning task in background (non-blocking)
        task = asyncio.create_task(
            self._run_planning_task(workflow_id, state, execution_state, profile)
        )
        self._planning_tasks[workflow_id] = task

        # Cleanup on completion
        def cleanup_planning(_: asyncio.Task[None]) -> None:
            self._planning_tasks.pop(workflow_id, None)

        task.add_done_callback(cleanup_planning)

        return workflow_id

    async def start_pending_workflow(self, workflow_id: str) -> None:
        """Start a pending workflow.

        Transitions a workflow from pending to in_progress state and
        spawns an execution task. Enforces single workflow per worktree
        and global concurrency limits.

        Args:
            workflow_id: The workflow ID to start.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateError: If workflow is not in pending state.
            WorkflowConflictError: If worktree already has an active workflow.
            ConcurrencyLimitError: If at max concurrent workflows.
        """
        async with self._start_lock:
            # Get workflow from repository
            workflow = await self._repository.get(workflow_id)
            if not workflow:
                raise WorkflowNotFoundError(workflow_id)

            # Validate workflow is in pending state
            if workflow.workflow_status != "pending":
                raise InvalidStateError(
                    f"Cannot start workflow in '{workflow.workflow_status}' state",
                    workflow_id=workflow_id,
                    current_status=workflow.workflow_status,
                )

            # Check for worktree conflict - another active workflow on same worktree
            active_on_worktree = await self._repository.get_by_worktree(
                workflow.worktree_path
            )
            if active_on_worktree and active_on_worktree.id != workflow_id:
                raise WorkflowConflictError(
                    workflow.worktree_path, active_on_worktree.id
                )

            # Also check in-memory tasks for worktree conflict
            if workflow.worktree_path in self._active_tasks:
                existing_id, _ = self._active_tasks[workflow.worktree_path]
                raise WorkflowConflictError(workflow.worktree_path, existing_id)

            # Check concurrency limit
            current_count = len(self._active_tasks)
            if current_count >= self._max_concurrent:
                raise ConcurrencyLimitError(self._max_concurrent, current_count)

            # Set started_at timestamp (status transition happens in _run_workflow)
            # NOTE: We don't set workflow_status here - _run_workflow handles
            # the pending -> in_progress transition, consistent with start_workflow
            workflow.started_at = datetime.now(UTC)
            await self._repository.update(workflow)

            logger.info(
                "Starting pending workflow",
                workflow_id=workflow_id,
                issue_id=workflow.issue_id,
                worktree_path=workflow.worktree_path,
            )

            # Spawn execution task
            task = asyncio.create_task(
                self._run_workflow_with_retry(workflow_id, workflow)
            )
            self._active_tasks[workflow.worktree_path] = (workflow_id, task)

        # Remove from active tasks on completion (same pattern as start_workflow)
        def cleanup_task(_: asyncio.Task[None]) -> None:
            """Clean up resources when workflow task completes.

            Args:
                _: The completed asyncio Task (unused).
            """
            self._active_tasks.pop(workflow.worktree_path, None)
            self._sequence_counters.pop(workflow_id, None)
            self._sequence_locks.pop(workflow_id, None)
            self._approval_events.pop(workflow_id, None)
            logger.debug(
                "Workflow task completed",
                workflow_id=workflow_id,
                worktree_path=workflow.worktree_path,
            )

        task.add_done_callback(cleanup_task)

    async def start_batch_workflows(
        self,
        request: BatchStartRequest,
    ) -> BatchStartResponse:
        """Start multiple pending workflows.

        Args:
            request: Batch start request with optional filters:
                - workflow_ids: Specific IDs to start (None = all pending)
                - worktree_path: Filter by worktree path

        Returns:
            BatchStartResponse with:
                - started: List of workflow IDs successfully started
                - errors: Map of workflow_id to error message for failures
        """
        started: list[str] = []
        errors: dict[str, str] = {}

        # Determine which workflows to start
        if request.workflow_ids:
            # Start specific workflow IDs
            workflow_ids = request.workflow_ids
        else:
            # Get all pending workflows
            pending_workflows = await self._repository.find_by_status(["pending"])

            # Filter by worktree_path if specified
            if request.worktree_path:
                pending_workflows = [
                    w for w in pending_workflows
                    if w.worktree_path == request.worktree_path
                ]

            workflow_ids = [w.id for w in pending_workflows]

        # Attempt to start each workflow
        for workflow_id in workflow_ids:
            try:
                await self.start_pending_workflow(workflow_id)
                started.append(workflow_id)
            except asyncio.CancelledError:
                # Don't swallow cancellation (e.g., during shutdown)
                raise
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
