"""PR comment poller service for autonomous fix cycle detection.

Periodically discovers pr_autofix-enabled profiles, lists their labeled PRs,
checks for unresolved review comments, and dispatches fix cycles via the
orchestrator. Respects rate limits and per-profile poll intervals.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger

from amelia.core.types import Profile
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.services.github_pr import GitHubPRService


if TYPE_CHECKING:
    from amelia.pipelines.pr_auto_fix.orchestrator import PRAutoFixOrchestrator
    from amelia.server.database.profile_repository import ProfileRepository
    from amelia.server.database.settings_repository import SettingsRepository
    from amelia.server.events.bus import EventBus


class PRCommentPoller:
    """Polls GitHub PRs for unresolved review comments and dispatches fix cycles.

    Follows the WorktreeHealthChecker lifecycle pattern: start() creates an
    asyncio task, stop() cancels it cleanly.

    Key behaviors:
    - Discovers profiles with pr_autofix enabled
    - Lists PRs matching the configured poll_label per profile
    - Checks for unresolved review comments
    - Dispatches fix cycles fire-and-forget via orchestrator
    - Respects per-profile poll_interval via next-poll timestamp tracking
    - Checks GitHub rate limit and backs off when < 10% remaining
    - Emits PR_POLL_RATE_LIMITED event when backing off
    - Logs errors and continues polling (never crashes)
    """

    def __init__(
        self,
        profile_repo: ProfileRepository,
        settings_repo: SettingsRepository,
        orchestrator: PRAutoFixOrchestrator,
        event_bus: EventBus,
        tick_interval: float = 5.0,
    ) -> None:
        """Initialize the PR comment poller.

        Args:
            profile_repo: Repository for listing profiles.
            settings_repo: Repository for server settings (polling toggle).
            orchestrator: PR auto-fix orchestrator for triggering fix cycles.
            event_bus: Event bus for emitting rate limit events.
            tick_interval: Seconds between poll loop iterations.
        """
        self._profile_repo = profile_repo
        self._settings_repo = settings_repo
        self._orchestrator = orchestrator
        self._event_bus = event_bus
        self._tick_interval = tick_interval

        self._task: asyncio.Task[None] | None = None
        self._next_poll: dict[str, float] = {}
        self._active_tasks: set[asyncio.Task[None]] = set()
        self._repo_slugs: dict[str, str] = {}
        self._processed_comments: dict[tuple[str, int], set[int]] = {}

    async def start(self) -> None:
        """Start the poll loop."""
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("PRCommentPoller started", tick_interval=self._tick_interval)

    async def stop(self) -> None:
        """Stop the poll loop and cancel all active fire-and-forget tasks."""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        # Cancel all fire-and-forget tasks
        for task in self._active_tasks:
            task.cancel()
        for task in self._active_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._active_tasks.clear()

        logger.info("PRCommentPoller stopped")

    async def _poll_loop(self) -> None:
        """Main poll loop: check settings toggle, then poll all profiles."""
        while True:
            try:
                settings = await self._settings_repo.get_server_settings()
                if settings.pr_polling_enabled:
                    await self._poll_all_profiles()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Poll loop iteration failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
            await asyncio.sleep(self._tick_interval)

    async def _poll_all_profiles(self) -> None:
        """Poll all eligible profiles.

        Checks rate limit first. Then iterates profiles, skipping those
        without pr_autofix or whose next-poll time hasn't passed.
        Sets next_poll BEFORE calling _poll_profile to prevent overlap.
        """
        # Find first enabled profile's repo_root for rate limit check
        profiles = await self._profile_repo.list_profiles()
        enabled_profiles = [p for p in profiles if p.pr_autofix is not None]

        if not enabled_profiles:
            return

        # Check rate limit using first enabled profile's repo
        backoff_seconds = await self._should_back_off(enabled_profiles[0].repo_root)
        if backoff_seconds is not None:
            self._emit_rate_limited_event(backoff_seconds)
            await asyncio.sleep(backoff_seconds)
            return

        now = time.monotonic()
        for profile in enabled_profiles:
            # Skip if next-poll time hasn't passed
            if now < self._next_poll.get(profile.name, 0):
                continue

            assert profile.pr_autofix is not None  # Guaranteed by enabled_profiles filter
            # Set next_poll BEFORE polling (prevents overlap)
            self._next_poll[profile.name] = now + profile.pr_autofix.poll_interval

            try:
                await self._poll_profile(profile)
            except Exception as exc:
                logger.error(
                    "Error polling profile",
                    profile=profile.name,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

    async def _poll_profile(self, profile: Profile) -> None:
        """Poll a single profile for PRs with unresolved comments.

        Creates a GitHubPRService, lists labeled PRs, checks each for
        unresolved comments, and dispatches fix cycles for those with
        comments. Logs a cycle summary at INFO level.

        Args:
            profile: Profile with pr_autofix enabled.
        """
        assert profile.pr_autofix is not None
        config = profile.pr_autofix

        service = GitHubPRService(profile.repo_root)
        if config.poll_label is None:
            logger.warning("poll_label is null, skipping poll cycle", profile=profile.name)
            return
        prs = await service.list_labeled_prs(config.poll_label)

        if not prs:
            return  # Silent when no labeled PRs

        triggered = 0
        for pr in prs:
            comments = await service.fetch_review_comments(
                pr.number,
                ignore_authors=config.ignore_authors,
            )
            key = (profile.name, pr.number)

            if not comments:
                # All resolved on GitHub — clear tracking so future comments trigger normally
                self._processed_comments.pop(key, None)
                continue

            current_ids = {c.id for c in comments}
            processed_ids = self._processed_comments.get(key, set())

            if current_ids <= processed_ids:
                logger.debug(
                    "All comments already processed, skipping",
                    profile=profile.name,
                    pr_number=pr.number,
                    comment_count=len(current_ids),
                )
                continue

            repo_slug = await self._get_repo_slug(profile.repo_root)

            # Emit PR_COMMENTS_DETECTED event
            detected_event = WorkflowEvent(
                id=uuid4(),
                workflow_id=self._orchestrator.get_workflow_id(repo_slug, pr.number),
                sequence=0,
                timestamp=datetime.now(UTC),
                agent="pr_poller",
                event_type=EventType.PR_COMMENTS_DETECTED,
                message=f"Detected {len(comments)} unresolved comment(s) on PR #{pr.number}",
                data={
                    "pr_number": pr.number,
                    "comment_count": len(comments),
                    "pr_title": pr.title,
                },
            )
            self._event_bus.emit(detected_event)

            # Fire-and-forget dispatch
            task = asyncio.create_task(
                self._orchestrator.trigger_fix_cycle(
                    pr_number=pr.number,
                    repo=repo_slug,
                    profile=profile,
                    head_branch=pr.head_branch,
                    config=config,
                    pr_title=pr.title,
                    comments=comments,
                ),
            )
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)
            self._processed_comments[key] = current_ids
            triggered += 1

        if triggered > 0 or len(prs) > 0:
            logger.info(
                "Poll cycle complete",
                profile=profile.name,
                prs_found=len(prs),
                fix_cycles_triggered=triggered,
            )

    async def _get_repo_slug(self, repo_root: str) -> str:
        """Get cached owner/repo slug for a repository.

        Args:
            repo_root: Path to the repository root.

        Returns:
            Repository slug in 'owner/repo' format.
        """
        if repo_root in self._repo_slugs:
            return self._repo_slugs[repo_root]

        proc = await asyncio.create_subprocess_exec(
            "gh",
            "repo",
            "view",
            "--json",
            "nameWithOwner",
            "-q",
            ".nameWithOwner",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=repo_root,
        )
        stdout_bytes, _ = await proc.communicate()
        slug = stdout_bytes.decode().strip()
        self._repo_slugs[repo_root] = slug
        return slug

    async def _check_rate_limit(
        self,
        repo_root: str,
    ) -> tuple[int, int, float]:
        """Check GitHub API rate limit.

        Args:
            repo_root: Repository root for gh CLI context.

        Returns:
            Tuple of (remaining, limit, reset_timestamp).
        """
        proc = await asyncio.create_subprocess_exec(
            "gh",
            "api",
            "/rate_limit",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=repo_root,
        )
        stdout_bytes, _ = await proc.communicate()
        if proc.returncode != 0:
            logger.warning(
                "gh api /rate_limit failed",
                returncode=proc.returncode,
            )
            return (5000, 5000, time.time() + 3600)
        try:
            data = json.loads(stdout_bytes.decode())
        except json.JSONDecodeError:
            logger.warning("Failed to parse rate limit JSON response")
            return (5000, 5000, time.time() + 3600)
        core = data.get("resources", {}).get("core", {})
        return (
            core.get("remaining", 5000),
            core.get("limit", 5000),
            float(core.get("reset", time.time() + 3600)),
        )

    async def _should_back_off(self, repo_root: str) -> float | None:
        """Check if we should back off due to rate limiting.

        Args:
            repo_root: Repository root for rate limit check.

        Returns:
            Seconds to sleep if backing off, None if budget is healthy.
        """
        remaining, limit, reset_ts = await self._check_rate_limit(repo_root)
        threshold = int(limit * 0.10)

        if remaining <= threshold:
            return max(0.0, reset_ts - time.time())

        return None

    def _emit_rate_limited_event(self, backoff_seconds: float) -> None:
        """Emit a PR_POLL_RATE_LIMITED event.

        Args:
            backoff_seconds: How long the poller will back off.
        """
        event = WorkflowEvent(
            id=uuid4(),
            workflow_id=uuid4(),
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="pr_poller",
            event_type=EventType.PR_POLL_RATE_LIMITED,
            message=f"Rate limit low, backing off for {backoff_seconds:.0f}s",
            data={"backoff_seconds": backoff_seconds},
        )
        self._event_bus.emit(event)
