"""PR auto-fix orchestrator with per-PR concurrency, cooldown, and divergence recovery.

Sits between trigger points (CLI/API, polling) and the fix pipeline.
Prevents race conditions, infinite loops, and branch corruption.
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from loguru import logger

from amelia.core.types import PRAutoFixConfig, Profile
from amelia.pipelines.pr_auto_fix.pipeline import PRAutoFixPipeline
from amelia.pipelines.pr_auto_fix.state import GroupFixStatus
from amelia.server.database import MetricsRepository, WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.models.state import (
    ServerExecutionState,
    WorkflowStatus,
    WorkflowType,
)
from amelia.services.classifier import get_prompt_hash
from amelia.services.github_pr import GitHubPRService
from amelia.tools.git_utils import GitOperations


# Maximum divergence retries per trigger (2 retries = 3 total attempts)
_MAX_DIVERGENCE_RETRIES: int = 2

_FINAL_FAILURE_MESSAGE: str = (
    "Could not apply fixes -- PR branch changed during fix attempt. Will retry on next cycle."
)


class PRAutoFixOrchestrator:
    """Orchestrates PR auto-fix cycles with concurrency control and safety.

    Responsibilities:
    - Per-PR locking so only one fix cycle runs per PR at a time
    - Pending flag (latest wins) for concurrent triggers on the same PR
    - Cooldown timer between pending cycles with reset-on-new-comments
    - Divergence recovery with retry on push failures
    - Repo-level git serialization across PRs sharing the same repo_path
    - Workflow DB record creation for dashboard visibility
    """

    def __init__(
        self,
        event_bus: EventBus,
        github_pr_service: GitHubPRService,
        workflow_repo: WorkflowRepository | None = None,
        metrics_repo: MetricsRepository | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._github_pr_service = github_pr_service
        self._workflow_repo = workflow_repo
        self._metrics_repo = metrics_repo

        # Per-PR concurrency control (keyed by (repo, pr_number))
        self._pr_locks: dict[tuple[str, int], asyncio.Lock] = {}
        self._pr_pending: dict[tuple[str, int], bool] = {}

        # Cooldown interruption
        self._cooldown_events: dict[tuple[str, int], asyncio.Event] = {}

        # Repo-level git serialization (keyed by repo_path)
        self._repo_locks: dict[str, asyncio.Lock] = {}

        # Per-PR synthetic workflow IDs for orchestration events
        self._pr_workflow_ids: dict[tuple[str, int], UUID] = {}

    def _get_pr_lock(self, repo: str, pr_number: int) -> asyncio.Lock:
        """Get or create the per-PR asyncio lock."""
        key = (repo, pr_number)
        if key not in self._pr_locks:
            self._pr_locks[key] = asyncio.Lock()
        return self._pr_locks[key]

    def _get_repo_lock(self, repo_path: str) -> asyncio.Lock:
        """Get or create the repo-level asyncio lock for git serialization."""
        if repo_path not in self._repo_locks:
            self._repo_locks[repo_path] = asyncio.Lock()
        return self._repo_locks[repo_path]

    def get_workflow_id(self, repo: str, pr_number: int) -> UUID:
        """Get or create a synthetic workflow ID for orchestration events."""
        key = (repo, pr_number)
        if key not in self._pr_workflow_ids:
            self._pr_workflow_ids[key] = uuid4()
        return self._pr_workflow_ids[key]

    async def trigger_fix_cycle(
        self,
        pr_number: int,
        repo: str,
        profile: Profile,
        head_branch: str = "",
        config: PRAutoFixConfig | None = None,
        pr_title: str = "",
    ) -> None:
        """Trigger a fix cycle for a PR with concurrency control.

        If a cycle is already running for this PR, sets the pending flag
        and returns immediately. The running cycle will pick up the pending
        work after completing (with cooldown in between).

        Args:
            pr_number: GitHub PR number.
            repo: Repository in 'owner/repo' format.
            profile: Execution profile with repo_root and config.
            head_branch: PR head branch name. Empty string skips checkout/reset
                (deferred to Phase 7).
            config: Optional config override (defaults to profile.pr_autofix).
            pr_title: PR title from the poller (avoids re-fetching).
        """
        effective_config = config or profile.pr_autofix or PRAutoFixConfig()
        key = (repo, pr_number)
        lock = self._get_pr_lock(repo, pr_number)

        if lock.locked():
            # Already running -- set pending flag (latest wins, no accumulation)
            self._pr_pending[key] = True
            # If in cooldown, reset the timer
            if key in self._cooldown_events:
                self._cooldown_events[key].set()
                self._emit_event(
                    EventType.PR_FIX_COOLDOWN_RESET,
                    pr_number,
                    f"Cooldown timer reset for PR #{pr_number} (new comment arrived)",
                    repo=repo,
                )
            self._emit_event(
                EventType.PR_FIX_QUEUED,
                pr_number,
                f"Fix cycle queued for PR #{pr_number}",
                repo=repo,
            )
            logger.info(
                "Fix cycle queued (already running)",
                pr_number=pr_number,
            )
            return

        effective_title = pr_title or f"PR #{pr_number}"

        async with lock:
            await self._run_fix_cycle(
                pr_number=pr_number,
                repo=repo,
                profile=profile,
                config=effective_config,
                head_branch=head_branch,
                pr_title=effective_title,
            )

            # Process pending cycle if any (with cooldown between)
            while self._pr_pending.pop(key, False):
                await self._run_cooldown(repo, pr_number, effective_config)
                await self._run_fix_cycle(
                    pr_number=pr_number,
                    repo=repo,
                    profile=profile,
                    config=effective_config,
                    head_branch=head_branch,
                    pr_title=effective_title,
                )

    async def _run_fix_cycle(
        self,
        pr_number: int,
        repo: str,
        profile: Profile,
        config: PRAutoFixConfig,
        head_branch: str = "",
        pr_title: str = "",
    ) -> None:
        """Run a single fix cycle with divergence recovery.

        Fetches and resets to remote HEAD before running the pipeline.
        On divergence, retries up to _MAX_DIVERGENCE_RETRIES times.

        Args:
            pr_number: GitHub PR number.
            repo: Repository in 'owner/repo' format.
            profile: Execution profile.
            config: Auto-fix configuration.
            head_branch: PR head branch name. Empty string skips checkout/reset
                (deferred to Phase 7).
        """

        for attempt in range(_MAX_DIVERGENCE_RETRIES + 1):
            try:
                # Git operations serialized per repo — hold the lock for the
                # entire cycle so another PR cannot switch branches mid-run.
                repo_lock = self._get_repo_lock(profile.repo_root)
                async with repo_lock:
                    git_ops = GitOperations(profile.repo_root)
                    await self._reset_to_remote(git_ops, head_branch)

                    # Run the pipeline (classify -> develop -> commit -> push -> resolve)
                    await self._execute_pipeline(
                        pr_number, repo, profile, config, head_branch, pr_title=pr_title
                    )
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
                        repo=repo,
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
                        repo=repo,
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
        head_branch: str = "",
        pr_title: str = "",
    ) -> None:
        """Execute the PR auto-fix pipeline with workflow record tracking.

        Creates a workflow DB record before pipeline execution and updates
        it with results after completion or failure. Emits lifecycle events.

        Args:
            pr_number: GitHub PR number.
            repo: Repository in 'owner/repo' format.
            profile: Execution profile.
            config: Auto-fix configuration.
            head_branch: PR head branch name.
            pr_title: PR title (passed from poller to avoid re-fetching).
        """
        pr_title = pr_title or f"PR #{pr_number}"

        # Create workflow record for dashboard visibility
        workflow_id = uuid4()
        now = datetime.now(UTC)
        issue_cache: dict[str, Any] = {
            "pr_number": pr_number,
            "pr_title": pr_title,
            "comment_count": 0,  # Updated after pipeline if data available
            "repo": repo,
            "head_branch": head_branch,
        }

        state = ServerExecutionState(
            id=workflow_id,
            issue_id=f"PR-{pr_number}",
            worktree_path=profile.repo_root,
            workflow_type=WorkflowType.PR_AUTO_FIX,
            profile_id=profile.name,
            workflow_status=WorkflowStatus.IN_PROGRESS,
            started_at=now,
            issue_cache=issue_cache,
        )

        if self._workflow_repo is not None:
            await self._workflow_repo.create(state)

        # Emit started event
        self._emit_event(
            EventType.PR_AUTO_FIX_STARTED,
            pr_number,
            f"PR auto-fix started for PR #{pr_number}",
            data={"workflow_id": str(workflow_id)},
            repo=repo,
        )

        try:
            # Run the pipeline with timing
            start_time = time.monotonic()

            pipeline = PRAutoFixPipeline()
            graph = pipeline.create_graph()
            initial_state = pipeline.get_initial_state(
                workflow_id=self.get_workflow_id(repo, pr_number),
                profile_id=profile.name,
                pr_number=pr_number,
                head_branch=head_branch,
                repo=repo,
            )
            final_state = await graph.ainvoke(
                initial_state,
                config={
                    "configurable": {
                        "thread_id": str(workflow_id),
                        "profile": profile,
                        "event_bus": self._event_bus,
                        "metrics_repo": self._metrics_repo,
                        "metrics_run_id": str(workflow_id),
                    },
                },
            )

            duration_seconds = time.monotonic() - start_time

            # Build pr_comments from final state for issue_cache
            pr_comments = self._build_pr_comments(final_state)
            comments_raw = final_state.get("comments", []) if isinstance(final_state, dict) else []
            issue_cache["comment_count"] = len(comments_raw)
            issue_cache["pr_comments"] = pr_comments

            # Update workflow record as completed
            state = state.model_copy(
                update={
                    "workflow_status": WorkflowStatus.COMPLETED,
                    "completed_at": datetime.now(UTC),
                    "issue_cache": issue_cache,
                },
            )
            if self._workflow_repo is not None:
                await self._workflow_repo.update(state)

            # Persist run metrics (isolated -- failure does not crash pipeline)
            if self._metrics_repo is not None:
                try:
                    group_results = (
                        final_state.get("group_results", [])
                        if isinstance(final_state, dict)
                        else []
                    )
                    resolution_results = (
                        final_state.get("resolution_results", [])
                        if isinstance(final_state, dict)
                        else []
                    )

                    # Count per-comment (iterate comment_ids, not groups -- Pitfall 3)
                    fixed = 0
                    failed = 0
                    for result in group_results:
                        result_dict = (
                            result
                            if isinstance(result, dict)
                            else result.model_dump()
                            if hasattr(result, "model_dump")
                            else {}
                        )
                        status = result_dict.get("status", "")
                        comment_count = len(result_dict.get("comment_ids", []))
                        if status == GroupFixStatus.FIXED:
                            fixed += comment_count
                        elif status == GroupFixStatus.FAILED:
                            failed += comment_count

                    comments_processed = len(comments_raw)
                    skipped = comments_processed - fixed - failed

                    commits_pushed = (
                        1
                        if (isinstance(final_state, dict) and final_state.get("commit_sha"))
                        else 0
                    )

                    threads_resolved = sum(
                        1
                        for r in resolution_results
                        if (
                            r
                            if isinstance(r, dict)
                            else r.model_dump()
                            if hasattr(r, "model_dump")
                            else {}
                        ).get("resolved", False)
                    )

                    run_id = uuid4()
                    prompt_hash = get_prompt_hash(config.aggressiveness.name)

                    await self._metrics_repo.save_run_metrics(
                        run_id=run_id,
                        workflow_id=workflow_id,
                        profile_id=profile.name,
                        pr_number=pr_number,
                        aggressiveness_level=config.aggressiveness.name,
                        comments_processed=comments_processed,
                        fixes_applied=fixed,
                        fixes_failed=failed,
                        fixes_skipped=skipped,
                        commits_pushed=commits_pushed,
                        threads_resolved=threads_resolved,
                        duration_seconds=duration_seconds,
                        prompt_hash=prompt_hash,
                    )
                except Exception as metrics_exc:
                    logger.warning(
                        "Failed to persist run metrics (non-fatal)",
                        pr_number=pr_number,
                        error=str(metrics_exc),
                    )

            # Emit completed event
            self._emit_event(
                EventType.PR_AUTO_FIX_COMPLETED,
                pr_number,
                f"PR auto-fix completed for PR #{pr_number}",
                data={"workflow_id": str(workflow_id)},
                repo=repo,
            )

        except Exception as exc:
            # Update workflow record as failed
            state = state.model_copy(
                update={
                    "workflow_status": WorkflowStatus.FAILED,
                    "completed_at": datetime.now(UTC),
                    "failure_reason": str(exc),
                },
            )
            if self._workflow_repo is not None:
                await self._workflow_repo.update(state)
            raise

    def _build_pr_comments(self, final_state: Any) -> list[dict[str, Any]]:
        """Build pr_comments list from pipeline final state.

        Extracts comments and their resolution status from the final
        pipeline state for storage in issue_cache.

        Args:
            final_state: Final state dict from graph.ainvoke().

        Returns:
            List of comment dicts with resolution status.
        """
        if not isinstance(final_state, dict):
            return []

        comments = final_state.get("comments", [])
        group_results = final_state.get("group_results", [])
        resolution_results = final_state.get("resolution_results", [])

        # Build lookup maps
        # comment_id -> group fix status
        comment_fix_status: dict[int, str] = {}
        for result in group_results:
            result_dict = (
                result
                if isinstance(result, dict)
                else result.model_dump()
                if hasattr(result, "model_dump")
                else {}
            )
            for cid in result_dict.get("comment_ids", []):
                comment_fix_status[cid] = result_dict.get("status", "unknown")

        # comment_id -> resolution result
        resolution_map: dict[int, dict[str, Any]] = {}
        for result in resolution_results:
            result_dict = (
                result
                if isinstance(result, dict)
                else result.model_dump()
                if hasattr(result, "model_dump")
                else {}
            )
            cid = result_dict.get("comment_id")
            if cid is not None:
                resolution_map[cid] = result_dict

        pr_comments: list[dict[str, Any]] = []
        for comment in comments:
            comment_dict = (
                comment
                if isinstance(comment, dict)
                else comment.model_dump()
                if hasattr(comment, "model_dump")
                else {}
            )
            cid = comment_dict.get("id")
            if cid is None:
                continue

            body = comment_dict.get("body", "")
            truncated_body = body[:200] if body else ""

            status = comment_fix_status.get(cid, "skipped")
            resolution = resolution_map.get(cid, {})

            pr_comments.append(
                {
                    "comment_id": cid,
                    "file_path": comment_dict.get("path"),
                    "line": comment_dict.get("line"),
                    "body": truncated_body,
                    "author": comment_dict.get("author")
                    or (
                        comment_dict.get("user", {}).get("login")
                        if isinstance(comment_dict.get("user"), dict)
                        else None
                    ),
                    "status": status,
                    "resolved": resolution.get("resolved", False),
                    "replied": resolution.get("replied", False),
                }
            )

        return pr_comments

    async def _run_cooldown(
        self,
        repo: str,
        pr_number: int,
        config: PRAutoFixConfig,
    ) -> None:
        """Wait for cooldown period between pending cycles.

        Uses asyncio.Event for interruptible wait. Timer resets when
        a new trigger arrives (sets the event), but respects
        max_cooldown_seconds as an absolute cap.

        Args:
            repo: Repository in 'owner/repo' format.
            pr_number: PR number for cooldown tracking.
            config: Configuration with cooldown durations.
        """
        key = (repo, pr_number)
        cooldown_seconds = config.post_push_cooldown_seconds
        max_cooldown = config.max_cooldown_seconds

        if cooldown_seconds == 0 and max_cooldown == 0:
            return  # No cooldown configured

        self._emit_event(
            EventType.PR_FIX_COOLDOWN_STARTED,
            pr_number,
            f"Cooldown started for PR #{pr_number} ({cooldown_seconds}s, max {max_cooldown}s)",
            data={"cooldown_seconds": cooldown_seconds, "max_cooldown_seconds": max_cooldown},
            repo=repo,
        )

        event = asyncio.Event()
        self._cooldown_events[key] = event
        loop = asyncio.get_running_loop()
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

        self._cooldown_events.pop(key, None)

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
        await git_ops.fetch_origin()
        if branch:
            await git_ops.checkout_and_reset(branch)

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
        repo: str = "",
    ) -> None:
        """Create and emit a workflow event for orchestration state changes.

        Args:
            event_type: The event type to emit.
            pr_number: PR number for context.
            message: Human-readable message.
            data: Optional structured payload.
            repo: Repository in 'owner/repo' format.
        """
        event_data: dict[str, object] = {"pr_number": pr_number}
        if data:
            event_data.update(data)

        event = WorkflowEvent(
            id=uuid4(),
            workflow_id=self.get_workflow_id(repo, pr_number),
            sequence=0,  # Orchestration events don't need sequence ordering
            timestamp=datetime.now(UTC),
            agent="pr_auto_fix",
            event_type=event_type,
            message=message,
            data=event_data,
        )
        self._event_bus.emit(event)
