"""Tests for on-demand review endpoint."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.dependencies import get_orchestrator
from amelia.server.routes.workflows import configure_exception_handlers, router


REVIEW_WORKFLOW_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440099")
REVIEW_URL = "/api/workflows/550e8400-e29b-41d4-a716-446655440000/review"


class TestRequestReviewEndpoint:

    @pytest.fixture
    def mock_orchestrator(self) -> MagicMock:
        orch = MagicMock()
        orch.request_review = AsyncMock(return_value=REVIEW_WORKFLOW_ID)
        return orch

    @pytest.fixture
    def client(self, mock_orchestrator: MagicMock) -> TestClient:
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
        configure_exception_handlers(app)
        return TestClient(app)

    @pytest.mark.parametrize("mode", ["review_only", "review_fix"])
    def test_request_review_accepted(
        self, client: TestClient, mock_orchestrator: MagicMock, mode: str
    ) -> None:
        response = client.post(REVIEW_URL, json={"mode": mode})
        assert response.status_code == 202
        mock_orchestrator.request_review.assert_called_once()

    def test_request_review_with_types(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        response = client.post(
            REVIEW_URL,
            json={"mode": "review_only", "review_types": ["general", "security"]},
        )
        assert response.status_code == 202

    def test_response_contains_review_workflow_id(
        self, client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        response = client.post(REVIEW_URL, json={"mode": "review_only"})
        data = response.json()
        assert data["workflow_id"] == str(REVIEW_WORKFLOW_ID)
        assert data["status"] == "review_requested"
