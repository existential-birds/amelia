"""Shared fixtures for generative MoA pipeline tests."""

import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create an initialized git repo with one committed file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "code.txt").write_text("line1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    return repo
