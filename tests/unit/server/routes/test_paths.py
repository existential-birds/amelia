"""Tests for path validation routes."""

import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.routes.paths import router


class TestValidatePath:
    """Tests for POST /api/paths/validate endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test app with paths router."""
        application = FastAPI()
        application.include_router(router, prefix="/api")
        return application

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def _mock_home_to_root(self) -> Iterator[None]:
        """Mock Path.home() to return root so temp dirs are within home."""
        with patch.object(Path, "home", return_value=Path("/")):
            yield

    @pytest.fixture
    def temp_dir(self) -> Iterator[str]:
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def temp_git_repo(self) -> Iterator[str]:
        """Create a temporary directory with a fake .git directory.

        This simulates a git repository for path validation without running
        real git commands. The validation code only checks for .git existence.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake .git directory
            (Path(tmpdir) / ".git").mkdir()
            yield tmpdir

    def test_validates_existing_git_repo(
        self, client: TestClient, temp_git_repo: str
    ) -> None:
        """Should return valid status for existing git repo."""
        with (
            patch(
                "amelia.server.routes.paths._get_git_branch_sync", return_value="main"
            ),
            patch(
                "amelia.server.routes.paths._has_uncommitted_changes_sync",
                return_value=False,
            ),
        ):
            response = client.post("/api/paths/validate", json={"path": temp_git_repo})

            assert response.status_code == 200
            data = response.json()
            assert data["exists"] is True
            assert data["is_git_repo"] is True
            assert data["branch"] == "main"
            assert data["repo_name"] is not None
            assert "Git repository" in data["message"]

    def test_detects_uncommitted_changes(
        self, client: TestClient, temp_git_repo: str
    ) -> None:
        """Should detect uncommitted changes in git repo."""
        with (
            patch(
                "amelia.server.routes.paths._get_git_branch_sync", return_value="main"
            ),
            patch(
                "amelia.server.routes.paths._has_uncommitted_changes_sync",
                return_value=True,
            ),
        ):
            response = client.post("/api/paths/validate", json={"path": temp_git_repo})

            assert response.status_code == 200
            data = response.json()
            assert data["exists"] is True
            assert data["is_git_repo"] is True
            assert data["has_changes"] is True
            assert "uncommitted" in data["message"].lower()

    def test_validates_non_git_directory(
        self, client: TestClient, temp_dir: str
    ) -> None:
        """Should return warning for directory that's not a git repo."""
        response = client.post("/api/paths/validate", json={"path": temp_dir})

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["is_git_repo"] is False
        assert data["repo_name"] is not None
        assert "not a git repository" in data["message"].lower()

    def test_returns_error_for_nonexistent_path(self, client: TestClient) -> None:
        """Should return not exists for nonexistent path."""
        response = client.post(
            "/api/paths/validate", json={"path": "/nonexistent/path/that/does/not/exist"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["is_git_repo"] is False
        assert "does not exist" in data["message"].lower()

    def test_returns_error_for_relative_path(self, client: TestClient) -> None:
        """Should return error for relative path."""
        response = client.post("/api/paths/validate", json={"path": "relative/path"})

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["is_git_repo"] is False
        assert "absolute" in data["message"].lower()

    def test_returns_error_for_file_path(self, client: TestClient) -> None:
        """Should return error when path is a file, not directory."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            file_path = f.name

        try:
            response = client.post("/api/paths/validate", json={"path": file_path})

            assert response.status_code == 200
            data = response.json()
            assert data["exists"] is True
            assert data["is_git_repo"] is False
            assert "not a directory" in data["message"].lower()
        finally:
            Path(file_path).unlink(missing_ok=True)

    def test_handles_git_command_timeout(
        self, client: TestClient, temp_git_repo: str
    ) -> None:
        """Should handle git command timeouts gracefully."""
        with (
            patch(
                "amelia.server.routes.paths._get_git_branch_sync", return_value=None
            ),
            patch(
                "amelia.server.routes.paths._has_uncommitted_changes_sync",
                return_value=False,
            ),
        ):
            response = client.post(
                "/api/paths/validate", json={"path": temp_git_repo}
            )

            # Should still return success, just without branch info
            assert response.status_code == 200
            data = response.json()
            assert data["exists"] is True
            assert data["is_git_repo"] is True
            assert data["branch"] is None

    def test_returns_repo_name_from_directory(
        self, client: TestClient, temp_git_repo: str
    ) -> None:
        """Should return directory name as repo_name."""
        with (
            patch(
                "amelia.server.routes.paths._get_git_branch_sync", return_value="main"
            ),
            patch(
                "amelia.server.routes.paths._has_uncommitted_changes_sync",
                return_value=False,
            ),
        ):
            response = client.post("/api/paths/validate", json={"path": temp_git_repo})

            assert response.status_code == 200
            data = response.json()
            assert data["repo_name"] == Path(temp_git_repo).name

    def test_rejects_path_outside_home_directory(self, client: TestClient) -> None:
        """Should reject paths that are outside the user's home directory."""
        with patch.object(Path, "home", return_value=Path("/home/testuser")):
            response = client.post(
                "/api/paths/validate", json={"path": "/etc/passwd"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["exists"] is False
            assert data["is_git_repo"] is False
            assert "home directory" in data["message"].lower()

    def test_accepts_path_within_home_directory(
        self, client: TestClient, temp_dir: str
    ) -> None:
        """Should accept paths that are within the user's home directory."""
        # Mock home to be the parent of temp_dir so it's "within" home
        parent = str(Path(temp_dir).resolve().parent)
        with patch.object(Path, "home", return_value=Path(parent)):
            response = client.post("/api/paths/validate", json={"path": temp_dir})

            assert response.status_code == 200
            data = response.json()
            assert data["exists"] is True
            # Not a git repo, but the path is accepted
            assert "home directory" not in data["message"].lower()
