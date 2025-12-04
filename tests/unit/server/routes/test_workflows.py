"""Tests for workflow routes and exception handlers."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from amelia.server.exceptions import (
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.routes.workflows import configure_exception_handlers


@pytest.fixture
def app() -> FastAPI:
    """Create a test FastAPI app."""
    test_app = FastAPI()
    configure_exception_handlers(test_app)
    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    """Create an async test client."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestExceptionHandlers:
    """Test exception handlers."""

    async def test_workflow_conflict_returns_409(self, app: FastAPI, client: AsyncClient):
        """WorkflowConflictError should return 409 with code WORKFLOW_CONFLICT."""

        @app.get("/test-conflict")
        async def trigger_conflict():
            raise WorkflowConflictError("/path/to/worktree", "workflow-123")

        response = await client.get("/test-conflict")
        assert response.status_code == 409
        data = response.json()
        assert data["code"] == "WORKFLOW_CONFLICT"
        assert "workflow-123" in data["error"]

    async def test_concurrency_limit_returns_429(self, app: FastAPI, client: AsyncClient):
        """ConcurrencyLimitError should return 429 with Retry-After header."""

        @app.get("/test-concurrency")
        async def trigger_concurrency():
            raise ConcurrencyLimitError(max_concurrent=10, current_count=10)

        response = await client.get("/test-concurrency")
        assert response.status_code == 429
        assert response.headers.get("Retry-After") == "30"
        data = response.json()
        assert data["code"] == "CONCURRENCY_LIMIT"

    async def test_invalid_state_returns_422(self, app: FastAPI, client: AsyncClient):
        """InvalidStateError should return 422 with code INVALID_STATE."""

        @app.get("/test-invalid-state")
        async def trigger_invalid_state():
            raise InvalidStateError(
                "Cannot transition from running to completed",
                "workflow-123",
                "running"
            )

        response = await client.get("/test-invalid-state")
        assert response.status_code == 422
        data = response.json()
        assert data["code"] == "INVALID_STATE"
        assert "running" in data["error"]
        assert "completed" in data["error"]

    async def test_workflow_not_found_returns_404(self, app: FastAPI, client: AsyncClient):
        """WorkflowNotFoundError should return 404 with code NOT_FOUND."""

        @app.get("/test-not-found")
        async def trigger_not_found():
            raise WorkflowNotFoundError("workflow-123")

        response = await client.get("/test-not-found")
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "NOT_FOUND"
        assert "workflow-123" in data["error"]

    async def test_validation_error_returns_400(self, app: FastAPI, client: AsyncClient):
        """Pydantic ValidationError should return 400 with code VALIDATION_ERROR."""

        @app.get("/test-validation")
        async def trigger_validation():
            # Trigger a Pydantic validation error
            from pydantic import BaseModel, field_validator

            class TestModel(BaseModel):
                value: int

                @field_validator("value")
                @classmethod
                def must_be_positive(cls, v: int) -> int:
                    if v <= 0:
                        raise ValueError("must be positive")
                    return v

            TestModel(value=-1)

        response = await client.get("/test-validation")
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "VALIDATION_ERROR"

    async def test_generic_exception_returns_500(self, app: FastAPI, client: AsyncClient):
        """Generic exceptions should return 500 with code INTERNAL_ERROR."""

        @app.get("/test-generic")
        async def trigger_generic():
            raise RuntimeError("Something went wrong")

        response = await client.get("/test-generic")
        assert response.status_code == 500
        data = response.json()
        assert data["code"] == "INTERNAL_ERROR"
        assert "Something went wrong" in data["error"]
