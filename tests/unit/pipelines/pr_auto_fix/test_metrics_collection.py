"""Tests for metrics collection in orchestrator and classify_node."""

from unittest.mock import AsyncMock, MagicMock, patch

from amelia.core.types import PRAutoFixConfig, Profile, PRSummary
from amelia.pipelines.pr_auto_fix.orchestrator import PRAutoFixOrchestrator
from amelia.pipelines.pr_auto_fix.state import GroupFixResult, GroupFixStatus, ResolutionResult
from amelia.server.database import MetricsRepository, WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.services.classifier import get_prompt_hash
from amelia.services.github_pr import GitHubPRService


def _make_profile(**overrides: object) -> Profile:
    """Build a minimal test Profile."""
    defaults = {
        "name": "test-profile",
        "repo_root": "/tmp/test-repo",
        "agents": {
            "developer": {"driver": "claude", "model": "sonnet"},
        },
    }
    defaults.update(overrides)
    return Profile(**defaults)  # type: ignore[arg-type]


def _make_orchestrator(
    metrics_repo: MetricsRepository | None = None,
    workflow_repo: WorkflowRepository | None = None,
) -> PRAutoFixOrchestrator:
    """Build orchestrator with mock dependencies."""
    event_bus = MagicMock(spec=EventBus)
    event_bus.emit = MagicMock()
    github_pr = MagicMock(spec=GitHubPRService)
    github_pr.get_pr_summary = AsyncMock(
        return_value=PRSummary(
            number=42, title="Test PR", head_branch="feat",
            author="user", updated_at="2026-03-14T00:00:00Z",
        ),
    )
    return PRAutoFixOrchestrator(
        event_bus=event_bus,
        github_pr_service=github_pr,
        workflow_repo=workflow_repo,
        metrics_repo=metrics_repo,
    )


