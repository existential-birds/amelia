"""Tests for PR auto-fix orchestrator config, event types, and orchestration logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from amelia.core.types import PRAutoFixConfig, Profile
from amelia.pipelines.pr_auto_fix.orchestrator import PRAutoFixOrchestrator
from amelia.server.database import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.models.state import WorkflowStatus, WorkflowType

from .conftest import mock_pipeline_context


# ---------------------------------------------------------------------------
# Phase 06-01 tests (config + event types)
# ---------------------------------------------------------------------------


class TestPRAutoFixConfigCooldown:
    """Tests for cooldown configuration fields on PRAutoFixConfig."""

    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("post_push_cooldown_seconds", 300),
            ("max_cooldown_seconds", 900),
        ],
    )
    def test_default_values(self, field: str, expected: int) -> None:
        config = PRAutoFixConfig()
        assert getattr(config, field) == expected

    def test_post_push_exceeds_max_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="post_push_cooldown_seconds"):
            PRAutoFixConfig(post_push_cooldown_seconds=600, max_cooldown_seconds=300)

    @pytest.mark.parametrize(
        ("post_push", "max_cd"),
        [(60, 120), (0, 0)],
        ids=["normal", "both-zero"],
    )
    def test_valid_cooldown_configs(self, post_push: int, max_cd: int) -> None:
        config = PRAutoFixConfig(
            post_push_cooldown_seconds=post_push, max_cooldown_seconds=max_cd,
        )
        assert config.post_push_cooldown_seconds == post_push
        assert config.max_cooldown_seconds == max_cd


class TestPRFixEventTypes:
    """Tests for new PR fix orchestration event types."""

    @pytest.mark.parametrize(
        ("member", "value"),
        [
            ("PR_FIX_QUEUED", "pr_fix_queued"),
            ("PR_FIX_DIVERGED", "pr_fix_diverged"),
            ("PR_FIX_COOLDOWN_STARTED", "pr_fix_cooldown_started"),
            ("PR_FIX_COOLDOWN_RESET", "pr_fix_cooldown_reset"),
            ("PR_FIX_RETRIES_EXHAUSTED", "pr_fix_retries_exhausted"),
        ],
    )
    def test_event_type_exists_with_correct_value(
        self, member: str, value: str,
    ) -> None:
        event = getattr(EventType, member)
        assert event == value
        assert isinstance(event, EventType)


# ---------------------------------------------------------------------------
# Autouse: patch GitOperations for all tests in this module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_git_operations(mock_git_operations: MagicMock) -> object:
    """Auto-patch GitOperations for all tests in this module."""
    with patch(
        "amelia.pipelines.pr_auto_fix.orchestrator.GitOperations",
        return_value=mock_git_operations,
    ):
        yield


# ---------------------------------------------------------------------------
# ORCH-01: Per-PR Concurrency Control
# ---------------------------------------------------------------------------


class TestConcurrencyControl:
    """Tests for per-PR lock and pending flag behavior."""

    async def test_single_trigger_runs_pipeline(
        self,
        orchestrator: PRAutoFixOrchestrator,
        orch_profile: Profile,
    ) -> None:
        orchestrator._execute_pipeline = AsyncMock()  # type: ignore[method-assign]
        await orchestrator.trigger_fix_cycle(
            pr_number=42, repo="owner/repo", profile=orch_profile,
        )
        orchestrator._execute_pipeline.assert_awaited_once()

    async def test_concurrent_triggers_same_pr_queued(
        self,
        orchestrator: PRAutoFixOrchestrator,
        orch_profile: Profile,
        captured_events: list[WorkflowEvent],
    ) -> None:
        call_count = 0
        pipeline_started = asyncio.Event()
        pipeline_continue = asyncio.Event()

        async def slow_pipeline(*args: object, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            pipeline_started.set()
            await pipeline_continue.wait()

        orchestrator._execute_pipeline = AsyncMock(side_effect=slow_pipeline)  # type: ignore[method-assign]

        task1 = asyncio.create_task(
            orchestrator.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=orch_profile)
        )
        await pipeline_started.wait()

        task2 = asyncio.create_task(
            orchestrator.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=orch_profile)
        )
        await asyncio.wait_for(task2, timeout=1.0)
        assert task2.done()
        queued_events = [e for e in captured_events if e.event_type == EventType.PR_FIX_QUEUED]
        assert len(queued_events) == 1

        pipeline_started.clear()
        pipeline_continue.set()
        await task1
        assert call_count == 2

    async def test_concurrent_different_repos_run_in_parallel(
        self,
        orchestrator: PRAutoFixOrchestrator,
        orch_profile: Profile,
    ) -> None:
        """PRs on *different* repos run in parallel (separate repo locks)."""
        profile_a = orch_profile.model_copy(update={"repo_root": "/tmp/repo-a"})
        profile_b = orch_profile.model_copy(update={"repo_root": "/tmp/repo-b"})

        pr42_started = asyncio.Event()
        pr99_started = asyncio.Event()
        both_running = asyncio.Event()

        async def mock_execute(pr_number: int, *args: object, **kwargs: object) -> None:
            ev = pr42_started if pr_number == 42 else pr99_started
            ev.set()
            await both_running.wait()

        orchestrator._execute_pipeline = AsyncMock(side_effect=mock_execute)  # type: ignore[method-assign]

        task1 = asyncio.create_task(
            orchestrator.trigger_fix_cycle(pr_number=42, repo="owner/repo-a", profile=profile_a)
        )
        task2 = asyncio.create_task(
            orchestrator.trigger_fix_cycle(pr_number=99, repo="owner/repo-b", profile=profile_b)
        )

        await asyncio.wait_for(pr42_started.wait(), timeout=2.0)
        await asyncio.wait_for(pr99_started.wait(), timeout=2.0)

        both_running.set()
        await task1
        await task2

    async def test_concurrent_same_repo_different_prs_serialized(
        self,
        orchestrator: PRAutoFixOrchestrator,
        orch_profile: Profile,
    ) -> None:
        """PRs on the *same* repo are serialized by the repo lock."""
        execution_order: list[int] = []

        async def mock_execute(pr_number: int, *args: object, **kwargs: object) -> None:
            execution_order.append(pr_number)
            await asyncio.sleep(0.01)

        orchestrator._execute_pipeline = AsyncMock(side_effect=mock_execute)  # type: ignore[method-assign]

        task1 = asyncio.create_task(
            orchestrator.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=orch_profile)
        )
        # Yield so task1 grabs the repo lock first
        await asyncio.sleep(0)
        task2 = asyncio.create_task(
            orchestrator.trigger_fix_cycle(pr_number=99, repo="owner/repo", profile=orch_profile)
        )

        await asyncio.gather(task1, task2)
        # PR 42 should finish before PR 99 starts
        assert execution_order == [42, 99]

    async def test_pending_flag_is_boolean_latest_wins(
        self,
        orchestrator: PRAutoFixOrchestrator,
        orch_profile: Profile,
    ) -> None:
        pipeline_started = asyncio.Event()
        pipeline_continue = asyncio.Event()
        call_count = 0

        async def slow_pipeline(*args: object, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                pipeline_started.set()
                await pipeline_continue.wait()

        orchestrator._execute_pipeline = AsyncMock(side_effect=slow_pipeline)  # type: ignore[method-assign]

        task1 = asyncio.create_task(
            orchestrator.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=orch_profile)
        )
        await pipeline_started.wait()

        for _ in range(3):
            await orchestrator.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=orch_profile)

        pipeline_continue.set()
        await task1
        assert call_count == 2


# ---------------------------------------------------------------------------
# ORCH-02: Cooldown with Reset
# ---------------------------------------------------------------------------


def _make_cooldown_orchestrator(
    event_bus: EventBus,
    github_pr_service: MagicMock,
    *,
    post_push: int,
    max_cd: int,
) -> tuple[PRAutoFixOrchestrator, Profile]:
    """Create orchestrator + profile with specific cooldown settings."""
    config = PRAutoFixConfig(
        post_push_cooldown_seconds=post_push,
        max_cooldown_seconds=max_cd,
    )
    profile = Profile(name="test", repo_root="/tmp/test-repo", pr_autofix=config)
    orch = PRAutoFixOrchestrator(
        event_bus=event_bus,
        github_pr_service=github_pr_service,
        workflow_repo=MagicMock(spec=WorkflowRepository, create=AsyncMock(), update=AsyncMock()),
    )
    return orch, profile


class TestCooldown:
    """Tests for cooldown timer between pending cycles."""

    async def test_cooldown_waits_before_next_cycle(
        self,
        event_bus: EventBus,
        github_pr_service: MagicMock,
        captured_events: list[WorkflowEvent],
    ) -> None:
        orch, profile = _make_cooldown_orchestrator(
            event_bus, github_pr_service, post_push=1, max_cd=5,
        )
        pipeline_started = asyncio.Event()
        pipeline_continue = asyncio.Event()
        call_count = 0

        async def slow_pipeline(*args: object, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                pipeline_started.set()
                await pipeline_continue.wait()

        orch._execute_pipeline = AsyncMock(side_effect=slow_pipeline)  # type: ignore[method-assign]

        task = asyncio.create_task(
            orch.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=profile)
        )
        await pipeline_started.wait()
        await orch.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=profile)
        pipeline_continue.set()
        await asyncio.wait_for(task, timeout=5.0)

        cooldown_events = [e for e in captured_events if e.event_type == EventType.PR_FIX_COOLDOWN_STARTED]
        assert len(cooldown_events) >= 1

    async def test_cooldown_resets_on_new_trigger(
        self,
        event_bus: EventBus,
        github_pr_service: MagicMock,
        captured_events: list[WorkflowEvent],
    ) -> None:
        orch, profile = _make_cooldown_orchestrator(
            event_bus, github_pr_service, post_push=10, max_cd=30,
        )
        pipeline_started = asyncio.Event()
        pipeline_continue = asyncio.Event()
        cooldown_entered = asyncio.Event()
        call_count = 0

        original_run_cooldown = orch._run_cooldown

        async def track_cooldown(*args: object, **kwargs: object) -> None:
            cooldown_entered.set()
            await original_run_cooldown(*args, **kwargs)  # type: ignore[arg-type]

        orch._run_cooldown = track_cooldown  # type: ignore[method-assign]

        async def slow_pipeline(*args: object, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                pipeline_started.set()
                await pipeline_continue.wait()

        orch._execute_pipeline = AsyncMock(side_effect=slow_pipeline)  # type: ignore[method-assign]

        task = asyncio.create_task(
            orch.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=profile)
        )
        await pipeline_started.wait()
        await orch.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=profile)
        pipeline_continue.set()

        await asyncio.wait_for(cooldown_entered.wait(), timeout=2.0)
        # Yield to event loop so _run_cooldown reaches its await point
        await asyncio.sleep(0)
        await orch.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=profile)

        reset_events = [e for e in captured_events if e.event_type == EventType.PR_FIX_COOLDOWN_RESET]
        assert len(reset_events) >= 1

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.parametrize(
        ("post_push", "max_cd", "timeout"),
        [
            (1, 1, 5.0),
            (0, 0, 2.0),
        ],
        ids=["max-cap", "zero-cooldown"],
    )
    async def test_cooldown_completes_pending_cycle(
        self,
        post_push: int,
        max_cd: int,
        timeout: float,
        event_bus: EventBus,
        github_pr_service: MagicMock,
    ) -> None:
        """Cooldown completes and pending cycle runs (parametrized: max-cap and zero)."""
        orch, profile = _make_cooldown_orchestrator(
            event_bus, github_pr_service, post_push=post_push, max_cd=max_cd,
        )
        pipeline_started = asyncio.Event()
        pipeline_continue = asyncio.Event()
        call_count = 0

        async def slow_pipeline(*args: object, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                pipeline_started.set()
                await pipeline_continue.wait()

        orch._execute_pipeline = AsyncMock(side_effect=slow_pipeline)  # type: ignore[method-assign]

        task = asyncio.create_task(
            orch.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=profile)
        )
        await pipeline_started.wait()
        await orch.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=profile)
        pipeline_continue.set()

        await asyncio.wait_for(task, timeout=timeout)
        assert call_count == 2


# ---------------------------------------------------------------------------
# ORCH-03: Branch Safety & Divergence Recovery
# ---------------------------------------------------------------------------


class TestDivergenceRecovery:
    """Tests for branch reset and divergence retry logic."""

    async def test_resets_to_remote_before_each_cycle(
        self,
        orchestrator: PRAutoFixOrchestrator,
        mock_git_operations: MagicMock,
        orch_profile: Profile,
    ) -> None:
        orchestrator._execute_pipeline = AsyncMock()  # type: ignore[method-assign]
        await orchestrator.trigger_fix_cycle(
            pr_number=42, repo="owner/repo", profile=orch_profile,
        )
        mock_git_operations.fetch_origin.assert_awaited_once()

    async def test_divergence_retries_up_to_two_times(
        self,
        orchestrator: PRAutoFixOrchestrator,
        orch_profile: Profile,
        captured_events: list[WorkflowEvent],
    ) -> None:
        orchestrator._execute_pipeline = AsyncMock(  # type: ignore[method-assign]
            side_effect=ValueError("Remote branch has diverged from local")
        )
        await orchestrator.trigger_fix_cycle(
            pr_number=42, repo="owner/repo", profile=orch_profile,
        )

        assert orchestrator._execute_pipeline.await_count == 3
        diverged_events = [e for e in captured_events if e.event_type == EventType.PR_FIX_DIVERGED]
        assert len(diverged_events) == 2
        exhausted_events = [e for e in captured_events if e.event_type == EventType.PR_FIX_RETRIES_EXHAUSTED]
        assert len(exhausted_events) == 1

    async def test_divergence_success_on_retry(
        self,
        orchestrator: PRAutoFixOrchestrator,
        orch_profile: Profile,
        captured_events: list[WorkflowEvent],
    ) -> None:
        call_count = 0

        async def flaky_pipeline(*args: object, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Remote branch has diverged from local")

        orchestrator._execute_pipeline = AsyncMock(side_effect=flaky_pipeline)  # type: ignore[method-assign]
        await orchestrator.trigger_fix_cycle(
            pr_number=42, repo="owner/repo", profile=orch_profile,
        )

        assert call_count == 2
        assert len([e for e in captured_events if e.event_type == EventType.PR_FIX_DIVERGED]) == 1
        assert len([e for e in captured_events if e.event_type == EventType.PR_FIX_RETRIES_EXHAUSTED]) == 0

    async def test_final_divergence_failure_posts_github_comment(
        self,
        orchestrator: PRAutoFixOrchestrator,
        github_pr_service: MagicMock,
        orch_profile: Profile,
    ) -> None:
        orchestrator._execute_pipeline = AsyncMock(  # type: ignore[method-assign]
            side_effect=ValueError("Remote branch has diverged from local")
        )
        await orchestrator.trigger_fix_cycle(
            pr_number=42, repo="owner/repo", profile=orch_profile,
        )

        github_pr_service.create_issue_comment.assert_awaited_once()
        call_args = github_pr_service.create_issue_comment.call_args
        assert call_args.kwargs["pr_number"] == 42
        assert "Could not apply fixes" in call_args.kwargs["body"]

    async def test_head_branch_threaded_to_reset(
        self,
        orchestrator: PRAutoFixOrchestrator,
        mock_git_operations: MagicMock,
        orch_profile: Profile,
    ) -> None:
        orchestrator._execute_pipeline = AsyncMock()  # type: ignore[method-assign]
        await orchestrator.trigger_fix_cycle(
            pr_number=42, repo="owner/repo", profile=orch_profile,
            head_branch="feat/my-branch",
        )
        mock_git_operations.fetch_origin.assert_awaited_once()
        mock_git_operations.checkout_and_reset.assert_awaited_once_with("feat/my-branch")

    async def test_non_divergence_error_not_retried(
        self,
        orchestrator: PRAutoFixOrchestrator,
        orch_profile: Profile,
    ) -> None:
        orchestrator._execute_pipeline = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("Something else broke")
        )
        await orchestrator.trigger_fix_cycle(
            pr_number=42, repo="owner/repo", profile=orch_profile,
        )
        assert orchestrator._execute_pipeline.await_count == 1


# ---------------------------------------------------------------------------
# Repo-level Git Serialization
# ---------------------------------------------------------------------------


class TestRepoLevelGitSerialization:

    async def test_repo_lock_serializes_git_across_prs(
        self,
        orchestrator: PRAutoFixOrchestrator,
        mock_git_operations: MagicMock,
        orch_profile: Profile,
    ) -> None:
        git_in_progress = asyncio.Event()

        async def slow_fetch(*args: object, **kwargs: object) -> None:
            if git_in_progress.is_set():
                pytest.fail("Repo-level git section overlapped across PRs")
            git_in_progress.set()
            try:
                await asyncio.sleep(0.05)
            finally:
                git_in_progress.clear()

        mock_git_operations.fetch_origin = AsyncMock(side_effect=slow_fetch)
        orchestrator._execute_pipeline = AsyncMock()  # type: ignore[method-assign]

        task1 = asyncio.create_task(
            orchestrator.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=orch_profile)
        )
        task2 = asyncio.create_task(
            orchestrator.trigger_fix_cycle(pr_number=99, repo="owner/repo", profile=orch_profile)
        )
        await asyncio.gather(task1, task2)
        assert orchestrator._execute_pipeline.call_count == 2


# ---------------------------------------------------------------------------
# Event Emission
# ---------------------------------------------------------------------------


class TestEventEmission:

    async def test_queued_event_has_pr_number(
        self,
        orchestrator: PRAutoFixOrchestrator,
        orch_profile: Profile,
        captured_events: list[WorkflowEvent],
    ) -> None:
        pipeline_started = asyncio.Event()
        pipeline_continue = asyncio.Event()

        async def slow_pipeline(*args: object, **kwargs: object) -> None:
            pipeline_started.set()
            await pipeline_continue.wait()

        orchestrator._execute_pipeline = AsyncMock(side_effect=slow_pipeline)  # type: ignore[method-assign]

        task = asyncio.create_task(
            orchestrator.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=orch_profile)
        )
        await pipeline_started.wait()
        await orchestrator.trigger_fix_cycle(pr_number=42, repo="owner/repo", profile=orch_profile)
        pipeline_continue.set()
        await task

        queued = [e for e in captured_events if e.event_type == EventType.PR_FIX_QUEUED]
        assert len(queued) == 1
        assert queued[0].data is not None
        assert queued[0].data["pr_number"] == 42


# ---------------------------------------------------------------------------
# Pipeline Wiring
# ---------------------------------------------------------------------------


class TestExecutePipelineWiring:

    async def test_execute_pipeline_creates_and_invokes_graph(
        self,
        orchestrator: PRAutoFixOrchestrator,
        orch_profile: Profile,
        pr_autofix_config: PRAutoFixConfig,
    ) -> None:
        async with mock_pipeline_context() as (mock_pipeline, mock_graph):
            await orchestrator._execute_pipeline(
                pr_number=42, repo="owner/repo", profile=orch_profile,
                config=pr_autofix_config, head_branch="feat/test",
            )

        mock_pipeline.create_graph.assert_called_once()
        init_kwargs = mock_pipeline.get_initial_state.call_args.kwargs
        assert init_kwargs["pr_number"] == 42
        assert init_kwargs["head_branch"] == "feat/test"
        assert init_kwargs["repo"] == "owner/repo"
        assert init_kwargs["profile_id"] == "test"
        call_args = mock_graph.ainvoke.await_args
        assert call_args[0][0] == {"mock": "state"}
        assert "thread_id" in call_args[1]["config"]["configurable"]


# ---------------------------------------------------------------------------
# Workflow Record Creation (Phase 09-01 Task 2)
# ---------------------------------------------------------------------------


class TestWorkflowRecordCreation:

    async def _run_execute_pipeline(
        self,
        orchestrator: PRAutoFixOrchestrator,
        orch_profile: Profile,
        pr_autofix_config: PRAutoFixConfig,
        **pipeline_kwargs: object,
    ) -> None:
        """Helper to run _execute_pipeline with mock pipeline context."""
        async with mock_pipeline_context():
            await orchestrator._execute_pipeline(
                pr_number=42, repo="owner/repo", profile=orch_profile,
                config=pr_autofix_config, head_branch="feat/test",
                **pipeline_kwargs,
            )

    async def test_execute_pipeline_creates_workflow_record(
        self,
        orchestrator: PRAutoFixOrchestrator,
        workflow_repo: MagicMock,
        orch_profile: Profile,
        pr_autofix_config: PRAutoFixConfig,
    ) -> None:
        await self._run_execute_pipeline(orchestrator, orch_profile, pr_autofix_config)
        workflow_repo.create.assert_awaited_once()
        state = workflow_repo.create.call_args[0][0]
        assert state.workflow_type == WorkflowType.PR_AUTO_FIX

    async def test_workflow_record_has_correct_fields(
        self,
        orchestrator: PRAutoFixOrchestrator,
        workflow_repo: MagicMock,
        orch_profile: Profile,
        pr_autofix_config: PRAutoFixConfig,
    ) -> None:
        await self._run_execute_pipeline(orchestrator, orch_profile, pr_autofix_config)
        state = workflow_repo.create.call_args[0][0]
        assert state.issue_id == "PR-42"
        assert state.worktree_path == orch_profile.repo_root
        assert state.profile_id == orch_profile.name

    async def test_issue_cache_contains_pr_metadata(
        self,
        orchestrator: PRAutoFixOrchestrator,
        workflow_repo: MagicMock,
        orch_profile: Profile,
        pr_autofix_config: PRAutoFixConfig,
    ) -> None:
        await self._run_execute_pipeline(orchestrator, orch_profile, pr_autofix_config)
        state = workflow_repo.create.call_args[0][0]
        assert state.issue_cache is not None
        assert state.issue_cache["pr_number"] == 42
        assert state.issue_cache["pr_title"] == "PR #42"
        assert "comment_count" in state.issue_cache

    async def test_pr_title_passed_through(
        self,
        orchestrator: PRAutoFixOrchestrator,
        workflow_repo: MagicMock,
        orch_profile: Profile,
        pr_autofix_config: PRAutoFixConfig,
    ) -> None:
        """PR title from caller is stored in issue_cache without re-fetching."""
        await self._run_execute_pipeline(
            orchestrator, orch_profile, pr_autofix_config,
            pr_title="Fix: broken tests",
        )
        state = workflow_repo.create.call_args[0][0]
        assert state.issue_cache["pr_title"] == "Fix: broken tests"

    async def test_pr_title_fallback_when_empty(
        self,
        orchestrator: PRAutoFixOrchestrator,
        workflow_repo: MagicMock,
        orch_profile: Profile,
        pr_autofix_config: PRAutoFixConfig,
    ) -> None:
        """When no pr_title is provided, falls back to 'PR #<number>'."""
        await self._run_execute_pipeline(orchestrator, orch_profile, pr_autofix_config)
        state = workflow_repo.create.call_args[0][0]
        assert state.issue_cache["pr_title"] == "PR #42"


class TestWorkflowEventEmission:

    @pytest.mark.parametrize(
        ("event_type_name",),
        [
            ("PR_AUTO_FIX_STARTED",),
            ("PR_AUTO_FIX_COMPLETED",),
        ],
    )
    async def test_lifecycle_events_emitted(
        self,
        event_type_name: str,
        orchestrator: PRAutoFixOrchestrator,
        captured_events: list[WorkflowEvent],
        orch_profile: Profile,
        pr_autofix_config: PRAutoFixConfig,
    ) -> None:
        async with mock_pipeline_context():
            await orchestrator._execute_pipeline(
                pr_number=42, repo="owner/repo", profile=orch_profile,
                config=pr_autofix_config, head_branch="feat/test",
            )

        event_type = getattr(EventType, event_type_name)
        matching = [e for e in captured_events if e.event_type == event_type]
        assert len(matching) == 1


class TestWorkflowFailureHandling:

    async def test_failure_sets_failed_status(
        self,
        orchestrator: PRAutoFixOrchestrator,
        workflow_repo: MagicMock,
        orch_profile: Profile,
        pr_autofix_config: PRAutoFixConfig,
    ) -> None:
        async with mock_pipeline_context(
            ainvoke_side_effect=RuntimeError("Pipeline crashed"),
        ):
            with pytest.raises(RuntimeError, match="Pipeline crashed"):
                await orchestrator._execute_pipeline(
                    pr_number=42, repo="owner/repo", profile=orch_profile,
                    config=pr_autofix_config, head_branch="feat/test",
                )

        workflow_repo.update.assert_awaited()
        update_state = workflow_repo.update.call_args[0][0]
        assert update_state.workflow_status == WorkflowStatus.FAILED
        assert "Pipeline crashed" in (update_state.failure_reason or "")


class TestWorkflowCompletion:

    async def test_issue_cache_updated_with_pr_comments(
        self,
        orchestrator: PRAutoFixOrchestrator,
        workflow_repo: MagicMock,
        orch_profile: Profile,
        pr_autofix_config: PRAutoFixConfig,
    ) -> None:
        final_state = {
            "comments": [
                {
                    "id": 101, "path": "src/main.py", "line": 10,
                    "body": "Fix this variable name",
                    "user": {"login": "reviewer1"},
                    "html_url": "https://github.com/owner/repo/pull/42#discussion_r101",
                },
            ],
            "group_results": [
                {"file_path": "src/main.py", "status": "fixed", "comment_ids": [101]},
            ],
            "resolution_results": [
                {"comment_id": 101, "replied": True, "resolved": True},
            ],
        }
        async with mock_pipeline_context(ainvoke_return=final_state):
            await orchestrator._execute_pipeline(
                pr_number=42, repo="owner/repo", profile=orch_profile,
                config=pr_autofix_config, head_branch="feat/test",
            )

        workflow_repo.update.assert_awaited()
        update_state = workflow_repo.update.call_args[0][0]
        assert update_state.workflow_status == WorkflowStatus.COMPLETED
        assert update_state.issue_cache is not None
        assert "pr_comments" in update_state.issue_cache
        assert update_state.issue_cache["pr_number"] == 42
        assert update_state.issue_cache["pr_title"] == "PR #42"
        assert "comment_count" in update_state.issue_cache
