"""PR auto-fix orchestrator with per-PR concurrency, cooldown, and divergence recovery.

Sits between trigger points (CLI/API, polling) and the fix pipeline.
Prevents race conditions, infinite loops, and branch corruption.
"""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from loguru import logger

from amelia.core.types import PRAutoFixConfig, Profile
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.services.github_pr import GitHubPRService
from amelia.tools.git_utils import GitOperations


# Maximum divergence retries per trigger (2 retries = 3 total attempts)
_MAX_DIVERGENCE_RETRIES: int = 2

_FINAL_FAILURE_MESSAGE: str = (
    "Could not apply fixes -- PR branch changed during fix attempt. "
    "Will retry on next cycle."
)


class PRAutoFixOrchestrator:
    """Orchestrates PR auto-fix cycles with concurrency control and safety.

    Responsibilities:
    - Per-PR locking so only one fix cycle runs per PR at a time
    - Pending flag (latest wins) for concurrent triggers on the same PR
    - Cooldown timer between pending cycles with reset-on-new-comments
    - Divergence recovery with retry on push failures
    - Repo-level git serialization across PRs sharing the same repo_path
    """

    def __init__(
        self,
        event_bus: EventBus,
        github_pr_service: GitHubPRService,
    ) -> None:
        self._event_bus = event_bus
        self._github_pr_service = github_pr_service

        # Per-PR concurrency control
        self._pr_locks: dict[int, asyncio.Lock] = {}
        self._pr_pending: dict[int, bool] = {}

        # Cooldown interruption
        self._cooldown_events: dict[int, asyncio.Event] = {}

        # Repo-level git serialization (keyed by repo_path)
        self._repo_locks: dict[str, asyncio.Lock] = {}

        # Per-PR synthetic workflow IDs for orchestration events
        self._pr_workflow_ids: dict[int, UUID] = {}

    def _get_pr_lock(self, pr_number: int) -> asyncio.Lock:
        """Get or create the per-PR asyncio lock."""
        if pr_number not in self._pr_locks:
            self._pr_locks[pr_number] = asyncio.Lock()
        return self._pr_locks[pr_number]

    def _get_repo_lock(self, repo_path: str) -> asyncio.Lock:
        """Get or create the repo-level asyncio lock for git serialization."""
        if repo_path not in self._repo_locks:
            self._repo_locks[repo_path] = asyncio.Lock()
        return self._repo_locks[repo_path]

    def _get_workflow_id(self, pr_number: int) -> UUID:
        """Get or create a synthetic workflow ID for orchestration events."""
        if pr_number not in self._pr_workflow_ids:
            self._pr_workflow_ids[pr_number] = uuid4()
        return self._pr_workflow_ids[pr_number]

    async def trigger_fix_cycle(
        self,
        pr_number: int,
        repo: str,
        profile: Profile,
        config: PRAutoFixConfig | None = None,
    ) -> None:
        """Trigger a fix cycle for a PR with concurrency control.

        If a cycle is already running for this PR, sets the pending flag
        and returns immediately. The running cycle will pick up the pending
        work after completing (with cooldown in between).

        Args:
            pr_number: GitHub PR number.
            repo: Repository in 'owner/repo' format.
            profile: Execution profile with repo_root and config.
            config: Optional config override (defaults to profile.pr_autofix).
        """
        effective_config = config or profile.pr_autofix or PRAutoFixConfig()
        lock = self._get_pr_lock(pr_number)

        if lock.locked():
            # Already running -- set pending flag (latest wins, no accumulation)
            self._pr_pending[pr_number] = True
            # If in cooldown, reset the timer
            if pr_number in self._cooldown_events:
                self._cooldown_events[pr_number].set()
                self._emit_event(
                    EventType.PR_FIX_COOLDOWN_RESET,
                    pr_number,
                    f"Cooldown timer reset for PR #{pr_number} (new comment arrived)",
                )
            self._emit_event(
                EventType.PR_FIX_QUEUED,
                pr_number,
                f"Fix cycle queued for PR #{pr_number}",
            )
            logger.info(
                "Fix cycle queued (already running)",
                pr_number=pr_number,
            )
            return

        async with lock:
            await self._run_fix_cycle(
                pr_number=pr_number,
                repo=repo,
                profile=profile,
                config=effective_config,
            )

            # Process pending cycle if any (with cooldown between)
            while self._pr_pending.pop(pr_number, False):
                await self._run_cooldown(pr_number, effective_config)
                await self._run_fix_cycle(
                    pr_number=pr_number,
                    repo=repo,
                    profile=profile,
                    config=effective_config,
                )

    async def _run_fix_cycle(
        self,
        pr_number: int,
        repo: str,
        profile: Profile,
        config: PRAutoFixConfig,
    ) -> None:
        """Run a single fix cycle with divergence recovery.

        Fetches and resets to remote HEAD before running the pipeline.
        On divergence, retries up to _MAX_DIVERGENCE_RETRIES times.

        Args:
            pr_number: GitHub PR number.
            repo: Repository in 'owner/repo' format.
            profile: Execution profile.
            config: Auto-fix configuration.
        """
        head_branch = ""  # Will be set from PR metadata in real usage

        for attempt in range(_MAX_DIVERGENCE_RETRIES + 1):
            try:
                # Git operations serialized per repo
                repo_lock = self._get_repo_lock(profile.repo_root)
                async with repo_lock:
                    git_ops = GitOperations(profile.repo_root)
                    await self._reset_to_remote(git_ops, head_branch)

                # Run the pipeline (classify -> develop -> commit -> push -> resolve)
                await self._execute_pipeline(pr_number, repo, profile, config)
                return  # Success

            except ValueError as exc:
                if "diverged" not in str(exc).lower():
                    # Non-divergence error -- log and return (don't retry)
                    logger.error(
                        "Fix cycle failed with non-divergence error",
                        pr_number=pr_number,
                        error=str(exc),
                    )
                    return

                if attempt < _MAX_DIVERGENCE_RETRIES:
                    self._emit_event(
                        EventType.PR_FIX_DIVERGED,
                        pr_number,
                        f"Branch diverged for PR #{pr_number}, retrying ({attempt + 1}/{_MAX_DIVERGENCE_RETRIES})",
                        data={"attempt": attempt + 1, "max_retries": _MAX_DIVERGENCE_RETRIES},
                    )
                    logger.warning(
                        "Branch diverged, retrying",
                        pr_number=pr_number,
                        attempt=attempt + 1,
                    )
                else:
                    # Final failure -- all retries exhausted
                    self._emit_event(
                        EventType.PR_FIX_RETRIES_EXHAUSTED,
                        pr_number,
                        f"All divergence retries exhausted for PR #{pr_number}",
                        data={"total_attempts": _MAX_DIVERGENCE_RETRIES + 1},
                    )
                    logger.error(
                        "Divergence retries exhausted",
                        pr_number=pr_number,
                        total_attempts=_MAX_DIVERGENCE_RETRIES + 1,
                    )
                    await self._post_final_failure_comment(repo, pr_number)

            except Exception as exc:
                logger.error(
                    "Fix cycle failed with unexpected error",
                    pr_number=pr_number,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                return

    async def _execute_pipeline(
        self,
        pr_number: int,
        repo: str,
        profile: Profile,
        config: PRAutoFixConfig,
    ) -> None:
        """Execute the PR auto-fix pipeline.

        This method exists as a seam for testing -- tests mock this
        to verify orchestration logic without running the real pipeline.
        """
        # Real implementation will create and run PRAutoFixPipeline
        # This is the integration point for Phase 7-8 triggers
        raise NotImplementedError("Pipeline execution not yet wired up")

    async def _run_cooldown(
        self,
        pr_number: int,
        config: PRAutoFixConfig,
    ) -> None:
        """Wait for cooldown period between pending cycles.

        Uses asyncio.Event for interruptible wait. Timer resets when
        a new trigger arrives (sets the event), but respects
        max_cooldown_seconds as an absolute cap.

        Args:
            pr_number: PR number for cooldown tracking.
            config: Configuration with cooldown durations.
        """
        cooldown_seconds = config.post_push_cooldown_seconds
        max_cooldown = config.max_cooldown_seconds

        if cooldown_seconds == 0 and max_cooldown == 0:
            return  # No cooldown configured

        self._emit_event(
            EventType.PR_FIX_COOLDOWN_STARTED,
            pr_number,
            f"Cooldown started for PR #{pr_number} ({cooldown_seconds}s, max {max_cooldown}s)",
            data={"cooldown_seconds": cooldown_seconds, "max_cooldown_seconds": max_cooldown},
        )

        event = asyncio.Event()
        self._cooldown_events[pr_number] = event
        loop = asyncio.get_event_loop()
        absolute_deadline = loop.time() + max_cooldown

        remaining = cooldown_seconds
        while remaining > 0:
            cap = min(remaining, absolute_deadline - loop.time())
            if cap <= 0:
                break
            event.clear()
            try:
                await asyncio.wait_for(event.wait(), timeout=cap)
                # Event was set -- new comment arrived, reset timer
                remaining = cooldown_seconds
                logger.info(
                    "Cooldown timer reset by new trigger",
                    pr_number=pr_number,
                    remaining=remaining,
                )
            except TimeoutError:
                # Timer expired naturally
                break

        self._cooldown_events.pop(pr_number, None)

    async def _reset_to_remote(
        self,
        git_ops: GitOperations,
        branch: str,
    ) -> None:
        """Fetch remote and hard reset to remote HEAD.

        Args:
            git_ops: GitOperations instance for the repo.
            branch: Branch name to reset to.
        """
        await git_ops._run_git("fetch", "origin")
        if branch:
            await git_ops._run_git("checkout", branch)
            await git_ops._run_git("reset", "--hard", f"origin/{branch}")

    async def _post_final_failure_comment(
        self,
        repo: str,
        pr_number: int,
    ) -> None:
        """Post a GitHub PR comment when all divergence retries are exhausted.

        Args:
            repo: Repository in 'owner/repo' format.
            pr_number: PR number to comment on.
        """
        try:
            await self._github_pr_service.create_issue_comment(
                repo=repo,
                pr_number=pr_number,
                body=_FINAL_FAILURE_MESSAGE,
            )
        except Exception as exc:
            # Non-fatal: dashboard event was already emitted
            logger.warning(
                "Failed to post divergence failure comment to PR",
                pr_number=pr_number,
                error=str(exc),
            )

    def _emit_event(
        self,
        event_type: EventType,
        pr_number: int,
        message: str,
        data: dict[str, object] | None = None,
    ) -> None:
        """Create and emit a workflow event for orchestration state changes.

        Args:
            event_type: The event type to emit.
            pr_number: PR number for context.
            message: Human-readable message.
            data: Optional structured payload.
        """
        event_data: dict[str, object] = {"pr_number": pr_number}
        if data:
            event_data.update(data)

        event = WorkflowEvent(
            id=uuid4(),
            workflow_id=self._get_workflow_id(pr_number),
            sequence=0,  # Orchestration events don't need sequence ordering
            timestamp=datetime.now(UTC),
            agent="pr_auto_fix",
            event_type=event_type,
            message=message,
            data=event_data,
        )
        self._event_bus.emit(event)
