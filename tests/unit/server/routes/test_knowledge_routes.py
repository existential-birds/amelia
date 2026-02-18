"""Unit tests for knowledge API routes."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.dependencies import get_knowledge_repository, get_knowledge_service


@pytest.fixture
def mock_knowledge_deps():
    """Mock knowledge dependencies."""
    mock_repo = AsyncMock()
    mock_service = AsyncMock()
    mock_service._pipeline = AsyncMock()
    mock_service._pipeline.embedding_client = AsyncMock()
    return mock_repo, mock_service


@pytest.fixture
def client(mock_knowledge_deps):
    """Test client with mocked dependencies."""
    from amelia.server.routes.knowledge import router

    app = FastAPI()
    app.include_router(router, prefix="/api")

    mock_repo, mock_service = mock_knowledge_deps

    app.dependency_overrides[get_knowledge_repository] = lambda: mock_repo
    app.dependency_overrides[get_knowledge_service] = lambda: mock_service

    return TestClient(app), mock_repo, mock_service


def test_list_documents(client):
    """Should return document list."""
    test_client, mock_repo, _ = client

    mock_repo.list_documents = AsyncMock(return_value=[])

    response = test_client.get("/api/knowledge/documents")

    assert response.status_code == 200
    assert response.json() == {"documents": []}


def test_get_document_not_found(client):
    """Should return 404 for missing document."""
    test_client, mock_repo, _ = client

    mock_repo.get_document = AsyncMock(return_value=None)

    response = test_client.get(f"/api/knowledge/documents/{uuid4()}")

    assert response.status_code == 404


def test_delete_document_not_found(client):
    """Should return 404 when deleting missing document."""
    test_client, mock_repo, _ = client

    mock_repo.get_document = AsyncMock(return_value=None)

    response = test_client.delete(f"/api/knowledge/documents/{uuid4()}")

    assert response.status_code == 404
