"""Unit tests for AmeliaClient API methods."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from amelia.client.api import (
    AmeliaClient,
    RateLimitError,
    ServerUnreachableError,
    WorkflowConflictError,
)


class TestCreateReviewWorkflow:
    """Tests for AmeliaClient.create_review_workflow."""

    @pytest.fixture
    def client(self) -> AmeliaClient:
        """Create client instance."""
        return AmeliaClient(base_url="http://localhost:8420")

    @pytest.fixture
    def mock_response_success(self) -> dict[str, Any]:
        """Successful response data."""
        return {
            "id": "wf-123",
            "status": "pending",
            "message": "Review workflow created",
        }

    async def test_create_review_workflow_success(
        self,
        client: AmeliaClient,
        mock_response_success: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Successfully creates review workflow."""
        worktree = tmp_path / "repo"
        worktree.mkdir()

        mock_resp = AsyncMock()
        mock_resp.status_code = 201
        # json() is a synchronous method, not async
        mock_resp.json = lambda: mock_response_success

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            response = await client.create_review_workflow(
                diff_content="+ new line",
                worktree_path=str(worktree),
                profile="default",
            )

        assert response.id == "wf-123"
        assert response.status == "pending"

    async def test_raises_server_unreachable_on_connect_error(
        self,
        client: AmeliaClient,
        tmp_path: Path,
    ) -> None:
        """Raises ServerUnreachableError when server is not running."""
        worktree = tmp_path / "repo"
        worktree.mkdir()

        with patch(
            "httpx.AsyncClient.post",
            side_effect=httpx.ConnectError("Connection refused"),
        ), pytest.raises(ServerUnreachableError) as exc_info:
            await client.create_review_workflow(
                diff_content="+ line",
                worktree_path=str(worktree),
            )

        assert "Cannot connect" in str(exc_info.value)

    async def test_raises_workflow_conflict_on_409(
        self,
        client: AmeliaClient,
        tmp_path: Path,
    ) -> None:
        """Raises WorkflowConflictError on 409 response."""
        worktree = tmp_path / "repo"
        worktree.mkdir()

        mock_resp = AsyncMock()
        mock_resp.status_code = 409
        # json() is a synchronous method, not async
        mock_resp.json = lambda: {
            "detail": {
                "message": "Workflow already active",
                "active_workflow": {
                    "id": "wf-existing",
                    "issue_id": "ISSUE-123",
                    "status": "in_progress",
                },
            }
        }

        with (
            patch("httpx.AsyncClient.post", return_value=mock_resp),
            pytest.raises(WorkflowConflictError) as exc_info,
        ):
            await client.create_review_workflow(
                diff_content="+ line",
                worktree_path=str(worktree),
            )

        assert exc_info.value.active_workflow is not None
        assert exc_info.value.active_workflow["id"] == "wf-existing"

    async def test_raises_rate_limit_on_429(
        self,
        client: AmeliaClient,
        tmp_path: Path,
    ) -> None:
        """Raises RateLimitError on 429 response."""
        worktree = tmp_path / "repo"
        worktree.mkdir()

        mock_resp = AsyncMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "30"}

        with (
            patch("httpx.AsyncClient.post", return_value=mock_resp),
            pytest.raises(RateLimitError) as exc_info,
        ):
            await client.create_review_workflow(
                diff_content="+ line",
                worktree_path=str(worktree),
            )

        assert exc_info.value.retry_after == 30
