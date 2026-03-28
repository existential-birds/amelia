"""Shared fixtures for orchestrator unit tests."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_setup_workflow_branch() -> AsyncMock:
    """Auto-mock _setup_workflow_branch for all orchestrator tests.

    Orchestrator unit tests use fake worktrees (just a .git file, not a real
    git repo), so real git commands would fail. This fixture patches the branch
    setup to return None (no branch created), which matches the pre-branch-creation
    behavior.
    """
    with patch(
        "amelia.server.orchestrator.service.OrchestratorService._setup_workflow_branch",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock:
        yield mock
