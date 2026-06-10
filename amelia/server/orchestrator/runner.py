"""LangGraph execution drivers for the orchestrator.

``GraphRunner`` owns the seam between the orchestrator service's lifecycle
methods and LangGraph itself: it builds graphs/configs/sandboxes, reconstructs
initial state, and runs the workflow / review / planning graphs (with retry).

The service constructs one ``GraphRunner`` and wraps each driver call in an
``asyncio.Task`` that it tracks in ``_active_tasks``. The runner never touches
``_active_tasks`` — task registration and cleanup stay on the service.
"""

import asyncio
import uuid
from typing import TYPE_CHECKING, Any, cast

from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from amelia.core.retry import with_retry
from amelia.core.types import (
    Issue,
    Profile,
    SandboxMode,
)
from amelia.pipelines.implementation import create_implementation_graph
from amelia.pipelines.implementation.external_plan import ExternalPlanImportResult
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.review import create_review_graph
from amelia.server.database import ProfileRepository
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models import ServerExecutionState
from amelia.server.models.events import EventType
from amelia.server.models.state import PlanCache, WorkflowStatus
from amelia.server.orchestrator._common import (
    TRANSIENT_EXCEPTIONS,
    get_git_head,
    update_profile_repo_root,
)
from amelia.server.orchestrator.event_emitter import (
    StreamEventEmitter,
    is_interrupt_chunk,
)
from amelia.trackers.factory import create_tracker


if TYPE_CHECKING:
    from amelia.sandbox.provider import SandboxProvider
    from amelia.trajectory.recorder import WorkflowTrajectoryRecorder


class _SandboxBootstrapHandled(Exception):
    """Internal sentinel: a sandbox-bootstrap failure that has already emitted
    WORKFLOW_FAILED and recorded FAILED status. Not a transient exception, so
    with_retry re-raises it immediately; the caller catches it to avoid
    double-emitting a non-transient failure.
    """


