"""Orchestrator service for managing concurrent workflow execution."""

import asyncio
import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from httpx import TimeoutException
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from amelia.core.constants import ToolName, resolve_plan_path
from amelia.core.types import (
    Design,
    Issue,
    Profile,
)
from amelia.ext import WorkflowEventType as ExtWorkflowEventType
from amelia.ext.exceptions import PolicyDeniedError
from amelia.ext.hooks import (
    check_policy_workflow_start,
    emit_workflow_event,
    flush_exporters,
)
from amelia.pipelines.implementation import create_implementation_graph
from amelia.pipelines.implementation.external_plan import import_external_plan
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.implementation.utils import extract_task_title
from amelia.pipelines.review import create_review_graph
from amelia.server.database import ProfileRepository
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
from amelia.server.models.state import WorkflowStatus, WorkflowType
from amelia.trackers.factory import create_tracker


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
        profile_repo: ProfileRepository | None = None,
        max_concurrent: int = 5,
        checkpoint_path: str = "~/.amelia/checkpoints.db",
    ) -> None:
        """Initialize orchestrator service.

        Args:
            event_bus: Event bus for broadcasting workflow events.
            repository: Repository for workflow persistence.
            profile_repo: Repository for profile lookup. Required for workflow execution.
            max_concurrent: Maximum number of concurrent workflows (default: 5).
            checkpoint_path: Path to checkpoint database file.
        """
        self._event_bus = event_bus
        self._repository = repository
        self._profile_repo = profile_repo
        self._max_concurrent = max_concurrent
        # Expand ~ and resolve path, ensure parent directory exists
        expanded_path = Path(checkpoint_path).expanduser().resolve()
        expanded_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpoint_path = str(expanded_path)
        self._active_tasks: dict[str, tuple[str, asyncio.Task[None]]] = {}  # worktree_path -> (workflow_id, task)
        self._planning_tasks: dict[str, asyncio.Task[None]] = {}  # workflow_id -> planning task
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
        return create_implementation_graph(
            checkpointer=checkpointer,
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
        """Look up profile by ID from database.

        Profiles are loaded from the database via ProfileRepository.
        There is no fallback - a valid profile must exist.

        Args:
            workflow_id: Workflow ID for logging and status updates.
            profile_id: Profile ID to look up in database.
            worktree_path: Worktree path for agent execution (overrides profile's working_dir).

        Returns:
            Profile if found, None if not found (after setting workflow to failed).
        """
        if self._profile_repo is None:
            logger.error(
                "ProfileRepository not configured",
                workflow_id=workflow_id,
            )
            await self._repository.set_status(
                workflow_id, WorkflowStatus.FAILED, failure_reason="ProfileRepository not configured"
            )
            return None

        record = await self._profile_repo.get_profile(profile_id)
        if record is None:
            logger.error("Profile not found", workflow_id=workflow_id, profile_id=profile_id)
            await self._repository.set_status(
                workflow_id, WorkflowStatus.FAILED, failure_reason=f"Profile '{profile_id}' not found"
            )
            return None

        return self._update_profile_working_dir(record, worktree_path)

    def _update_profile_working_dir(self, profile: Profile, worktree_path: str) -> Profile:
        """Update profile's working_dir for workflow execution.

        Args:
            profile: Profile from database.
            worktree_path: Worktree path to use as working_dir (overrides profile).

        Returns:
            Profile instance with updated working_dir.
        """
        return profile.model_copy(update={"working_dir": worktree_path})

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
        workflow_id: str,
        worktree_path: str,
        issue_id: str,
        profile_name: str | None = None,
        task_title: str | None = None,
        task_description: str | None = None,
        artifact_path: str | None = None,
    ) -> tuple[str, Profile, ImplementationState]:
        """Prepare common state needed to create or start a workflow.

        Centralizes the common initialization logic for profile resolution,
        issue fetching, and ImplementationState creation shared across
        queue_workflow, start_workflow, and queue_and_plan_workflow.

        Args:
            workflow_id: The workflow ID (UUID).
            worktree_path: Resolved worktree path (already validated).
            issue_id: The issue ID to work on.
            profile_name: Optional profile name (defaults to active profile).
            task_title: Optional task title for noop tracker.
            task_description: Optional task description (defaults to task_title).
            artifact_path: Optional path to design artifact file from brainstorming.
                Can be worktree-relative (e.g., docs/plans/design.md or /docs/plans/design.md)
                or an absolute path within the worktree.

        Returns:
            Tuple of (resolved_path, profile, execution_state).

        Raises:
            ValueError: If profile not found, task_title used with non-none
                tracker, or artifact_path escapes worktree.
            FileNotFoundError: If artifact_path is provided but the file doesn't exist.
        """
        # Get profile from database
        if self._profile_repo is None:
            raise ValueError("ProfileRepository not configured")

        if profile_name:
            record = await self._profile_repo.get_profile(profile_name)
            if record is None:
                raise ValueError(f"Profile '{profile_name}' not found")
        else:
            record = await self._profile_repo.get_active_profile()
            if record is None:
                raise ValueError(
                    "No active profile set. Use --profile to specify one or set an active profile."
                )

        # Convert to Profile with worktree_path as working_dir
        profile = self._update_profile_working_dir(record, worktree_path)

        # Fetch issue from tracker (or construct from task_title)
        if task_title is not None:
            # Validate that tracker is noop when using task_title
            if profile.tracker != "noop":
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

        # Load design from artifact path if provided
        design = None
        if artifact_path:
            # Resolve worktree path to canonical form for validation
            worktree_resolved = Path(worktree_path).resolve()
            artifact_as_path = Path(artifact_path)

            # Handle both absolute and relative paths
            if artifact_as_path.is_absolute():
                resolved_artifact = artifact_as_path.resolve()
                # Check if absolute path is within worktree (e.g., from LLM write_design_doc)
                try:
                    resolved_artifact.relative_to(worktree_resolved)
                    # Path is within worktree, use it directly
                    full_artifact_path = resolved_artifact
                except ValueError:
                    # Absolute path outside worktree - treat as worktree-relative
                    # (strip leading slash and resolve against worktree)
                    relative_artifact = artifact_path.lstrip("/")
                    full_artifact_path = (worktree_resolved / relative_artifact).resolve()
            else:
                # Relative path: resolve against worktree
                full_artifact_path = (worktree_resolved / artifact_path).resolve()

            # Validate the resolved path stays within the worktree
            # (prevents traversal via .. sequences or symlinks)
            try:
                full_artifact_path.relative_to(worktree_resolved)
            except ValueError:
                raise ValueError(
                    f"artifact_path '{artifact_path}' resolves outside worktree directory"
                ) from None

            if not full_artifact_path.exists():
                raise FileNotFoundError(f"Artifact file not found: {full_artifact_path}")

            design = Design.from_file(full_artifact_path)

        # Create ImplementationState with all required fields
        execution_state = ImplementationState(
            workflow_id=workflow_id,
            profile_id=profile.name,
            created_at=datetime.now(UTC),
            status="pending",
            issue=issue,
            base_commit=base_commit,
            design=design,
        )

        return worktree_path, profile, execution_state

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

            # Prepare issue and execution state using the helper
            # This also loads the profile from the database
            _, loaded_profile, execution_state = await self._prepare_workflow_state(
                workflow_id=workflow_id,
                worktree_path=resolved_path,
                issue_id=issue_id,
                profile_name=profile,
                task_title=task_title,
                task_description=task_description,
            )

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

            state = ServerExecutionState(
                id=workflow_id,
                issue_id=issue_id,
                worktree_path=resolved_path,
                execution_state=execution_state,
                workflow_status=WorkflowStatus.PENDING,
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

        # Generate workflow ID before preparing state (required by ImplementationState)
        workflow_id = str(uuid4())

        # Prepare common workflow state (settings, profile, issue, execution_state)
        resolved_path, profile, execution_state = await self._prepare_workflow_state(
            workflow_id=workflow_id,
            worktree_path=resolved_path,
            issue_id=request.issue_id,
            profile_name=request.profile,
            task_title=request.task_title,
            task_description=request.task_description,
            artifact_path=request.artifact_path,
        )

        # Handle external plan if provided
        if request.plan_file is not None or request.plan_content is not None:
            # Resolve target plan path
            plan_rel_path = resolve_plan_path(profile.plan_path_pattern, request.issue_id)
            working_dir = Path(profile.working_dir) if profile.working_dir else Path(".")
            target_path = working_dir / plan_rel_path

            # Import and validate external plan
            plan_result = await import_external_plan(
                plan_file=request.plan_file,
                plan_content=request.plan_content,
                target_path=target_path,
                profile=profile,
                workflow_id=workflow_id,
            )

            # Update execution state with plan data and external flag
            execution_state = execution_state.model_copy(
                update={
                    "external_plan": True,
                    "goal": plan_result.goal,
                    "plan_markdown": plan_result.plan_markdown,
                    "plan_path": plan_result.plan_path,
                    "key_files": plan_result.key_files,
                    "total_tasks": plan_result.total_tasks,
                }
            )

        # Create ServerExecutionState in pending status (not started)
        state = ServerExecutionState(
            id=workflow_id,
            issue_id=request.issue_id,
            worktree_path=resolved_path,
            execution_state=execution_state,
            workflow_status=WorkflowStatus.PENDING,
            # No started_at - workflow hasn't started
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

            # Get profile from database
            if self._profile_repo is None:
                raise ValueError("ProfileRepository not configured")

            if profile:
                record = await self._profile_repo.get_profile(profile)
                if record is None:
                    raise ValueError(f"Profile '{profile}' not found")
            else:
                record = await self._profile_repo.get_active_profile()
                if record is None:
                    raise ValueError(
                        "No active profile set. Use --profile to specify one or set an active profile."
                    )

            # Convert to Profile with resolved_path as working_dir
            loaded_profile = self._update_profile_working_dir(record, resolved_path)

            # Create dummy issue for review context
            dummy_issue = Issue(
                id="LOCAL-REVIEW",
                title="Local Code Review",
                description="Review local uncommitted changes."
            )

            # Get current HEAD for tracking (even though diff is provided)
            base_commit = await get_git_head(resolved_path)

            # Initialize ImplementationState with diff content
            execution_state = ImplementationState(
                workflow_id=workflow_id,
                profile_id=loaded_profile.name,
                created_at=datetime.now(UTC),
                status="pending",
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
                workflow_type=WorkflowType.REVIEW,
                execution_state=execution_state,
                workflow_status=WorkflowStatus.PENDING,
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
        cancellable_states = {WorkflowStatus.PENDING, WorkflowStatus.IN_PROGRESS, WorkflowStatus.BLOCKED}
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

        if workflow_id in self._planning_tasks:
            self._planning_tasks[workflow_id].cancel()

        # Persist the cancelled status to database
        await self._repository.set_status(workflow_id, WorkflowStatus.CANCELLED)

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

    async def resume_workflow(self, workflow_id: str) -> ServerExecutionState:
        """Resume a failed workflow from its last checkpoint.

        Validates the workflow is in FAILED status, has a valid checkpoint,
        and the worktree is not occupied. Then clears error state, transitions
        to IN_PROGRESS, and re-launches the workflow task.

        Args:
            workflow_id: The workflow to resume.

        Returns:
            The updated workflow state.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateError: If workflow is not FAILED, has no checkpoint,
                or its worktree is occupied.
        """
        workflow = await self._repository.get(workflow_id)
        if not workflow:
            raise WorkflowNotFoundError(workflow_id)

        if workflow.workflow_status != WorkflowStatus.FAILED:
            raise InvalidStateError(
                f"Cannot resume: workflow must be in 'failed' status, "
                f"got '{workflow.workflow_status}'",
                workflow_id=workflow_id,
                current_status=workflow.workflow_status,
            )

        # Validate checkpoint exists (read-only, safe outside lock)
        async with AsyncSqliteSaver.from_conn_string(
            str(self._checkpoint_path)
        ) as checkpointer:
            graph = self._create_server_graph(checkpointer)
            config: RunnableConfig = {
                "configurable": {"thread_id": workflow_id},
            }
            checkpoint_state = await graph.aget_state(config)
            if checkpoint_state is None or not checkpoint_state.values:
                raise InvalidStateError(
                    "Cannot resume: no checkpoint found for workflow",
                    workflow_id=workflow_id,
                    current_status=workflow.workflow_status,
                )

        async with self._start_lock:
            # Check worktree is not occupied (under lock to prevent TOCTOU race)
            if workflow.worktree_path in self._active_tasks:
                existing_id, _ = self._active_tasks[workflow.worktree_path]
                raise InvalidStateError(
                    f"Cannot resume: worktree is occupied by workflow {existing_id}",
                    workflow_id=workflow_id,
                    current_status=workflow.workflow_status,
                )

            # Clear error state and transition to IN_PROGRESS
            workflow.failure_reason = None
            workflow.completed_at = None
            workflow.workflow_status = WorkflowStatus.IN_PROGRESS
            await self._repository.update(workflow)

            await self._emit(
                workflow_id,
                EventType.WORKFLOW_STARTED,
                "Workflow resumed from checkpoint",
                data={"resumed": True},
            )

            logger.info("Resuming workflow", workflow_id=workflow_id)

            # Launch workflow task (same as start_workflow)
            task = asyncio.create_task(
                self._run_workflow_with_retry(workflow_id, workflow)
            )
            self._active_tasks[workflow.worktree_path] = (workflow_id, task)

        def cleanup_task(_: asyncio.Task[None]) -> None:
            """Clean up resources when resumed workflow task completes."""
            self._active_tasks.pop(workflow.worktree_path, None)
            self._sequence_counters.pop(workflow_id, None)
            self._sequence_locks.pop(workflow_id, None)
            logger.debug(
                "Resumed workflow task completed",
                workflow_id=workflow_id,
                worktree_path=workflow.worktree_path,
            )

        task.add_done_callback(cleanup_task)

        return workflow

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
                workflow_id, WorkflowStatus.FAILED, failure_reason="Missing execution state"
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
            # Recursion limit: 4 base steps + 3 per task + buffer
            # Default 100 handles up to ~30 tasks
            config: RunnableConfig = {
                "recursion_limit": 100,
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "event_bus": self._event_bus,
                    "profile": profile,
                    "repository": self._repository,
                    "prompts": prompts,
                },
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
                # Only set status to IN_PROGRESS if not already in that state.
                # This handles resumed workflows which are already IN_PROGRESS.
                workflow = await self._repository.get(workflow_id)
                if workflow and workflow.workflow_status != WorkflowStatus.IN_PROGRESS:
                    await self._repository.set_status(workflow_id, WorkflowStatus.IN_PROGRESS)

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
                        )
                        await self._repository.set_status(workflow_id, WorkflowStatus.BLOCKED)
                        # Emit PAUSED event for workflow being blocked
                        await emit_workflow_event(
                            ExtWorkflowEventType.PAUSED,
                            workflow_id=workflow_id,
                        )
                        break
                    # Handle combined mode chunk
                    await self._handle_combined_stream_chunk(workflow_id, chunk_tuple)

                if not was_interrupted:
                    # Workflow completed without interruption (no human approval needed).
                    # Note: A separate COMPLETED emission exists in approve_workflow() for
                    # workflows that resume after human approval. These are mutually exclusive
                    # code paths - only one COMPLETED event is ever emitted per workflow.

                    # Check for task failure before marking complete (multi-task mode)
                    await self._emit_task_failed_if_applicable(workflow_id)

                    await self._emit(
                        workflow_id,
                        EventType.WORKFLOW_COMPLETED,
                        "Workflow completed successfully",
                    )
                    await emit_workflow_event(
                        ExtWorkflowEventType.COMPLETED,
                        workflow_id=workflow_id,
                    )
                    await self._repository.set_status(workflow_id, WorkflowStatus.COMPLETED)

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
                workflow_id, WorkflowStatus.FAILED, failure_reason="Missing execution state"
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
                return  # Success

            except TRANSIENT_EXCEPTIONS as e:
                attempt += 1

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
                        WorkflowStatus.FAILED,
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
                    workflow_id, WorkflowStatus.FAILED, failure_reason=str(e)
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
                workflow_id, WorkflowStatus.FAILED, failure_reason="Missing execution state"
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
            # Use dedicated review graph for review workflows
            graph = create_review_graph(
                checkpointer=checkpointer,
            )

            # Pass event_bus via config
            # Step limit: 4 base + 3 per task + buffer (default 100 handles ~30 tasks)
            config: RunnableConfig = {
                "recursion_limit": 100,
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "event_bus": self._event_bus,
                    "profile": profile,
                    "repository": self._repository,
                    "prompts": prompts,
                },
            }

            await self._emit(
                workflow_id,
                EventType.WORKFLOW_STARTED,
                "Review workflow started",
                data={"issue_id": state.issue_id, "workflow_type": "review"},
            )

            try:
                await self._repository.set_status(workflow_id, WorkflowStatus.IN_PROGRESS)

                # Convert Pydantic model to JSON-serializable dict for checkpointing
                initial_state = state.execution_state.model_dump(mode="json")

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

                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_COMPLETED,
                    "Review workflow completed",
                )
                await self._repository.set_status(workflow_id, WorkflowStatus.COMPLETED)

            except Exception as e:
                logger.exception("Review workflow failed", workflow_id=workflow_id)
                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Review workflow failed: {e}",
                    data={"error": str(e)},
                )
                await self._repository.set_status(
                    workflow_id, WorkflowStatus.FAILED, failure_reason=str(e)
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

    async def _delete_checkpoint(self, workflow_id: str) -> None:
        """Delete LangGraph checkpoint data for a workflow.

        Removes all checkpoint records (checkpoints, writes, blobs) for
        the given thread ID. Used by replan to start fresh.

        Args:
            workflow_id: The workflow/thread ID whose checkpoint to delete.
        """
        async with AsyncSqliteSaver.from_conn_string(
            str(self._checkpoint_path)
        ) as saver:
            await saver.setup()
            await saver.adelete_thread(workflow_id)
            logger.info("Deleted checkpoint", workflow_id=workflow_id)

    async def approve_workflow(self, workflow_id: str) -> None:
        """Approve a blocked workflow and resume LangGraph execution.

        Args:
            workflow_id: The workflow to approve.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateError: If workflow is not in "blocked" state.
        """
        async with self._approval_lock:
            workflow = await self._repository.get(workflow_id)
            if not workflow:
                raise WorkflowNotFoundError(workflow_id)

            if workflow.workflow_status != WorkflowStatus.BLOCKED:
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
                "recursion_limit": 100,
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "event_bus": self._event_bus,
                    "profile": profile,
                    "repository": self._repository,
                    "prompts": prompts,
                },
            }

            # Update checkpoint state with approval decision
            await graph.aupdate_state(config, {"human_approved": True})

            # Update status to in_progress before resuming
            await self._repository.set_status(workflow_id, WorkflowStatus.IN_PROGRESS)

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

                # Check for task failure before marking complete (multi-task mode)
                await self._emit_task_failed_if_applicable(workflow_id)

                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_COMPLETED,
                    "Workflow completed successfully",
                )
                await emit_workflow_event(
                    ExtWorkflowEventType.COMPLETED,
                    workflow_id=workflow_id,
                )
                await self._repository.set_status(workflow_id, WorkflowStatus.COMPLETED)

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
                    workflow_id, WorkflowStatus.FAILED, failure_reason=str(e)
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
        if workflow.workflow_status != WorkflowStatus.BLOCKED:
            raise InvalidStateError(
                f"Cannot reject workflow in '{workflow.workflow_status}' state",
                workflow_id=workflow_id,
                current_status=workflow.workflow_status,
            )

        async with self._approval_lock:
            # Update workflow status to failed with feedback
            await self._repository.set_status(
                workflow_id, WorkflowStatus.FAILED, failure_reason=feedback
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
                "recursion_limit": 100,
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "profile": profile,
                    "repository": self._repository,
                },
            }

            await graph.aupdate_state(config, {"human_approved": False})

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

            # Emit TASK_COMPLETED when next_task_node completes
            if node_name == "next_task_node":
                # Get total_tasks from output (passed through by next_task_node)
                total_tasks = output.get("total_tasks")
                if total_tasks is not None:
                    # The output contains the NEW index, so completed task is index - 1
                    new_index = output.get("current_task_index", 0)
                    completed_index = new_index - 1 if new_index > 0 else 0

                    await self._emit(
                        workflow_id,
                        EventType.TASK_COMPLETED,
                        f"Completed Task {completed_index + 1}/{total_tasks}",
                        agent="system",
                        data={
                            "task_index": completed_index,
                            "total_tasks": total_tasks,
                        },
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

        # Emit TASK_STARTED for developer_node in task-based mode
        if node_name == "developer_node":
            input_state = task_data.get("input")
            # input_state is an ImplementationState Pydantic model from LangGraph.
            # Access attributes directly, not via .get() which doesn't exist on Pydantic models.
            if input_state is not None and getattr(input_state, "total_tasks", None) is not None:
                total_tasks = input_state.total_tasks
                task_index = input_state.current_task_index
                plan_markdown = input_state.plan_markdown or ""
                task_title = extract_task_title(plan_markdown, task_index) or "Unknown"

                await self._emit(
                    workflow_id,
                    EventType.TASK_STARTED,
                    f"Starting Task {task_index + 1}/{total_tasks}: {task_title}",
                    agent="developer",
                    data={
                        "task_index": task_index,
                        "total_tasks": total_tasks,
                        "task_title": task_title,
                    },
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

    async def _emit_task_failed_if_applicable(self, workflow_id: str) -> None:
        """Emit TASK_FAILED if workflow ended due to unapproved task.

        Called when workflow completes to check if the final task was not approved
        (indicating failure due to max iterations).

        Args:
            workflow_id: The workflow to check.
        """
        state = await self._repository.get(workflow_id)
        if state is None or state.execution_state is None:
            return

        exec_state = state.execution_state
        total_tasks = exec_state.total_tasks

        # Only emit in task mode
        if total_tasks is None:
            return

        # Check if last review was not approved
        last_review = exec_state.last_review
        if last_review is None:
            return

        if last_review.approved:
            return

        task_index = exec_state.current_task_index
        iterations = exec_state.task_review_iteration

        await self._emit(
            workflow_id,
            EventType.TASK_FAILED,
            f"Task {task_index + 1}/{total_tasks} failed after {iterations} review iterations",
            agent="system",
            data={
                "task_index": task_index,
                "total_tasks": total_tasks,
                "iterations": iterations,
            },
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
            tool_calls = checkpoint_state.values.get("tool_calls", [])
            tool_results = checkpoint_state.values.get("tool_results", [])

            # Log checkpoint values for debugging
            logger.info(
                "Syncing plan from checkpoint",
                workflow_id=workflow_id,
                has_goal=goal is not None,
                goal_preview=goal[:100] if goal else None,
                has_plan_markdown=plan_markdown is not None,
                plan_markdown_length=len(plan_markdown) if plan_markdown else 0,
                has_raw_output=raw_architect_output is not None,
                tool_calls_count=len(tool_calls),
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

            # Build update dict with goal, plan_markdown, and tool_calls
            update_dict: dict[str, Any] = {}
            if goal is not None:
                update_dict["goal"] = goal
            if plan_markdown is not None:
                update_dict["plan_markdown"] = plan_markdown
            if tool_calls:
                update_dict["tool_calls"] = tool_calls
            if tool_results:
                update_dict["tool_results"] = tool_results

            # Extract plan_path from Write tool calls
            for tc in tool_calls:
                tool_name = getattr(tc, "tool_name", None) or tc.get("tool_name")
                tool_input = getattr(tc, "tool_input", None) or tc.get("tool_input", {})
                if tool_name == ToolName.WRITE_FILE and "file_path" in tool_input:
                    update_dict["plan_path"] = Path(tool_input["file_path"])
                    logger.debug(
                        "Extracted plan_path from tool calls",
                        plan_path=str(update_dict["plan_path"]),
                    )
                    break

            if not update_dict:
                return

            # Update the execution_state with synced fields
            # ExecutionState is frozen, so we use model_copy to create an updated instance
            state.execution_state = state.execution_state.model_copy(update=update_dict)

            # Save back to repository
            await self._repository.update(state)
            logger.debug(
                "Synced plan to ServerExecutionState",
                workflow_id=workflow_id,
                tool_calls_count=len(tool_calls),
                has_plan_path="plan_path" in update_dict,
            )

        except Exception as e:
            # Log but don't fail the workflow - plan sync is best-effort
            logger.warning(
                "Failed to sync plan from checkpoint",
                workflow_id=workflow_id,
                error=str(e),
            )


    async def recover_interrupted_workflows(self) -> None:
        """Recover workflows that were running when server restarted.

        IN_PROGRESS workflows are marked FAILED (recoverable). BLOCKED workflows
        get their APPROVAL_REQUIRED event re-emitted so dashboard clients see them.
        """
        failed_count = 0
        blocked_count = 0

        # Handle IN_PROGRESS workflows — mark as FAILED
        in_progress = await self._repository.find_by_status([WorkflowStatus.IN_PROGRESS])
        for wf in in_progress:
            await self._repository.set_status(
                wf.id,
                WorkflowStatus.FAILED,
                failure_reason="Server restarted while workflow was running",
            )
            await self._emit(
                wf.id,
                EventType.WORKFLOW_FAILED,
                "Server restarted while workflow was running",
                data={"recoverable": True},
            )
            logger.info("Recovered interrupted workflow", workflow_id=wf.id)
            failed_count += 1

        # Handle BLOCKED workflows — re-emit approval events
        blocked = await self._repository.find_by_status([WorkflowStatus.BLOCKED])
        for wf in blocked:
            await self._emit(
                wf.id,
                EventType.APPROVAL_REQUIRED,
                "Plan ready for review - awaiting human approval (restored after restart)",
                agent="human_approval",
                data={"paused_at": "human_approval_node"},
            )
            logger.info("Restored blocked workflow approval", workflow_id=wf.id)
            blocked_count += 1

        logger.info(
            "Recovery complete",
            workflows_failed=failed_count,
            approvals_restored=blocked_count,
        )

    async def _run_planning_task(
        self,
        workflow_id: str,
        state: ServerExecutionState,
        execution_state: ImplementationState,
        profile: Profile,
    ) -> None:
        """Background task to run planning via LangGraph.

        Runs the orchestrator graph until it interrupts at human_approval_node,
        creating a checkpoint that can be resumed by approve_workflow().

        Note:
            This task re-fetches workflow state from the repository before
            any mutations, so the passed ``state`` and ``execution_state``
            are only used for initial graph input — not for later updates.

        Args:
            workflow_id: The workflow ID being planned.
            state: The server execution state to update.
            execution_state: The execution state for the architect.
            profile: The profile with driver configuration.
        """
        # Resolve prompts for architect
        prompts = await self._resolve_prompts(workflow_id)

        async with AsyncSqliteSaver.from_conn_string(
            str(self._checkpoint_path)
        ) as checkpointer:
            graph = self._create_server_graph(checkpointer)

            config: RunnableConfig = {
                "recursion_limit": 100,
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "event_bus": self._event_bus,
                    "profile": profile,
                    "repository": self._repository,
                    "prompts": prompts,
                },
            }

            try:
                # Convert Pydantic model to JSON-serializable dict for checkpointing
                input_state = execution_state.model_dump(mode="json")

                was_interrupted = False
                async for chunk in graph.astream(
                    input_state,
                    config=config,
                    stream_mode=["updates", "tasks"],
                ):
                    chunk_tuple = cast(tuple[str, Any], chunk)
                    if self._is_interrupt_chunk(chunk_tuple):
                        was_interrupted = True
                        mode, data = chunk_tuple
                        interrupt_data = (
                            data.get("__interrupt__") if isinstance(data, dict) else None
                        )
                        logger.info(
                            "Planning paused for human approval",
                            workflow_id=workflow_id,
                            interrupt_data=interrupt_data,
                        )
                        # Sync plan from LangGraph checkpoint to ServerExecutionState
                        await self._sync_plan_from_checkpoint(workflow_id, graph, config)

                        # Re-fetch to avoid clobbering concurrent updates
                        fresh = await self._repository.get(workflow_id)
                        if fresh is None:
                            logger.warning(
                                "Workflow deleted during planning",
                                workflow_id=workflow_id,
                            )
                            return

                        # Only update if still pending (planning in background)
                        if fresh.workflow_status != WorkflowStatus.PENDING:
                            logger.info(
                                "Planning finished but workflow status changed",
                                workflow_id=workflow_id,
                                workflow_status=fresh.workflow_status,
                            )
                            return

                        fresh.workflow_status = WorkflowStatus.BLOCKED
                        await self._repository.update(fresh)

                        await self._emit(
                            workflow_id,
                            EventType.APPROVAL_REQUIRED,
                            "Plan ready for review - awaiting human approval",
                            agent="human_approval",
                            data={"paused_at": "human_approval_node"},
                        )

                        logger.info(
                            "Workflow queued with plan",
                            workflow_id=workflow_id,
                            issue_id=fresh.issue_id,
                        )
                        break

                    # Handle combined mode chunk (updates, tasks)
                    await self._handle_combined_stream_chunk(workflow_id, chunk_tuple)

                if not was_interrupted:
                    # Graph completed without interrupting - unexpected for planning
                    logger.warning(
                        "Planning completed without interrupt at human_approval_node",
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
                    if fresh is not None and fresh.workflow_status == WorkflowStatus.PENDING:
                        fresh.workflow_status = WorkflowStatus.FAILED
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

        # Generate workflow ID before preparing state (required by ImplementationState)
        workflow_id = str(uuid4())

        # Prepare common workflow state (settings, profile, issue, execution_state)
        resolved_path, profile, execution_state = await self._prepare_workflow_state(
            workflow_id=workflow_id,
            worktree_path=resolved_path,
            issue_id=request.issue_id,
            profile_name=request.profile,
            task_title=request.task_title,
            task_description=request.task_description,
        )

        # Create ServerExecutionState in pending status (architect running)
        state = ServerExecutionState(
            id=workflow_id,
            issue_id=request.issue_id,
            worktree_path=resolved_path,
            execution_state=execution_state,
            workflow_status=WorkflowStatus.PENDING,
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
            if workflow.workflow_status != WorkflowStatus.PENDING:
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
            pending_workflows = await self._repository.find_by_status([WorkflowStatus.PENDING])

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

    async def set_workflow_plan(
        self,
        workflow_id: str,
        plan_file: str | None = None,
        plan_content: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Set or replace the plan for a queued workflow.

        This method allows setting an external plan on a workflow that is
        in pending status. The plan will be validated and stored
        in the standard plan location.

        Args:
            workflow_id: The workflow ID.
            plan_file: Path to plan file (relative to worktree or absolute).
            plan_content: Inline plan markdown content.
            force: If True, overwrite existing plan.

        Returns:
            Dict with goal, key_files, total_tasks.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateError: If workflow not in pending status.
            WorkflowConflictError: If plan exists and force=False, or architect running.
            FileNotFoundError: If plan_file doesn't exist.
        """
        # Load workflow
        workflow = await self._repository.get(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(workflow_id)

        # Check status - only allow setting plan on pending workflows
        valid_statuses = {WorkflowStatus.PENDING}
        if workflow.workflow_status not in valid_statuses:
            raise InvalidStateError(
                f"Workflow must be in pending status, "
                f"but is in {workflow.workflow_status}",
                workflow_id=workflow_id,
                current_status=str(workflow.workflow_status),
            )

        # Check for active planning task - don't interfere with architect
        if workflow_id in self._planning_tasks:
            raise WorkflowConflictError(
                f"Architect is currently running for workflow {workflow_id}"
            )

        # Prevent updates once execution has started
        if workflow.worktree_path in self._active_tasks:
            existing_id, _ = self._active_tasks[workflow.worktree_path]
            raise WorkflowConflictError(
                f"Workflow {existing_id} is already running for worktree {workflow.worktree_path}"
            )

        # Check existing plan - require force to overwrite
        execution_state = workflow.execution_state
        if execution_state is not None and execution_state.plan_markdown is not None and not force:
            raise WorkflowConflictError(
                "Plan already exists. Use force=true to overwrite."
            )

        # Ensure execution_state exists before importing plan
        if execution_state is None:
            raise InvalidStateError(
                "Cannot set plan: workflow has no execution state",
                workflow_id=workflow_id,
            )

        # Get profile for plan path resolution
        profile = await self._get_profile_or_fail(
            workflow_id,
            execution_state.profile_id,
            workflow.worktree_path,
        )
        if profile is None:
            raise ValueError("Profile not found for workflow")

        profile = self._update_profile_working_dir(profile, workflow.worktree_path)

        # Resolve target plan path
        plan_rel_path = resolve_plan_path(profile.plan_path_pattern, workflow.issue_id)
        working_dir = Path(profile.working_dir) if profile.working_dir else Path(".")
        target_path = working_dir / plan_rel_path

        # Import and validate external plan
        plan_result = await import_external_plan(
            plan_file=plan_file,
            plan_content=plan_content,
            target_path=target_path,
            profile=profile,
            workflow_id=workflow_id,
        )

        # Update execution state with plan data
        updated_execution_state = execution_state.model_copy(
            update={
                "external_plan": True,
                "goal": plan_result.goal,
                "plan_markdown": plan_result.plan_markdown,
                "plan_path": plan_result.plan_path,
                "key_files": plan_result.key_files,
                "total_tasks": plan_result.total_tasks,
            }
        )

        # Update workflow with plan data
        updated_workflow = workflow.model_copy(
            update={
                "execution_state": updated_execution_state,
            }
        )
        await self._repository.update(updated_workflow)

        # Emit plan set event
        await self._emit(
            workflow_id,
            EventType.AGENT_MESSAGE,
            f"External plan set: {plan_result.goal}",
            agent="system",
            data={
                "goal": plan_result.goal,
                "key_files": plan_result.key_files,
                "total_tasks": plan_result.total_tasks,
            },
        )

        logger.info(
            "External plan set",
            workflow_id=workflow_id,
            goal=plan_result.goal,
            total_tasks=plan_result.total_tasks,
        )

        return {
            "goal": plan_result.goal,
            "key_files": plan_result.key_files,
            "total_tasks": plan_result.total_tasks,
        }

    async def replan_workflow(self, workflow_id: str) -> None:
        """Regenerate the plan for a blocked workflow.

        Deletes the stale LangGraph checkpoint, clears plan-related fields,
        transitions the workflow back to PENDING, and spawns a fresh
        planning task using the same issue/profile.

        Args:
            workflow_id: The workflow to replan.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateError: If workflow is not in blocked status.
            WorkflowConflictError: If a planning task is already running.
            ValueError: If profile is not found.
        """
        async with self._approval_lock:
            workflow = await self._repository.get(workflow_id)
            if workflow is None:
                raise WorkflowNotFoundError(workflow_id)

            if workflow.workflow_status != WorkflowStatus.BLOCKED:
                raise InvalidStateError(
                    f"Workflow must be in blocked status to replan, but is in {workflow.workflow_status}",
                    workflow_id=workflow_id,
                    current_status=str(workflow.workflow_status),
                )

            # Defensive: reject if planning task is already running
            if workflow_id in self._planning_tasks:
                raise WorkflowConflictError(
                    f"Planning task already running for workflow {workflow_id}"
                )

            if workflow.execution_state is None:
                raise InvalidStateError(
                    "Cannot replan workflow without execution state",
                    workflow_id=workflow_id,
                    current_status=str(workflow.workflow_status),
                )

            # Resolve profile without side-effects: replan is a user-initiated
            # retry action, so a missing profile should raise an error to the
            # caller without transitioning the workflow to FAILED. This keeps
            # the workflow in BLOCKED so the user can fix the profile and retry.
            if self._profile_repo is None:
                raise ValueError(f"ProfileRepository not configured for workflow {workflow_id}")
            record = await self._profile_repo.get_profile(
                workflow.execution_state.profile_id,
            )
            if record is None:
                raise ValueError(
                    f"Profile '{workflow.execution_state.profile_id}' not found for workflow {workflow_id}"
                )
            profile = self._update_profile_working_dir(record, workflow.worktree_path)

            # Delete stale checkpoint (best-effort: the checkpoint will be
            # regenerated, so a failure here should not block replanning)
            try:
                await self._delete_checkpoint(workflow_id)
            except Exception:
                logger.warning(
                    "Failed to delete stale checkpoint, continuing with replan",
                    workflow_id=workflow_id,
                    exc_info=True,
                )

            # Clear plan-related fields from execution_state
            workflow.execution_state = workflow.execution_state.model_copy(
                update={
                    "external_plan": False,
                    "goal": None,
                    "plan_markdown": None,
                    "raw_architect_output": None,
                    "plan_path": None,
                    "key_files": [],
                    "total_tasks": 1,
                    "tool_calls": [],
                    "tool_results": [],
                    "human_approved": None,
                    "human_feedback": None,
                }
            )

            # Transition to PENDING.
            # Design note: we use repository.update() instead of set_status()
            # because multiple fields must change atomically (status,
            # execution_state). The BLOCKED → PENDING guard is enforced
            # explicitly above.
            workflow.workflow_status = WorkflowStatus.PENDING
            await self._repository.update(workflow)

            # Emit replanning event inside the lock, before spawning the task,
            # to guarantee ordering: STAGE_STARTED always precedes any events
            # emitted by _run_planning_task (e.g. APPROVAL_REQUIRED).
            await self._emit(
                workflow_id,
                EventType.STAGE_STARTED,
                "Replanning: regenerating plan with Architect",
                agent="architect",
                data={"stage": "architect", "replan": True},
            )

            # Spawn planning task in background (reuses existing _run_planning_task).
            # Note: workflow/execution_state are only used as initial graph input
            # (see _run_planning_task docstring). The cleared execution_state is
            # intentional — it seeds a fresh planning run. The task re-fetches
            # from the repository before any mutations, so staleness is safe.
            task = asyncio.create_task(
                self._run_planning_task(workflow_id, workflow, workflow.execution_state, profile)
            )
            self._planning_tasks[workflow_id] = task

            def cleanup_planning(_: asyncio.Task[None]) -> None:
                self._planning_tasks.pop(workflow_id, None)

            task.add_done_callback(cleanup_planning)

        logger.info(
            "Replan started",
            workflow_id=workflow_id,
            issue_id=workflow.issue_id,
        )
