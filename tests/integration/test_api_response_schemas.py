"""Integration tests for API client/server response schema compatibility.

These tests verify that the server responses match the client model schemas,
preventing regressions like the CreateWorkflowResponse/WorkflowResponse mismatch.

Uses real WorkflowRepository with in-memory SQLite. Only mocks the orchestrator
since it calls external LLM APIs.
"""

import asyncio
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import uvicorn

from amelia.client.api import AmeliaClient
from amelia.client.models import CreateWorkflowResponse, WorkflowResponse
from amelia.core.state import ExecutionState
from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository
from amelia.server.dependencies import get_orchestrator, get_repository
from amelia.server.main import app
from amelia.server.models.state import ServerExecutionState


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create temporary database path."""
    return tmp_path / "test_api_schemas.db"


@pytest.fixture
async def test_db(temp_db_path: Path) -> AsyncGenerator[Database, None]:
    """Create and initialize in-memory SQLite database."""
    db = Database(temp_db_path)
    await db.connect()
    await db.ensure_schema()
    yield db
    await db.close()


@pytest.fixture
def test_repository(test_db: Database) -> WorkflowRepository:
    """Create repository backed by test database."""
    return WorkflowRepository(test_db)


async def create_test_workflow(
    repository: WorkflowRepository,
    workflow_id: str,
    issue_id: str = "TEST-456",
    worktree_path: str = "/test/path",
    workflow_status: str = "pending",
) -> ServerExecutionState:
    """Create and persist a test workflow."""
    execution_state = ExecutionState(profile_id="test")
    workflow = ServerExecutionState(
        id=workflow_id,
        issue_id=issue_id,
        worktree_path=worktree_path,
        workflow_status=workflow_status,
        started_at=datetime.now(UTC),
        execution_state=execution_state,
    )
    await repository.create(workflow)
    return workflow


class TestAPIResponseSchemas:
    """Integration tests verifying client/server schema compatibility.

    Uses real WorkflowRepository with in-memory SQLite.
    Only mocks the orchestrator (external LLM boundary).
    """

    @pytest.fixture
    def mock_orchestrator(self) -> MagicMock:
        """Create a mock orchestrator that returns predictable workflow IDs."""
        orchestrator = MagicMock()
        orchestrator.start_workflow = AsyncMock(return_value="test-workflow-id-123")
        return orchestrator

    @pytest.fixture
    async def server_with_real_db(
        self,
        mock_orchestrator: MagicMock,
        test_repository: WorkflowRepository,
        find_free_port: Callable[[], int],
    ) -> AsyncGenerator[str, None]:
        """Start server with real repository and mocked orchestrator."""
        # Create the test workflow in the real database
        await create_test_workflow(
            test_repository,
            workflow_id="test-workflow-id-123",
            issue_id="TEST-456",
            worktree_path="/test/path",
        )

        # Override dependencies - real repository, mocked orchestrator
        app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
        app.dependency_overrides[get_repository] = lambda: test_repository

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

    async def test_create_workflow_returns_minimal_response(
        self, server_with_real_db: str
    ) -> None:
        """REGRESSION: POST /api/workflows returns CreateWorkflowResponse schema.

        The server returns only {id, status, message} for workflow creation.
        The client must NOT expect full workflow details (issue_id, worktree_path, etc.)
        in this response.

        Bug context: Previously, client.create_workflow() tried to deserialize
        the response as WorkflowResponse (which has many required fields),
        causing ValidationError when the server returned the minimal
        CreateWorkflowResponse format.
        """
        client = AmeliaClient(base_url=server_with_real_db)

        # This should succeed - response contains only {id, status, message}
        response = await client.create_workflow(
            issue_id="TEST-123",
            worktree_path="/test/repo/path",
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

    async def test_create_workflow_raw_response_schema(
        self, server_with_real_db: str
    ) -> None:
        """Verify raw HTTP response matches CreateWorkflowResponse schema exactly."""
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                f"{server_with_real_db}/api/workflows",
                json={
                    "issue_id": "TEST-789",
                    "worktree_path": "/some/path",
                },
            )

        assert response.status_code == 201

        data = response.json()

        # Verify exact schema: only these 3 keys
        assert set(data.keys()) == {"id", "status", "message"}
        assert isinstance(data["id"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["message"], str)

    async def test_get_workflow_returns_full_response(
        self, server_with_real_db: str
    ) -> None:
        """GET /api/workflows/{id} returns WorkflowResponse with full details."""
        client = AmeliaClient(base_url=server_with_real_db)

        # Get workflow details (workflow was created in fixture)
        response = await client.get_workflow("test-workflow-id-123")

        # Verify correct response type with full details
        assert isinstance(response, WorkflowResponse)
        assert response.id == "test-workflow-id-123"
        assert response.issue_id == "TEST-456"
        assert response.worktree_path == "/test/path"
        assert response.status == "pending"

    async def test_get_workflow_raw_response_schema(
        self, server_with_real_db: str
    ) -> None:
        """Verify raw HTTP response from GET includes full workflow details."""
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(
                f"{server_with_real_db}/api/workflows/test-workflow-id-123"
            )

        assert response.status_code == 200

        data = response.json()

        # WorkflowDetailResponse should have these required fields
        assert "id" in data
        assert "issue_id" in data
        assert "worktree_path" in data
        assert "status" in data

        # Verify values match our test workflow
        assert data["id"] == "test-workflow-id-123"
        assert data["issue_id"] == "TEST-456"
        assert data["worktree_path"] == "/test/path"
