"""Shared fixtures for client unit tests."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from amelia.client.api import AmeliaClient


@pytest.fixture
def runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def api_client() -> AmeliaClient:
    """Create AmeliaClient instance for testing."""
    return AmeliaClient(base_url="http://localhost:8420")


@pytest.fixture
def mock_worktree(tmp_path: Path) -> Path:
    """Create a fake git worktree directory for CLI tests."""
    worktree = tmp_path / "repo"
    worktree.mkdir()
    (worktree / ".git").touch()
    return worktree
