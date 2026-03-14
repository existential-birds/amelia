"""Unit tests for PR auto-fix pipeline node functions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.agents.schemas.classifier import (
    CommentCategory,
    CommentClassification,
)
from amelia.core.agentic_state import AgenticStatus
from amelia.core.types import (
    AgentConfig,
    DriverType,
    PRAutoFixConfig,
    Profile,
    PRReviewComment,
)
from amelia.pipelines.pr_auto_fix.nodes import (
    classify_node,
    commit_push_node,
    develop_node,
)
from amelia.pipelines.pr_auto_fix.state import (
    GroupFixResult,
    GroupFixStatus,
    PRAutoFixState,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_comment(
    *,
    id: int = 1,
    body: str = "Fix this bug",
    path: str | None = "src/app.py",
    line: int | None = 42,
    diff_hunk: str | None = "@@ -1,3 +1,4 @@\n+new line",
) -> PRReviewComment:
    return PRReviewComment(
        id=id,
        body=body,
        author="reviewer1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        path=path,
        line=line,
        diff_hunk=diff_hunk,
    )


def _make_state(
    *,
    comments: list[PRReviewComment] | None = None,
    file_groups: dict[str | None, list[int]] | None = None,
    classified_comments: list[CommentClassification] | None = None,
    pr_number: int = 123,
    head_branch: str = "feat/my-feature",
    repo: str = "owner/repo",
) -> PRAutoFixState:
    return PRAutoFixState(
        workflow_id=uuid.uuid4(),
        profile_id="test",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        pr_number=pr_number,
        head_branch=head_branch,
        repo=repo,
        comments=comments or [],
        file_groups=file_groups or {},
        classified_comments=classified_comments or [],
    )


def _make_profile() -> Profile:
    return Profile(
        name="test",
        repo_root="/tmp/test-repo",
        agents={
            "developer": AgentConfig(driver=DriverType.CLAUDE, model="test-model"),
            "classifier": AgentConfig(driver=DriverType.API, model="test-model"),
        },
    )


def _make_config(profile: Profile | None = None) -> dict[str, Any]:
    """Build a LangGraph-style RunnableConfig."""
    if profile is None:
        profile = _make_profile()
    return {
        "configurable": {
            "thread_id": uuid.uuid4(),
            "profile": profile,
            "event_bus": None,
        }
    }


def _make_classification(
    comment_id: int,
    *,
    category: CommentCategory = CommentCategory.BUG,
    actionable: bool = True,
) -> CommentClassification:
    return CommentClassification(
        comment_id=comment_id,
        category=category,
        confidence=0.95,
        actionable=actionable,
        reason="test classification",
    )


# ---------------------------------------------------------------------------
# classify_node tests
# ---------------------------------------------------------------------------


class TestClassifyNode:
    """Tests for classify_node."""

    @pytest.mark.asyncio
    async def test_classify_orchestrates_filter_classify_group_flow(self) -> None:
        """classify_node calls filter -> classify -> group and writes results."""
        c1 = _make_comment(id=1, path="src/app.py", body="Fix bug here")
        c2 = _make_comment(id=2, path="src/utils.py", body="Style issue")
        state = _make_state(comments=[c1, c2])
        config = _make_config()

        cls1 = _make_classification(1, category=CommentCategory.BUG)
        cls2 = _make_classification(2, category=CommentCategory.STYLE)

        mock_driver = MagicMock()

        with (
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.filter_comments",
                return_value=[c1, c2],
            ) as mock_filter,
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.classify_comments",
                new_callable=AsyncMock,
                return_value={1: cls1, 2: cls2},
            ) as mock_classify,
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.group_comments_by_file",
                return_value={"src/app.py": [c1], "src/utils.py": [c2]},
            ) as mock_group,
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.get_driver",
                return_value=mock_driver,
            ),
        ):
            result = await classify_node(state, config)

        # Verify call chain
        mock_filter.assert_called_once()
        mock_classify.assert_called_once()
        mock_group.assert_called_once()

        # Verify returned state updates
        assert "classified_comments" in result
        assert len(result["classified_comments"]) == 2
        assert "file_groups" in result
        assert "src/app.py" in result["file_groups"]
        assert "src/utils.py" in result["file_groups"]
        # file_groups should map to comment IDs (ints), not PRReviewComment objects
        assert result["file_groups"]["src/app.py"] == [1]
        assert result["file_groups"]["src/utils.py"] == [2]

    @pytest.mark.asyncio
    async def test_classify_empty_comments_returns_empty(self) -> None:
        """classify_node with no comments returns empty results without LLM call."""
        state = _make_state(comments=[])
        config = _make_config()

        with (
            patch(
                "amelia.pipelines.pr_auto_fix.nodes.classify_comments",
                new_callable=AsyncMock,
            ) as mock_classify,
        ):
            result = await classify_node(state, config)

        mock_classify.assert_not_called()
        assert result["classified_comments"] == []
        assert result["file_groups"] == {}


# ---------------------------------------------------------------------------
# develop_node tests
# ---------------------------------------------------------------------------


class TestDevelopNode:
    """Tests for develop_node."""

    @pytest.mark.asyncio
    async def test_develop_builds_goal_with_full_context(self) -> None:
        """develop_node goal string includes body, path, line, diff_hunk, pr_number, category, constraints."""
        c1 = _make_comment(
            id=1,
            body="Fix this null check",
            path="src/app.py",
            line=42,
            diff_hunk="@@ -10,3 +10,4 @@\n+bad code",
        )
        cls1 = _make_classification(1, category=CommentCategory.BUG)
        state = _make_state(
            comments=[c1],
            file_groups={"src/app.py": [1]},
            classified_comments=[cls1],
        )
        config = _make_config()

        captured_goal: str | None = None

        # Mock Developer to capture goal
        mock_dev_instance = MagicMock()

        async def fake_run(impl_state, profile, workflow_id):  # noqa: ANN001, ARG001
            nonlocal captured_goal
            captured_goal = impl_state.goal
            # Yield a completed state
            final_state = impl_state.model_copy(
                update={"agentic_status": AgenticStatus.COMPLETED}
            )
            yield final_state, MagicMock()

        mock_dev_instance.run = fake_run

        with patch(
            "amelia.pipelines.pr_auto_fix.nodes.Developer",
            return_value=mock_dev_instance,
        ):
            result = await develop_node(state, config)

        # Verify goal content
        assert captured_goal is not None
        assert "Fix this null check" in captured_goal
        assert "src/app.py" in captured_goal
        assert "42" in captured_goal
        assert "@@ -10,3 +10,4 @@" in captured_goal
        assert "123" in captured_goal  # pr_number
        assert "bug" in captured_goal.lower()  # category
        # Constraints
        assert "root cause" in captured_goal.lower() or "only modify" in captured_goal.lower()

        # Verify result
        assert len(result["group_results"]) == 1
        assert result["group_results"][0].status == GroupFixStatus.FIXED

    @pytest.mark.asyncio
    async def test_develop_mixed_success_and_failure(self) -> None:
        """develop_node records both successes and failures, continues on failure."""
        c1 = _make_comment(id=1, path="src/good.py", body="Fix A")
        c2 = _make_comment(id=2, path="src/bad.py", body="Fix B")
        cls1 = _make_classification(1)
        cls2 = _make_classification(2)
        state = _make_state(
            comments=[c1, c2],
            file_groups={"src/good.py": [1], "src/bad.py": [2]},
            classified_comments=[cls1, cls2],
        )
        config = _make_config()

        call_count = 0

        mock_dev_instance = MagicMock()

        async def fake_run(impl_state, profile, workflow_id):  # noqa: ANN001, ARG001
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First group succeeds
                final = impl_state.model_copy(
                    update={"agentic_status": AgenticStatus.COMPLETED}
                )
                yield final, MagicMock()
            else:
                # Second group fails
                raise RuntimeError("Developer failed on bad.py")

        mock_dev_instance.run = fake_run

        with patch(
            "amelia.pipelines.pr_auto_fix.nodes.Developer",
            return_value=mock_dev_instance,
        ):
            result = await develop_node(state, config)

        assert len(result["group_results"]) == 2
        statuses = {r.file_path: r.status for r in result["group_results"]}
        assert GroupFixStatus.FIXED in statuses.values()
        assert GroupFixStatus.FAILED in statuses.values()
        # Failed one has error message
        failed = [r for r in result["group_results"] if r.status == GroupFixStatus.FAILED]
        assert len(failed) == 1
        assert "Developer failed" in (failed[0].error or "")

    @pytest.mark.asyncio
    async def test_develop_empty_file_groups_returns_completed(self) -> None:
        """develop_node with empty file_groups returns empty results and COMPLETED."""
        state = _make_state(file_groups={})
        config = _make_config()

        result = await develop_node(state, config)

        assert result["group_results"] == []
        assert result["agentic_status"] == AgenticStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_develop_uses_pr_fix_system_prompt(self) -> None:
        """develop_node passes developer.pr_fix.system prompt to Developer constructor."""
        c1 = _make_comment(id=1, path="src/app.py", body="Fix this")
        cls1 = _make_classification(1)
        state = _make_state(
            comments=[c1],
            file_groups={"src/app.py": [1]},
            classified_comments=[cls1],
        )
        config = _make_config()

        mock_dev_cls = MagicMock()
        mock_dev_instance = MagicMock()

        async def fake_run(impl_state, profile, workflow_id):  # noqa: ANN001, ARG001
            final = impl_state.model_copy(
                update={"agentic_status": AgenticStatus.COMPLETED}
            )
            yield final, MagicMock()

        mock_dev_instance.run = fake_run
        mock_dev_cls.return_value = mock_dev_instance

        with patch(
            "amelia.pipelines.pr_auto_fix.nodes.Developer",
            mock_dev_cls,
        ):
            await develop_node(state, config)

        # Verify Developer constructor received the pr_fix prompt
        call_kwargs = mock_dev_cls.call_args
        prompts = call_kwargs.kwargs.get("prompts") or call_kwargs[1].get("prompts")
        expected_prompt = PROMPT_DEFAULTS["developer.pr_fix.system"].content
        assert prompts is not None
        assert prompts.get("developer.system") == expected_prompt

    @pytest.mark.asyncio
    async def test_develop_all_groups_fail_returns_failed_status(self) -> None:
        """If every group fails, develop_node returns FAILED status."""
        c1 = _make_comment(id=1, path="src/a.py", body="Fix")
        cls1 = _make_classification(1)
        state = _make_state(
            comments=[c1],
            file_groups={"src/a.py": [1]},
            classified_comments=[cls1],
        )
        config = _make_config()

        mock_dev_instance = MagicMock()

        async def fake_run(impl_state, profile, workflow_id):  # noqa: ANN001, ARG001
            raise RuntimeError("Total failure")
            yield  # Make it an async generator  # noqa: RET503

        mock_dev_instance.run = fake_run

        with patch(
            "amelia.pipelines.pr_auto_fix.nodes.Developer",
            return_value=mock_dev_instance,
        ):
            result = await develop_node(state, config)

        assert result["agentic_status"] == AgenticStatus.FAILED
        assert all(r.status == GroupFixStatus.FAILED for r in result["group_results"])


# ---------------------------------------------------------------------------
# commit_push_node tests
# ---------------------------------------------------------------------------


class TestCommitPushNode:
    """Tests for commit_push_node."""

    @pytest.mark.asyncio
    async def test_commit_push_with_changes(self) -> None:
        """commit_push_node stages, commits, and pushes when changes exist."""
        c1 = _make_comment(id=1, path="src/app.py", line=42, body="Fix this bug")
        state = _make_state(
            comments=[c1],
            file_groups={"src/app.py": [1]},
        )
        # Add group_results to state
        state = state.model_copy(update={
            "group_results": [
                GroupFixResult(
                    file_path="src/app.py",
                    status=GroupFixStatus.FIXED,
                    comment_ids=[1],
                ),
            ],
        })
        config = _make_config()

        with patch(
            "amelia.pipelines.pr_auto_fix.nodes.GitOperations"
        ) as mock_git_cls:
            mock_git = AsyncMock()
            mock_git_cls.return_value = mock_git
            mock_git._run_git.return_value = " M src/app.py"  # porcelain output
            mock_git.stage_and_commit.return_value = "abc123def456"
            mock_git.safe_push.return_value = "abc123def456"

            result = await commit_push_node(state, config)

        assert result["status"] == "completed"
        assert result["commit_sha"] == "abc123def456"
        mock_git.stage_and_commit.assert_called_once()
        mock_git.safe_push.assert_called_once_with("feat/my-feature")

        # Verify commit message includes prefix and comment info
        commit_msg = mock_git.stage_and_commit.call_args[0][0]
        assert "fix(review):" in commit_msg
        assert "src/app.py:42" in commit_msg

    @pytest.mark.asyncio
    async def test_commit_push_no_changes_skips(self) -> None:
        """commit_push_node skips commit/push when no files changed."""
        state = _make_state()
        config = _make_config()

        with patch(
            "amelia.pipelines.pr_auto_fix.nodes.GitOperations"
        ) as mock_git_cls:
            mock_git = AsyncMock()
            mock_git_cls.return_value = mock_git
            mock_git._run_git.return_value = ""  # empty porcelain = no changes

            result = await commit_push_node(state, config)

        assert result["status"] == "completed"
        assert result["commit_sha"] is None
        mock_git.stage_and_commit.assert_not_called()
        mock_git.safe_push.assert_not_called()

    @pytest.mark.asyncio
    async def test_commit_push_git_error_returns_failed(self) -> None:
        """commit_push_node returns failed status on git error."""
        state = _make_state()
        config = _make_config()

        with patch(
            "amelia.pipelines.pr_auto_fix.nodes.GitOperations"
        ) as mock_git_cls:
            mock_git = AsyncMock()
            mock_git_cls.return_value = mock_git
            mock_git._run_git.return_value = " M src/app.py"
            mock_git.stage_and_commit.side_effect = ValueError("nothing to commit")

            result = await commit_push_node(state, config)

        assert result["status"] == "failed"
        assert "nothing to commit" in result["error"]

    @pytest.mark.asyncio
    async def test_commit_message_format(self) -> None:
        """Commit message uses configurable prefix and lists addressed comments."""
        c1 = _make_comment(id=1, path="src/app.py", line=10, body="Fix null check")
        c2 = _make_comment(id=2, path="src/utils.py", line=20, body="Add validation")
        state = _make_state(comments=[c1, c2])
        state = state.model_copy(update={
            "group_results": [
                GroupFixResult(
                    file_path="src/app.py",
                    status=GroupFixStatus.FIXED,
                    comment_ids=[1],
                ),
                GroupFixResult(
                    file_path="src/utils.py",
                    status=GroupFixStatus.FIXED,
                    comment_ids=[2],
                ),
            ],
            "autofix_config": PRAutoFixConfig(commit_prefix="chore(review):"),
        })
        config = _make_config()

        with patch(
            "amelia.pipelines.pr_auto_fix.nodes.GitOperations"
        ) as mock_git_cls:
            mock_git = AsyncMock()
            mock_git_cls.return_value = mock_git
            mock_git._run_git.return_value = " M src/app.py\n M src/utils.py"
            mock_git.stage_and_commit.return_value = "abc123"
            mock_git.safe_push.return_value = "abc123"

            await commit_push_node(state, config)

        commit_msg = mock_git.stage_and_commit.call_args[0][0]
        assert "chore(review):" in commit_msg
        assert "address PR review comments" in commit_msg
        assert "src/app.py:10" in commit_msg
        assert "Fix null check" in commit_msg
        assert "src/utils.py:20" in commit_msg
        assert "Add validation" in commit_msg
