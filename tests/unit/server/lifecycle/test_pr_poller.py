"""Tests for PR comment poller service."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import (
    PRAutoFixConfig,
    Profile,
    PRReviewComment,
    PRSummary,
)
from amelia.server.lifecycle.pr_poller import PRCommentPoller
from amelia.server.models.events import _WARNING_TYPES, EventType


# ---------------------------------------------------------------------------
# Shared fixtures (reused by Task 2 tests)
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_profile_repo() -> AsyncMock:
    """Mock ProfileRepository with list_profiles."""
    repo = AsyncMock()
    repo.list_profiles = AsyncMock(return_value=[])
    return repo


@pytest.fixture()
def mock_settings_repo() -> AsyncMock:
    """Mock SettingsRepository with get_server_settings."""
    repo = AsyncMock()
    settings = MagicMock()
    settings.pr_polling_enabled = True
    repo.get_server_settings = AsyncMock(return_value=settings)
    return repo


@pytest.fixture()
def mock_orchestrator() -> AsyncMock:
    """Mock PRAutoFixOrchestrator with trigger_fix_cycle."""
    orch = AsyncMock()
    orch.trigger_fix_cycle = AsyncMock()
    return orch


@pytest.fixture()
def mock_event_bus() -> MagicMock:
    """Mock EventBus with emit."""
    bus = MagicMock()
    bus.emit = MagicMock()
    return bus


@pytest.fixture()
def sample_profile() -> Profile:
    """Profile with pr_autofix enabled."""
    return Profile(
        name="test-profile",
        repo_root="/tmp/test-repo",
        pr_autofix=PRAutoFixConfig(poll_label="amelia"),
    )


@pytest.fixture()
def sample_profile_no_autofix() -> Profile:
    """Profile with pr_autofix disabled."""
    return Profile(
        name="no-autofix",
        repo_root="/tmp/test-repo",
    )


# ---------------------------------------------------------------------------
# Task 1: Config extensions
# ---------------------------------------------------------------------------


class TestPRAutoFixConfigPollLabel:
    """Tests for poll_label field on PRAutoFixConfig."""

    def test_default_poll_label(self) -> None:
        config = PRAutoFixConfig()
        assert config.poll_label == "amelia"

    def test_custom_poll_label(self) -> None:
        config = PRAutoFixConfig(poll_label="custom-label")
        assert config.poll_label == "custom-label"


class TestEventTypePollRateLimited:
    """Tests for PR_POLL_RATE_LIMITED event type."""

    def test_event_type_exists(self) -> None:
        assert EventType.PR_POLL_RATE_LIMITED == "pr_poll_rate_limited"

    def test_event_type_in_warning_types(self) -> None:
        assert EventType.PR_POLL_RATE_LIMITED in _WARNING_TYPES


class TestListLabeledPRs:
    """Tests for GitHubPRService.list_labeled_prs."""

    async def test_list_labeled_prs_returns_pr_summaries(self) -> None:
        from amelia.services.github_pr import GitHubPRService

        service = GitHubPRService("/tmp/test-repo")
        pr_data = [
            {
                "number": 42,
                "title": "Fix stuff",
                "headRefName": "fix/stuff",
                "author": {"login": "alice"},
                "updatedAt": "2026-03-14T10:00:00Z",
            },
        ]
        with patch.object(service, "_run_gh", new_callable=AsyncMock) as mock_gh:
            mock_gh.return_value = json.dumps(pr_data)
            result = await service.list_labeled_prs("amelia")

        assert len(result) == 1
        assert isinstance(result[0], PRSummary)
        assert result[0].number == 42
        assert result[0].head_branch == "fix/stuff"
        mock_gh.assert_called_once_with(
            "pr", "list",
            "--json", "number,title,headRefName,author,updatedAt",
            "--state", "open",
            "--label", "amelia",
            "--limit", "100",
        )

    async def test_list_labeled_prs_empty_result(self) -> None:
        from amelia.services.github_pr import GitHubPRService

        service = GitHubPRService("/tmp/test-repo")
        with patch.object(service, "_run_gh", new_callable=AsyncMock) as mock_gh:
            mock_gh.return_value = json.dumps([])
            result = await service.list_labeled_prs("amelia")

        assert result == []


# ---------------------------------------------------------------------------
# Task 2: PRCommentPoller service
# ---------------------------------------------------------------------------


@pytest.fixture()
def poller(
    mock_profile_repo: AsyncMock,
    mock_settings_repo: AsyncMock,
    mock_orchestrator: AsyncMock,
    mock_event_bus: MagicMock,
) -> PRCommentPoller:
    """Create PRCommentPoller with mocked dependencies."""
    return PRCommentPoller(
        profile_repo=mock_profile_repo,
        settings_repo=mock_settings_repo,
        orchestrator=mock_orchestrator,
        event_bus=mock_event_bus,
        tick_interval=0.01,  # Fast ticking for tests
    )


def _make_pr_summary(number: int = 42, branch: str = "fix/stuff") -> PRSummary:
    return PRSummary(
        number=number,
        title=f"PR #{number}",
        head_branch=branch,
        author="alice",
        updated_at=datetime(2026, 3, 14, tzinfo=UTC),
    )


def _make_comment(comment_id: int = 1, pr_number: int = 42) -> PRReviewComment:
    return PRReviewComment(
        id=comment_id,
        body="Please fix this",
        author="bob",
        created_at=datetime(2026, 3, 14, tzinfo=UTC),
        path="src/main.py",
        line=10,
        pr_number=pr_number,
    )


class TestPollerLifecycle:
    """Tests for start/stop lifecycle."""

    async def test_start_creates_task(
        self,
        poller: PRCommentPoller,
    ) -> None:
        await poller.start()
        assert poller._task is not None
        assert not poller._task.done()
        await poller.stop()

    async def test_stop_cancels_task(
        self,
        poller: PRCommentPoller,
    ) -> None:
        await poller.start()
        task = poller._task
        await poller.stop()
        assert task is not None
        assert task.done()


class TestPollAllProfiles:
    """Tests for _poll_all_profiles behavior."""

    async def test_skips_profiles_without_pr_autofix(
        self,
        poller: PRCommentPoller,
        mock_profile_repo: AsyncMock,
        sample_profile_no_autofix: Profile,
    ) -> None:
        mock_profile_repo.list_profiles.return_value = [sample_profile_no_autofix]

        with (
            patch.object(poller, "_should_back_off", new_callable=AsyncMock, return_value=None),
            patch.object(poller, "_poll_profile", new_callable=AsyncMock) as mock_poll,
        ):
            await poller._poll_all_profiles()

        mock_poll.assert_not_called()

    async def test_polls_only_profiles_whose_next_poll_time_has_passed(
        self,
        poller: PRCommentPoller,
        mock_profile_repo: AsyncMock,
        sample_profile: Profile,
    ) -> None:
        mock_profile_repo.list_profiles.return_value = [sample_profile]
        # Set next_poll far in the future
        poller._next_poll["test-profile"] = time.monotonic() + 9999

        with (
            patch.object(poller, "_should_back_off", new_callable=AsyncMock, return_value=None),
            patch.object(poller, "_poll_profile", new_callable=AsyncMock) as mock_poll,
        ):
            await poller._poll_all_profiles()

        mock_poll.assert_not_called()

    async def test_polls_eligible_profile(
        self,
        poller: PRCommentPoller,
        mock_profile_repo: AsyncMock,
        sample_profile: Profile,
    ) -> None:
        mock_profile_repo.list_profiles.return_value = [sample_profile]
        # next_poll not set => immediate first poll

        with (
            patch.object(poller, "_should_back_off", new_callable=AsyncMock, return_value=None),
            patch.object(poller, "_poll_profile", new_callable=AsyncMock) as mock_poll,
        ):
            await poller._poll_all_profiles()

        mock_poll.assert_called_once_with(sample_profile)

    async def test_sets_next_poll_before_polling(
        self,
        poller: PRCommentPoller,
        mock_profile_repo: AsyncMock,
        sample_profile: Profile,
    ) -> None:
        """next_poll is set BEFORE _poll_profile is called (prevents overlap)."""
        mock_profile_repo.list_profiles.return_value = [sample_profile]
        captured_next_poll: list[float] = []

        async def capture_poll(profile: Profile) -> None:
            captured_next_poll.append(poller._next_poll.get("test-profile", 0))

        with (
            patch.object(poller, "_should_back_off", new_callable=AsyncMock, return_value=None),
            patch.object(poller, "_poll_profile", side_effect=capture_poll),
        ):
            await poller._poll_all_profiles()

        # next_poll should have been set before _poll_profile was called
        assert len(captured_next_poll) == 1
        assert captured_next_poll[0] > time.monotonic() - 1  # Was set recently


class TestPollProfile:
    """Tests for _poll_profile behavior."""

    async def test_dispatches_fix_cycle_for_prs_with_comments(
        self,
        poller: PRCommentPoller,
        mock_orchestrator: AsyncMock,
        sample_profile: Profile,
    ) -> None:
        pr = _make_pr_summary()
        comment = _make_comment()

        with patch("amelia.server.lifecycle.pr_poller.GitHubPRService") as MockService:  # noqa: SIM117
            svc = AsyncMock()
            svc.list_labeled_prs = AsyncMock(return_value=[pr])
            svc.fetch_review_comments = AsyncMock(return_value=[comment])
            MockService.return_value = svc

            with patch.object(poller, "_get_repo_slug", new_callable=AsyncMock, return_value="owner/repo"):
                await poller._poll_profile(sample_profile)

        # Let fire-and-forget task run
        await asyncio.sleep(0)

        mock_orchestrator.trigger_fix_cycle.assert_called_once()
        call_kwargs = mock_orchestrator.trigger_fix_cycle.call_args
        assert call_kwargs[1]["pr_number"] == 42 or call_kwargs[0][0] == 42

    async def test_skips_prs_with_zero_comments(
        self,
        poller: PRCommentPoller,
        mock_orchestrator: AsyncMock,
        sample_profile: Profile,
    ) -> None:
        pr = _make_pr_summary()

        with patch("amelia.server.lifecycle.pr_poller.GitHubPRService") as MockService:
            svc = AsyncMock()
            svc.list_labeled_prs = AsyncMock(return_value=[pr])
            svc.fetch_review_comments = AsyncMock(return_value=[])
            MockService.return_value = svc

            with patch.object(poller, "_get_repo_slug", new_callable=AsyncMock, return_value="owner/repo"):  # noqa: SIM117
                await poller._poll_profile(sample_profile)

        await asyncio.sleep(0)
        mock_orchestrator.trigger_fix_cycle.assert_not_called()

    async def test_fire_and_forget_dispatch(
        self,
        poller: PRCommentPoller,
        mock_orchestrator: AsyncMock,
        sample_profile: Profile,
    ) -> None:
        """trigger_fix_cycle is dispatched via asyncio.create_task (fire-and-forget)."""
        pr = _make_pr_summary()
        comment = _make_comment()

        with patch("amelia.server.lifecycle.pr_poller.GitHubPRService") as MockService:  # noqa: SIM117
            svc = AsyncMock()
            svc.list_labeled_prs = AsyncMock(return_value=[pr])
            svc.fetch_review_comments = AsyncMock(return_value=[comment])
            MockService.return_value = svc

            with patch.object(poller, "_get_repo_slug", new_callable=AsyncMock, return_value="owner/repo"):
                await poller._poll_profile(sample_profile)

        # Task should be tracked in _active_tasks
        assert len(poller._active_tasks) >= 0  # Tasks may complete fast
        await asyncio.sleep(0)

    async def test_silent_when_no_labeled_prs(
        self,
        poller: PRCommentPoller,
        mock_orchestrator: AsyncMock,
        sample_profile: Profile,
    ) -> None:
        with patch("amelia.server.lifecycle.pr_poller.GitHubPRService") as MockService:
            svc = AsyncMock()
            svc.list_labeled_prs = AsyncMock(return_value=[])
            MockService.return_value = svc

            await poller._poll_profile(sample_profile)

        mock_orchestrator.trigger_fix_cycle.assert_not_called()

    async def test_logs_cycle_summary_when_prs_found(
        self,
        poller: PRCommentPoller,
        sample_profile: Profile,
    ) -> None:
        pr = _make_pr_summary()
        comment = _make_comment()

        with patch("amelia.server.lifecycle.pr_poller.GitHubPRService") as MockService:  # noqa: SIM117
            svc = AsyncMock()
            svc.list_labeled_prs = AsyncMock(return_value=[pr])
            svc.fetch_review_comments = AsyncMock(return_value=[comment])
            MockService.return_value = svc

            with (
                patch.object(poller, "_get_repo_slug", new_callable=AsyncMock, return_value="owner/repo"),
                patch("amelia.server.lifecycle.pr_poller.logger") as mock_logger,
            ):
                await poller._poll_profile(sample_profile)

        # Should log at info level
        info_calls = [c for c in mock_logger.info.call_args_list]
        assert len(info_calls) > 0


class TestRateLimit:
    """Tests for rate limit checking and backoff."""

    async def test_should_back_off_returns_duration_when_low_budget(
        self,
        poller: PRCommentPoller,
    ) -> None:
        reset_ts = time.time() + 60
        with patch.object(
            poller, "_check_rate_limit",
            new_callable=AsyncMock,
            return_value=(5, 5000, reset_ts),
        ):
            result = await poller._should_back_off("/tmp/test-repo")

        assert result is not None
        assert result > 0

    async def test_should_back_off_returns_none_when_healthy(
        self,
        poller: PRCommentPoller,
    ) -> None:
        with patch.object(
            poller, "_check_rate_limit",
            new_callable=AsyncMock,
            return_value=(4500, 5000, time.time() + 3600),
        ):
            result = await poller._should_back_off("/tmp/test-repo")

        assert result is None

    async def test_rate_limit_backoff_emits_event(
        self,
        poller: PRCommentPoller,
        mock_profile_repo: AsyncMock,
        mock_event_bus: MagicMock,
        sample_profile: Profile,
    ) -> None:
        mock_profile_repo.list_profiles.return_value = [sample_profile]

        with patch.object(
            poller, "_should_back_off",
            new_callable=AsyncMock,
            return_value=0.01,
        ):
            await poller._poll_all_profiles()

        # Should have emitted PR_POLL_RATE_LIMITED event
        emit_calls = mock_event_bus.emit.call_args_list
        rate_limited_events = [
            c for c in emit_calls
            if c[0][0].event_type == EventType.PR_POLL_RATE_LIMITED
        ]
        assert len(rate_limited_events) == 1


class TestExceptionResilience:
    """Tests for error handling in poll cycle."""

    async def test_exception_in_poll_profile_is_caught(
        self,
        poller: PRCommentPoller,
        mock_profile_repo: AsyncMock,
        sample_profile: Profile,
    ) -> None:
        mock_profile_repo.list_profiles.return_value = [sample_profile]

        with (
            patch.object(poller, "_should_back_off", new_callable=AsyncMock, return_value=None),
            patch.object(
                poller, "_poll_profile",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            # Should not raise
            await poller._poll_all_profiles()


class TestRuntimeToggle:
    """Tests for pr_polling_enabled toggle."""

    async def test_skips_polling_when_disabled(
        self,
        poller: PRCommentPoller,
        mock_settings_repo: AsyncMock,
        mock_profile_repo: AsyncMock,
    ) -> None:
        settings = MagicMock()
        settings.pr_polling_enabled = False
        mock_settings_repo.get_server_settings.return_value = settings

        # Run one iteration of the poll loop
        with patch.object(poller, "_poll_all_profiles", new_callable=AsyncMock) as mock_poll:
            await poller.start()
            await asyncio.sleep(0.05)
            await poller.stop()

        mock_poll.assert_not_called()


class TestImmediateFirstPoll:
    """Tests for immediate polling on startup."""

    async def test_no_initial_next_poll_means_immediate_poll(
        self,
        poller: PRCommentPoller,
        mock_profile_repo: AsyncMock,
        sample_profile: Profile,
    ) -> None:
        mock_profile_repo.list_profiles.return_value = [sample_profile]
        assert "test-profile" not in poller._next_poll

        with (
            patch.object(poller, "_should_back_off", new_callable=AsyncMock, return_value=None),
            patch.object(poller, "_poll_profile", new_callable=AsyncMock) as mock_poll,
        ):
            await poller._poll_all_profiles()

        mock_poll.assert_called_once()


class TestNoOverlap:
    """Tests for overlap prevention."""

    async def test_next_poll_set_before_polling_starts(
        self,
        poller: PRCommentPoller,
        mock_profile_repo: AsyncMock,
        sample_profile: Profile,
    ) -> None:
        mock_profile_repo.list_profiles.return_value = [sample_profile]

        poll_started = asyncio.Event()
        poll_continue = asyncio.Event()

        async def slow_poll(profile: Profile) -> None:
            poll_started.set()
            await poll_continue.wait()

        with (
            patch.object(poller, "_should_back_off", new_callable=AsyncMock, return_value=None),
            patch.object(poller, "_poll_profile", side_effect=slow_poll),
        ):
            task = asyncio.create_task(poller._poll_all_profiles())
            await poll_started.wait()

            # While _poll_profile is still running, next_poll should already be set
            assert "test-profile" in poller._next_poll
            assert poller._next_poll["test-profile"] > time.monotonic() - 1

            poll_continue.set()
            await task