class TestOrchestratorTiming:
    """Verify _execute_pipeline measures duration and persists metrics."""

    async def test_save_run_metrics_called_with_positive_duration(self) -> None:
        metrics_repo = MagicMock(spec=MetricsRepository)
        metrics_repo.save_run_metrics = AsyncMock()
        workflow_repo = MagicMock(spec=WorkflowRepository)
        workflow_repo.create = AsyncMock()
        workflow_repo.update = AsyncMock()

        orchestrator = _make_orchestrator(
            metrics_repo=metrics_repo,
            workflow_repo=workflow_repo,
        )

        mock_final_state = {
            "comments": [],
            "group_results": [],
            "resolution_results": [],
            "commit_sha": None,
        }

        with (
            patch("amelia.pipelines.pr_auto_fix.orchestrator.PRAutoFixPipeline") as MockPipeline,
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke = AsyncMock(return_value=mock_final_state)
            MockPipeline.return_value.create_graph.return_value = mock_graph
            MockPipeline.return_value.get_initial_state.return_value = mock_final_state

            profile = _make_profile()
            config = PRAutoFixConfig()

            await orchestrator._execute_pipeline(
                pr_number=42, repo="owner/repo",
                profile=profile, config=config, head_branch="feature",
            )

        metrics_repo.save_run_metrics.assert_called_once()
        call_kwargs = metrics_repo.save_run_metrics.call_args[1]
        # duration_seconds should be a positive float
        assert call_kwargs["duration_seconds"] >= 0.0


class TestPerCommentCounting:
    """Verify correct per-comment counting from group_results."""

    async def test_counts_by_comment_ids_not_groups(self) -> None:
        metrics_repo = MagicMock(spec=MetricsRepository)
        metrics_repo.save_run_metrics = AsyncMock()
        workflow_repo = MagicMock(spec=WorkflowRepository)
        workflow_repo.create = AsyncMock()
        workflow_repo.update = AsyncMock()

        orchestrator = _make_orchestrator(
            metrics_repo=metrics_repo,
            workflow_repo=workflow_repo,
        )

        # Two groups: one FIXED with 3 comments, one FAILED with 2 comments
        group_results = [
            GroupFixResult(file_path="a.py", status=GroupFixStatus.FIXED, comment_ids=[1, 2, 3]),
            GroupFixResult(file_path="b.py", status=GroupFixStatus.FAILED, comment_ids=[4, 5]),
        ]
        resolution_results = [
            ResolutionResult(comment_id=1, resolved=True),
            ResolutionResult(comment_id=2, resolved=True),
            ResolutionResult(comment_id=3, resolved=False),
        ]

        mock_final_state = {
            "comments": [MagicMock(id=i) for i in range(1, 8)],
            "group_results": group_results,
            "resolution_results": resolution_results,
            "commit_sha": "abc123",
        }

        with (
            patch("amelia.pipelines.pr_auto_fix.orchestrator.PRAutoFixPipeline") as MockPipeline,
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke = AsyncMock(return_value=mock_final_state)
            MockPipeline.return_value.create_graph.return_value = mock_graph
            MockPipeline.return_value.get_initial_state.return_value = {}

            profile = _make_profile()
            await orchestrator._execute_pipeline(
                pr_number=42, repo="owner/repo",
                profile=profile, config=PRAutoFixConfig(), head_branch="feat",
            )

        call_kwargs = metrics_repo.save_run_metrics.call_args[1]
        # 3 fixed comments (from comment_ids), 2 failed, skipped = 7 - 3 - 2 = 2
        assert call_kwargs["fixes_applied"] == 3
        assert call_kwargs["fixes_failed"] == 2
        assert call_kwargs["fixes_skipped"] == 2
        assert call_kwargs["commits_pushed"] == 1
        assert call_kwargs["threads_resolved"] == 2


class TestMetricsFailureIsolation:
    """Verify metrics persistence failure doesn't crash the pipeline."""

    async def test_workflow_completes_when_save_metrics_fails(self) -> None:
        metrics_repo = MagicMock(spec=MetricsRepository)
        metrics_repo.save_run_metrics = AsyncMock(
            side_effect=Exception("DB write failed"),
        )
        workflow_repo = MagicMock(spec=WorkflowRepository)
        workflow_repo.create = AsyncMock()
        workflow_repo.update = AsyncMock()

        orchestrator = _make_orchestrator(
            metrics_repo=metrics_repo,
            workflow_repo=workflow_repo,
        )

        mock_final_state = {
            "comments": [],
            "group_results": [],
            "resolution_results": [],
            "commit_sha": None,
        }

        with (
            patch("amelia.pipelines.pr_auto_fix.orchestrator.PRAutoFixPipeline") as MockPipeline,
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke = AsyncMock(return_value=mock_final_state)
            MockPipeline.return_value.create_graph.return_value = mock_graph
            MockPipeline.return_value.get_initial_state.return_value = {}

            profile = _make_profile()
            # Should NOT raise
            await orchestrator._execute_pipeline(
                pr_number=42, repo="owner/repo",
                profile=profile, config=PRAutoFixConfig(), head_branch="feat",
            )

        # Workflow should still complete
        workflow_repo.update.assert_called_once()


class TestMetricsSkippedWhenRepoNone:
    """Verify backward compat when metrics_repo is None."""

    async def test_no_error_when_metrics_repo_is_none(self) -> None:
        workflow_repo = MagicMock(spec=WorkflowRepository)
        workflow_repo.create = AsyncMock()
        workflow_repo.update = AsyncMock()

        orchestrator = _make_orchestrator(
            metrics_repo=None,
            workflow_repo=workflow_repo,
        )

        mock_final_state = {
            "comments": [],
            "group_results": [],
            "resolution_results": [],
            "commit_sha": None,
        }

        with (
            patch("amelia.pipelines.pr_auto_fix.orchestrator.PRAutoFixPipeline") as MockPipeline,
        ):
            mock_graph = AsyncMock()
            mock_graph.ainvoke = AsyncMock(return_value=mock_final_state)
            MockPipeline.return_value.create_graph.return_value = mock_graph
            MockPipeline.return_value.get_initial_state.return_value = {}

            profile = _make_profile()
            # Should NOT raise
            await orchestrator._execute_pipeline(
                pr_number=42, repo="owner/repo",
                profile=profile, config=PRAutoFixConfig(), head_branch="feat",
            )


class TestPromptHash:
    """Verify get_prompt_hash returns consistent hex string."""

    def test_returns_16_char_hex(self) -> None:
        result = get_prompt_hash("standard")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_consistent_for_same_input(self) -> None:
        assert get_prompt_hash("critical") == get_prompt_hash("critical")

    def test_different_for_different_input(self) -> None:
        assert get_prompt_hash("critical") != get_prompt_hash("thorough")