class GraphRunner:
    """Runs LangGraph workflow/review/planning graphs for the orchestrator.

    Holds the LangGraph setup helpers (graph/config/sandbox construction,
    state reconstruction, profile resolution, checkpoint plan sync) and the
    execution drivers. Receives all collaborators via constructor DI; never
    reaches back into the owning service.
    """

    def __init__(
        self,
        repository: WorkflowRepository,
        events: StreamEventEmitter,
        event_bus: EventBus,
        checkpointer: BaseCheckpointSaver[Any] | None,
        profile_repo: ProfileRepository | None,
        recorders: "dict[uuid.UUID, WorkflowTrajectoryRecorder] | None" = None,
    ) -> None:
        """Initialize the graph runner.

        Args:
            repository: Repository for workflow persistence and status.
            events: Stream event emitter (owns per-workflow sequencing).
            event_bus: Event bus passed into the LangGraph runnable config.
            checkpointer: LangGraph checkpoint saver for state persistence.
            profile_repo: Repository for profile lookup.
            recorders: Shared per-workflow trajectory recorder registry
                (owned by the service; the runner threads recorders into
                graph config and finalizes them at terminal seams).
        """
        self._repository = repository
        self._events = events
        self._event_bus = event_bus
        self._checkpointer = checkpointer
        self._profile_repo = profile_repo
        self._recorders: dict[uuid.UUID, WorkflowTrajectoryRecorder] = (
            recorders if recorders is not None else {}
        )

    def create_server_graph(
        self,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
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

    async def resolve_prompts(self, workflow_id: uuid.UUID) -> dict[str, str]:
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

    async def get_profile_or_fail(
        self,
        workflow_id: uuid.UUID,
        profile_id: str,
        worktree_path: str,
    ) -> Profile | None:
        """Look up profile by ID from database.

        Profiles are loaded from the database via ProfileRepository.
        There is no fallback - a valid profile must exist.

        Args:
            workflow_id: Workflow ID for logging and status updates.
            profile_id: Profile ID to look up in database.
            worktree_path: Worktree path for agent execution (overrides profile's repo_root).

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

        return update_profile_repo_root(record, worktree_path)

    async def create_sandbox_provider(
        self,
        profile: Profile,
        agent_name: str = "developer",
    ) -> "SandboxProvider | None":
        """Create and bootstrap a Daytona sandbox provider if configured.

        Returns ``None`` when the profile's sandbox mode is not Daytona.

        Args:
            profile: The resolved workflow profile.
            agent_name: Agent whose options are used for LLM provider
                resolution (default ``"developer"``).

        Returns:
            A bootstrapped ``SandboxProvider``, or ``None``.
        """
        if profile.sandbox.mode != SandboxMode.DAYTONA:
            return None

        from amelia.drivers.factory import create_daytona_provider  # noqa: PLC0415

        agent_options = None
        try:
            agent_config = profile.get_agent_config(agent_name)
            agent_options = agent_config.options
        except ValueError:
            pass

        provider, _worker_env = create_daytona_provider(
            profile.sandbox, options=agent_options, retry_config=profile.retry,
        )
        await provider.ensure_running()
        return provider

    def build_runnable_config(
        self,
        workflow_id: uuid.UUID,
        profile: Profile,
        prompts: dict[str, str],
        sandbox_provider: "SandboxProvider | None" = None,
        **extra: Any,
    ) -> RunnableConfig:
        """Build a ``RunnableConfig`` for LangGraph execution.

        Args:
            workflow_id: Workflow / LangGraph thread identifier.
            profile: Resolved profile for the workflow.
            prompts: Resolved prompt map.
            sandbox_provider: Optional sandbox provider.
            **extra: Additional keys merged into ``configurable``.

        Returns:
            A ``RunnableConfig`` dict ready for ``graph.astream``.
        """
        configurable: dict[str, Any] = {
            "thread_id": str(workflow_id),
            "execution_mode": "server",
            "event_bus": self._event_bus,
            "profile": profile,
            "repository": self._repository,
            "prompts": prompts,
            "sandbox_provider": sandbox_provider,
            "trajectory_recorder": self._recorders.get(workflow_id),
            **extra,
        }
        return {
            "recursion_limit": 100,
            "configurable": configurable,
        }

    async def _reconstruct_initial_state(
        self,
        state: ServerExecutionState,
        profile: Profile,
    ) -> dict[str, Any]:
        """Reconstruct ImplementationState from ServerExecutionState columns.

        Used when no LangGraph checkpoint exists and execution_state is not
        available. Reconstructs the minimal state needed to start the workflow.

        Args:
            state: ServerExecutionState with issue_cache and other fields.
            profile: Resolved profile for the workflow.

        Returns:
            JSON-serializable dict for LangGraph initial state.

        Raises:
            ValueError: If required fields are missing.
        """
        issue = None
        if state.issue_cache:
            issue = Issue.model_validate(state.issue_cache)
        else:
            # Fallback: fetch from tracker (shouldn't normally happen)
            tracker = create_tracker(profile)
            issue = tracker.get_issue(state.issue_id, cwd=state.worktree_path)

        # Get current HEAD as base commit (we're starting fresh)
        base_commit = await get_git_head(state.worktree_path)

        # Hydrate plan fields from plan_cache if present (external plans)
        plan_fields: dict[str, Any] = {}
        if state.plan_cache is not None:
            plan_cache = state.plan_cache
            if plan_cache.goal is not None:
                plan_fields["goal"] = plan_cache.goal
            plan_markdown = await plan_cache.get_plan_markdown()
            if plan_markdown is not None:
                plan_fields["plan_markdown"] = plan_markdown
            if plan_cache.plan_path is not None:
                plan_fields["plan_path"] = plan_cache.plan_path
                plan_fields["external_plan"] = True
            if plan_cache.total_tasks is not None:
                plan_fields["total_tasks"] = plan_cache.total_tasks
            if plan_cache.current_task_index is not None:
                plan_fields["current_task_index"] = plan_cache.current_task_index

        impl_state = ImplementationState(
            workflow_id=state.id,
            profile_id=profile.name,
            created_at=state.created_at,
            status="pending",
            issue=issue,
            base_commit=base_commit,
            **plan_fields,
        )

        logger.debug(
            "Reconstructed ImplementationState from columns",
            workflow_id=state.id,
            issue_id=state.issue_id,
            profile_id=profile.name,
            has_plan_cache=state.plan_cache is not None,
        )

        return impl_state.model_dump(mode="json")

    async def _sync_plan_from_checkpoint(
        self,
        workflow_id: uuid.UUID,
        graph: CompiledStateGraph[Any],
        config: RunnableConfig,
    ) -> None:
        """Sync plan from LangGraph checkpoint to plan_cache column.

        Uses LangGraph's get_state() API to fetch the current checkpoint state,
        ensuring the plan is available via REST API when workflow is blocked.

        This method writes directly to the plan_cache column for efficiency,
        avoiding the need to load and re-serialize the entire ServerExecutionState.

        Args:
            workflow_id: The workflow ID.
            graph: The compiled LangGraph instance.
            config: The RunnableConfig with thread_id.
        """
        try:
            checkpoint_state = await graph.aget_state(config)
            if checkpoint_state is None or checkpoint_state.values is None:
                logger.warning(
                    "Cannot sync plan - no checkpoint state",
                    workflow_id=workflow_id,
                )
                return

            goal = checkpoint_state.values.get("goal")
            plan_markdown = checkpoint_state.values.get("plan_markdown")

            logger.info(
                "Syncing plan from checkpoint",
                workflow_id=workflow_id,
                has_goal=goal is not None,
                goal_preview=goal[:100] if goal else None,
                has_plan_markdown=plan_markdown is not None,
                plan_markdown_length=len(plan_markdown) if plan_markdown else 0,
            )

            if goal is None and plan_markdown is None:
                logger.warning(
                    "No goal or plan_markdown in checkpoint - architect may not have completed",
                    workflow_id=workflow_id,
                    checkpoint_keys=list(checkpoint_state.values.keys()) if checkpoint_state.values else [],
                )
                return

            plan_cache = PlanCache.from_checkpoint_values(checkpoint_state.values)

            # Update plan_cache column directly (efficient, no full state load)
            await self._repository.update_plan_cache(workflow_id, plan_cache)

            logger.debug(
                "Synced plan to plan_cache column",
                workflow_id=workflow_id,
                has_plan_path=plan_cache.plan_path is not None,
            )

        except Exception as e:
            # Log but don't fail the workflow - plan sync is best-effort
            logger.warning(
                "Failed to sync plan from checkpoint",
                workflow_id=workflow_id,
                error=str(e),
            )

    async def emit_plan_validation_event(
        self,
        workflow_id: uuid.UUID,
        plan_result: ExternalPlanImportResult,
    ) -> dict[str, Any]:
        """Emit plan validation event and return response dict.

        Args:
            workflow_id: The workflow ID.
            plan_result: Result from import_external_plan with validation data.

        Returns:
            Dict with status, goal, key_files, total_tasks, and
            validation_issues if invalid.
        """
        validation = plan_result.validation_result
        if validation is not None and not validation.valid:
            await self._events.emit(
                workflow_id,
                EventType.PLAN_VALIDATION_FAILED,
                f"Plan validation failed: {'; '.join(validation.issues)}",
                agent="system",
                data={
                    "issues": validation.issues,
                    "severity": validation.severity,
                },
            )
            return {
                "status": "invalid",
                "goal": plan_result.goal,
                "key_files": plan_result.key_files,
                "total_tasks": plan_result.total_tasks,
                "validation_issues": validation.issues,
            }

        await self._events.emit(
            workflow_id,
            EventType.PLAN_VALIDATED,
            f"Plan validated: {plan_result.goal}",
            agent="system",
            data={
                "goal": plan_result.goal,
                "key_files": plan_result.key_files,
                "total_tasks": plan_result.total_tasks,
            },
        )
        return {
            "status": "ready",
            "goal": plan_result.goal,
            "key_files": plan_result.key_files,
            "total_tasks": plan_result.total_tasks,
        }

    async def _get_review_verdicts(self, workflow_id: uuid.UUID) -> list[dict[str, Any]]:
        """Read the final review verdicts from the LangGraph checkpoint, if any.

        Best-effort: any checkpoint read failure returns an empty list.

        Args:
            workflow_id: Workflow whose checkpoint to inspect.

        Returns:
            ``[{persona, approved, severity}]`` projected from ``last_reviews``.
        """
        if self._checkpointer is None:
            return []
        try:
            graph = self.create_server_graph(self._checkpointer)
            snapshot = await graph.aget_state(
                {"configurable": {"thread_id": str(workflow_id)}}
            )
        except Exception:
            logger.warning(
                "Could not read review verdicts from checkpoint",
                workflow_id=workflow_id,
                exc_info=True,
            )
            return []
        values = snapshot.values if snapshot is not None else None
        raw_reviews = (values or {}).get("last_reviews") or []
        verdicts: list[dict[str, Any]] = []
        for review in raw_reviews:
            if isinstance(review, dict):
                persona = review.get("reviewer_persona")
                approved = review.get("approved")
                severity = review.get("severity")
            else:
                persona = getattr(review, "reviewer_persona", None)
                approved = getattr(review, "approved", None)
                severity = getattr(review, "severity", None)
            verdicts.append(
                {
                    "persona": persona,
                    "approved": approved,
                    "severity": getattr(severity, "value", severity),
                }
            )
        return verdicts

    async def finalize_trajectory(
        self,
        workflow_id: uuid.UUID,
        status: str,
        failure_reason: str | None = None,
    ) -> None:
        """Finalize and index the workflow's trajectory, if one is recording.

        Pops the recorder from the shared registry (idempotent across seams:
        whichever terminal seam runs first wins), writes the trajectory file
        with the outcome, and persists the thin index columns. Errors are
        logged and never propagate — finalization must not mask the workflow's
        own success or failure.

        Args:
            workflow_id: Workflow whose recorder to finalize.
            status: Terminal outcome status (``completed``/``failed``/``cancelled``).
            failure_reason: Outcome failure reason for failed workflows.
        """
        recorder = self._recorders.pop(workflow_id, None)
        if recorder is None:
            return
        try:
            outcome_extra: dict[str, Any] = {"pipeline": "implementation"}
            verdicts = await self._get_review_verdicts(workflow_id)
            if verdicts:
                outcome_extra["reviews"] = verdicts
            path = await recorder.finalize(
                status=status,
                failure_reason=failure_reason,
                outcome_extra=outcome_extra,
            )
            await self._repository.set_trajectory_index(
                workflow_id, path, recorder.final_metrics
            )
            logger.info(
                "Trajectory finalized",
                workflow_id=workflow_id,
                status=status,
                path=str(path),
            )
        except Exception:
            logger.exception(
                "Failed to finalize trajectory",
                workflow_id=workflow_id,
                status=status,
            )

    async def run_workflow(
        self,
        workflow_id: uuid.UUID,
        state: ServerExecutionState,
        sandbox_provider: "SandboxProvider | None" = None,
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
        profile_id = state.profile_id
        if profile_id is None:
            logger.error("No profile_id in ServerExecutionState", workflow_id=workflow_id)
            await self._repository.set_status(
                workflow_id, WorkflowStatus.FAILED, failure_reason="Missing profile_id"
            )
            return

        profile = await self.get_profile_or_fail(
            workflow_id, profile_id, state.worktree_path
        )
        if profile is None:
            return

        prompts = await self.resolve_prompts(workflow_id)

        # CRITICAL: Pass interrupt_before to enable server-mode approval
        graph = self.create_server_graph(self._checkpointer)

        config = self.build_runnable_config(workflow_id, profile, prompts, sandbox_provider)

        await self._events.emit(
            workflow_id,
            EventType.WORKFLOW_STARTED,
            "Workflow execution started",
            data={"issue_id": state.issue_id},
        )

        # Only set status to IN_PROGRESS if not already in that state.
        # This handles resumed workflows which are already IN_PROGRESS.
        workflow = await self._repository.get(workflow_id)
        if workflow and workflow.workflow_status != WorkflowStatus.IN_PROGRESS:
            await self._repository.set_status(workflow_id, WorkflowStatus.IN_PROGRESS)

        was_interrupted = False
        # Use astream with stream_mode="updates" to detect interrupts
        # astream_events does NOT surface __interrupt__ events

        # If we have an existing checkpoint, pass None to resume from it.
        # If no checkpoint, pass initial_state to start fresh.
        # This prevents the infinite loop bug where retries would restart
        # the workflow from review_iteration=0 instead of resuming.
        checkpoint_state = await graph.aget_state(config)
        if checkpoint_state is not None and checkpoint_state.values:
            logger.debug(
                "Resuming workflow from existing checkpoint",
                workflow_id=workflow_id,
                checkpoint_keys=list(checkpoint_state.values.keys())[:5],
            )
            input_state = None
        else:
            input_state = await self._reconstruct_initial_state(state, profile)

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
            if is_interrupt_chunk(chunk_tuple):
                was_interrupted = True
                _mode, _data = chunk_tuple
                # Sync plan from LangGraph checkpoint to ServerExecutionState
                # so it's available via REST API while blocked
                await self._sync_plan_from_checkpoint(workflow_id, graph, config)
                await self._events.emit(
                    workflow_id,
                    EventType.APPROVAL_REQUIRED,
                    "Plan ready for review - awaiting human approval",
                    agent="human_approval",
                    data={"paused_at": "human_approval_node"},
                )
                await self._repository.set_status(workflow_id, WorkflowStatus.BLOCKED)
                break
            await self._events.handle_combined_stream_chunk(workflow_id, chunk_tuple)

        if not was_interrupted:
            # Workflow completed without interruption (no human approval needed).
            # Note: A separate COMPLETED emission exists in approve_workflow() for
            # workflows that resume after human approval. These are mutually exclusive
            # code paths - only one COMPLETED event is ever emitted per workflow.

            await self._events.emit(
                workflow_id,
                EventType.WORKFLOW_COMPLETED,
                "Workflow completed successfully",
            )
            await self._repository.set_status(workflow_id, WorkflowStatus.COMPLETED)
            await self.finalize_trajectory(workflow_id, status="completed")

    async def run_workflow_with_retry(
        self,
        workflow_id: uuid.UUID,
        state: ServerExecutionState,
    ) -> None:
        """Execute workflow with automatic retry for transient failures.

        Args:
            workflow_id: The workflow ID.
            state: Server execution state.
        """
        profile_id = state.profile_id
        if profile_id is None:
            await self._repository.set_status(
                workflow_id, WorkflowStatus.FAILED, failure_reason="Missing profile_id"
            )
            return

        profile = await self.get_profile_or_fail(
            workflow_id, profile_id, state.worktree_path
        )
        if profile is None:
            return
        retry_config = profile.retry

        # Create shared sandbox provider if Daytona mode. The provider is
        # (re)created inside _attempt so a transient Daytona failure tears it
        # down and recreates it on the next retry. The outer finally guarantees
        # teardown after the final attempt (success or failure).
        sandbox_provider: SandboxProvider | None = None

        async def _attempt() -> None:
            nonlocal sandbox_provider
            try:
                # Create sandbox inside the attempt so transient Daytona
                # failures are retried (sandbox recreated on the next attempt).
                if sandbox_provider is None:
                    try:
                        sandbox_provider = await self.create_sandbox_provider(profile)
                    except ValueError:
                        raise  # Non-transient config errors fail immediately
                    except TRANSIENT_EXCEPTIONS:
                        raise  # Let with_retry apply retry logic
                    except Exception as e:
                        logger.exception("Daytona sandbox bootstrap failed", workflow_id=workflow_id)
                        await self._events.emit(
                            workflow_id,
                            EventType.WORKFLOW_FAILED,
                            f"Sandbox bootstrap failed: {e!s}",
                            data={"error": str(e), "error_type": "sandbox_bootstrap"},
                        )
                        await self._repository.set_status(
                            workflow_id, WorkflowStatus.FAILED, failure_reason=f"Sandbox bootstrap failed: {e}"
                        )
                        # Already emitted/recorded — wrap so the outer handler
                        # does not double-emit a non-transient failure.
                        raise _SandboxBootstrapHandled from e

                await self.run_workflow(workflow_id, state, sandbox_provider=sandbox_provider)
            except BaseException:
                # Tear down the sandbox so the next retry recreates it cleanly.
                if sandbox_provider is not None:
                    try:
                        await sandbox_provider.teardown()
                    except Exception:
                        logger.warning("Sandbox teardown failed during retry", exc_info=True)
                    sandbox_provider = None
                raise

        try:
            try:
                await with_retry(
                    _attempt,
                    config=retry_config,
                    retryable_exceptions=TRANSIENT_EXCEPTIONS,
                )
            except _SandboxBootstrapHandled as e:
                # Bootstrap failure already emitted WORKFLOW_FAILED + set FAILED.
                await self.finalize_trajectory(
                    workflow_id,
                    status="failed",
                    failure_reason=f"Sandbox bootstrap failed: {e.__cause__}",
                )
                return
            except TRANSIENT_EXCEPTIONS as e:
                # Retries exhausted. The total attempt count is 1 + max_retries.
                attempts = retry_config.max_retries + 1
                logger.exception("Workflow failed after retries exhausted", workflow_id=workflow_id)
                await self._events.emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Workflow failed after {attempts} attempts: {e!s}",
                    data={"error": str(e), "attempts": attempts},
                )
                await self._repository.set_status(
                    workflow_id,
                    WorkflowStatus.FAILED,
                    failure_reason=f"Failed after {attempts} attempts: {e}",
                )
                await self.finalize_trajectory(
                    workflow_id,
                    status="failed",
                    failure_reason=f"Failed after {attempts} attempts: {e}",
                )
                raise
            except Exception as e:
                # Non-transient error - fail immediately.
                logger.exception("Workflow failed with non-transient error", workflow_id=workflow_id)
                await self._events.emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Workflow failed: {e!s}",
                    data={"error": str(e), "error_type": "non-transient"},
                )
                await self._repository.set_status(
                    workflow_id, WorkflowStatus.FAILED, failure_reason=str(e)
                )
                await self.finalize_trajectory(
                    workflow_id, status="failed", failure_reason=str(e)
                )
                raise
        finally:
            if sandbox_provider is not None:
                try:
                    await sandbox_provider.teardown()
                except Exception:
                    logger.warning("Sandbox teardown failed", exc_info=True)

    async def resume_workflow_with_retry(
        self,
        workflow_id: uuid.UUID,
        profile_id: str | None,
        worktree_path: str,
    ) -> None:
        """Resume a post-approval workflow from checkpoint with retry.

        Updates the LangGraph checkpoint state with ``human_approved=True`` and
        streams from the existing checkpoint (``None`` input).  Uses the same
        retry/failure-ladder as ``run_workflow_with_retry`` so transient errors
        are retried and sandbox lifecycle is managed correctly.

        Args:
            workflow_id: The workflow to resume.
            profile_id: Profile ID; if ``None`` the workflow is failed immediately.
            worktree_path: Worktree path used to resolve the profile's repo root.
        """
        if profile_id is None:
            logger.error("No profile_id in workflow", workflow_id=workflow_id)
            await self._repository.set_status(
                workflow_id, WorkflowStatus.FAILED, failure_reason="Missing profile_id"
            )
            return

        profile = await self.get_profile_or_fail(workflow_id, profile_id, worktree_path)
        if profile is None:
            return

        retry_config = profile.retry
        sandbox_provider: SandboxProvider | None = None

        async def _resume() -> None:
            nonlocal sandbox_provider
            try:
                if sandbox_provider is None:
                    try:
                        sandbox_provider = await self.create_sandbox_provider(profile)
                    except ValueError:
                        raise  # Non-transient config errors fail immediately
                    except TRANSIENT_EXCEPTIONS:
                        raise  # Let with_retry apply retry logic
                    except Exception as e:
                        logger.exception("Daytona sandbox bootstrap failed", workflow_id=workflow_id)
                        await self._events.emit(
                            workflow_id,
                            EventType.WORKFLOW_FAILED,
                            f"Sandbox bootstrap failed: {e!s}",
                            data={"error": str(e), "error_type": "sandbox_bootstrap"},
                        )
                        await self._repository.set_status(
                            workflow_id,
                            WorkflowStatus.FAILED,
                            failure_reason=f"Sandbox bootstrap failed: {e}",
                        )
                        raise _SandboxBootstrapHandled from e

                prompts = await self.resolve_prompts(workflow_id)
                graph = self.create_server_graph(self._checkpointer)
                config = self.build_runnable_config(workflow_id, profile, prompts, sandbox_provider)

                # Inject the approval decision into the checkpoint before resuming.
                await graph.aupdate_state(config, {"human_approved": True})

                async for chunk in graph.astream(
                    None,  # Resume from checkpoint, no new input needed
                    config=config,
                    stream_mode=["updates", "tasks"],
                ):
                    chunk_tuple = cast(tuple[str, Any], chunk)
                    # In agentic mode, no interrupts expected after initial approval
                    if is_interrupt_chunk(chunk_tuple):
                        _, _data = chunk_tuple
                        state = await graph.aget_state(config)
                        next_nodes = state.next if state else []
                        logger.warning(
                            "Unexpected interrupt after approval",
                            workflow_id=workflow_id,
                            next_nodes=next_nodes,
                        )
                        continue
                    await self._events.handle_combined_stream_chunk(workflow_id, chunk_tuple)

                # Workflow completed after human approval.
                # Note: A separate COMPLETED emission exists in run_workflow() for
                # workflows that complete without interruption. These are mutually
                # exclusive code paths — only one COMPLETED event is emitted per workflow.
                await self._events.emit(
                    workflow_id,
                    EventType.WORKFLOW_COMPLETED,
                    "Workflow completed successfully",
                )
                await self._repository.set_status(workflow_id, WorkflowStatus.COMPLETED)
                await self.finalize_trajectory(workflow_id, status="completed")
            except BaseException:
                # Tear down the sandbox so the next retry recreates it cleanly.
                if sandbox_provider is not None:
                    try:
                        await sandbox_provider.teardown()
                    except Exception:
                        logger.warning("Sandbox teardown failed during retry", exc_info=True)
                    sandbox_provider = None
                raise

        try:
            try:
                await with_retry(
                    _resume,
                    config=retry_config,
                    retryable_exceptions=TRANSIENT_EXCEPTIONS,
                )
            except _SandboxBootstrapHandled as e:
                # Bootstrap failure already emitted WORKFLOW_FAILED + set FAILED.
                await self.finalize_trajectory(
                    workflow_id,
                    status="failed",
                    failure_reason=f"Sandbox bootstrap failed: {e.__cause__}",
                )
                return
            except TRANSIENT_EXCEPTIONS as e:
                attempts = retry_config.max_retries + 1
                logger.exception(
                    "Workflow failed after approval retries exhausted",
                    workflow_id=workflow_id,
                )
                await self._events.emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Workflow failed after {attempts} attempts: {e!s}",
                    data={"error": str(e), "attempts": attempts},
                )
                await self._repository.set_status(
                    workflow_id,
                    WorkflowStatus.FAILED,
                    failure_reason=f"Failed after {attempts} attempts: {e}",
                )
                await self.finalize_trajectory(
                    workflow_id,
                    status="failed",
                    failure_reason=f"Failed after {attempts} attempts: {e}",
                )
                raise
            except Exception as e:
                logger.exception("Workflow failed after approval", workflow_id=workflow_id)
                await self._events.emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Workflow failed: {e!s}",
                    data={"error": str(e)},
                )
                await self._repository.set_status(
                    workflow_id, WorkflowStatus.FAILED, failure_reason=str(e)
                )
                await self.finalize_trajectory(
                    workflow_id, status="failed", failure_reason=str(e)
                )
                raise
        finally:
            if sandbox_provider is not None:
                try:
                    await sandbox_provider.teardown()
                except Exception:
                    logger.warning("Sandbox teardown failed", exc_info=True)

    async def run_review_workflow(
        self,
        workflow_id: uuid.UUID,
        state: ServerExecutionState,
        execution_state: ImplementationState,
        review_mode: str = "review_fix",
        review_types: list[str] | None = None,
    ) -> None:
        """Run the review-fix workflow graph.

        Similar to run_workflow but uses review graph and no approval pauses.
        The graph runs autonomously until approved or max iterations reached.

        Args:
            workflow_id: The workflow ID.
            state: Server execution state (for worktree path etc).
            execution_state: The ImplementationState for graph input.
            review_mode: "review_only" or "review_fix".
            review_types: Optional list of review types to run.
        """
        # Get profile from settings using profile_id
        if state.profile_id is None:
            logger.error("No profile_id in ServerExecutionState", workflow_id=workflow_id)
            await self._repository.set_status(
                workflow_id, WorkflowStatus.FAILED, failure_reason="Missing profile_id"
            )
            return

        profile = await self.get_profile_or_fail(
            workflow_id, state.profile_id, state.worktree_path
        )
        if profile is None:
            return

        prompts = await self.resolve_prompts(workflow_id)

        graph = create_review_graph(
            checkpointer=self._checkpointer,
        )

        sandbox_provider: SandboxProvider | None = None
        try:
            try:
                sandbox_provider = await self.create_sandbox_provider(profile)

                config = self.build_runnable_config(
                    workflow_id, profile, prompts, sandbox_provider,
                    review_mode=review_mode, review_types=review_types,
                )
            except Exception as e:
                logger.exception("Review workflow setup failed", workflow_id=workflow_id)
                await self._events.emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Review workflow setup failed: {e}",
                    data={"error": str(e), "error_type": "setup"},
                )
                await self._repository.set_status(
                    workflow_id, WorkflowStatus.FAILED, failure_reason=f"Setup failed: {e}"
                )
                return

            await self._events.emit(
                workflow_id,
                EventType.WORKFLOW_STARTED,
                "Review workflow started",
                data={"issue_id": state.issue_id, "workflow_type": "review"},
            )

            try:
                await self._repository.set_status(workflow_id, WorkflowStatus.IN_PROGRESS)

                initial_state = execution_state.model_dump(mode="json")

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
                    if is_interrupt_chunk(chunk_tuple):
                        mode, data = chunk_tuple
                        logger.warning(
                            "Unexpected interrupt in review workflow",
                            workflow_id=workflow_id,
                        )
                        await self._events.emit(
                            workflow_id,
                            EventType.WORKFLOW_FAILED,
                            "Review workflow aborted due to unexpected interrupt",
                            data={"error": "unexpected_interrupt"},
                        )
                        await self._repository.set_status(
                            workflow_id,
                            WorkflowStatus.FAILED,
                            failure_reason="Unexpected interrupt in review workflow",
                        )
                        return
                    await self._events.handle_combined_stream_chunk(workflow_id, chunk_tuple)

                await self._events.emit(
                    workflow_id,
                    EventType.WORKFLOW_COMPLETED,
                    "Review workflow completed",
                )
                await self._repository.set_status(workflow_id, WorkflowStatus.COMPLETED)

            except Exception as e:
                logger.exception("Review workflow failed", workflow_id=workflow_id)
                await self._events.emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Review workflow failed: {e}",
                    data={"error": str(e)},
                )
                await self._repository.set_status(
                    workflow_id, WorkflowStatus.FAILED, failure_reason=str(e)
                )
        finally:
            if sandbox_provider is not None:
                try:
                    await sandbox_provider.teardown()
                except Exception:
                    logger.warning("Sandbox teardown failed", exc_info=True)

    async def validate_resume_checkpoint(
        self,
        workflow_id: uuid.UUID,
        workflow_status: "WorkflowStatus",
    ) -> None:
        """Validate that a resumable checkpoint exists for *workflow_id*.

        Reads the LangGraph checkpoint state (read-only) and raises
        ``InvalidStateError`` if the checkpoint is missing or corrupted.

        Args:
            workflow_id: The workflow whose checkpoint to validate.
            workflow_status: The current workflow status (used in error messages).

        Raises:
            InvalidStateError: If the checkpoint data is absent or corrupted.
        """
        from amelia.server.exceptions import InvalidStateError  # noqa: PLC0415

        graph = self.create_server_graph(self._checkpointer)
        config: RunnableConfig = {"configurable": {"thread_id": str(workflow_id)}}
        try:
            checkpoint_state = await graph.aget_state(config)
        except Exception as exc:
            raise InvalidStateError(
                f"Cannot resume: checkpoint data is corrupted ({type(exc).__name__}: {exc})",
                workflow_id=workflow_id,
                current_status=workflow_status,
            ) from exc
        if checkpoint_state is None or not checkpoint_state.values:
            raise InvalidStateError(
                "Cannot resume: no checkpoint found for workflow",
                workflow_id=workflow_id,
                current_status=workflow_status,
            )

    async def record_rejection(
        self,
        workflow_id: uuid.UUID,
        profile_id: str | None,
        worktree_path: str,
    ) -> None:
        """Write ``human_approved=False`` into the LangGraph checkpoint.

        Called by the service after a rejection has been persisted to the
        repository and the waiting task has been cancelled. Failure is
        warn-and-continue: the checkpoint write is best-effort — the workflow
        is already in FAILED state when this runs.

        Args:
            workflow_id: The rejected workflow.
            profile_id: Profile ID; if ``None`` the update is skipped and an
                error is logged (matching the pre-extraction behaviour).
            worktree_path: Worktree path for profile resolution.
        """
        if profile_id is None:
            logger.error("No profile_id in workflow", workflow_id=workflow_id)
            return
        profile = await self.get_profile_or_fail(workflow_id, profile_id, worktree_path)
        if profile is None:
            return
        graph = self.create_server_graph(self._checkpointer)
        config = self.build_runnable_config(workflow_id, profile, prompts={})
        await graph.aupdate_state(config, {"human_approved": False})

    async def run_planning_task(
        self,
        workflow_id: uuid.UUID,
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
        prompts = await self.resolve_prompts(workflow_id)

        graph = self.create_server_graph(self._checkpointer)

        sandbox_provider: SandboxProvider | None = None
        try:
            sandbox_provider = await self.create_sandbox_provider(profile, agent_name="architect")

            config = self.build_runnable_config(workflow_id, profile, prompts, sandbox_provider)

            was_interrupted = False
            input_state = execution_state.model_dump(mode="json")

            async for chunk in graph.astream(
                input_state,
                config=config,
                stream_mode=["updates", "tasks"],
            ):
                chunk_tuple = cast(tuple[str, Any], chunk)
                if is_interrupt_chunk(chunk_tuple):
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

                    await self._events.emit(
                        workflow_id,
                        EventType.APPROVAL_REQUIRED,
                        "Plan ready for review - awaiting human approval",
                        agent="human_approval",
                        data={"paused_at": "human_approval_node"},
                    )

                    break

                await self._events.handle_combined_stream_chunk(workflow_id, chunk_tuple)

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

            await self._events.emit(
                workflow_id,
                EventType.WORKFLOW_FAILED,
                f"Planning failed: {e}",
                data={"error": str(e)},
            )
            await self.finalize_trajectory(
                workflow_id, status="failed", failure_reason=f"Planning failed: {e}"
            )

            logger.error(
                "Planning task failed",
                workflow_id=workflow_id,
                error=str(e),
            )
        finally:
            if sandbox_provider is not None:
                try:
                    await sandbox_provider.teardown()
                except Exception:
                    logger.warning("Sandbox teardown failed", exc_info=True)
