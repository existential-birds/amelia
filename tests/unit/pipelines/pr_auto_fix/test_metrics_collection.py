"""Tests for metrics collection in orchestrator and classify_node."""

from unittest.mock import AsyncMock, MagicMock, patch

from amelia.core.types import PRAutoFixConfig
from amelia.pipelines.pr_auto_fix.state import GroupFixResult, GroupFixStatus, ResolutionResult
from amelia.server.database import MetricsRepository, WorkflowRepository
from amelia.services.classifier import get_prompt_hash

from .conftest import make_metrics_profile, make_orchestrator


def _make_repos(
    *, metrics_side_effect: Exception | None = None,
    include_metrics: bool = True,
) -> tuple[MagicMock | None, MagicMock]:
    """Create metrics_repo and workflow_repo mocks."""
    workflow_repo = MagicMock(spec=WorkflowRepository)
    workflow_repo.create = AsyncMock()
    workflow_repo.update = AsyncMock()

    if not include_metrics:
        return None, workflow_repo

    metrics_repo = MagicMock(spec=MetricsRepository)
    metrics_repo.save_run_metrics = AsyncMock(side_effect=metrics_side_effect)
    return metrics_repo, workflow_repo


async def _run_pipeline_with_metrics(
    *,
    metrics_side_effect: Exception | None = None,
    include_metrics: bool = True,
    final_state: dict | None = None,
) -> tuple[MagicMock | None, MagicMock]:
    """Run _execute_pipeline with mock pipeline, returning (metrics_repo, workflow_repo)."""
    metrics_repo, workflow_repo = _make_repos(
        metrics_side_effect=metrics_side_effect,
        include_metrics=include_metrics,
    )
    orchestrator = make_orchestrator(
        metrics_repo=metrics_repo, workflow_repo=workflow_repo,
    )

    default_state = {
        "comments": [],
        "group_results": [],
        "resolution_results": [],
        "commit_sha": None,
    }
    mock_final = final_state or default_state

    with patch("amelia.pipelines.pr_auto_fix.orchestrator.PRAutoFixPipeline") as MockPipeline:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=mock_final)
        MockPipeline.return_value.create_graph.return_value = mock_graph
        MockPipeline.return_value.get_initial_state.return_value = (
            mock_final if final_state else {}
        )

        await orchestrator._execute_pipeline(
            pr_number=42, repo="owner/repo",
            profile=make_metrics_profile(), config=PRAutoFixConfig(),
            head_branch="feat",
        )

    return metrics_repo, workflow_repo


class TestOrchestratorTiming:
    """Verify _execute_pipeline measures duration and persists metrics."""

    async def test_save_run_metrics_called_with_positive_duration(self) -> None:
        metrics_repo, _ = await _run_pipeline_with_metrics()
        assert metrics_repo is not None
        metrics_repo.save_run_metrics.assert_called_once()
        assert metrics_repo.save_run_metrics.call_args[1]["duration_seconds"] >= 0.0


class TestPerCommentCounting:
    """Verify correct per-comment counting from group_results."""

    async def test_counts_by_comment_ids_not_groups(self) -> None:
        group_results = [
            GroupFixResult(file_path="a.py", status=GroupFixStatus.FIXED, comment_ids=[1, 2, 3]),
            GroupFixResult(file_path="b.py", status=GroupFixStatus.FAILED, comment_ids=[4, 5]),
        ]
        resolution_results = [
            ResolutionResult(comment_id=1, resolved=True),
            ResolutionResult(comment_id=2, resolved=True),
            ResolutionResult(comment_id=3, resolved=False),
        ]
        final_state = {
            "comments": [MagicMock(id=i) for i in range(1, 8)],
            "group_results": group_results,
            "resolution_results": resolution_results,
            "commit_sha": "abc123",
        }

        metrics_repo, _ = await _run_pipeline_with_metrics(final_state=final_state)
        assert metrics_repo is not None
        kw = metrics_repo.save_run_metrics.call_args[1]
        assert kw["fixes_applied"] == 3
        assert kw["fixes_failed"] == 2
        assert kw["fixes_skipped"] == 2
        assert kw["commits_pushed"] == 1
        assert kw["threads_resolved"] == 2


class TestMetricsFailureIsolation:
    """Verify metrics persistence failure doesn't crash the pipeline."""

    async def test_workflow_completes_when_save_metrics_fails(self) -> None:
        _, workflow_repo = await _run_pipeline_with_metrics(
            metrics_side_effect=Exception("DB write failed"),
        )
        workflow_repo.update.assert_called_once()


class TestMetricsSkippedWhenRepoNone:
    """Verify backward compat when metrics_repo is None."""

    async def test_no_error_when_metrics_repo_is_none(self) -> None:
        # Should NOT raise
        await _run_pipeline_with_metrics(include_metrics=False)


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


class TestNoChangesStatus:
    """Verify NO_CHANGES status is counted as skipped in metrics."""

    async def test_no_changes_counted_as_skipped_in_metrics(self) -> None:
        """NO_CHANGES group results should be excluded from fixed/failed,
        and their comments counted as skipped."""
        group_results = [
            GroupFixResult(
                file_path="a.py",
                status=GroupFixStatus.NO_CHANGES,
                comment_ids=[1, 2],
            ),
        ]
        final_state = {
            "comments": [MagicMock(id=i) for i in range(1, 4)],
            "group_results": group_results,
            "resolution_results": [],
            "commit_sha": None,
        }

        metrics_repo, _ = await _run_pipeline_with_metrics(final_state=final_state)
        assert metrics_repo is not None
        kw = metrics_repo.save_run_metrics.call_args[1]
        assert kw["fixes_applied"] == 0
        assert kw["fixes_failed"] == 0
        # 3 comments total - 0 fixed - 0 failed = 3 skipped
        assert kw["fixes_skipped"] == 3

    async def test_mixed_statuses_counted_correctly(self) -> None:
        """FIXED, FAILED, and NO_CHANGES groups produce correct counters."""
        group_results = [
            GroupFixResult(
                file_path="a.py",
                status=GroupFixStatus.FIXED,
                comment_ids=[1, 2],
            ),
            GroupFixResult(
                file_path="b.py",
                status=GroupFixStatus.FAILED,
                comment_ids=[3],
            ),
            GroupFixResult(
                file_path="c.py",
                status=GroupFixStatus.NO_CHANGES,
                comment_ids=[4, 5],
            ),
        ]
        final_state = {
            "comments": [MagicMock(id=i) for i in range(1, 8)],
            "group_results": group_results,
            "resolution_results": [],
            "commit_sha": "abc123",
        }

        metrics_repo, _ = await _run_pipeline_with_metrics(final_state=final_state)
        assert metrics_repo is not None
        kw = metrics_repo.save_run_metrics.call_args[1]
        assert kw["fixes_applied"] == 2
        assert kw["fixes_failed"] == 1
        # 7 comments - 2 fixed - 1 failed = 4 skipped
        assert kw["fixes_skipped"] == 4


