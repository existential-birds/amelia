"""Unit tests for AmeliaClient PR API methods."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from amelia.client.api import (
    AmeliaClient,
    InvalidRequestError,
    PRAutoFixStatusResponse,
    ServerUnreachableError,
    TriggerPRAutoFixResponse,
    WorkflowNotFoundError,
)


def _make_response(status: int, body: dict, *, method: str = "GET", url: str = "http://test") -> httpx.Response:
    request = httpx.Request(method, url)
    return httpx.Response(status_code=status, json=body, request=request)


@pytest.fixture
def client() -> AmeliaClient:
    return AmeliaClient(base_url="http://localhost:8420")


class TestTriggerPRAutofix:
    """Tests for AmeliaClient.trigger_pr_autofix."""

    async def test_trigger_success(self, client: AmeliaClient) -> None:
        """POST to /api/github/prs/{n}/auto-fix returns TriggerPRAutoFixResponse."""
        mock_resp = _make_response(202, {
            "workflow_id": "wf-123",
            "message": "Auto-fix cycle triggered for PR #42",
        })

        with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
            result = await client.trigger_pr_autofix(42, "myprofile")

        assert isinstance(result, TriggerPRAutoFixResponse)
        assert result.workflow_id == "wf-123"
        assert "42" in result.message
        # Verify URL and params
        call_args = mock_post.call_args
        assert "/api/github/prs/42/auto-fix" in call_args.args[0]
        assert call_args.kwargs["params"] == {"profile": "myprofile"}

    async def test_trigger_with_aggressiveness(self, client: AmeliaClient) -> None:
        """Aggressiveness override is sent as JSON body."""
        mock_resp = _make_response(202, {"workflow_id": "wf-456", "message": "ok"})

        with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
            await client.trigger_pr_autofix(10, "prof", aggressiveness="thorough")

        call_args = mock_post.call_args
        assert call_args.kwargs["json"] == {"aggressiveness": "thorough"}

    async def test_trigger_no_aggressiveness_no_body(self, client: AmeliaClient) -> None:
        """Without aggressiveness, no JSON body is sent."""
        mock_resp = _make_response(202, {"workflow_id": "wf-789", "message": "ok"})

        with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
            await client.trigger_pr_autofix(10, "prof")

        call_args = mock_post.call_args
        # No json kwarg or json=None
        assert call_args.kwargs.get("json") is None

    async def test_trigger_server_unreachable(self, client: AmeliaClient) -> None:
        """Connection failure raises ServerUnreachableError."""
        with (
            patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("refused")),
            pytest.raises(ServerUnreachableError),
        ):
            await client.trigger_pr_autofix(1, "prof")

    async def test_trigger_invalid_request(self, client: AmeliaClient) -> None:
        """400 response raises InvalidRequestError."""
        mock_resp = _make_response(400, {"detail": "bad request"})

        with (
            patch("httpx.AsyncClient.post", return_value=mock_resp),
            pytest.raises(InvalidRequestError),
        ):
            await client.trigger_pr_autofix(1, "prof")


class TestListPRs:
    """Tests for AmeliaClient.list_prs."""

    async def test_list_prs_success(self, client: AmeliaClient) -> None:
        """GET /api/github/prs returns PRListResponse."""
        mock_resp = _make_response(200, {
            "prs": [
                {
                    "number": 42,
                    "title": "Fix bug",
                    "author": "user1",
                    "head_branch": "fix-bug",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ]
        })

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            result = await client.list_prs("myprofile")

        assert len(result.prs) == 1
        assert result.prs[0].number == 42

    async def test_list_prs_profile_not_found(self, client: AmeliaClient) -> None:
        """404 response raises WorkflowNotFoundError."""
        mock_resp = _make_response(404, {"detail": "Profile not found"})

        with (
            patch("httpx.AsyncClient.get", return_value=mock_resp),
            pytest.raises(WorkflowNotFoundError),
        ):
            await client.list_prs("nonexistent")


class TestGetPRComments:
    """Tests for AmeliaClient.get_pr_comments."""

    async def test_get_comments_success(self, client: AmeliaClient) -> None:
        """GET /api/github/prs/{n}/comments returns PRCommentsResponse."""
        mock_resp = _make_response(200, {
            "comments": [
                {
                    "id": 1,
                    "body": "Fix this",
                    "path": "src/main.py",
                    "line": 10,
                    "diff_hunk": "@@ -1,3 +1,4 @@",
                    "author": "reviewer",
                    "created_at": "2026-01-01T00:00:00Z",
                    "in_reply_to_id": None,
                    "pr_number": 42,
                }
            ]
        })

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            result = await client.get_pr_comments(42, "myprofile")

        assert len(result.comments) == 1
        assert result.comments[0].body == "Fix this"

    async def test_get_comments_server_error(self, client: AmeliaClient) -> None:
        """5xx response raises HTTPStatusError (not InvalidRequestError)."""
        mock_resp = _make_response(500, {"detail": "Internal error"})

        with (
            patch("httpx.AsyncClient.get", return_value=mock_resp),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await client.get_pr_comments(42, "prof")


class TestGetPRAutoFixStatus:
    """Tests for AmeliaClient.get_pr_autofix_status."""

    async def test_status_enabled(self, client: AmeliaClient) -> None:
        """Returns PRAutoFixStatusResponse with enabled=True."""
        mock_resp = _make_response(200, {
            "enabled": True,
            "config": {
                "aggressiveness": 2,
                "auto_resolve": True,
                "resolve_no_changes": True,
            },
        })

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            result = await client.get_pr_autofix_status("myprofile")

        assert isinstance(result, PRAutoFixStatusResponse)
        assert result.enabled is True
        assert result.config is not None

    async def test_status_disabled(self, client: AmeliaClient) -> None:
        """Returns PRAutoFixStatusResponse with enabled=False."""
        mock_resp = _make_response(200, {"enabled": False, "config": None})

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            result = await client.get_pr_autofix_status("myprofile")

        assert result.enabled is False
        assert result.config is None

    async def test_status_profile_not_found(self, client: AmeliaClient) -> None:
        """404 response raises WorkflowNotFoundError."""
        mock_resp = _make_response(404, {"detail": "Profile not found"})

        with (
            patch("httpx.AsyncClient.get", return_value=mock_resp),
            pytest.raises(WorkflowNotFoundError),
        ):
            await client.get_pr_autofix_status("nonexistent")
