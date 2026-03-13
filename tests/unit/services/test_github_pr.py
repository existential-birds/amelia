"""Unit tests for GitHubPRService (GHAPI-01 through GHAPI-05)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import PRAutoFixConfig, PRReviewComment, PRSummary
from amelia.services.github_pr import AMELIA_FOOTER, GitHubPRService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def service(tmp_path: object) -> GitHubPRService:
    """Create a GitHubPRService with a temporary repo root."""
    return GitHubPRService(repo_root=str(tmp_path))


def _make_mock_process(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> AsyncMock:
    """Create a mock async subprocess with configurable outputs."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(
        return_value=(stdout.encode(), stderr.encode()),
    )
    proc.returncode = returncode
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 13, 12, 0, 0, tzinfo=timezone.utc)

_REST_COMMENTS = [
    {
        "id": 100,
        "body": "Please fix this variable name",
        "user": {"login": "reviewer1"},
        "created_at": "2026-03-13T12:00:00Z",
        "path": "src/main.py",
        "line": 42,
        "diff_hunk": "@@ -40,3 +40,5 @@",
        "in_reply_to_id": None,
        "node_id": "PRRC_node100",
    },
    {
        "id": 101,
        "body": f"Fixed the name\n\n---\n{AMELIA_FOOTER}",
        "user": {"login": "amelia-bot"},
        "created_at": "2026-03-13T12:05:00Z",
        "path": "src/main.py",
        "line": 42,
        "diff_hunk": "@@ -40,3 +40,5 @@",
        "in_reply_to_id": 100,
        "node_id": "PRRC_node101",
    },
    {
        "id": 102,
        "body": "Looks good but consider using a constant",
        "user": {"login": "ignored-user"},
        "created_at": "2026-03-13T12:10:00Z",
        "path": "src/config.py",
        "line": 10,
        "diff_hunk": "@@ -8,3 +8,5 @@",
        "in_reply_to_id": None,
        "node_id": "PRRC_node102",
    },
    {
        "id": 103,
        "body": "Missing error handling here",
        "user": {"login": "reviewer2"},
        "created_at": "2026-03-13T12:15:00Z",
        "path": "src/handler.py",
        "line": 55,
        "diff_hunk": "@@ -53,3 +53,5 @@",
        "in_reply_to_id": None,
        "node_id": "PRRC_node103",
    },
]

