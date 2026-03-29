from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from amelia.core.types import AgentConfig, Issue, Profile, ReviewResult
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.nodes import call_reviewer_node


@pytest.fixture
def profile_with_agents():
    return Profile(
        name="test",
        tracker="noop",
        repo_root="/tmp/test",
        agents={
            "reviewer": AgentConfig(driver="claude", model="opus", options={"max_iterations": 3}),
            "task_reviewer": AgentConfig(driver="claude", model="sonnet", options={"max_iterations": 5}),
        },
    )


@pytest.fixture
def mock_state():
    return ImplementationState(
        workflow_id=uuid4(),
        profile_id="test",
        created_at=datetime.now(UTC),
        status="running",
        issue=Issue(id="TEST-1", title="Test", description="Test issue"),
        goal="Implement test feature",
        base_commit="abc123",
    )


@pytest.mark.asyncio
async def test_call_reviewer_node_uses_agent_config(profile_with_agents, mock_state):
    """call_reviewer_node should use profile.get_agent_config('reviewer')."""
    config = {
        "configurable": {
            "profile": profile_with_agents,
            "thread_id": str(uuid4()),
        }
    }

    mock_review_result = ReviewResult(
        severity="none",
        approved=True,
        comments=[],
        reviewer_persona="Senior Engineer",
    )

    with patch("amelia.pipelines.nodes.Reviewer") as MockReviewer:
        mock_reviewer = MagicMock()
        mock_reviewer.agentic_review = AsyncMock(return_value=(mock_review_result, "session-1"))
        mock_reviewer.driver = MagicMock()
        MockReviewer.return_value = mock_reviewer

        with patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock):
            await call_reviewer_node(mock_state, config)

        # Verify Reviewer was instantiated with AgentConfig
        call_args = MockReviewer.call_args
        assert call_args is not None
        config_arg = call_args[0][0]  # First positional arg
        assert isinstance(config_arg, AgentConfig)
        assert config_arg.driver == "claude"
        assert config_arg.model == "opus"  # reviewer, not task_reviewer


@pytest.mark.asyncio
async def test_call_reviewer_node_writes_diff_file(profile_with_agents, mock_state):
    """call_reviewer_node should write a diff.patch file before calling agentic_review.

    The file must be at /tmp/amelia-review-{workflow_id}/diff.patch and the
    agentic_review mock should be called with diff_path kwarg pointing to it.
    """
    thread_id = str(uuid4())
    config = {
        "configurable": {
            "profile": profile_with_agents,
            "thread_id": thread_id,
        }
    }

    mock_review_result = ReviewResult(
        severity="none",
        approved=True,
        comments=[],
        reviewer_persona="Senior Engineer",
    )

    captured_kwargs: dict = {}

    async def capture_agentic_review(state, base_commit, profile, **kwargs):
        captured_kwargs.update(kwargs)
        return (mock_review_result, "session-1")

    with patch("amelia.pipelines.nodes.Reviewer") as MockReviewer:
        mock_reviewer = MagicMock()
        mock_reviewer.agentic_review = capture_agentic_review
        mock_reviewer.driver = MagicMock()
        MockReviewer.return_value = mock_reviewer

        with patch("amelia.pipelines.nodes._run_git_command", new_callable=AsyncMock) as mock_git:
            mock_git.side_effect = [
                "file1.py\nfile2.py",  # --name-only
                "diff --git a/file1.py b/file1.py\n--- a/file1.py\n+++ b/file1.py\n@@ -1 +1 @@\n-old\n+new",  # diff
                "2 files changed, 1 insertion(+), 1 deletion(-)",  # --stat
            ]

            with patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock):
                await call_reviewer_node(mock_state, config)

    # agentic_review must have been called with diff_path kwarg
    assert "diff_path" in captured_kwargs, "agentic_review must be called with diff_path kwarg"
    diff_path_str = captured_kwargs["diff_path"]
    assert diff_path_str is not None
    assert "diff.patch" in diff_path_str
    assert thread_id in diff_path_str

    # The diff directory should be cleaned up after the call
    expected_dir = Path(f"/tmp/amelia-review-{thread_id}")
    assert not expected_dir.exists(), "diff directory should be cleaned up after review"


@pytest.mark.asyncio
async def test_call_reviewer_node_diff_file_content(profile_with_agents, mock_state):
    """diff.patch must contain stat summary, changed file list, and raw diff.

    Checks the content written to the diff file before cleanup.
    """
    written_content: list[str] = []

    config = {
        "configurable": {
            "profile": profile_with_agents,
            "thread_id": str(uuid4()),
        }
    }

    mock_review_result = ReviewResult(
        severity="none",
        approved=True,
        comments=[],
        reviewer_persona="Senior Engineer",
    )

    original_write_text = Path.write_text

    def capturing_write_text(self: Path, content: str, *args, **kwargs):
        if "diff.patch" in str(self):
            written_content.append(content)
        return original_write_text(self, content, *args, **kwargs)

    with patch("amelia.pipelines.nodes.Reviewer") as MockReviewer:
        mock_reviewer = MagicMock()
        mock_reviewer.agentic_review = AsyncMock(return_value=(mock_review_result, "session-1"))
        mock_reviewer.driver = MagicMock()
        MockReviewer.return_value = mock_reviewer

        with patch("amelia.pipelines.nodes._run_git_command", new_callable=AsyncMock) as mock_git:
            mock_git.side_effect = [
                "file1.py\nfile2.py",  # --name-only
                "diff --git a/file1.py b/file1.py\n+new line",  # diff
                "1 file changed, 1 insertion(+)",  # --stat
            ]

            with (
                patch.object(Path, "write_text", capturing_write_text),
                patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock),
            ):
                await call_reviewer_node(mock_state, config)

    assert len(written_content) == 1, "Expected exactly one diff.patch write"
    content = written_content[0]

    # Must contain stat header
    assert "1 file changed, 1 insertion(+)" in content, "Must contain stat summary"
    # Must contain changed file list
    assert "file1.py" in content, "Must contain changed files"
    assert "file2.py" in content, "Must contain changed files"
    # Must contain raw diff
    assert "diff --git" in content, "Must contain raw diff"


@pytest.mark.asyncio
async def test_call_reviewer_node_cleans_up_diff_on_error(profile_with_agents, mock_state):
    """diff directory must be cleaned up even when agentic_review raises an exception."""
    thread_id = str(uuid4())
    expected_dir = Path(f"/tmp/amelia-review-{thread_id}")

    config = {
        "configurable": {
            "profile": profile_with_agents,
            "thread_id": thread_id,
        }
    }

    with patch("amelia.pipelines.nodes.Reviewer") as MockReviewer:
        mock_reviewer = MagicMock()
        mock_reviewer.agentic_review = AsyncMock(side_effect=RuntimeError("Review failed"))
        mock_reviewer.driver = MagicMock()
        MockReviewer.return_value = mock_reviewer

        with patch("amelia.pipelines.nodes._run_git_command", new_callable=AsyncMock) as mock_git:
            mock_git.side_effect = [
                "file1.py",  # --name-only
                "diff content",  # diff
                "1 file changed",  # --stat
            ]

            with (
                patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock),
                pytest.raises(RuntimeError, match="Review failed"),
            ):
                await call_reviewer_node(mock_state, config)

    # The diff directory must be cleaned up even after an exception
    assert not expected_dir.exists(), "diff directory must be cleaned up even on error"
