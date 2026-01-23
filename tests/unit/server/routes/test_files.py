"""Tests for files routes."""
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.core.types import AgentConfig, Profile
from amelia.server.dependencies import get_profile_repository
from amelia.server.routes.files import router


def _create_mock_profile_repo(working_dir: Path) -> MagicMock:
    """Create a mock profile repository with an active profile pointing to working_dir."""
    repo = MagicMock()
    agent_config = AgentConfig(driver="cli:claude", model="claude-3-5-sonnet")
    repo.get_active_profile = AsyncMock(
        return_value=Profile(
            name="test",
            tracker="noop",
            working_dir=str(working_dir),
            agents={
                "architect": agent_config,
                "developer": agent_config,
                "reviewer": agent_config,
            },
        )
    )
    return repo


class TestReadFile:
    """Tests for POST /api/files/read endpoint."""

    @pytest.fixture
    def mock_profile_repo(self, tmp_path: Path) -> MagicMock:
        """Create a mock profile repo with working_dir set to tmp_path (allows all temp files)."""
        # Use /tmp (or platform equivalent) to allow access to temp files created by tests
        return _create_mock_profile_repo(Path(tempfile.gettempdir()))

    @pytest.fixture
    def app(self, mock_profile_repo: MagicMock) -> FastAPI:
        """Create test app with files router."""
        application = FastAPI()
        application.include_router(router, prefix="/api")
        application.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo
        return application

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def temp_file(self) -> Iterator[str]:
        """Create a temporary markdown file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write("# Queue Workflows Design\n\n## Problem\n\nUsers cannot queue workflows.")
            path = f.name
        yield path
        if os.path.exists(path):
            os.unlink(path)

    def test_reads_file_content(self, client: TestClient, temp_file: str) -> None:
        """Should return file content and filename."""
        response = client.post("/api/files/read", json={"path": temp_file})

        assert response.status_code == 200
        data = response.json()
        assert "Queue Workflows Design" in data["content"]
        assert data["filename"].endswith(".md")

    def test_returns_404_for_missing_file(self, client: TestClient) -> None:
        """Should return 404 when file doesn't exist (within working_dir)."""
        # Path must be inside working_dir (tempdir) to get 404 instead of 400
        missing_file = Path(tempfile.gettempdir()) / "nonexistent_file_12345.md"
        response = client.post("/api/files/read", json={"path": str(missing_file)})

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]["error"].lower()

    def test_returns_400_for_relative_path(self, client: TestClient) -> None:
        """Should return 400 when path is not absolute."""
        response = client.post("/api/files/read", json={"path": "relative/path.md"})

        assert response.status_code == 400
        assert "absolute" in response.json()["detail"]["error"].lower()

    def test_returns_400_for_path_outside_working_dir(
        self, app: FastAPI, temp_file: str
    ) -> None:
        """Should return 400 when path is outside working_dir."""
        # Override with a different working_dir
        mock_profile_repo = _create_mock_profile_repo(Path("/some/other/directory"))
        app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo

        client = TestClient(app)
        response = client.post("/api/files/read", json={"path": temp_file})

        assert response.status_code == 400
        assert "not accessible" in response.json()["detail"]["error"].lower()

    def test_allows_path_within_working_dir(self, app: FastAPI) -> None:
        """Should allow paths within working_dir subtree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file inside working_dir
            file_path = Path(tmpdir) / "docs" / "design.md"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("# Test Design\n\nContent here.")

            # Override with matching working_dir
            mock_profile_repo = _create_mock_profile_repo(Path(tmpdir))
            app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo

            client = TestClient(app)
            response = client.post("/api/files/read", json={"path": str(file_path)})

            assert response.status_code == 200
            assert "Test Design" in response.json()["content"]

    def test_returns_400_when_no_active_profile(self, app: FastAPI, temp_file: str) -> None:
        """Should return 400 when no active profile is set."""
        mock_profile_repo = MagicMock()
        mock_profile_repo.get_active_profile = AsyncMock(return_value=None)
        app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo

        client = TestClient(app)
        response = client.post("/api/files/read", json={"path": temp_file})

        assert response.status_code == 400
        assert "no active profile" in response.json()["detail"]["error"].lower()


class TestGetFile:
    """Tests for GET /api/files/{file_path:path} endpoint."""

    @pytest.fixture
    def mock_profile_repo(self, tmp_path: Path) -> MagicMock:
        """Create a mock profile repo with working_dir set to tmp_path."""
        return _create_mock_profile_repo(Path(tempfile.gettempdir()))

    @pytest.fixture
    def app(self, mock_profile_repo: MagicMock) -> FastAPI:
        """Create test app with files router."""
        application = FastAPI()
        application.include_router(router, prefix="/api")
        application.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo
        return application

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def temp_file(self) -> Iterator[str]:
        """Create a temporary markdown file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write("# Design Document\n\n## Overview\n\nThis is the design.")
            path = f.name
        yield path
        if os.path.exists(path):
            os.unlink(path)

    def test_gets_file_content(self, client: TestClient, temp_file: str) -> None:
        """Should return file content with text/plain content-type."""
        # Double slash needed for absolute paths: /api/files/ + /var/... = /api/files//var/...
        response = client.get(f"/api/files/{temp_file}")

        assert response.status_code == 200
        assert "Design Document" in response.text
        assert response.headers["content-type"].startswith("text/")

    def test_returns_404_for_missing_file(self, client: TestClient) -> None:
        """Should return 404 when file doesn't exist."""
        missing_file = Path(tempfile.gettempdir()) / "nonexistent_file_99999.md"
        # Double slash needed for absolute paths
        response = client.get(f"/api/files/{missing_file}")

        assert response.status_code == 404

    def test_returns_400_for_path_outside_working_dir(
        self, app: FastAPI
    ) -> None:
        """Should return 400 when path is outside working_dir."""
        mock_profile_repo = _create_mock_profile_repo(Path("/some/restricted/directory"))
        app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo

        client = TestClient(app)
        # Double slash makes the path absolute: /api/files/ + /etc/passwd
        response = client.get("/api/files//etc/passwd")

        assert response.status_code == 400

    def test_returns_400_when_no_active_profile(self, app: FastAPI) -> None:
        """Should return 400 when no active profile is set."""
        mock_profile_repo = MagicMock()
        mock_profile_repo.get_active_profile = AsyncMock(return_value=None)
        app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo

        client = TestClient(app)
        response = client.get("/api/files//etc/passwd")

        assert response.status_code == 400
        assert "no active profile" in response.json()["detail"]["error"].lower()
