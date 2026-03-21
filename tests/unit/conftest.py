"""Shared fixtures for unit tests."""

from unittest.mock import AsyncMock

import pytest

from amelia.client.streaming import WorkflowSummary


@pytest.fixture
def mock_client() -> AsyncMock:
    """Create a mock AmeliaClient with default success behavior."""
    client = AsyncMock()
    client.get_pr_autofix_status.return_value = AsyncMock(
        enabled=True,
        config=AsyncMock(),
    )
    client.trigger_pr_autofix.return_value = AsyncMock(
        workflow_id="wf-test-123",
    )
    return client


@pytest.fixture
def mock_summary() -> WorkflowSummary:
    """Create a default WorkflowSummary."""
    return WorkflowSummary(
        fixed=2,
        skipped=1,
        failed=0,
        commit_sha="abc123def456",
    )
