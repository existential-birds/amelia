"""Tests for GET /api/files/list endpoint."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.core.types import AgentConfig, Profile
from amelia.server.dependencies import get_profile_repository
from amelia.server.routes.files import router
from amelia.server.routes.workflows import configure_exception_handlers


def _create_mock_profile_repo(working_dir: Path) -> MagicMock:
    """Create a mock profile repository with an active profile pointing to working_dir."""
    repo = MagicMock()
    agent_config = AgentConfig(driver="cli", model="claude-3-5-sonnet")
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


class TestListFiles:
    """Tests for GET /api/files/list endpoint."""

    @pytest.fixture
    def working_dir(self, tmp_path: Path) -> Path:
        """Create a working directory with test files."""
        docs_dir = tmp_path / "docs" / "plans"
        docs_dir.mkdir(parents=True)

        # Create some markdown files
        (docs_dir / "plan-a.md").write_text("# Plan A\n\nContent for plan A.")
        (docs_dir / "plan-b.md").write_text("# Plan B\n\nContent for plan B.")
        (docs_dir / "notes.txt").write_text("Some notes.")

        # Create a subdirectory (should not appear in non-recursive listing)
        sub_dir = docs_dir / "archive"
        sub_dir.mkdir()
        (sub_dir / "old-plan.md").write_text("# Old Plan")

        return tmp_path

    @pytest.fixture
    def mock_profile_repo(self, working_dir: Path) -> MagicMock:
        """Create a mock profile repo with working_dir set to the test directory."""
        return _create_mock_profile_repo(working_dir)

    @pytest.fixture
    def app(self, mock_profile_repo: MagicMock) -> FastAPI:
        """Create test app with files router."""
        application = FastAPI()
        application.include_router(router, prefix="/api")
        application.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo
        configure_exception_handlers(application)
        return application

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_returns_md_files_by_default(
        self, client: TestClient, working_dir: Path
    ) -> None:
        """Should return .md files when using default glob pattern."""
        response = client.get("/api/files/list", params={"directory": "docs/plans"})

        assert response.status_code == 200
        data = response.json()
        assert data["directory"] == "docs/plans"
        file_names = [f["name"] for f in data["files"]]
        assert "plan-a.md" in file_names
        assert "plan-b.md" in file_names
        # .txt should not appear with default *.md pattern
        assert "notes.txt" not in file_names

    def test_custom_glob_pattern(
        self, client: TestClient, working_dir: Path
    ) -> None:
        """Should respect custom glob pattern."""
        response = client.get(
            "/api/files/list",
            params={"directory": "docs/plans", "glob_pattern": "*.txt"},
        )

        assert response.status_code == 200
        data = response.json()
        file_names = [f["name"] for f in data["files"]]
        assert "notes.txt" in file_names
        assert "plan-a.md" not in file_names

    def test_file_entry_shape(
        self, client: TestClient, working_dir: Path
    ) -> None:
        """Should return file entries with correct fields."""
        response = client.get("/api/files/list", params={"directory": "docs/plans"})

        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) > 0

        entry = data["files"][0]
        assert "name" in entry
        assert "relative_path" in entry
        assert "size_bytes" in entry
        assert "modified_at" in entry
        assert isinstance(entry["size_bytes"], int)
        assert entry["size_bytes"] > 0

    def test_relative_path_in_entries(
        self, client: TestClient, working_dir: Path
    ) -> None:
        """Should return paths relative to working_dir."""
        response = client.get("/api/files/list", params={"directory": "docs/plans"})

        assert response.status_code == 200
        data = response.json()
        for entry in data["files"]:
            assert entry["relative_path"].startswith("docs/plans/")

    def test_returns_empty_for_nonexistent_directory(
        self, client: TestClient
    ) -> None:
        """Should return empty list when directory does not exist."""
        response = client.get(
            "/api/files/list", params={"directory": "nonexistent/dir"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["files"] == []
        assert data["directory"] == "nonexistent/dir"

    def test_rejects_path_traversal(self, client: TestClient) -> None:
        """Should return 400 for path traversal attempts."""
        response = client.get(
            "/api/files/list", params={"directory": "../../etc"}
        )

        assert response.status_code == 400

    def test_rejects_absolute_path_traversal(self, client: TestClient) -> None:
        """Should return 400 for absolute path that escapes working_dir."""
        response = client.get(
            "/api/files/list", params={"directory": "/etc"}
        )

        assert response.status_code == 400

    def test_requires_directory_param(self, client: TestClient) -> None:
        """Should return 422 when directory param is missing."""
        response = client.get("/api/files/list")

        assert response.status_code == 422

    def test_returns_400_when_no_active_profile(self, app: FastAPI) -> None:
        """Should return 400 when no active profile is set."""
        mock_profile_repo = MagicMock()
        mock_profile_repo.get_active_profile = AsyncMock(return_value=None)
        app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo

        client = TestClient(app)
        response = client.get("/api/files/list", params={"directory": "docs"})

        assert response.status_code == 400
        assert "no active profile" in response.json()["error"].lower()

    def test_sorted_by_modified_time_newest_first(
        self, client: TestClient, working_dir: Path
    ) -> None:
        """Should return files sorted by modification time, newest first."""
        docs_dir = working_dir / "docs" / "plans"

        # Touch plan-a.md to make it newer
        import time

        time.sleep(0.05)
        (docs_dir / "plan-a.md").write_text("# Plan A updated")

        response = client.get("/api/files/list", params={"directory": "docs/plans"})

        assert response.status_code == 200
        data = response.json()
        md_files = [f for f in data["files"] if f["name"].endswith(".md")]
        assert len(md_files) >= 2
        # plan-a.md was touched last, should be first
        assert md_files[0]["name"] == "plan-a.md"

    def test_does_not_include_subdirectories(
        self, client: TestClient, working_dir: Path
    ) -> None:
        """Should not include subdirectory entries, only files."""
        response = client.get(
            "/api/files/list",
            params={"directory": "docs/plans", "glob_pattern": "*"},
        )

        assert response.status_code == 200
        data = response.json()
        file_names = [f["name"] for f in data["files"]]
        # "archive" is a subdirectory, should not appear
        assert "archive" not in file_names
