# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
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

    @pytest.mark.parametrize(
        "method_name,endpoint_suffix,method_kwargs,expected_status,should_check_feedback",
        [
            ("approve_workflow", "approve", {}, "approved", False),
            ("reject_workflow", "reject", {"reason": "Not ready"}, "rejected", True),
            ("cancel_workflow", "cancel", {}, "cancelled", False),
        ],
    )
    async def test_workflow_actions(
        self, client, method_name, endpoint_suffix, method_kwargs, expected_status, should_check_feedback
    ):
        """Workflow action methods send POST requests to correct endpoints."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={"status": expected_status})

            method = getattr(client, method_name)
            await method(workflow_id="wf-123", **method_kwargs)

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert f"/api/workflows/wf-123/{endpoint_suffix}" in str(call_args)

            # Verify feedback is passed for reject action
            if should_check_feedback:
                call_kwargs = mock_post.call_args.kwargs
                assert call_kwargs["json"]["feedback"] == "Not ready"

    async def test_get_active_workflows(self, client):
        """get_active_workflows fetches active workflows."""
        mock_response = {
            "workflows": [
                {
                    "id": "wf-123",
                    "issue_id": "ISSUE-123",
                    "status": "in_progress",
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

    async def test_get_active_workflows_filter_by_worktree(self, client):
        """get_active_workflows passes worktree filter as query param."""
        mock_response = {
            "workflows": [
                {
                    "id": "wf-123",
                    "issue_id": "ISSUE-123",
                    "status": "in_progress",
                    "worktree_name": "main",
                    "started_at": "2025-12-01T10:00:00Z",
                },
            ],
            "total": 1,
            "cursor": None,
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = httpx.Response(200, json=mock_response)

            result = await client.get_active_workflows(worktree_path="/home/user/repo")

            # Verify query param is passed
            call_args = mock_get.call_args
            assert "/api/workflows/active" in str(call_args)
            # Verify worktree param was passed
            assert "worktree" in str(call_args) or "params" in str(call_args)

            # Verify response parsed correctly
            assert len(result.workflows) == 1
            assert result.workflows[0].id == "wf-123"
            assert result.total == 1

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

    @pytest.mark.parametrize(
        "error_type,mock_behavior,expected_exception,assertion_checks",
        [
            (
                "409_conflict",
                {
                    "return_value": httpx.Response(
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
                },
                WorkflowConflictError,
                lambda exc_value: "already active" in str(exc_value).lower(),
            ),
            (
                "429_rate_limit",
                {
                    "return_value": httpx.Response(
                        429,
                        headers={"Retry-After": "30"},
                        json={"detail": "Too many concurrent workflows"},
                    )
                },
                RateLimitError,
                lambda exc_value: "30" in str(exc_value),
            ),
            (
                "connection_error",
                {"side_effect": httpx.ConnectError("Connection refused")},
                ServerUnreachableError,
                lambda exc_value: "server" in str(exc_value).lower() and "8420" in str(exc_value),
            ),
        ],
    )
    async def test_client_error_handling(self, client, error_type, mock_behavior, expected_exception, assertion_checks):
        """Client raises appropriate exceptions for various error conditions."""
        with patch("httpx.AsyncClient.post") as mock_post:
            # Apply mock behavior (either return_value or side_effect)
            for attr, value in mock_behavior.items():
                setattr(mock_post, attr, value)

            with pytest.raises(expected_exception) as exc_info:
                await client.create_workflow(
                    issue_id="ISSUE-123",
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                )

            assert assertion_checks(exc_info.value)
