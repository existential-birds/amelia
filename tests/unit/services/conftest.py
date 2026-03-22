"""Shared fixtures for services unit tests."""

import pytest

from amelia.services.github_pr import GitHubPRService


@pytest.fixture
def service(tmp_path: object) -> GitHubPRService:
    """Create a GitHubPRService with a temporary repo root."""
    return GitHubPRService(repo_root=str(tmp_path))
