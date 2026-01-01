# tests/unit/server/routes/test_prompts.py
"""Tests for prompts API routes."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.agents.prompts.models import Prompt, PromptVersion
from amelia.server.routes.prompts import get_prompt_repository, router


@pytest.fixture
def mock_repo():
    """Create mock repository."""
    repo = MagicMock()
    repo.list_prompts = AsyncMock(return_value=[])
    repo.get_prompt = AsyncMock(return_value=None)
    repo.get_versions = AsyncMock(return_value=[])
    repo.get_version = AsyncMock(return_value=None)
    repo.create_version = AsyncMock()
    repo.reset_to_default = AsyncMock()
    return repo


@pytest.fixture
def app(mock_repo):
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_prompt_repository] = lambda: mock_repo
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestListPrompts:
    """Tests for GET /api/prompts."""

    def test_list_prompts_empty(self, client, mock_repo):
        """Should return empty list when no prompts."""
        response = client.get("/api/prompts")
        assert response.status_code == 200
        assert response.json()["prompts"] == []

    def test_list_prompts_with_data(self, client, mock_repo):
        """Should return prompts with version info."""
        mock_repo.list_prompts.return_value = [
            Prompt(id="test.prompt", agent="test", name="Test Prompt"),
        ]
        response = client.get("/api/prompts")
        assert response.status_code == 200
        data = response.json()
        assert len(data["prompts"]) == 1
        assert data["prompts"][0]["id"] == "test.prompt"


class TestGetPrompt:
    """Tests for GET /api/prompts/{id}."""

    def test_get_prompt_not_found(self, client, mock_repo):
        """Should return 404 for unknown prompt."""
        response = client.get("/api/prompts/nonexistent")
        assert response.status_code == 404

    def test_get_prompt_with_versions(self, client, mock_repo):
        """Should return prompt with version history."""
        mock_repo.get_prompt.return_value = Prompt(
            id="test.prompt", agent="test", name="Test"
        )
        mock_repo.get_versions.return_value = [
            PromptVersion(id="v1", prompt_id="test.prompt", version_number=1, content="Content"),
        ]
        response = client.get("/api/prompts/test.prompt")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test.prompt"
        assert len(data["versions"]) == 1


class TestGetVersions:
    """Tests for GET /api/prompts/{id}/versions."""

    def test_get_versions_not_found(self, client, mock_repo):
        """Should return 404 for unknown prompt."""
        mock_repo.get_prompt.return_value = None
        response = client.get("/api/prompts/nonexistent/versions")
        assert response.status_code == 404

    def test_get_versions(self, client, mock_repo):
        """Should return version list."""
        mock_repo.get_prompt.return_value = Prompt(
            id="test", agent="test", name="Test"
        )
        mock_repo.get_versions.return_value = [
            PromptVersion(id="v2", prompt_id="test", version_number=2, content="V2"),
            PromptVersion(id="v1", prompt_id="test", version_number=1, content="V1"),
        ]
        response = client.get("/api/prompts/test/versions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["versions"]) == 2
        assert data["versions"][0]["version_number"] == 2


class TestCreateVersion:
    """Tests for POST /api/prompts/{id}/versions."""

    def test_create_version(self, client, mock_repo):
        """Should create new version."""
        mock_repo.get_prompt.return_value = Prompt(
            id="test.prompt", agent="test", name="Test"
        )
        mock_repo.create_version.return_value = PromptVersion(
            id="v-new", prompt_id="test.prompt", version_number=1, content="New content"
        )
        response = client.post(
            "/api/prompts/test.prompt/versions",
            json={"content": "New content", "change_note": "Initial"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "v-new"

    def test_create_version_empty_content(self, client, mock_repo):
        """Should reject empty content."""
        mock_repo.get_prompt.return_value = Prompt(
            id="test.prompt", agent="test", name="Test"
        )
        response = client.post(
            "/api/prompts/test.prompt/versions",
            json={"content": "", "change_note": None},
        )
        # FastAPI returns 422 for Pydantic validation errors
        assert response.status_code == 422


class TestResetToDefault:
    """Tests for POST /api/prompts/{id}/reset."""

    def test_reset_to_default(self, client, mock_repo):
        """Should reset prompt to default."""
        mock_repo.get_prompt.return_value = Prompt(
            id="architect.system", agent="architect", name="Test"
        )
        response = client.post("/api/prompts/architect.system/reset")
        assert response.status_code == 200
        mock_repo.reset_to_default.assert_called_once_with("architect.system")


class TestGetDefault:
    """Tests for GET /api/prompts/{id}/default."""

    def test_get_default_content(self, client, mock_repo):
        """Should return hardcoded default content."""
        response = client.get("/api/prompts/architect.system/default")
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == PROMPT_DEFAULTS["architect.system"].content

    def test_get_default_unknown_prompt(self, client, mock_repo):
        """Should return 404 for unknown prompt."""
        response = client.get("/api/prompts/unknown.prompt/default")
        assert response.status_code == 404
