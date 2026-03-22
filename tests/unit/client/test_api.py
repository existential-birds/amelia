"""Unit tests for AmeliaClient API methods."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

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
    def mock_response_success(self) -> dict[str, Any]:
        """Successful response data."""
        return {
            "id": str(uuid4()),
            "status": "pending",
            "message": "Review workflow created",
        }

    async def test_create_review_workflow_success(
        self,
        api_client: AmeliaClient,
        mock_response_success: dict[str, Any],
        mock_worktree: Path,
    ) -> None:
        """Successfully creates review workflow."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 201
        mock_resp.json = lambda: mock_response_success

        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            response = await api_client.create_review_workflow(
                diff_content="+ new line",
                worktree_path=str(mock_worktree),
                profile="default",
            )

        assert response.id is not None
        assert response.status == "pending"

    async def test_raises_server_unreachable_on_connect_error(
        self,
        api_client: AmeliaClient,
        mock_worktree: Path,
    ) -> None:
        """Raises ServerUnreachableError when server is not running."""
        with patch(
            "httpx.AsyncClient.post",
            side_effect=httpx.ConnectError("Connection refused"),
        ), pytest.raises(ServerUnreachableError) as exc_info:
            await api_client.create_review_workflow(
                diff_content="+ line",
                worktree_path=str(mock_worktree),
            )

        assert "Cannot connect" in str(exc_info.value)

    async def test_raises_workflow_conflict_on_409(
        self,
        api_client: AmeliaClient,
        mock_worktree: Path,
    ) -> None:
        """Raises WorkflowConflictError on 409 response."""
        wf_id = str(uuid4())
        mock_resp = AsyncMock()
        mock_resp.status_code = 409
        mock_resp.json = lambda: {
            "detail": {
                "message": "Workflow already active",
                "active_workflow": {
                    "id": wf_id,
                    "issue_id": "ISSUE-123",
                    "status": "in_progress",
                },
            }
        }

        with (
            patch("httpx.AsyncClient.post", return_value=mock_resp),
            pytest.raises(WorkflowConflictError) as exc_info,
        ):
            await api_client.create_review_workflow(
                diff_content="+ line",
                worktree_path=str(mock_worktree),
            )

        assert exc_info.value.active_workflow is not None
        assert exc_info.value.active_workflow["id"] == wf_id

    async def test_raises_rate_limit_on_429(
        self,
        api_client: AmeliaClient,
        mock_worktree: Path,
    ) -> None:
        """Raises RateLimitError on 429 response."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "30"}

        with (
            patch("httpx.AsyncClient.post", return_value=mock_resp),
            pytest.raises(RateLimitError) as exc_info,
        ):
            await api_client.create_review_workflow(
                diff_content="+ line",
                worktree_path=str(mock_worktree),
            )

        assert exc_info.value.retry_after == 30
