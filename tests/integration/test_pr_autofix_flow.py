"""Integration tests for PR auto-fix end-to-end flow.

Tests the full pipeline graph: classify_node → develop_node →
commit_push_node → reply_resolve_node. Mocks only at external
boundaries: LLM driver, Developer agent, git operations, GitHub API.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from amelia.agents.schemas.classifier import (
    ClassificationOutput,
    CommentCategory,
    CommentClassification,
)
from amelia.core.types import (
    AgentConfig,
    DriverType,
    PRAutoFixConfig,
    Profile,
    PRReviewComment,
    PRSummary,
)
from amelia.pipelines.pr_auto_fix.graph import create_pr_auto_fix_graph
from amelia.pipelines.pr_auto_fix.orchestrator import PRAutoFixOrchestrator
from amelia.pipelines.pr_auto_fix.state import GroupFixStatus, PRAutoFixState
from amelia.server.events.bus import EventBus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)


def _make_profile(tmp_path: object) -> Profile:
    return Profile(
        name="test-profile",
        repo_root=str(tmp_path),
        agents={
            "developer": AgentConfig(driver=DriverType.API, model="test-model"),
        },
        pr_autofix=PRAutoFixConfig(
            poll_label="amelia",
            poll_interval=60,
            ignore_authors=["bot-user"],
            post_push_cooldown_seconds=0,
            max_cooldown_seconds=0,
        ),
    )


def _make_comments(pr_number: int = 42) -> list[PRReviewComment]:
    return [
        PRReviewComment(
            id=100,
            body="Variable name `x` should be `count` for clarity.",
            author="reviewer1",
            created_at=_NOW,
            path="src/app.py",
            line=10,
            diff_hunk="@@ -8,3 +8,4 @@\n+x = 0",
            thread_id="PRRT_thread1",
            pr_number=pr_number,
        ),
        PRReviewComment(
            id=101,
            body="Missing null check before accessing `.name`.",
            author="reviewer2",
            created_at=_NOW,
            path="src/app.py",
            line=25,
            diff_hunk="@@ -23,3 +23,4 @@\n+print(obj.name)",
            thread_id="PRRT_thread2",
            pr_number=pr_number,
        ),
    ]


def _make_classification_output(comment_ids: list[int]) -> ClassificationOutput:
    """Build a ClassificationOutput matching the test comments."""
    return ClassificationOutput(
        classifications=[
            CommentClassification(
                comment_id=comment_ids[0],
                category=CommentCategory.STYLE,
                confidence=0.95,
                actionable=True,
                reason="Variable naming",
            ),
            CommentClassification(
                comment_id=comment_ids[1],
                category=CommentCategory.BUG,
                confidence=0.90,
                actionable=True,
                reason="Missing null check",
            ),
        ]
    )


@pytest.fixture()
def profile(tmp_path: object) -> Profile:
    return _make_profile(tmp_path)


@pytest.fixture()
def comments() -> list[PRReviewComment]:
    return _make_comments()


@pytest.fixture()
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def orchestrator(event_bus: EventBus) -> PRAutoFixOrchestrator:
    github_pr = MagicMock()
    github_pr.create_issue_comment = AsyncMock()
    return PRAutoFixOrchestrator(
        event_bus=event_bus,
        github_pr_service=github_pr,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_driver_for_classify(comment_ids: list[int]) -> MagicMock:
    """Create a mock driver that returns valid ClassificationOutput."""
    driver = MagicMock()
    output = _make_classification_output(comment_ids)
    driver.generate = AsyncMock(return_value=(output, None))
    return driver


def _mock_developer() -> MagicMock:
    """Create a mock Developer whose run() yields one state then stops."""

    async def fake_run(state: Any, **kwargs: Any):
        """Yield the state back unchanged (simulates successful fix)."""
        yield state, None

    dev = MagicMock()
    dev.run = fake_run
    return dev


# ---------------------------------------------------------------------------
# Test: Full pipeline graph with real nodes
# ---------------------------------------------------------------------------


class TestPipelineEndToEnd:
    """Run the real LangGraph graph with mocks only at external boundaries."""

    async def test_comments_flow_through_classify_to_develop(
        self,
        profile: Profile,
        comments: list[PRReviewComment],
        event_bus: EventBus,
    ) -> None:
        """Comments must be classified by classify_node, grouped, then
        developed by develop_node, committed, and replied to."""

        graph = create_pr_auto_fix_graph()

        initial_state = PRAutoFixState(
            workflow_id=uuid4(),
            profile_id=profile.name,
            pr_number=42,
            head_branch="feat/test",
            repo="owner/repo",
            comments=comments,
            autofix_config=profile.pr_autofix,
            created_at=datetime.now(tz=UTC),
        )

        config = {
            "configurable": {
                "thread_id": str(uuid4()),
                "profile": profile,
                "event_bus": event_bus,
                "metrics_repo": None,
                "metrics_run_id": None,
            },
        }

        mock_driver = _mock_driver_for_classify([100, 101])
        mock_dev = _mock_developer()

        mock_git_ops = MagicMock()
        mock_git_ops.has_changes = AsyncMock(return_value=True)
        mock_git_ops.stage_and_commit = AsyncMock(return_value="abc1234")
        mock_git_ops.safe_push = AsyncMock()

        mock_github_service = MagicMock()
        mock_github_service.reply_to_comment = AsyncMock()
        mock_github_service.resolve_thread = AsyncMock()

        with (
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.get_driver",
                return_value=mock_driver,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.Developer",
                return_value=mock_dev,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitOperations",
                return_value=mock_git_ops,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitHubPRService",
                return_value=mock_github_service,
            ),
        ):
            final_state = await graph.ainvoke(initial_state, config=config)

        # classify_node should have produced classifications
        assert len(final_state["classified_comments"]) == 2

        # develop_node should have produced group results
        assert len(final_state["group_results"]) > 0
        assert any(r.status == GroupFixStatus.FIXED for r in final_state["group_results"])

        # commit_push_node should have committed
        mock_git_ops.stage_and_commit.assert_called_once()

        # reply_resolve_node should have replied and resolved
        assert mock_github_service.reply_to_comment.call_count >= 1
        assert mock_github_service.resolve_thread.call_count >= 1

    async def test_empty_comments_skip_all_nodes(
        self,
        profile: Profile,
        event_bus: EventBus,
    ) -> None:
        """When comments list is empty, classify_node returns early,
        develop_node has no groups, and no commits or replies happen."""

        graph = create_pr_auto_fix_graph()

        initial_state = PRAutoFixState(
            workflow_id=uuid4(),
            profile_id=profile.name,
            pr_number=42,
            head_branch="feat/test",
            repo="owner/repo",
            comments=[],
            autofix_config=profile.pr_autofix,
            created_at=datetime.now(tz=UTC),
        )

        config = {
            "configurable": {
                "thread_id": str(uuid4()),
                "profile": profile,
                "event_bus": event_bus,
                "metrics_repo": None,
                "metrics_run_id": None,
            },
        }

        mock_git_ops = MagicMock()
        mock_git_ops.has_changes = AsyncMock(return_value=False)
        mock_git_ops.stage_and_commit = AsyncMock()

        mock_github_service = MagicMock()
        mock_github_service.reply_to_comment = AsyncMock()

        with (
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitOperations",
                return_value=mock_git_ops,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitHubPRService",
                return_value=mock_github_service,
            ),
        ):
            final_state = await graph.ainvoke(initial_state, config=config)

        assert final_state["classified_comments"] == []
        assert final_state["file_groups"] == {}
        mock_git_ops.stage_and_commit.assert_not_called()
        mock_github_service.reply_to_comment.assert_not_called()

    async def test_driver_error_propagates(
        self,
        profile: Profile,
        comments: list[PRReviewComment],
        event_bus: EventBus,
    ) -> None:
        """If the LLM driver fails with RuntimeError, it must propagate
        up (not be silently swallowed with an empty commit)."""

        graph = create_pr_auto_fix_graph()

        initial_state = PRAutoFixState(
            workflow_id=uuid4(),
            profile_id=profile.name,
            pr_number=42,
            head_branch="feat/test",
            repo="owner/repo",
            comments=comments,
            autofix_config=profile.pr_autofix,
            created_at=datetime.now(tz=UTC),
        )

        config = {
            "configurable": {
                "thread_id": str(uuid4()),
                "profile": profile,
                "event_bus": event_bus,
                "metrics_repo": None,
                "metrics_run_id": None,
            },
        }

        mock_driver = MagicMock()
        mock_driver.generate = AsyncMock(
            side_effect=RuntimeError("Claude SDK did not return a result message"),
        )

        mock_git_ops = MagicMock()
        mock_git_ops.stage_and_commit = AsyncMock()

        with (
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.get_driver",
                return_value=mock_driver,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitOperations",
                return_value=mock_git_ops,
            ),
            pytest.raises(RuntimeError, match="Claude SDK did not return a result message"),
        ):
            await graph.ainvoke(initial_state, config=config)

        # Must NOT have committed anything
        mock_git_ops.stage_and_commit.assert_not_called()


# ---------------------------------------------------------------------------
# Test: Orchestrator threads comments into pipeline
# ---------------------------------------------------------------------------


class TestOrchestratorThreadsComments:
    """Verify the orchestrator passes comments and config to the real pipeline."""

    async def test_trigger_fix_cycle_runs_pipeline_with_comments(
        self,
        orchestrator: PRAutoFixOrchestrator,
        profile: Profile,
        comments: list[PRReviewComment],
        event_bus: EventBus,
    ) -> None:
        """trigger_fix_cycle must pass comments and autofix_config
        through to the graph execution."""

        mock_driver = _mock_driver_for_classify([100, 101])
        mock_dev = _mock_developer()

        mock_git_ops = MagicMock()
        mock_git_ops.has_changes = AsyncMock(return_value=True)
        mock_git_ops.stage_and_commit = AsyncMock(return_value="abc1234")
        mock_git_ops.safe_push = AsyncMock()
        mock_git_ops.fetch_origin = AsyncMock()
        mock_git_ops.checkout_and_reset = AsyncMock()

        mock_github_service = MagicMock()
        mock_github_service.reply_to_comment = AsyncMock()
        mock_github_service.resolve_thread = AsyncMock()

        # Mock LocalWorktree as async context manager returning a fake path
        mock_worktree_instance = AsyncMock()
        mock_worktree_instance.__aenter__ = AsyncMock(return_value="/tmp/fake-worktree")
        mock_worktree_instance.__aexit__ = AsyncMock(return_value=None)
        mock_worktree_cls = MagicMock(return_value=mock_worktree_instance)

        with (
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.get_driver",
                return_value=mock_driver,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.Developer",
                return_value=mock_dev,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitOperations",
                return_value=mock_git_ops,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.orchestrator.GitOperations",
                return_value=mock_git_ops,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.orchestrator.LocalWorktree",
                mock_worktree_cls,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitHubPRService",
                return_value=mock_github_service,
            ),
        ):
            await orchestrator.trigger_fix_cycle(
                pr_number=42,
                repo="owner/repo",
                profile=profile,
                head_branch="feat/test",
                comments=comments,
            )

        # The driver was called (classify_node ran with real comments)
        mock_driver.generate.assert_called_once()
        # Git commit happened (develop + commit_push ran)
        mock_git_ops.stage_and_commit.assert_called_once()
        # Replies were posted (reply_resolve ran)
        assert mock_github_service.reply_to_comment.call_count >= 1


# ---------------------------------------------------------------------------
# Test: Poller passes comments to orchestrator
# ---------------------------------------------------------------------------


class TestPollerPassesComments:
    """Verify the poller threads comments through to the orchestrator."""

    async def test_poller_passes_comments_to_trigger_fix_cycle(
        self,
        profile: Profile,
        comments: list[PRReviewComment],
        event_bus: EventBus,
    ) -> None:
        """When the poller detects unresolved comments, it must pass them
        to trigger_fix_cycle so the pipeline can process them."""
        from amelia.server.lifecycle.pr_poller import PRCommentPoller

        mock_orchestrator = MagicMock()
        mock_orchestrator.trigger_fix_cycle = AsyncMock()

        mock_settings_repo = AsyncMock()
        mock_settings_repo.get_server_settings = AsyncMock(
            return_value=MagicMock(pr_polling_enabled=True),
        )

        mock_profile_repo = AsyncMock()
        mock_profile_repo.list_profiles = AsyncMock(return_value=[profile])

        poller = PRCommentPoller(
            profile_repo=mock_profile_repo,
            settings_repo=mock_settings_repo,
            orchestrator=mock_orchestrator,
            event_bus=event_bus,
        )

        mock_service = MagicMock()
        mock_service.list_labeled_prs = AsyncMock(
            return_value=[
                PRSummary(
                    number=42,
                    title="Fix: test PR",
                    head_branch="feat/test",
                    author="dev1",
                    updated_at="2026-03-15T12:00:00Z",
                ),
            ],
        )
        mock_service.fetch_review_comments = AsyncMock(return_value=comments)

        with (
            patch(
                "amelia.server.lifecycle.pr_poller.GitHubPRService",
                return_value=mock_service,
            ),
            patch.object(poller, "_get_repo_slug", return_value="owner/repo"),
        ):
            await poller._poll_profile(profile)

        await asyncio.sleep(0.1)

        mock_orchestrator.trigger_fix_cycle.assert_called_once()
        call_kwargs = mock_orchestrator.trigger_fix_cycle.call_args.kwargs
        assert "comments" in call_kwargs, "Poller must pass comments to trigger_fix_cycle"
        assert len(call_kwargs["comments"]) == 2


# ---------------------------------------------------------------------------
# Test: Concurrent trigger queueing + cooldown
# ---------------------------------------------------------------------------


class TestConcurrentTriggerQueueing:
    """Verify that concurrent trigger_fix_cycle calls queue properly."""

    async def test_second_trigger_queued_while_first_running(
        self,
        profile: Profile,
        comments: list[PRReviewComment],
        event_bus: EventBus,
    ) -> None:
        """When a fix cycle is running for a PR, a second trigger should
        queue (emit PR_FIX_QUEUED) and the pending cycle should run after
        the first completes."""
        from amelia.server.models.events import EventType

        github_pr = MagicMock()
        github_pr.create_issue_comment = AsyncMock()

        orchestrator = PRAutoFixOrchestrator(
            event_bus=event_bus,
            github_pr_service=github_pr,
        )

        # Collect emitted events
        emitted_events: list[Any] = []
        event_bus.subscribe(lambda e: emitted_events.append(e))

        # Track _execute_pipeline calls
        execute_call_count = 0
        execute_started = asyncio.Event()
        execute_proceed = asyncio.Event()

        async def fake_execute_pipeline(*args: Any, **kwargs: Any) -> None:
            nonlocal execute_call_count
            execute_call_count += 1
            if execute_call_count == 1:
                execute_started.set()
                await execute_proceed.wait()
            # Second call completes immediately

        # Mock LocalWorktree as async context manager
        mock_worktree_instance = AsyncMock()
        mock_worktree_instance.__aenter__ = AsyncMock(return_value="/tmp/fake-worktree")
        mock_worktree_instance.__aexit__ = AsyncMock(return_value=None)
        mock_worktree_cls = MagicMock(return_value=mock_worktree_instance)

        with (
            patch.object(orchestrator, "_execute_pipeline", side_effect=fake_execute_pipeline),
            patch(
                "amelia.pipelines.pr_auto_fix.orchestrator.LocalWorktree",
                mock_worktree_cls,
            ),
        ):
            # Start first call in a task
            task1 = asyncio.create_task(
                orchestrator.trigger_fix_cycle(
                    pr_number=42,
                    repo="owner/repo",
                    profile=profile,
                    head_branch="feat/test",
                    comments=comments,
                )
            )
            # Wait for first execute to start
            await execute_started.wait()

            # Second call while first is running
            await orchestrator.trigger_fix_cycle(
                pr_number=42,
                repo="owner/repo",
                profile=profile,
                head_branch="feat/test",
                comments=comments,
            )

            # Let first call complete
            execute_proceed.set()
            await task1

        # PR_FIX_QUEUED should have been emitted
        queued_events = [e for e in emitted_events if e.event_type == EventType.PR_FIX_QUEUED]
        assert len(queued_events) >= 1, "PR_FIX_QUEUED event must be emitted for queued trigger"

        # _execute_pipeline should have been called twice (initial + pending)
        assert execute_call_count == 2, (
            f"Expected 2 _execute_pipeline calls (initial + pending), got {execute_call_count}"
        )


# ---------------------------------------------------------------------------
# Test: Event emission sequence
# ---------------------------------------------------------------------------


class TestEventEmissionSequence:
    """Verify PR_AUTO_FIX_STARTED and PR_AUTO_FIX_COMPLETED events."""

    async def test_started_then_completed_events_emitted(
        self,
        profile: Profile,
        comments: list[PRReviewComment],
        event_bus: EventBus,
    ) -> None:
        """trigger_fix_cycle must emit PR_AUTO_FIX_STARTED followed by
        PR_AUTO_FIX_COMPLETED, both with workflow_id and matching pr_number."""
        from amelia.server.models.events import EventType

        mock_workflow_repo = AsyncMock()
        mock_workflow_repo.create = AsyncMock()
        mock_workflow_repo.update = AsyncMock()

        github_pr = MagicMock()
        github_pr.create_issue_comment = AsyncMock()

        orchestrator = PRAutoFixOrchestrator(
            event_bus=event_bus,
            github_pr_service=github_pr,
            workflow_repo=mock_workflow_repo,
        )

        emitted_events: list[Any] = []
        event_bus.subscribe(lambda e: emitted_events.append(e))

        mock_driver = _mock_driver_for_classify([100, 101])
        mock_dev = _mock_developer()

        mock_git_ops = MagicMock()
        mock_git_ops.has_changes = AsyncMock(return_value=True)
        mock_git_ops.stage_and_commit = AsyncMock(return_value="abc1234")
        mock_git_ops.safe_push = AsyncMock()

        mock_github_service = MagicMock()
        mock_github_service.reply_to_comment = AsyncMock()
        mock_github_service.resolve_thread = AsyncMock()

        mock_worktree_instance = AsyncMock()
        mock_worktree_instance.__aenter__ = AsyncMock(return_value="/tmp/fake-worktree")
        mock_worktree_instance.__aexit__ = AsyncMock(return_value=None)
        mock_worktree_cls = MagicMock(return_value=mock_worktree_instance)

        with (
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.get_driver",
                return_value=mock_driver,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.Developer",
                return_value=mock_dev,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitOperations",
                return_value=mock_git_ops,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.orchestrator.LocalWorktree",
                mock_worktree_cls,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitHubPRService",
                return_value=mock_github_service,
            ),
        ):
            await orchestrator.trigger_fix_cycle(
                pr_number=42,
                repo="owner/repo",
                profile=profile,
                head_branch="feat/test",
                comments=comments,
            )

        # Filter lifecycle events
        started_events = [
            e for e in emitted_events if e.event_type == EventType.PR_AUTO_FIX_STARTED
        ]
        completed_events = [
            e for e in emitted_events if e.event_type == EventType.PR_AUTO_FIX_COMPLETED
        ]

        assert len(started_events) >= 1, "PR_AUTO_FIX_STARTED must be emitted"
        assert len(completed_events) >= 1, "PR_AUTO_FIX_COMPLETED must be emitted"

        # Verify order: STARTED before COMPLETED
        started_idx = emitted_events.index(started_events[0])
        completed_idx = emitted_events.index(completed_events[0])
        assert started_idx < completed_idx, "STARTED must precede COMPLETED"

        # Both must contain workflow_id in data
        assert "workflow_id" in (started_events[0].data or {}), (
            "PR_AUTO_FIX_STARTED must contain workflow_id in data"
        )
        assert "workflow_id" in (completed_events[0].data or {}), (
            "PR_AUTO_FIX_COMPLETED must contain workflow_id in data"
        )

        # Both must have pr_number
        assert started_events[0].data["pr_number"] == 42
        assert completed_events[0].data["pr_number"] == 42


# ---------------------------------------------------------------------------
# Test: Divergence recovery -> retry -> success
# ---------------------------------------------------------------------------


class TestDivergenceRecovery:
    """Verify divergence retry logic in the orchestrator."""

    async def test_divergence_triggers_retry_and_succeeds(
        self,
        profile: Profile,
        comments: list[PRReviewComment],
        event_bus: EventBus,
    ) -> None:
        """When _execute_pipeline raises ValueError('diverged'), the orchestrator
        should emit PR_FIX_DIVERGED and retry. Second attempt succeeds."""
        from amelia.server.models.events import EventType

        github_pr = MagicMock()
        github_pr.create_issue_comment = AsyncMock()

        orchestrator = PRAutoFixOrchestrator(
            event_bus=event_bus,
            github_pr_service=github_pr,
        )

        emitted_events: list[Any] = []
        event_bus.subscribe(lambda e: emitted_events.append(e))

        call_count = 0

        async def fake_execute(
            *args: Any, **kwargs: Any
        ) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("branch diverged from remote")

        mock_worktree_instance = AsyncMock()
        mock_worktree_instance.__aenter__ = AsyncMock(return_value="/tmp/fake-worktree")
        mock_worktree_instance.__aexit__ = AsyncMock(return_value=None)
        mock_worktree_cls = MagicMock(return_value=mock_worktree_instance)

        with (
            patch.object(orchestrator, "_execute_pipeline", side_effect=fake_execute),
            patch(
                "amelia.pipelines.pr_auto_fix.orchestrator.LocalWorktree",
                mock_worktree_cls,
            ),
        ):
            await orchestrator.trigger_fix_cycle(
                pr_number=42,
                repo="owner/repo",
                profile=profile,
                head_branch="feat/test",
                comments=comments,
            )

        # PR_FIX_DIVERGED should have been emitted
        diverged_events = [
            e for e in emitted_events if e.event_type == EventType.PR_FIX_DIVERGED
        ]
        assert len(diverged_events) >= 1, "PR_FIX_DIVERGED must be emitted on divergence"
        assert diverged_events[0].data["attempt"] == 1

        # _execute_pipeline should have been called 2 times (initial + retry)
        assert call_count == 2, f"Expected 2 calls (initial + retry), got {call_count}"


# ---------------------------------------------------------------------------
# Test: Multi-file-group partial failure
# ---------------------------------------------------------------------------


class TestMultiFileGroupPartialFailure:
    """Verify per-group error isolation in the pipeline."""

    async def test_one_group_fixed_one_group_failed(
        self,
        profile: Profile,
        event_bus: EventBus,
    ) -> None:
        """When two file groups are processed and the Developer fails on one,
        the pipeline should produce one FIXED and one FAILED GroupFixResult."""
        from amelia.agents.schemas.classifier import (
            ClassificationOutput,
            CommentCategory,
            CommentClassification,
        )

        # Create comments across two different files
        comments = [
            PRReviewComment(
                id=200,
                body="Rename variable for clarity.",
                author="reviewer1",
                created_at=_NOW,
                path="src/app.py",
                line=10,
                diff_hunk="@@ -8,3 +8,4 @@\n+x = 0",
                thread_id="PRRT_thread_a",
                pr_number=42,
            ),
            PRReviewComment(
                id=201,
                body="Add error handling here.",
                author="reviewer2",
                created_at=_NOW,
                path="src/utils.py",
                line=15,
                diff_hunk="@@ -13,3 +13,4 @@\n+do_thing()",
                thread_id="PRRT_thread_b",
                pr_number=42,
            ),
        ]

        # Mock driver to classify both as actionable
        classification_output = ClassificationOutput(
            classifications=[
                CommentClassification(
                    comment_id=200,
                    category=CommentCategory.STYLE,
                    confidence=0.95,
                    actionable=True,
                    reason="Naming",
                ),
                CommentClassification(
                    comment_id=201,
                    category=CommentCategory.BUG,
                    confidence=0.90,
                    actionable=True,
                    reason="Missing error handling",
                ),
            ]
        )

        mock_driver = MagicMock()
        mock_driver.generate = AsyncMock(return_value=(classification_output, None))

        # Developer succeeds for src/app.py group, fails for src/utils.py group
        dev_call_count = 0

        def make_developer(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal dev_call_count
            dev_call_count += 1

            if dev_call_count == 2:
                # Second group fails
                async def failing_run(state: Any, **kw: Any):
                    raise RuntimeError("LLM refused to generate code")
                    yield  # noqa: B027 - makes it a generator

                dev = MagicMock()
                dev.run = failing_run
                return dev

            # First group succeeds
            return _mock_developer()

        mock_git_ops = MagicMock()
        mock_git_ops.has_changes = AsyncMock(return_value=True)
        mock_git_ops.stage_and_commit = AsyncMock(return_value="def5678")
        mock_git_ops.safe_push = AsyncMock()

        mock_github_service = MagicMock()
        mock_github_service.reply_to_comment = AsyncMock()
        mock_github_service.resolve_thread = AsyncMock()

        graph = create_pr_auto_fix_graph()

        initial_state = PRAutoFixState(
            workflow_id=uuid4(),
            profile_id=profile.name,
            pr_number=42,
            head_branch="feat/test",
            repo="owner/repo",
            comments=comments,
            autofix_config=profile.pr_autofix,
            created_at=datetime.now(tz=UTC),
        )

        config = {
            "configurable": {
                "thread_id": str(uuid4()),
                "profile": profile,
                "event_bus": event_bus,
                "metrics_repo": None,
                "metrics_run_id": None,
            },
        }

        with (
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.get_driver",
                return_value=mock_driver,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.Developer",
                side_effect=make_developer,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitOperations",
                return_value=mock_git_ops,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitHubPRService",
                return_value=mock_github_service,
            ),
        ):
            final_state = await graph.ainvoke(initial_state, config=config)

        # Should have 2 group results
        group_results = final_state["group_results"]
        assert len(group_results) == 2, f"Expected 2 group results, got {len(group_results)}"

        statuses = {r.status for r in group_results}
        assert GroupFixStatus.FIXED in statuses, "One group should be FIXED"
        assert GroupFixStatus.FAILED in statuses, "One group should be FAILED"

        # Commit should still have happened for the fixed group
        mock_git_ops.stage_and_commit.assert_called_once()
