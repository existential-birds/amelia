"""Tests for path validation routes."""

import os
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.routes.paths import router


def _get_isolated_git_env() -> dict[str, str]:
    """Get environment that completely isolates git from parent worktree.

    CRITICAL: Git commands in tests were modifying the parent worktree.
    This function creates an environment that prevents git from discovering
    or modifying any parent repositories.

    Returns:
        Environment dict with all git context vars removed.
    """
    env = os.environ.copy()
    # Remove ALL git environment variables that could cause git to interact
    # with the wrong repository. This is especially important when tests
    # run inside git hooks (pre-push) where GIT_* vars are set.
    git_vars_to_clear = [
        "GIT_DIR",  # Overrides .git directory discovery
        "GIT_WORK_TREE",  # Overrides work tree location
        "GIT_INDEX_FILE",  # Could point to parent's index
        "GIT_OBJECT_DIRECTORY",  # Could use parent's objects
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",  # Same
        "GIT_QUARANTINE_PATH",  # Used during receive-pack
        "GIT_COMMON_DIR",  # Worktree common dir
        "GIT_CEILING_DIRECTORIES",  # Limits discovery
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",  # Controls discovery
    ]
    for var in git_vars_to_clear:
        env.pop(var, None)
    return env


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

    @pytest.fixture
    def temp_dir(self) -> Iterator[str]:
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def temp_git_repo(self) -> Iterator[str]:
        """Create a temporary git repository in complete isolation.

        Uses isolated environment to prevent any interaction with the
        parent worktree. This is critical when running inside git hooks.
        """
        isolated_env = _get_isolated_git_env()

        with tempfile.TemporaryDirectory() as tmpdir:
            # SAFETY CHECK: Ensure we're not accidentally in the project dir
            project_markers = [".git", "pyproject.toml", "CLAUDE.md"]
            for marker in project_markers:
                if (Path(tmpdir) / marker).exists():
                    raise RuntimeError(f"Safety check failed: {tmpdir} looks like project root")

            # Initialize git repo with isolated environment
            subprocess.run(
                ["git", "init"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
                env=isolated_env,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
                env=isolated_env,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
                env=isolated_env,
            )
            # Disable gpg signing and hooks for test repo
            subprocess.run(
                ["git", "config", "commit.gpgsign", "false"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
                env=isolated_env,
            )
            # Create initial commit to establish branch
            readme = Path(tmpdir) / "README.md"
            readme.write_text("# Test Repo")
            subprocess.run(
                ["git", "add", "."],
                cwd=tmpdir,
                capture_output=True,
                check=True,
                env=isolated_env,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=tmpdir,
                capture_output=True,
                check=True,
                env=isolated_env,
            )
            yield tmpdir

    def test_validates_existing_git_repo(
        self, client: TestClient, temp_git_repo: str
    ) -> None:
        """Should return valid status for existing git repo."""
        response = client.post("/api/paths/validate", json={"path": temp_git_repo})

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["is_git_repo"] is True
        assert data["branch"] is not None
        assert data["repo_name"] is not None
        assert "Git repository" in data["message"]

    def test_detects_uncommitted_changes(
        self, client: TestClient, temp_git_repo: str
    ) -> None:
        """Should detect uncommitted changes in git repo."""
        # Create an uncommitted file
        new_file = Path(temp_git_repo) / "new_file.txt"
        new_file.write_text("Uncommitted content")

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
        with patch("subprocess.run") as mock_run:
            # First call is for branch check
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=5)

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
        response = client.post("/api/paths/validate", json={"path": temp_git_repo})

        assert response.status_code == 200
        data = response.json()
        assert data["repo_name"] == Path(temp_git_repo).name
