"""Unit tests for PR auto-fix pipeline node functions."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.agents.schemas.classifier import CommentCategory
from amelia.core.agentic_state import AgenticStatus
from amelia.core.types import PRAutoFixConfig
from amelia.pipelines.pr_auto_fix.nodes import (
    _build_developer_goal,
    classify_node,
    commit_push_node,
    develop_node,
    reply_resolve_node,
)
from amelia.pipelines.pr_auto_fix.state import (
    GroupFixResult,
    GroupFixStatus,
)

from .conftest import (
    make_classification,
    make_comment,
    make_runnable_config,
    make_state,
)


# ---------------------------------------------------------------------------
# classify_node tests
# ---------------------------------------------------------------------------


class TestClassifyNode:
    """Tests for classify_node."""

    async def test_classify_orchestrates_filter_classify_group_flow(self) -> None:
        c1 = make_comment(id=1, path="src/app.py", body="Fix bug here")
        c2 = make_comment(id=2, path="src/utils.py", body="Style issue")
        state = make_state(comments=[c1, c2])
        config = make_runnable_config()

        cls1 = make_classification(1, category=CommentCategory.BUG)
        cls2 = make_classification(2, category=CommentCategory.STYLE)

        with (
            patch("amelia.pipelines.pr_auto_fix.nodes.filter_comments", return_value=[c1, c2]) as mock_filter,
            patch("amelia.pipelines.pr_auto_fix.nodes.classify_comments", new_callable=AsyncMock, return_value={1: cls1, 2: cls2}) as mock_classify,
            patch("amelia.pipelines.pr_auto_fix.nodes.group_comments_by_file", return_value={"src/app.py": [c1], "src/utils.py": [c2]}) as mock_group,
            patch("amelia.pipelines.pr_auto_fix.nodes.get_driver", return_value=MagicMock()),
        ):
            result = await classify_node(state, config)

        mock_filter.assert_called_once()
        mock_classify.assert_called_once()
        mock_group.assert_called_once()

        assert len(result["classified_comments"]) == 2
        assert result["file_groups"]["src/app.py"] == [1]
        assert result["file_groups"]["src/utils.py"] == [2]

    async def test_classify_empty_comments_returns_empty(self) -> None:
        state = make_state(comments=[])
        config = make_runnable_config()

        with patch("amelia.pipelines.pr_auto_fix.nodes.classify_comments", new_callable=AsyncMock) as mock_classify:
            result = await classify_node(state, config)

        mock_classify.assert_not_called()
        assert result["classified_comments"] == []
        assert result["file_groups"] == {}


# ---------------------------------------------------------------------------
# develop_node helpers
# ---------------------------------------------------------------------------


def _fake_dev_run_success(impl_state: Any, profile: Any, workflow_id: Any) -> Any:
    """Async generator that yields a completed state."""
    async def gen() -> Any:
        final = impl_state.model_copy(update={"agentic_status": AgenticStatus.COMPLETED})
        yield final, MagicMock()
    return gen()


def _fake_dev_run_failure(impl_state: Any, profile: Any, workflow_id: Any) -> Any:
    """Async generator that raises RuntimeError."""
    async def gen() -> Any:
        raise RuntimeError("Developer failed")
        yield  # noqa: RET503
    return gen()


# ---------------------------------------------------------------------------
# _build_developer_goal tests
# ---------------------------------------------------------------------------


class TestBuildDeveloperGoal:
    """Tests for _build_developer_goal context preservation."""

    def test_includes_original_line_when_line_is_none(self) -> None:
        """When line is null (outdated), original_line is used as fallback."""
        c = make_comment(id=1, path="src/app.py", line=None, original_line=15)
        goal = _build_developer_goal("src/app.py", [c], {}, pr_number=1, head_branch="main")
        assert "**Line:** 15" in goal

    def test_includes_multi_line_range(self) -> None:
        """Multi-line comments show start-end range."""
        c = make_comment(id=1, path="src/app.py", line=30, start_line=20)
        goal = _build_developer_goal("src/app.py", [c], {}, pr_number=1, head_branch="main")
        assert "**Lines:** 20-30" in goal

    def test_includes_original_multi_line_range(self) -> None:
        """Multi-line comments with original lines show range when current lines are null."""
        c = make_comment(
            id=1, path="src/app.py", line=None, original_line=28,
            start_line=None, original_start_line=18,
        )
        goal = _build_developer_goal("src/app.py", [c], {}, pr_number=1, head_branch="main")
        assert "**Lines:** 18-28" in goal

    def test_includes_side_label(self) -> None:
        """Side field is rendered as human-readable label."""
        c_right = make_comment(id=1, path="src/app.py", side="RIGHT")
        goal = _build_developer_goal("src/app.py", [c_right], {}, pr_number=1, head_branch="main")
        assert "new code" in goal
        assert "RIGHT" in goal

        c_left = make_comment(id=2, path="src/app.py", side="LEFT")
        goal = _build_developer_goal("src/app.py", [c_left], {}, pr_number=1, head_branch="main")
        assert "old code" in goal
        assert "LEFT" in goal

    def test_includes_file_level_scope(self) -> None:
        """File-level comments are labeled as such."""
        c = make_comment(id=1, path="src/app.py", subject_type="file")
        goal = _build_developer_goal("src/app.py", [c], {}, pr_number=1, head_branch="main")
        assert "file-level comment" in goal

    def test_line_level_has_no_scope_label(self) -> None:
        """Line-level comments don't get extra scope label."""
        c = make_comment(id=1, path="src/app.py", subject_type="line")
        goal = _build_developer_goal("src/app.py", [c], {}, pr_number=1, head_branch="main")
        assert "file-level comment" not in goal


