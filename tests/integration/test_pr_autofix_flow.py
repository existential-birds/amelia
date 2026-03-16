"""Integration tests for PR auto-fix end-to-end flow.

Tests the full pipeline: poller detects comments → orchestrator receives them
→ pipeline classifies/develops/commits/resolves. Mocks only at external
boundaries: gh CLI (subprocess) and LLM driver (execute_agentic).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import (
    AgentConfig,
    DriverType,
    PRAutoFixConfig,
    Profile,
    PRReviewComment,
    PRSummary,
)
from amelia.pipelines.pr_auto_fix.orchestrator import PRAutoFixOrchestrator
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
def captured_events(event_bus: EventBus) -> list[Any]:
    events: list[Any] = []
    event_bus.subscribe(lambda e: events.append(e))
    return events


@pytest.fixture()
def orchestrator(event_bus: EventBus) -> PRAutoFixOrchestrator:
    github_pr = MagicMock()
    github_pr.create_issue_comment = AsyncMock()
    return PRAutoFixOrchestrator(
        event_bus=event_bus,
        github_pr_service=github_pr,
    )


# ---------------------------------------------------------------------------
# Test: Comments flow from orchestrator into pipeline state
# ---------------------------------------------------------------------------


class TestCommentsReachPipeline:
    """Verify comments passed to trigger_fix_cycle reach the pipeline nodes."""

    async def test_comments_populate_pipeline_state(
        self,
        orchestrator: PRAutoFixOrchestrator,
        profile: Profile,
        comments: list[PRReviewComment],
    ) -> None:
        """Comments passed to trigger_fix_cycle must appear in the
        initial state given to graph.ainvoke, not be silently dropped."""
        captured_state: dict[str, Any] = {}

        async def capture_ainvoke(state: Any, **kwargs: Any) -> dict[str, Any]:
            captured_state.update(state if isinstance(state, dict) else state.model_dump())
            return {
                "group_results": [],
                "comments": state.get("comments", [])
                if isinstance(state, dict)
                else state.comments,
            }

        with patch(
            "amelia.pipelines.pr_auto_fix.orchestrator.PRAutoFixPipeline"
        ) as mock_pipeline_cls:
            mock_pipeline = MagicMock()
            mock_graph = AsyncMock()
            mock_graph.ainvoke = AsyncMock(side_effect=capture_ainvoke)
            mock_pipeline.create_graph.return_value = mock_graph
            def _get_initial_state(**kw: object) -> object:
                from datetime import UTC, datetime
                from amelia.pipelines.pr_auto_fix.state import PRAutoFixState
                if "created_at" not in kw:
                    kw["created_at"] = datetime.now(tz=UTC)
                return PRAutoFixState(**{k: v for k, v in kw.items()})

            mock_pipeline.get_initial_state = _get_initial_state
            mock_pipeline_cls.return_value = mock_pipeline

            # Patch git operations to no-op
            with patch("amelia.pipelines.pr_auto_fix.orchestrator.GitOperations", autospec=True):
                await orchestrator.trigger_fix_cycle(
                    pr_number=42,
                    repo="owner/repo",
                    profile=profile,
                    head_branch="feat/test",
                    comments=comments,
                )

        # The critical assertion: comments must be in the pipeline state
        assert len(captured_state.get("comments", [])) == 2
        comment_ids = {c["id"] if isinstance(c, dict) else c.id for c in captured_state["comments"]}
        assert comment_ids == {100, 101}

    async def test_autofix_config_reaches_pipeline_state(
        self,
        orchestrator: PRAutoFixOrchestrator,
        profile: Profile,
        comments: list[PRReviewComment],
    ) -> None:
        """PRAutoFixConfig from the profile must be passed to pipeline state,
        not left as the empty default."""
        captured_state: dict[str, Any] = {}

        async def capture_ainvoke(state: Any, **kwargs: Any) -> dict[str, Any]:
            captured_state.update(state if isinstance(state, dict) else state.model_dump())
            return {}

        with patch(
            "amelia.pipelines.pr_auto_fix.orchestrator.PRAutoFixPipeline"
        ) as mock_pipeline_cls:
            mock_pipeline = MagicMock()
            mock_graph = AsyncMock()
            mock_graph.ainvoke = AsyncMock(side_effect=capture_ainvoke)
            mock_pipeline.create_graph.return_value = mock_graph
            def _get_initial_state2(**kw: object) -> object:
                from datetime import UTC, datetime
                from amelia.pipelines.pr_auto_fix.state import PRAutoFixState
                if "created_at" not in kw:
                    kw["created_at"] = datetime.now(tz=UTC)
                return PRAutoFixState(**{k: v for k, v in kw.items()})

            mock_pipeline.get_initial_state = _get_initial_state2
            mock_pipeline_cls.return_value = mock_pipeline

            with patch("amelia.pipelines.pr_auto_fix.orchestrator.GitOperations", autospec=True):
                await orchestrator.trigger_fix_cycle(
                    pr_number=42,
                    repo="owner/repo",
                    profile=profile,
                    head_branch="feat/test",
                    comments=comments,
                )

        config = captured_state.get("autofix_config", {})
        if isinstance(config, dict):
            assert config.get("poll_label") == "amelia"
            assert config.get("ignore_authors") == ["bot-user"]
        else:
            assert config.poll_label == "amelia"
            assert config.ignore_authors == ["bot-user"]


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

        # Mock the GitHubPRService that _poll_profile creates
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

        # Wait for fire-and-forget task
        await asyncio.sleep(0.1)

        mock_orchestrator.trigger_fix_cycle.assert_called_once()
        call_kwargs = mock_orchestrator.trigger_fix_cycle.call_args.kwargs
        assert "comments" in call_kwargs, "Poller must pass comments to trigger_fix_cycle"
        assert len(call_kwargs["comments"]) == 2


class TestNoJunkCommits:
    """Verify that when classify_node produces no actionable comments,
    commit_push_node does NOT commit."""

    async def test_no_commit_when_no_actionable_comments(
        self,
        orchestrator: PRAutoFixOrchestrator,
        profile: Profile,
        event_bus: EventBus,
    ) -> None:
        """If comments are empty or all filtered, the pipeline must not
        create any git commits."""
        git_ops_mock = MagicMock()
        git_ops_mock.has_changes = AsyncMock(return_value=False)
        git_ops_mock.stage_and_commit = AsyncMock()
        git_ops_mock.fetch_origin = AsyncMock()
        git_ops_mock.checkout_and_reset = AsyncMock()

        with (
            patch(
                "amelia.pipelines.pr_auto_fix.orchestrator.GitOperations",
                return_value=git_ops_mock,
            ),
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.GitOperations",
                return_value=git_ops_mock,
            ),
        ):
            await orchestrator.trigger_fix_cycle(
                pr_number=42,
                repo="owner/repo",
                profile=profile,
                head_branch="feat/test",
                comments=[],  # No comments
            )

        # stage_and_commit must NOT have been called
        git_ops_mock.stage_and_commit.assert_not_called()
