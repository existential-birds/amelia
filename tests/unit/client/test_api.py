# tests/unit/client/test_api.py
"""Tests for REST API client."""
from unittest.mock import patch

import httpx
import pytest

from amelia.client.api import (
    AmeliaClient,
    RateLimitError,
    ServerUnreachableError,
    WorkflowConflictError,
)
from amelia.client.models import CreateWorkflowResponse, WorkflowListResponse, WorkflowResponse


class TestAmeliaClient:
    """Tests for AmeliaClient."""

    @pytest.fixture
    def client(self):
        """Create API client instance."""
        return AmeliaClient(base_url="http://localhost:8420")

    def test_client_initialization(self, client):
        """Client initializes with base URL."""
        assert client.base_url == "http://localhost:8420"

    @pytest.mark.asyncio
    async def test_create_workflow(self, client):
        """create_workflow sends POST request with correct payload."""
        mock_response = {
            "id": "wf-123",
            "status": "pending",
            "message": "Workflow created for issue ISSUE-123",
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                201,
                json=mock_response,
            )

            result = await client.create_workflow(
                issue_id="ISSUE-123",
                worktree_path="/home/user/repo",
                worktree_name="main",
            )

            assert isinstance(result, CreateWorkflowResponse)
            assert result.id == "wf-123"
            assert result.status == "pending"
            assert "ISSUE-123" in result.message

            # Verify request was made correctly
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs["json"]["issue_id"] == "ISSUE-123"
            assert call_kwargs["json"]["worktree_path"] == "/home/user/repo"

    @pytest.mark.asyncio
    async def test_create_workflow_with_profile(self, client):
        """create_workflow includes profile when provided."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                201,
                json={
                    "id": "wf-123",
                    "status": "pending",
                    "message": "Workflow created for issue ISSUE-123",
                },
            )

            await client.create_workflow(
                issue_id="ISSUE-123",
                worktree_path="/home/user/repo",
                worktree_name="main",
                profile="work",
            )

            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs["json"]["profile"] == "work"

    @pytest.mark.asyncio
    async def test_approve_workflow(self, client):
        """approve_workflow sends POST to correct endpoint."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={"status": "approved"})

            await client.approve_workflow(workflow_id="wf-123")

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/workflows/wf-123/approve" in str(call_args)

    @pytest.mark.asyncio
    async def test_reject_workflow(self, client):
        """reject_workflow sends POST with feedback."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={"status": "rejected"})

            await client.reject_workflow(workflow_id="wf-123", reason="Not ready")

            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs["json"]["feedback"] == "Not ready"

    @pytest.mark.asyncio
    async def test_cancel_workflow(self, client):
        """cancel_workflow sends POST to cancel endpoint."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={"status": "cancelled"})

            await client.cancel_workflow(workflow_id="wf-123")

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/workflows/wf-123/cancel" in str(call_args)

    @pytest.mark.asyncio
    async def test_get_active_workflows(self, client):
        """get_active_workflows fetches active workflows."""
        mock_response = {
            "workflows": [
                {
                    "id": "wf-123",
                    "issue_id": "ISSUE-123",
                    "status": "in_progress",
                    "worktree_path": "/home/user/repo",
                    "worktree_name": "main",
                    "started_at": "2025-12-01T10:00:00Z",
                }
            ],
            "total": 1,
            "cursor": None,
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = httpx.Response(200, json=mock_response)

            result = await client.get_active_workflows()

            assert isinstance(result, WorkflowListResponse)
            assert len(result.workflows) == 1
            assert result.total == 1

    @pytest.mark.asyncio
    async def test_get_active_workflows_filter_by_worktree(self, client):
        """get_active_workflows filters by worktree path client-side."""
        mock_response = {
            "workflows": [
                {
                    "id": "wf-123",
                    "issue_id": "ISSUE-123",
                    "status": "in_progress",
                    "worktree_path": "/home/user/repo",
                    "worktree_name": "main",
                    "started_at": "2025-12-01T10:00:00Z",
                },
                {
                    "id": "wf-456",
                    "issue_id": "ISSUE-456",
                    "status": "in_progress",
                    "worktree_path": "/home/user/other",
                    "worktree_name": "feature",
                    "started_at": "2025-12-01T11:00:00Z",
                },
            ],
            "total": 2,
            "cursor": None,
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = httpx.Response(200, json=mock_response)

            result = await client.get_active_workflows(worktree_path="/home/user/repo")

            # Verify endpoint is /api/workflows/active
            call_args = mock_get.call_args
            assert "/api/workflows/active" in str(call_args)

            # Verify client-side filtering worked
            assert len(result.workflows) == 1
            assert result.workflows[0].id == "wf-123"
            assert result.total == 1

    @pytest.mark.asyncio
    async def test_get_workflow(self, client):
        """get_workflow fetches single workflow by ID."""
        mock_response = {
            "id": "wf-123",
            "issue_id": "ISSUE-123",
            "status": "in_progress",
            "worktree_path": "/home/user/repo",
            "worktree_name": "main",
            "started_at": "2025-12-01T10:00:00Z",
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = httpx.Response(200, json=mock_response)

            result = await client.get_workflow(workflow_id="wf-123")

            assert isinstance(result, WorkflowResponse)
            assert result.id == "wf-123"

    @pytest.mark.asyncio
    async def test_client_handles_409_conflict(self, client):
        """Client raises descriptive error on 409 Conflict."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                409,
                json={
                    "detail": {
                        "error": "workflow_already_active",
                        "message": "Workflow already active",
                        "active_workflow": {
                            "id": "wf-existing",
                            "issue_id": "ISSUE-99",
                            "status": "in_progress",
                        },
                    }
                },
            )

            with pytest.raises(WorkflowConflictError) as exc_info:
                await client.create_workflow(
                    issue_id="ISSUE-123",
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                )

            assert "already active" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_client_handles_429_rate_limit(self, client):
        """Client raises descriptive error on 429 Too Many Requests."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                429,
                headers={"Retry-After": "30"},
                json={"detail": "Too many concurrent workflows"},
            )

            with pytest.raises(RateLimitError) as exc_info:
                await client.create_workflow(
                    issue_id="ISSUE-123",
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                )

            assert "30" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_client_handles_connection_error(self, client):
        """Client raises descriptive error when server is unreachable."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")

            with pytest.raises(ServerUnreachableError) as exc_info:
                await client.create_workflow(
                    issue_id="ISSUE-123",
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                )

            assert "server" in str(exc_info.value).lower()
            assert "8420" in str(exc_info.value)