# ---------------------------------------------------------------------------
# develop_node tests
# ---------------------------------------------------------------------------


class TestDevelopNode:
    """Tests for develop_node."""

    async def test_develop_builds_goal_with_full_context(self) -> None:
        c1 = make_comment(
            id=1, body="Fix this null check", path="src/app.py",
            line=42, diff_hunk="@@ -10,3 +10,4 @@\n+bad code",
        )
        cls1 = make_classification(1, category=CommentCategory.BUG)
        state = make_state(
            comments=[c1],
            file_groups={"src/app.py": [1]},
            classified_comments=[cls1],
        )
        config = make_runnable_config()

        captured_goal: str | None = None
        mock_dev_instance = MagicMock()

        async def fake_run(impl_state: Any, profile: Any, workflow_id: Any) -> Any:
            nonlocal captured_goal
            captured_goal = impl_state.goal
            final = impl_state.model_copy(update={"agentic_status": AgenticStatus.COMPLETED})
            yield final, MagicMock()

        mock_dev_instance.run = fake_run

        with patch("amelia.pipelines.pr_auto_fix.nodes.Developer", return_value=mock_dev_instance):
            result = await develop_node(state, config)

        assert captured_goal is not None
        for expected in ["Fix this null check", "src/app.py", "42", "@@ -10,3 +10,4 @@", "123"]:
            assert expected in captured_goal
        assert "bug" in captured_goal.lower()
        assert "root cause" in captured_goal.lower() or "only modify" in captured_goal.lower()

        assert len(result["group_results"]) == 1
        assert result["group_results"][0].status == GroupFixStatus.FIXED

    async def test_develop_mixed_success_and_failure(self) -> None:
        c1 = make_comment(id=1, path="src/good.py", body="Fix A")
        c2 = make_comment(id=2, path="src/bad.py", body="Fix B")
        state = make_state(
            comments=[c1, c2],
            file_groups={"src/good.py": [1], "src/bad.py": [2]},
            classified_comments=[make_classification(1), make_classification(2)],
        )
        config = make_runnable_config()

        call_count = 0
        mock_dev_instance = MagicMock()

        async def fake_run(impl_state: Any, profile: Any, workflow_id: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                final = impl_state.model_copy(update={"agentic_status": AgenticStatus.COMPLETED})
                yield final, MagicMock()
            else:
                raise RuntimeError("Developer failed on bad.py")

        mock_dev_instance.run = fake_run

        with patch("amelia.pipelines.pr_auto_fix.nodes.Developer", return_value=mock_dev_instance):
            result = await develop_node(state, config)

        assert len(result["group_results"]) == 2
        statuses = {r.file_path: r.status for r in result["group_results"]}
        assert GroupFixStatus.FIXED in statuses.values()
        assert GroupFixStatus.FAILED in statuses.values()
        failed = [r for r in result["group_results"] if r.status == GroupFixStatus.FAILED]
        assert "Developer failed" in (failed[0].error or "")

    async def test_develop_empty_file_groups_returns_completed(self) -> None:
        result = await develop_node(make_state(file_groups={}), make_runnable_config())
        assert result["group_results"] == []
        assert result["agentic_status"] == AgenticStatus.COMPLETED

    async def test_develop_uses_pr_fix_system_prompt(self) -> None:
        c1 = make_comment(id=1, path="src/app.py", body="Fix this")
        state = make_state(
            comments=[c1],
            file_groups={"src/app.py": [1]},
            classified_comments=[make_classification(1)],
        )

        mock_dev_cls = MagicMock()
        mock_dev_instance = MagicMock()
        mock_dev_instance.run = _fake_dev_run_success
        mock_dev_cls.return_value = mock_dev_instance

        with patch("amelia.pipelines.pr_auto_fix.nodes.Developer", mock_dev_cls):
            await develop_node(state, make_runnable_config())

        call_kwargs = mock_dev_cls.call_args
        prompts = call_kwargs.kwargs.get("prompts") or call_kwargs[1].get("prompts")
        expected_prompt = PROMPT_DEFAULTS["developer.pr_fix.system"].content
        assert prompts is not None
        assert prompts.get("developer.system") == expected_prompt

    async def test_develop_all_groups_fail_returns_failed_status(self) -> None:
        c1 = make_comment(id=1, path="src/a.py", body="Fix")
        state = make_state(
            comments=[c1],
            file_groups={"src/a.py": [1]},
            classified_comments=[make_classification(1)],
        )

        mock_dev_instance = MagicMock()
        mock_dev_instance.run = _fake_dev_run_failure

        with patch("amelia.pipelines.pr_auto_fix.nodes.Developer", return_value=mock_dev_instance):
            result = await develop_node(state, make_runnable_config())

        assert result["agentic_status"] == AgenticStatus.FAILED
        assert all(r.status == GroupFixStatus.FAILED for r in result["group_results"])


# ---------------------------------------------------------------------------
# commit_push_node tests
# ---------------------------------------------------------------------------


class TestCommitPushNode:
    """Tests for commit_push_node."""

    @staticmethod
    def _mock_git(*, has_changes: bool = True, commit_sha: str = "abc123def456") -> tuple[MagicMock, AsyncMock]:
        """Return (mock_git_cls, mock_git) for patching GitOperations."""
        mock_git = AsyncMock()
        mock_git.has_changes.return_value = has_changes
        mock_git.stage_and_commit.return_value = commit_sha
        mock_git.safe_push.return_value = commit_sha
        mock_git_cls = MagicMock(return_value=mock_git)
        return mock_git_cls, mock_git

    async def test_commit_push_with_changes(self) -> None:
        c1 = make_comment(id=1, path="src/app.py", line=42, body="Fix this bug")
        state = make_state(comments=[c1], file_groups={"src/app.py": [1]})
        state = state.model_copy(update={
            "group_results": [
                GroupFixResult(file_path="src/app.py", status=GroupFixStatus.FIXED, comment_ids=[1]),
            ],
        })

        mock_git_cls, mock_git = self._mock_git()
        with patch("amelia.pipelines.pr_auto_fix.nodes.GitOperations", mock_git_cls):
            result = await commit_push_node(state, make_runnable_config())

        assert result["status"] == "completed"
        assert result["commit_sha"] == "abc123def456"
        mock_git.stage_and_commit.assert_called_once()
        mock_git.safe_push.assert_called_once_with("feat/my-feature")

        commit_msg = mock_git.stage_and_commit.call_args[0][0]
        assert "fix(review):" in commit_msg
        assert "src/app.py:42" in commit_msg

    async def test_commit_push_no_changes_skips(self) -> None:
        mock_git_cls, mock_git = self._mock_git(has_changes=False)
        with patch("amelia.pipelines.pr_auto_fix.nodes.GitOperations", mock_git_cls):
            result = await commit_push_node(make_state(), make_runnable_config())

        assert result["status"] == "completed"
        assert result["commit_sha"] is None
        mock_git.stage_and_commit.assert_not_called()
        mock_git.safe_push.assert_not_called()

    async def test_commit_push_git_error_returns_failed(self) -> None:
        mock_git_cls, mock_git = self._mock_git()
        mock_git.stage_and_commit.side_effect = ValueError("nothing to commit")
        with patch("amelia.pipelines.pr_auto_fix.nodes.GitOperations", mock_git_cls):
            result = await commit_push_node(make_state(), make_runnable_config())

        assert result["status"] == "failed"
        assert "nothing to commit" in result["error"]

    async def test_commit_message_format(self) -> None:
        c1 = make_comment(id=1, path="src/app.py", line=10, body="Fix null check")
        c2 = make_comment(id=2, path="src/utils.py", line=20, body="Add validation")
        state = make_state(comments=[c1, c2])
        state = state.model_copy(update={
            "group_results": [
                GroupFixResult(file_path="src/app.py", status=GroupFixStatus.FIXED, comment_ids=[1]),
                GroupFixResult(file_path="src/utils.py", status=GroupFixStatus.FIXED, comment_ids=[2]),
            ],
            "autofix_config": PRAutoFixConfig(commit_prefix="chore(review):"),
        })

        mock_git_cls, mock_git = self._mock_git(commit_sha="abc123")
        mock_git._run_git.return_value = " M src/app.py\n M src/utils.py"
        with patch("amelia.pipelines.pr_auto_fix.nodes.GitOperations", mock_git_cls):
            await commit_push_node(state, make_runnable_config())

        commit_msg = mock_git.stage_and_commit.call_args[0][0]
        for expected in ["chore(review):", "address PR review comments", "src/app.py:10", "Fix null check", "src/utils.py:20", "Add validation"]:
            assert expected in commit_msg


# ---------------------------------------------------------------------------
# reply_resolve_node tests
# ---------------------------------------------------------------------------


def _make_reply_resolve_state(
    *,
    comment_ids: list[int] | None = None,
    status: GroupFixStatus = GroupFixStatus.FIXED,
    error: str | None = None,
    commit_sha: str = "abc1234567890",
    authors: list[str] | None = None,
    thread_ids: list[str | None] | None = None,
    autofix_config: PRAutoFixConfig | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Build state + config for reply_resolve_node tests."""
    cids = comment_ids or [1]
    auths = authors or ["reviewer1"] * len(cids)
    tids = thread_ids or ["T_abc123"] * len(cids)

    comments = [
        make_comment(id=cid, author=auth, thread_id=tid)
        for cid, auth, tid in zip(cids, auths, tids, strict=True)
    ]
    groups = [
        GroupFixResult(
            file_path=f"src/file{i}.py",
            status=status,
            error=error,
            comment_ids=[cid],
        )
        for i, cid in enumerate(cids)
    ]
    state = make_state(
        comments=comments,
        commit_sha=commit_sha,
        group_results=groups,
        autofix_config=autofix_config,
    )
    return state, make_runnable_config()


class TestReplyResolveNode:
    """Tests for reply_resolve_node."""

    @staticmethod
    async def _run_node(
        state: Any, config: dict[str, Any], *, setup_mock: Any = None,
    ) -> tuple[dict[str, Any], AsyncMock]:
        with patch("amelia.pipelines.pr_auto_fix.nodes.GitHubPRService") as mock_gh_cls:
            mock_gh = AsyncMock()
            mock_gh_cls.return_value = mock_gh
            if setup_mock:
                setup_mock(mock_gh)
            result = await reply_resolve_node(state, config)
        return result, mock_gh

    async def test_fixed_comment_gets_reply_and_resolve(self) -> None:
        state, config = _make_reply_resolve_state()
        result, mock_gh = await self._run_node(state, config)

        mock_gh.reply_to_comment.assert_called_once()
        body = mock_gh.reply_to_comment.call_args[0][2]
        assert "abc1234" in body

        mock_gh.resolve_thread.assert_called_once_with("T_abc123")
        assert result["status"] == "completed"
        assert result["resolution_results"][0].replied is True
        assert result["resolution_results"][0].resolved is True

    async def test_fixed_reply_includes_commit_sha(self) -> None:
        state, config = _make_reply_resolve_state(commit_sha="deadbeef1234567")
        _, mock_gh = await self._run_node(state, config)

        body = mock_gh.reply_to_comment.call_args[0][2]
        assert "deadbee" in body

    async def test_reply_mentions_author(self) -> None:
        state, config = _make_reply_resolve_state(authors=["octocat"])
        _, mock_gh = await self._run_node(state, config)

        body = mock_gh.reply_to_comment.call_args[0][2]
        assert body.startswith("@octocat")

    async def test_failed_comment_reply_no_resolve(self) -> None:
        state, config = _make_reply_resolve_state(
            status=GroupFixStatus.FAILED, error="Syntax error in generated code",
        )
        result, mock_gh = await self._run_node(state, config)

        body = mock_gh.reply_to_comment.call_args[0][2]
        assert "Syntax error in generated code" in body
        mock_gh.resolve_thread.assert_not_called()
        assert result["resolution_results"][0].replied is True
        assert result["resolution_results"][0].resolved is False

    @pytest.mark.parametrize(
        ("resolve_no_changes", "expect_resolved"),
        [(True, True), (False, False)],
        ids=["resolve-true", "resolve-false"],
    )
    async def test_no_changes_resolve_config_gated(
        self, resolve_no_changes: bool, expect_resolved: bool,
    ) -> None:
        state, config = _make_reply_resolve_state(
            status=GroupFixStatus.NO_CHANGES,
            autofix_config=PRAutoFixConfig(resolve_no_changes=resolve_no_changes),
        )
        result, mock_gh = await self._run_node(state, config)

        if expect_resolved:
            mock_gh.resolve_thread.assert_called_once_with("T_abc123")
        else:
            mock_gh.resolve_thread.assert_not_called()
        assert result["resolution_results"][0].resolved is expect_resolved

    async def test_missing_thread_id_skips_resolve(self) -> None:
        state, config = _make_reply_resolve_state(thread_ids=[None])
        result, mock_gh = await self._run_node(state, config)

        mock_gh.reply_to_comment.assert_called_once()
        mock_gh.resolve_thread.assert_not_called()
        assert result["resolution_results"][0].replied is True
        assert result["resolution_results"][0].resolved is False

    async def test_resolve_failure_nonfatal(self) -> None:
        state, config = _make_reply_resolve_state(
            comment_ids=[1, 2],
            authors=["reviewer1", "reviewer2"],
            thread_ids=["T_abc123", "T_def456"],
        )
        result, mock_gh = await self._run_node(
            state, config,
            setup_mock=lambda m: setattr(m.resolve_thread, "side_effect", [Exception("GraphQL error"), None]),
        )

        assert mock_gh.reply_to_comment.call_count == 2
        assert mock_gh.resolve_thread.call_count == 2

        res1, res2 = result["resolution_results"]
        assert res1.replied is True and res1.resolved is False and res1.error is not None
        assert res2.replied is True and res2.resolved is True

    async def test_graph_includes_reply_resolve(self) -> None:
        from amelia.pipelines.pr_auto_fix.graph import create_pr_auto_fix_graph

        graph = create_pr_auto_fix_graph()
        assert "reply_resolve_node" in set(graph.nodes.keys())
