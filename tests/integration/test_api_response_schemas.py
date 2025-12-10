# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Integration tests for API client/server response schema compatibility.

These tests verify that the server responses match the client model schemas,
preventing regressions like the CreateWorkflowResponse/WorkflowResponse mismatch.
"""
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import uvicorn

from amelia.client.api import AmeliaClient
from amelia.client.models import CreateWorkflowResponse, WorkflowResponse
from amelia.server.dependencies import get_orchestrator, get_repository
from amelia.server.main import app
from amelia.server.models.state import ServerExecutionState


class TestAPIResponseSchemas:
    """Integration tests verifying client/server schema compatibility."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator that returns predictable workflow IDs."""
        orchestrator = MagicMock()
        orchestrator.start_workflow = AsyncMock(return_value="test-workflow-id-123")
        return orchestrator

    @pytest.fixture
    def mock_repository(self):
        """Create a mock repository with a test workflow."""
        repository = MagicMock()

        # Create a realistic workflow state
        workflow_state = ServerExecutionState(
            id="test-workflow-id-123",
            issue_id="TEST-456",
            worktree_path="/test/path",
            worktree_name="test-worktree",
            workflow_status="pending",
            started_at=datetime.now(UTC),
        )

        repository.get = AsyncMock(return_value=workflow_state)
        repository.save = AsyncMock()
        return repository

    @pytest.fixture
    async def server_with_mocks(self, mock_orchestrator, mock_repository, find_free_port):
        """Start server with mocked dependencies for testing."""
        # Override dependencies
        app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
        app.dependency_overrides[get_repository] = lambda: mock_repository

        port = find_free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)

        # Run server in background task
        task = asyncio.create_task(server.serve())

        # Wait for server to be ready
        base_url = f"http://127.0.0.1:{port}"
        async with httpx.AsyncClient() as client:
            for _ in range(50):  # 5 second timeout
                try:
                    response = await client.get(f"{base_url}/api/health/live")
                    if response.status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.1)

        yield base_url

        # Cleanup
        server.should_exit = True
        await task
        app.dependency_overrides.clear()

    async def test_create_workflow_returns_minimal_response(self, server_with_mocks):
        """REGRESSION: POST /api/workflows returns CreateWorkflowResponse schema.

        The server returns only {id, status, message} for workflow creation.
        The client must NOT expect full workflow details (issue_id, worktree_path, etc.)
        in this response.

        Bug context: Previously, client.create_workflow() tried to deserialize
        the response as WorkflowResponse (which has many required fields),
        causing ValidationError when the server returned the minimal
        CreateWorkflowResponse format.
        """
        client = AmeliaClient(base_url=server_with_mocks)

        # This should succeed - response contains only {id, status, message}
        response = await client.create_workflow(
            issue_id="TEST-123",
            worktree_path="/test/repo/path",
            worktree_name="main",
        )

        # Verify correct response type
        assert isinstance(response, CreateWorkflowResponse)

        # Verify only the minimal fields are present
        assert response.id == "test-workflow-id-123"
        assert response.status == "pending"
        assert "TEST-123" in response.message

        # These fields should NOT exist on CreateWorkflowResponse
        assert not hasattr(response, "issue_id")
        assert not hasattr(response, "worktree_path")
        assert not hasattr(response, "started_at")
        assert not hasattr(response, "current_stage")

    async def test_create_workflow_raw_response_schema(self, server_with_mocks):
        """Verify raw HTTP response matches CreateWorkflowResponse schema exactly."""
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                f"{server_with_mocks}/api/workflows",
                json={
                    "issue_id": "TEST-789",
                    "worktree_path": "/some/path",
                    "worktree_name": "feature",
                },
            )

        assert response.status_code == 201

        data = response.json()

        # Verify exact schema: only these 3 keys
        assert set(data.keys()) == {"id", "status", "message"}
        assert isinstance(data["id"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["message"], str)

    async def test_get_workflow_returns_full_response(self, server_with_mocks):
        """GET /api/workflows/{id} returns WorkflowResponse with full details."""
        client = AmeliaClient(base_url=server_with_mocks)

        # Get workflow details
        response = await client.get_workflow("test-workflow-id-123")

        # Verify correct response type with full details
        assert isinstance(response, WorkflowResponse)
        assert response.id == "test-workflow-id-123"
        assert response.issue_id == "TEST-456"
        assert response.worktree_path == "/test/path"
        assert response.worktree_name == "test-worktree"
        assert response.status == "pending"

    async def test_get_workflow_raw_response_schema(self, server_with_mocks):
        """Verify raw HTTP response from GET includes full workflow details."""
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(
                f"{server_with_mocks}/api/workflows/test-workflow-id-123"
            )

        assert response.status_code == 200

        data = response.json()

        # WorkflowDetailResponse should have these required fields
        assert "id" in data
        assert "issue_id" in data
        assert "worktree_path" in data
        assert "worktree_name" in data
        assert "status" in data

        # Verify values match our mock
        assert data["id"] == "test-workflow-id-123"
        assert data["issue_id"] == "TEST-456"
        assert data["worktree_path"] == "/test/path"

    async def test_create_then_get_workflow_uses_different_schemas(
        self, server_with_mocks
    ):
        """Create returns minimal schema, get returns full schema."""
        client = AmeliaClient(base_url=server_with_mocks)

        # Create workflow - minimal response
        create_response = await client.create_workflow(
            issue_id="TEST-999",
            worktree_path="/another/path",
            worktree_name="develop",
        )

        assert isinstance(create_response, CreateWorkflowResponse)
        assert not hasattr(create_response, "issue_id")

        # Get workflow - full response
        get_response = await client.get_workflow(create_response.id)

        assert isinstance(get_response, WorkflowResponse)
        assert hasattr(get_response, "issue_id")
        assert hasattr(get_response, "worktree_path")
        assert hasattr(get_response, "started_at")