_GRAPHQL_THREADS = {
    "data": {
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "pageInfo": {"hasNextPage": False},
                    "nodes": [
                        {
                            "id": "PRRT_thread1",
                            "isResolved": False,
                            "comments": {"nodes": [{"databaseId": 100}]},
                        },
                        {
                            "id": "PRRT_thread2",
                            "isResolved": True,  # resolved -- should be filtered
                            "comments": {"nodes": [{"databaseId": 101}]},
                        },
                        {
                            "id": "PRRT_thread3",
                            "isResolved": False,
                            "comments": {"nodes": [{"databaseId": 102}]},
                        },
                        {
                            "id": "PRRT_thread4",
                            "isResolved": False,
                            "comments": {"nodes": [{"databaseId": 103}]},
                        },
                    ],
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# GHAPI-01: Fetch unresolved review comments
# ---------------------------------------------------------------------------


async def test_fetch_review_comments_returns_unresolved(
    service: GitHubPRService,
) -> None:
    """Fetch review comments filters out resolved threads and returns PRReviewComment."""
    rest_proc = _make_mock_process(stdout=json.dumps(_REST_COMMENTS))
    graphql_proc = _make_mock_process(stdout=json.dumps(_GRAPHQL_THREADS))

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = [rest_proc, graphql_proc]
        comments = await service.fetch_review_comments(pr_number=42)

    # Comment 101 is in a resolved thread -> filtered
    # Comment 101 also has Amelia footer -> would be filtered by skip logic too
    # Comments 100, 102, 103 are in unresolved threads
    # But 101 belongs to resolved thread -> should not appear
    assert all(isinstance(c, PRReviewComment) for c in comments)
    comment_ids = {c.id for c in comments}
    assert 101 not in comment_ids  # resolved thread
    # At least some unresolved comments should be present
    assert len(comments) > 0
    # Check fields are set correctly
    for c in comments:
        assert c.pr_number == 42
        assert c.thread_id is not None


# ---------------------------------------------------------------------------
# GHAPI-05: Skip self-authored and ignored comments
# ---------------------------------------------------------------------------


async def test_fetch_review_comments_skips_self_and_ignored(
    service: GitHubPRService,
) -> None:
    """Amelia footer comments and ignore-listed authors are filtered out."""
    rest_proc = _make_mock_process(stdout=json.dumps(_REST_COMMENTS))
    graphql_proc = _make_mock_process(stdout=json.dumps(_GRAPHQL_THREADS))

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = [rest_proc, graphql_proc]
        comments = await service.fetch_review_comments(
            pr_number=42,
            ignore_authors=["ignored-user"],
        )

    comment_ids = {c.id for c in comments}
    # Comment 101: Amelia footer -> skipped
    assert 101 not in comment_ids
    # Comment 102: ignored-user -> skipped
    assert 102 not in comment_ids
    # Comments 100, 103 should remain (unresolved, not skipped)
    assert 100 in comment_ids
    assert 103 in comment_ids


# ---------------------------------------------------------------------------
# GHAPI-02: List open PRs
# ---------------------------------------------------------------------------


async def test_list_open_prs(service: GitHubPRService) -> None:
    """list_open_prs returns PRSummary instances with correct field mapping."""
    pr_data = [
        {
            "number": 1,
            "title": "Add feature",
            "headRefName": "feat/new-thing",
            "author": {"login": "dev1"},
            "updatedAt": "2026-03-13T12:00:00Z",
        },
        {
            "number": 2,
            "title": "Fix bug",
            "headRefName": "fix/crash",
            "author": {"login": "dev2"},
            "updatedAt": "2026-03-13T13:00:00Z",
        },
    ]
    proc = _make_mock_process(stdout=json.dumps(pr_data))

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        prs = await service.list_open_prs()

    assert len(prs) == 2
    assert all(isinstance(pr, PRSummary) for pr in prs)
    assert prs[0].head_branch == "feat/new-thing"
    assert prs[0].author == "dev1"
    assert prs[1].number == 2


# ---------------------------------------------------------------------------
# GHAPI-03: Resolve thread
# ---------------------------------------------------------------------------


async def test_resolve_thread(service: GitHubPRService) -> None:
    """resolve_thread sends correct GraphQL mutation."""
    proc = _make_mock_process(
        stdout=json.dumps({
            "data": {"resolveReviewThread": {"thread": {"isResolved": True}}},
        }),
    )

    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        await service.resolve_thread(thread_node_id="PRRT_thread1")

    # Verify gh api graphql was called
    call_args = mock_exec.call_args
    args = call_args[0]
    assert "gh" in args
    assert "graphql" in args
    # threadId should be passed
    arg_str = " ".join(str(a) for a in args)
    assert "PRRT_thread1" in arg_str


# ---------------------------------------------------------------------------
# GHAPI-04: Reply to comment
# ---------------------------------------------------------------------------


async def test_reply_to_comment(service: GitHubPRService) -> None:
    """reply_to_comment appends Amelia footer and uses correct endpoint."""
    proc = _make_mock_process(stdout="{}")

    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        await service.reply_to_comment(
            pr_number=42,
            comment_id=100,
            body="Fixed the variable name.",
        )

    call_args = mock_exec.call_args
    args = call_args[0]
    arg_str = " ".join(str(a) for a in args)
    # Should contain the footer
    assert AMELIA_FOOTER in arg_str
    # Should target the comment endpoint
    assert "/comments/100/replies" in arg_str


async def test_reply_to_comment_uses_parent_id(service: GitHubPRService) -> None:
    """When in_reply_to_id is set, reply uses the parent comment ID (Pitfall 7)."""
    proc = _make_mock_process(stdout="{}")

    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        await service.reply_to_comment(
            pr_number=42,
            comment_id=200,  # This is a reply comment
            body="Fixed.",
            in_reply_to_id=100,  # Parent comment
        )

    call_args = mock_exec.call_args
    args = call_args[0]
    arg_str = " ".join(str(a) for a in args)
    # Should use parent (100), not child (200)
    assert "/comments/100/replies" in arg_str


# ---------------------------------------------------------------------------
# GHAPI-05: _should_skip_comment
# ---------------------------------------------------------------------------


def test_should_skip_comment_footer_match(service: GitHubPRService) -> None:
    """Comment with Amelia footer should be skipped."""
    assert service._should_skip_comment(
        comment_body=f"I fixed it\n\n---\n{AMELIA_FOOTER}",
        comment_author="some-user",
        ignore_authors=[],
    ) is True


def test_should_skip_comment_ignore_list(service: GitHubPRService) -> None:
    """Comment author in ignore list should be skipped."""
    assert service._should_skip_comment(
        comment_body="Normal review comment",
        comment_author="bot-user",
        ignore_authors=["bot-user", "ci-bot"],
    ) is True

    assert service._should_skip_comment(
        comment_body="Normal review comment",
        comment_author="human-reviewer",
        ignore_authors=["bot-user", "ci-bot"],
    ) is False


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


async def test_gh_command_failure_raises_valueerror(
    service: GitHubPRService,
) -> None:
    """Non-zero exit code from gh CLI raises ValueError with stderr."""
    proc = _make_mock_process(
        stdout="",
        stderr="HTTP 404: Not Found",
        returncode=1,
    )

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(ValueError, match="HTTP 404"):
            await service.list_open_prs()


# ---------------------------------------------------------------------------
# PRAutoFixConfig ignore_authors tests
# ---------------------------------------------------------------------------


def test_prautofix_config_ignore_authors_default() -> None:
    """PRAutoFixConfig defaults ignore_authors to empty list."""
    config = PRAutoFixConfig()
    assert config.ignore_authors == []


def test_prautofix_config_ignore_authors_roundtrip() -> None:
    """PRAutoFixConfig with ignore_authors serializes/deserializes correctly."""
    config = PRAutoFixConfig(ignore_authors=["bot1", "bot2"])
    data = config.model_dump(mode="json")
    assert data["ignore_authors"] == ["bot1", "bot2"]

    restored = PRAutoFixConfig.model_validate(data)
    assert restored.ignore_authors == ["bot1", "bot2"]


def test_prautofix_config_backward_compat() -> None:
    """Existing configs without ignore_authors still parse correctly."""
    data = {
        "aggressiveness": "standard",
        "poll_interval": 60,
        "auto_resolve": True,
        "max_iterations": 3,
        "commit_prefix": "fix(review):",
    }
    config = PRAutoFixConfig.model_validate(data)
    assert config.ignore_authors == []
