"""Orchestrator service for managing concurrent workflow execution."""

import asyncio
import contextlib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from loguru import logger

from amelia.core.constants import resolve_plan_path
from amelia.core.types import (
    Design,
    Issue,
    Profile,
    SandboxMode,
)
from amelia.pipelines.implementation.external_plan import import_external_plan
from amelia.pipelines.implementation.state import ImplementationState
from amelia.server.config import ServerConfig
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
from amelia.server.models.events import EventType
from amelia.server.models.requests import BatchStartRequest, CreateWorkflowRequest
from amelia.server.models.responses import BatchStartResponse
from amelia.server.models.state import PlanCache, WorkflowStatus, WorkflowType
from amelia.server.orchestrator._common import (
    get_git_head,
    update_profile_repo_root,
)
from amelia.server.orchestrator.event_emitter import StreamEventEmitter
from amelia.server.orchestrator.runner import GraphRunner
from amelia.trackers.factory import create_tracker
from amelia.trajectory import WorkflowTrajectoryRecorder


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
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        trajectory_dir: Path | None = None,
    ) -> None:
        """Initialize orchestrator service.

        Args:
            event_bus: Event bus for broadcasting workflow events.
            repository: Repository for workflow persistence.
            profile_repo: Repository for profile lookup. Required for workflow execution.
            max_concurrent: Maximum number of concurrent workflows (default: 5).
            checkpointer: LangGraph checkpoint saver for workflow state persistence.
            trajectory_dir: Root directory for ATIF trajectory files. Defaults
                to ``ServerConfig().trajectory_dir``.
        """
        self._event_bus = event_bus
        self._repository = repository
        self._profile_repo = profile_repo
        self._max_concurrent = max_concurrent
        self._checkpointer = checkpointer
        self._trajectory_dir = (
            trajectory_dir if trajectory_dir is not None else ServerConfig().trajectory_dir
        )
        # workflow_id -> trajectory recorder; shared with the runner, which
        # threads recorders into graph config and finalizes at terminal seams.
        self._recorders: dict[uuid.UUID, WorkflowTrajectoryRecorder] = {}
        # Strong refs to in-flight recorder drain tasks (cleanup callback).
        self._drain_tasks: set[asyncio.Task[None]] = set()
        # Owns event emission + per-workflow sequencing.
        self._events = StreamEventEmitter(repository=repository, event_bus=event_bus)
        # Owns LangGraph execution drivers + their setup helpers.
        self._runner = GraphRunner(
            repository=repository,
            events=self._events,
            event_bus=event_bus,
            checkpointer=checkpointer,
            profile_repo=profile_repo,
            recorders=self._recorders,
        )
        # worktree_path -> (workflow_id, task)
        self._active_tasks: dict[str, tuple[uuid.UUID, asyncio.Task[None]]] = {}
        # workflow_id -> planning task
        self._planning_tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._approval_lock = asyncio.Lock()  # Prevents race conditions on approvals
        self._start_lock = asyncio.Lock()  # Prevents race conditions on workflow start

    def _ensure_recorder(
        self,
        workflow_id: uuid.UUID,
        issue_id: str,
        profile: Profile,
    ) -> WorkflowTrajectoryRecorder:
        """Create and register the workflow's trajectory recorder if absent.

        The profile snapshot records ``profile_id``, ``issue_id``, and each
        agent's ``{driver, model}`` so the trajectory file is self-describing.
        If a trajectory file already exists for the workflow (resume after a
        finalized run), the recorder loads it and appends.

        Args:
            workflow_id: Workflow the recorder belongs to.
            issue_id: Issue the workflow is working on.
            profile: Resolved profile for the snapshot.

        Returns:
            The registered recorder.
        """
        recorder = self._recorders.get(workflow_id)
        if recorder is not None:
            return recorder
        snapshot: dict[str, Any] = {
            "profile_id": profile.name,
            "issue_id": issue_id,
            "agents": {
                name: {"driver": cfg.driver, "model": cfg.model}
                for name, cfg in profile.agents.items()
            },
        }
        recorder = WorkflowTrajectoryRecorder(
            workflow_id=workflow_id,
            trajectory_dir=self._trajectory_dir,
            profile_snapshot=snapshot,
        )
        self._recorders[workflow_id] = recorder
        return recorder

    def get_recorder(
        self, workflow_id: uuid.UUID
    ) -> WorkflowTrajectoryRecorder | None:
        """Return the live trajectory recorder for a workflow, if registered.

        Used by the API layer to project history for active workflows
        directly from the in-memory recorder instead of the trajectory file.

        Args:
            workflow_id: Workflow whose recorder to look up.

        Returns:
            The registered recorder, or None when the workflow is not active.
        """
        return self._recorders.get(workflow_id)

    async def _ensure_recorder_for_state(self, workflow: ServerExecutionState) -> None:
        """Best-effort recorder registration from a persisted workflow row.

        Used at task-start seams where only ``profile_id`` is at hand
        (start-pending/resume/approve). Failure to resolve the profile is
        logged — recording is never allowed to block workflow execution.

        Args:
            workflow: Persisted workflow state with ``profile_id``/``issue_id``.
        """
        if workflow.id in self._recorders or workflow.profile_id is None:
            return
        try:
            profile = await self._resolve_profile(
                workflow.profile_id, workflow.worktree_path
            )
            self._ensure_recorder(workflow.id, workflow.issue_id, profile)
        except Exception:
            logger.warning(
                "Could not create trajectory recorder for workflow",
                workflow_id=workflow.id,
                exc_info=True,
            )

    def _schedule_recorder_drain(self, workflow_id: uuid.UUID) -> None:
        """Schedule a best-effort drain of an un-finalized recorder.

        Called from the task done-callback. No-op when the recorder was
        already finalized (and popped) at a terminal seam.

        Args:
            workflow_id: Workflow whose recorder may need draining.
        """
        if workflow_id not in self._recorders:
            return
        task = asyncio.create_task(self._drain_recorder(workflow_id))
        self._drain_tasks.add(task)
        task.add_done_callback(self._drain_tasks.discard)

    async def _drain_recorder(self, workflow_id: uuid.UUID) -> None:
        """Drain an un-finalized recorder after its workflow task exited.

        Blocked/pending workflows keep their recorder registered — the
        post-approval resume continues recording into it. Anything else is
        finalized with the workflow's terminal status (defaulting to
        ``failed`` for unexpected exits) so captured steps are never lost.

        Args:
            workflow_id: Workflow whose recorder to drain.
        """
        try:
            workflow = await self._repository.get(workflow_id)
            status = workflow.workflow_status if workflow is not None else None
            if status in (WorkflowStatus.PENDING, WorkflowStatus.BLOCKED):
                return  # Awaiting approval/start — recorder keeps accumulating
            terminal_status = {
                WorkflowStatus.COMPLETED: "completed",
                WorkflowStatus.CANCELLED: "cancelled",
            }.get(status, "failed") if status is not None else "failed"
            failure_reason: str | None = None
            if terminal_status == "failed":
                failure_reason = (
                    workflow.failure_reason if workflow is not None else None
                ) or "workflow task exited without finalizing trajectory"
            await self._runner.finalize_trajectory(
                workflow_id, status=terminal_status, failure_reason=failure_reason
            )
        except Exception:
            logger.exception(
                "Failed to drain trajectory recorder",
                workflow_id=workflow_id,
            )

    def _make_cleanup_callback(
        self,
        worktree_path: str,
        workflow_id: uuid.UUID,
    ) -> Callable[[asyncio.Task[None]], None]:
        """Create a done-callback that cleans up after a workflow task.

        Args:
            worktree_path: The worktree key in ``_active_tasks``.
            workflow_id: The workflow whose sequence state should be purged.

        Returns:
            A callback suitable for ``Task.add_done_callback``.
        """
        def _cleanup(_: asyncio.Task[None]) -> None:
            self._active_tasks.pop(worktree_path, None)
            self._events.forget(workflow_id)
            # Drain any un-finalized trajectory recorder (crash/unexpected exit).
            self._schedule_recorder_drain(workflow_id)
            logger.debug(
                "Workflow task completed",
                workflow_id=workflow_id,
                worktree_path=worktree_path,
            )

        return _cleanup

    async def _resolve_profile(
        self,
        profile_name: str | None,
        worktree_path: str,
    ) -> Profile:
        """Resolve a profile by name (or the active profile) and bind it to a worktree.

        Args:
            profile_name: Explicit profile name, or ``None`` for the active profile.
            worktree_path: Worktree path used as ``repo_root``.

        Returns:
            A ``Profile`` with ``repo_root`` set to *worktree_path*.

        Raises:
            ValueError: If ``ProfileRepository`` is not configured, the named
                profile does not exist, or no active profile is set.
        """
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

        return update_profile_repo_root(record, worktree_path)

    async def _prepare_workflow_state(
        self,
        workflow_id: uuid.UUID,
        worktree_path: str,
        issue_id: str,
        profile_name: str | None = None,
        task_title: str | None = None,
        task_description: str | None = None,
        artifact_path: str | None = None,
        branch: str | None = None,
    ) -> tuple[str, Profile, ImplementationState, str | None]:
        """Prepare common state needed to create or start a workflow.

        Centralizes the common initialization logic for profile resolution,
        issue fetching, branch creation, and ImplementationState creation
        shared across queue_workflow, start_workflow, and queue_and_plan_workflow.

        Args:
            workflow_id: The workflow ID (UUID).
            worktree_path: Resolved worktree path (already validated).
            issue_id: The issue ID to work on.
            profile_name: Optional profile name (defaults to active profile).
            task_title: Optional task title (skips tracker fetch when provided).
            task_description: Optional task description (defaults to task_title).
            artifact_path: Optional path to design artifact file from brainstorming.
                Can be worktree-relative (e.g., docs/plans/design.md or /docs/plans/design.md)
                or an absolute path within the worktree.
            branch: Branch override. None=auto-create amelia/<issue-id>.
                Empty string=use current branch as-is. Non-empty=create that branch.

        Returns:
            Tuple of (resolved_path, profile, execution_state, branch_name).

        Raises:
            ValueError: If profile not found, artifact_path escapes worktree,
                or branch validation fails.
            FileNotFoundError: If artifact_path is provided but the file doesn't exist.
        """
        profile = await self._resolve_profile(profile_name, worktree_path)

        # Branch creation for local (non-sandbox) workflows
        created_branch: str | None = None
        if profile.sandbox.mode not in (SandboxMode.DAYTONA, SandboxMode.CONTAINER):
            created_branch = await self._setup_workflow_branch(
                worktree_path, issue_id, branch,
            )

        # Construct issue from provided title or fetch from tracker
        if task_title is not None:
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
                    relative_artifact = artifact_path.removeprefix("/")
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

        return worktree_path, profile, execution_state, created_branch

    @staticmethod
    async def _setup_workflow_branch(
        worktree_path: str,
        issue_id: str,
        branch: str | None,
    ) -> str | None:
        """Create or validate the git branch for a local workflow.

        Args:
            worktree_path: Path to the git worktree.
            issue_id: Issue ID used to generate branch name.
            branch: Branch override from user. None=auto-create,
                empty string=use current branch, non-empty=create that branch.

        Returns:
            The branch name being used, or None if branch setup was skipped.

        Raises:
            ValueError: If on a non-default branch without override,
                working tree is dirty, or branch creation fails.
        """
        from amelia.tools.git_utils import (  # noqa: PLC0415
            PROTECTED_BRANCHES,
            checkout_branch as _checkout_branch,
            create_and_checkout_branch,
            get_current_branch,
            has_uncommitted_changes,
        )

        current_branch = await get_current_branch(worktree_path)

        # Validate we're on a default branch (or detached HEAD is an error)
        if current_branch is None:
            raise ValueError(
                "Currently in detached HEAD state. "
                "Checkout a default branch (main/master/develop) before starting a workflow, "
                "or pass --branch to override."
            )

        if await has_uncommitted_changes(worktree_path):
            raise ValueError(
                "Working tree has uncommitted changes. "
                "Commit or stash them before starting a workflow."
            )

        # Explicit opt-in: use current branch as-is
        if branch == "":
            return current_branch

        if current_branch not in PROTECTED_BRANCHES:
            raise ValueError(
                f"Currently on non-default branch '{current_branch}'. "
                f"Switch to a default branch (main/master/develop) first, "
                f"or pass --branch to use the current branch as-is."
            )

        # Determine target branch name
        target_branch = branch if branch else f"amelia/{issue_id}"

        await create_and_checkout_branch(worktree_path, target_branch)
        logger.info("Created workflow branch", branch=target_branch, from_branch=current_branch)

        # Restore worktree to the original branch so queued workflows
        # don't leave the worktree on the issue branch
        await _checkout_branch(worktree_path, current_branch)

        return target_branch

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

    @staticmethod
    def _resolve_target_plan_path(
        plan_file: str | None,
        plan_path_pattern: str,
        issue_id: str,
        working_dir: Path,
    ) -> Path:
        """Resolve the filesystem path where a plan should be stored.

        Args:
            plan_file: Explicit plan file path (relative or absolute).
                When provided the file is used in-place.
            plan_path_pattern: Profile pattern used to derive the conventional
                path when *plan_file* is ``None``.
            issue_id: Issue ID substituted into *plan_path_pattern*.
            working_dir: Repo root; relative paths are resolved against it.

        Returns:
            Resolved absolute ``Path`` for the plan file.
        """
        if plan_file is not None:
            working_dir_resolved = working_dir.resolve()
            source = Path(plan_file)
            if not source.is_absolute():
                source = working_dir_resolved / plan_file
            resolved = source.expanduser().resolve()
            # Validate the resolved path stays within the repository
            # (prevents traversal via .. sequences or symlinks)
            try:
                resolved.relative_to(working_dir_resolved)
            except ValueError:
                raise ValueError(
                    f"plan_file '{plan_file}' resolves outside repository directory"
                ) from None
            return resolved
        plan_rel_path = resolve_plan_path(plan_path_pattern, issue_id)
        return working_dir / plan_rel_path

    def _assert_can_acquire_worktree(self, worktree_path: str) -> None:
        """Assert a worktree can be acquired for a new workflow.

        Must be called while holding ``self._start_lock`` so the observed
        active-task count is stable.

        Args:
            worktree_path: Resolved worktree path to acquire.

        Raises:
            WorkflowConflictError: If the worktree already has an active task.
            ConcurrencyLimitError: If at the max concurrent workflow limit.
        """
        if worktree_path in self._active_tasks:
            existing_id, _ = self._active_tasks[worktree_path]
            raise WorkflowConflictError(worktree_path, existing_id)

        current_count = len(self._active_tasks)
        if current_count >= self._max_concurrent:
            raise ConcurrencyLimitError(self._max_concurrent, current_count)

    async def start_workflow(
        self,
        issue_id: str,
        worktree_path: str,
        profile: str | None = None,
        driver: str | None = None,
        task_title: str | None = None,
        task_description: str | None = None,
        branch: str | None = None,
    ) -> uuid.UUID:
        """Start a new workflow.

        Args:
            issue_id: The issue ID to work on.
            worktree_path: Absolute path to the worktree.
            profile: Optional profile name.
            driver: Optional driver override.
            task_title: Optional task title (skips tracker fetch when provided).
            task_description: Optional task description (defaults to task_title if not provided).
            branch: Branch override. None=auto-create amelia/<issue-id>.
                Empty string=use current branch as-is.

        Returns:
            The workflow ID (UUID).

        Raises:
            InvalidWorktreeError: If worktree path doesn't exist or is not a git repo.
            WorkflowConflictError: If worktree already has active workflow.
            ConcurrencyLimitError: If at max concurrent workflows.
            ValueError: If profile not found.
        """
        # Validate and resolve worktree before acquiring lock (fast-fail)
        worktree = self._validate_worktree_path(worktree_path)
        resolved_path = str(worktree)

        async with self._start_lock:
            self._assert_can_acquire_worktree(resolved_path)

            workflow_id = uuid4()

            # Prepare issue and execution state using the helper
            # This also loads the profile from the database
            _, loaded_profile, execution_state, created_branch = await self._prepare_workflow_state(
                workflow_id=workflow_id,
                worktree_path=resolved_path,
                issue_id=issue_id,
                profile_name=profile,
                task_title=task_title,
                task_description=task_description,
                branch=branch,
            )

            # execution_state.issue is always set by _prepare_workflow_state
            assert execution_state.issue is not None
            state = ServerExecutionState(
                id=workflow_id,
                issue_id=issue_id,
                worktree_path=resolved_path,
                profile_id=loaded_profile.name,
                issue_cache=execution_state.issue.model_dump(mode="json"),
                workflow_status=WorkflowStatus.PENDING,
                started_at=datetime.now(UTC),
                base_commit=execution_state.base_commit,
                branch=created_branch,
            )
            try:
                await self._repository.create(state)
            except Exception as e:
                # Handle DB constraint violation (e.g., crash recovery scenario)
                if "UNIQUE constraint failed" in str(e):
                    raise WorkflowConflictError(resolved_path, "existing") from e
                raise

            # Record the run's ATIF trajectory from the first agent invocation
            self._ensure_recorder(workflow_id, issue_id, loaded_profile)

            # Start async task with retry wrapper for transient failures
            task = asyncio.create_task(self._runner.run_workflow_with_retry(workflow_id, state))
            self._active_tasks[resolved_path] = (workflow_id, task)

        task.add_done_callback(self._make_cleanup_callback(resolved_path, workflow_id))

        return workflow_id

    async def queue_workflow(self, request: CreateWorkflowRequest) -> uuid.UUID:
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
        workflow_id = uuid4()

        # Prepare common workflow state (settings, profile, issue, execution_state)
        resolved_path, profile, execution_state, created_branch = await self._prepare_workflow_state(
            workflow_id=workflow_id,
            worktree_path=resolved_path,
            issue_id=request.issue_id,
            profile_name=request.profile,
            task_title=request.task_title,
            task_description=request.task_description,
            artifact_path=request.artifact_path,
            branch=request.branch,
        )

        # Handle external plan if provided
        plan_cache: PlanCache | None = None
        if request.plan_file is not None or request.plan_content is not None:
            working_dir = Path(profile.repo_root)

            target_path = self._resolve_target_plan_path(
                request.plan_file,
                profile.plan_path_pattern,
                request.issue_id,
                working_dir,
            )

            # Import and validate external plan (regex extraction)
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

            # Persist plan data so _reconstruct_initial_state can restore external_plan=True
            plan_cache = PlanCache(
                goal=plan_result.goal,
                plan_markdown=plan_result.plan_markdown,
                plan_path=str(plan_result.plan_path),
                total_tasks=plan_result.total_tasks,
                external_plan=True,
            )

        # Create ServerExecutionState in pending status (not started)
        # execution_state.issue is always set by _prepare_workflow_state
        assert execution_state.issue is not None
        state = ServerExecutionState(
            id=workflow_id,
            issue_id=request.issue_id,
            worktree_path=resolved_path,
            profile_id=profile.name,
            issue_cache=execution_state.issue.model_dump(mode="json"),
            plan_cache=plan_cache,
            workflow_status=WorkflowStatus.PENDING,
            base_commit=execution_state.base_commit,
            branch=created_branch,
            # No started_at - workflow hasn't started
        )

        # Save to database
        await self._repository.create(state)

        # Emit created event
        await self._events.emit(
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

    async def _launch_review(
        self,
        *,
        worktree_path: str,
        profile: Profile,
        issue: Issue | None,
        diff_content: str,
        base_commit: str | None,
        mode: str,
        review_types: list[str] | None,
    ) -> uuid.UUID:
        """Create a REVIEW workflow and launch its background task.

        Shared tail for ``start_review_workflow`` and ``request_review``. Acquires
        the worktree under ``_start_lock``, builds the ``ImplementationState`` and
        ``ServerExecutionState`` (workflow_type=REVIEW), persists the state, spawns
        the review-graph task, registers it in ``_active_tasks`` and attaches the
        cleanup callback.

        Args:
            worktree_path: Resolved worktree path (already validated).
            profile: Profile already resolved and bound to the worktree.
            issue: Issue for review context, or ``None``.
            diff_content: The diff the review graph operates on.
            base_commit: Base commit for the review diff (may be ``None``).
            mode: Review mode (e.g. ``"review_only"``/``"review_fix"``).
            review_types: Optional list of review types to run.

        Returns:
            The new review workflow ID (UUID).

        Raises:
            WorkflowConflictError: If worktree already has active workflow.
            ConcurrencyLimitError: If at max concurrent workflows.
        """
        async with self._start_lock:
            self._assert_can_acquire_worktree(worktree_path)

            new_id = uuid4()

            execution_state = ImplementationState(
                workflow_id=new_id,
                profile_id=profile.name,
                created_at=datetime.now(UTC),
                status="pending",
                issue=issue,
                code_changes_for_review=diff_content,
                base_commit=base_commit,
                review_iteration=0,
                review_mode=mode,
            )

            state = ServerExecutionState(
                id=new_id,
                issue_id=issue.id if issue is not None else "LOCAL-REVIEW",
                worktree_path=worktree_path,
                workflow_type=WorkflowType.REVIEW,
                profile_id=profile.name,
                issue_cache=issue.model_dump(mode="json") if issue is not None else None,
                workflow_status=WorkflowStatus.PENDING,
                started_at=datetime.now(UTC),
                base_commit=base_commit,
            )

            await self._repository.create(state)

            # Start with review graph instead of full graph
            task = asyncio.create_task(
                self._runner.run_review_workflow(
                    new_id, state, execution_state,
                    review_mode=mode, review_types=review_types,
                )
            )
            self._active_tasks[worktree_path] = (new_id, task)

        task.add_done_callback(self._make_cleanup_callback(worktree_path, new_id))

        return new_id

    async def start_review_workflow(
        self,
        diff_content: str,
        worktree_path: str,
        profile: str | None = None,
    ) -> uuid.UUID:
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

        loaded_profile = await self._resolve_profile(profile, resolved_path)

        # Create dummy issue for review context
        dummy_issue = Issue(
            id="LOCAL-REVIEW",
            title="Local Code Review",
            description="Review local uncommitted changes."
        )

        # Get current HEAD for tracking (even though diff is provided)
        base_commit = await get_git_head(resolved_path)

        return await self._launch_review(
            worktree_path=resolved_path,
            profile=loaded_profile,
            issue=dummy_issue,
            diff_content=diff_content,
            base_commit=base_commit,
            mode="review_fix",
            review_types=None,
        )

    async def cancel_workflow(
        self,
        workflow_id: uuid.UUID,
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

        # Finalize the trajectory with the cancelled outcome (no-op if the
        # workflow never recorded or was already finalized).
        await self._runner.finalize_trajectory(workflow_id, status="cancelled")

    async def resume_workflow(self, workflow_id: uuid.UUID) -> ServerExecutionState:
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
        await self._runner.validate_resume_checkpoint(workflow_id, workflow.workflow_status)

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

            await self._events.emit(
                workflow_id,
                EventType.WORKFLOW_STARTED,
                "Workflow resumed from checkpoint",
                data={"resumed": True},
            )

            # Continue the trajectory: an existing file is loaded and appended to
            await self._ensure_recorder_for_state(workflow)

            # Launch workflow task (same as start_workflow)
            task = asyncio.create_task(
                self._runner.run_workflow_with_retry(workflow_id, workflow)
            )
            self._active_tasks[workflow.worktree_path] = (workflow_id, task)

        task.add_done_callback(self._make_cleanup_callback(workflow.worktree_path, workflow_id))

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


    async def _delete_checkpoint(self, workflow_id: uuid.UUID) -> None:
        """Delete LangGraph checkpoint data for a workflow.

        Removes all checkpoint records (checkpoints, writes, blobs) for
        the given thread ID. Used by replan to start fresh.

        Args:
            workflow_id: The workflow/thread ID whose checkpoint to delete.
        """
        if self._checkpointer is None:
            return
        await self._checkpointer.adelete_thread(str(workflow_id))
        logger.info("Deleted checkpoint", workflow_id=workflow_id)

    async def approve_workflow(self, workflow_id: uuid.UUID) -> None:
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

            await self._events.emit(
                workflow_id,
                EventType.APPROVAL_GRANTED,
                "Plan approved",
                agent="human_approval",
            )

            await self._repository.set_status(workflow_id, WorkflowStatus.IN_PROGRESS)

        # Recorder normally survives the approval pause in-memory; recreate it
        # after a server restart so the post-approval run is still recorded.
        await self._ensure_recorder_for_state(workflow)

        # Delegate post-approval execution to the runner, which owns the
        # execution-driver pattern (retry/failure-ladder, sandbox lifecycle).
        await self._runner.resume_workflow_with_retry(
            workflow_id,
            workflow.profile_id,
            workflow.worktree_path,
        )

    async def reject_workflow(
        self,
        workflow_id: uuid.UUID,
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
            await self._events.emit(
                workflow_id,
                EventType.APPROVAL_REJECTED,
                f"Plan rejected: {feedback}",
            )

            # Cancel the waiting task
            if workflow.worktree_path in self._active_tasks:
                _, task = self._active_tasks[workflow.worktree_path]
                task.cancel()

        # Write human_approved=False into the LangGraph checkpoint (best-effort)
        await self._runner.record_rejection(
            workflow_id, workflow.profile_id, workflow.worktree_path
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
            await self._events.emit(
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
            await self._events.emit(
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

    async def queue_and_plan_workflow(
        self,
        request: CreateWorkflowRequest,
    ) -> uuid.UUID:
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
        workflow_id = uuid4()

        # Prepare common workflow state (settings, profile, issue, execution_state)
        resolved_path, profile, execution_state, created_branch = await self._prepare_workflow_state(
            workflow_id=workflow_id,
            worktree_path=resolved_path,
            issue_id=request.issue_id,
            profile_name=request.profile,
            task_title=request.task_title,
            task_description=request.task_description,
            branch=request.branch,
        )

        # Create ServerExecutionState in pending status (architect running)
        # execution_state.issue is always set by _prepare_workflow_state
        assert execution_state.issue is not None
        state = ServerExecutionState(
            id=workflow_id,
            issue_id=request.issue_id,
            worktree_path=resolved_path,
            profile_id=profile.name,
            issue_cache=execution_state.issue.model_dump(mode="json"),
            workflow_status=WorkflowStatus.PENDING,
            base_commit=execution_state.base_commit,
            branch=created_branch,
            # Note: started_at is None - workflow hasn't started yet
        )

        # Save initial state
        await self._repository.create(state)

        # Emit workflow created event
        await self._events.emit(
            workflow_id,
            EventType.WORKFLOW_CREATED,
            f"Workflow queued for {request.issue_id}, planning...",
            data={"issue_id": request.issue_id, "queued": True, "planning": True},
        )

        # Planning runs the architect — record it into the workflow trajectory
        self._ensure_recorder(workflow_id, request.issue_id, profile)

        # Spawn planning task in background (non-blocking)
        task = asyncio.create_task(
            self._runner.run_planning_task(workflow_id, state, execution_state, profile)
        )
        self._planning_tasks[workflow_id] = task

        # Cleanup on completion
        def cleanup_planning(_: asyncio.Task[None]) -> None:
            self._planning_tasks.pop(workflow_id, None)

        task.add_done_callback(cleanup_planning)

        return workflow_id

    async def start_pending_workflow(self, workflow_id: uuid.UUID) -> None:
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

            # Also check in-memory tasks for worktree conflict and limit
            self._assert_can_acquire_worktree(workflow.worktree_path)

            # Checkout the workflow branch if one was persisted
            if workflow.branch:
                from amelia.tools.git_utils import checkout_branch  # noqa: PLC0415

                try:
                    await checkout_branch(workflow.worktree_path, workflow.branch)
                except ValueError as exc:
                    raise InvalidStateError(
                        f"Cannot checkout workflow branch '{workflow.branch}': {exc}",
                        workflow_id=workflow_id,
                        current_status=workflow.workflow_status,
                    ) from exc

            # Set started_at timestamp (status transition happens in runner.run_workflow)
            # NOTE: We don't set workflow_status here - runner.run_workflow handles
            # the pending -> in_progress transition, consistent with start_workflow
            workflow.started_at = datetime.now(UTC)
            await self._repository.update(workflow)

            # Record the run's ATIF trajectory (best-effort profile resolution)
            await self._ensure_recorder_for_state(workflow)

            # Spawn execution task
            task = asyncio.create_task(
                self._runner.run_workflow_with_retry(workflow_id, workflow)
            )
            self._active_tasks[workflow.worktree_path] = (workflow_id, task)

        task.add_done_callback(self._make_cleanup_callback(workflow.worktree_path, workflow_id))

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

            workflow_ids = [str(w.id) for w in pending_workflows]

        # Attempt to start each workflow
        for workflow_id in workflow_ids:
            try:
                await self.start_pending_workflow(uuid.UUID(workflow_id))
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
        workflow_id: uuid.UUID,
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
        has_existing_plan = (
            workflow.plan_cache is not None
            and (
                workflow.plan_cache.plan_markdown is not None
                or workflow.plan_cache.plan_path is not None
            )
        )
        if has_existing_plan and not force:
            raise WorkflowConflictError(
                "Plan already exists. Use force=true to overwrite."
            )

        # Ensure profile_id exists
        if workflow.profile_id is None:
            raise InvalidStateError(
                "Cannot set plan: workflow has no profile_id",
                workflow_id=workflow_id,
            )

        # Get profile for plan path resolution
        profile = await self._runner.get_profile_or_fail(
            workflow_id,
            workflow.profile_id,
            workflow.worktree_path,
        )
        if profile is None:
            raise ValueError("Profile not found for workflow")

        profile = update_profile_repo_root(profile, workflow.worktree_path)

        # Resolve target plan path
        working_dir = Path(profile.repo_root)
        target_path = self._resolve_target_plan_path(
            plan_file, profile.plan_path_pattern, workflow.issue_id, working_dir
        )

        # Delegate to import_external_plan for read, write, extract, validate
        plan_result = await import_external_plan(
            plan_file=plan_file,
            plan_content=plan_content,
            target_path=target_path,
            profile=profile,
            workflow_id=workflow_id,
        )

        # Save PlanCache with goal populated
        plan_cache = PlanCache(
            goal=plan_result.goal,
            plan_markdown=plan_result.plan_markdown,
            plan_path=str(plan_result.plan_path),
            total_tasks=plan_result.total_tasks,
            external_plan=True,
        )
        await self._repository.update_plan_cache(workflow_id, plan_cache)

        # Emit validation event and build response
        result = await self._runner.emit_plan_validation_event(workflow_id, plan_result)

        logger.info(
            "External plan imported and validated",
            workflow_id=workflow_id,
            goal=plan_result.goal,
            total_tasks=plan_result.total_tasks,
        )

        return result

    async def replan_workflow(self, workflow_id: uuid.UUID) -> None:
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

            if workflow.profile_id is None:
                raise InvalidStateError(
                    "Cannot replan workflow without profile_id",
                    workflow_id=workflow_id,
                    current_status=str(workflow.workflow_status),
                )

            # Resolve profile without side-effects: replan is a user-initiated
            # retry action, so a missing profile should raise an error to the
            # caller without transitioning the workflow to FAILED. This keeps
            # the workflow in BLOCKED so the user can fix the profile and retry.
            if self._profile_repo is None:
                raise ValueError(f"ProfileRepository not configured for workflow {workflow_id}")
            record = await self._profile_repo.get_profile(workflow.profile_id)
            if record is None:
                raise ValueError(
                    f"Profile '{workflow.profile_id}' not found for workflow {workflow_id}"
                )
            profile = update_profile_repo_root(record, workflow.worktree_path)

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

            # Clear plan_cache by setting empty values
            empty_plan_cache = PlanCache()
            await self._repository.update_plan_cache(workflow_id, empty_plan_cache)

            # Transition to PENDING
            await self._repository.set_status(workflow_id, WorkflowStatus.PENDING)

            # Reconstruct ImplementationState for graph input
            # Parse issue from issue_cache
            issue = None
            if workflow.issue_cache:
                issue = Issue.model_validate(workflow.issue_cache)
            else:
                # Fallback: fetch from tracker
                tracker = create_tracker(profile)
                issue = tracker.get_issue(workflow.issue_id, cwd=workflow.worktree_path)

            # Get current HEAD as base commit
            base_commit = await get_git_head(workflow.worktree_path)

            execution_state = ImplementationState(
                workflow_id=workflow_id,
                profile_id=profile.name,
                created_at=workflow.created_at,
                status="pending",
                issue=issue,
                base_commit=base_commit,
            )

            # Emit replanning event inside the lock, before spawning the task,
            # to guarantee ordering: STAGE_STARTED always precedes any events
            # emitted by runner.run_planning_task (e.g. APPROVAL_REQUIRED).
            await self._events.emit(
                workflow_id,
                EventType.STAGE_STARTED,
                "Replanning: regenerating plan with Architect",
                agent="architect",
                data={"stage": "architect", "replan": True},
            )

            # Replanning re-runs the architect — keep recording into the trajectory
            self._ensure_recorder(workflow_id, workflow.issue_id, profile)

            # Spawn planning task in background (reuses existing runner.run_planning_task).
            # Note: workflow/execution_state are only used as initial graph input
            # (see runner.run_planning_task docstring). The reconstructed execution_state
            # seeds a fresh planning run. The task re-fetches from the repository
            # before any mutations, so staleness is safe.
            task = asyncio.create_task(
                self._runner.run_planning_task(workflow_id, workflow, execution_state, profile)
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

    async def request_review(
        self,
        workflow_id: uuid.UUID,
        mode: str = "review_only",
        review_types: list[str] | None = None,
        base_commit: str | None = None,
    ) -> uuid.UUID:
        """Request an on-demand code review for a workflow.

        Args:
            workflow_id: The workflow to review.
            mode: Review mode - 'review_only' for read-only review,
                  'review_fix' for review with automatic fixes.
            review_types: List of review types to run (e.g. ['general', 'security']).
                Defaults to ['general'].
            base_commit: Optional base commit for the diff. If None, uses
                the workflow's stored base commit.

        Returns:
            The new review workflow ID (UUID).

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            WorkflowConflictError: If worktree already has active workflow.
            ConcurrencyLimitError: If at max concurrent workflows.
        """
        if review_types is None:
            review_types = ["general"]

        workflow = await self._repository.get(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(workflow_id)

        logger.info(
            "On-demand review requested",
            workflow_id=workflow_id,
            mode=mode,
            review_types=review_types,
            base_commit=base_commit,
        )

        # Resolve base commit and diff content.
        # Use the source workflow's stored base_commit (the HEAD at workflow start)
        # so the diff captures all changes the workflow made. Falling back to HEAD
        # would produce an empty diff (HEAD vs HEAD).
        worktree_path = workflow.worktree_path
        if base_commit is None:
            base_commit = workflow.base_commit
        if base_commit is None:
            logger.warning(
                "No base_commit stored for workflow, review diff may be empty",
                workflow_id=workflow_id,
            )

        # Get diff content
        diff_content = ""
        if base_commit:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "git", "diff", base_commit, "HEAD",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=worktree_path,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0:
                    diff_content = stdout.decode()
            except (FileNotFoundError, OSError):
                logger.warning("Failed to get diff", worktree_path=worktree_path)

        # Keep the PARENT workflow's profile (no override): resolve by its
        # profile_id, falling back to the active profile when unset.
        loaded_profile = await self._resolve_profile(workflow.profile_id, worktree_path)

        # Reconstruct issue from cached data
        issue = None
        if workflow.issue_cache:
            issue = Issue.model_validate(workflow.issue_cache)

        return await self._launch_review(
            worktree_path=worktree_path,
            profile=loaded_profile,
            issue=issue,
            diff_content=diff_content,
            base_commit=base_commit,
            mode=mode,
            review_types=review_types,
        )
