"""Shared fixtures for unit/core tests."""

from typing import Any

import pytest


@pytest.fixture
def mock_runnable_config(mock_profile_factory):
    """Create a mock RunnableConfig for review node tests."""
    def _create(
        profile=None,
        workflow_id: str = "test-workflow-123",
        event_bus=None,
        repository=None,
    ) -> dict[str, Any]:
        if profile is None:
            profile = mock_profile_factory(preset="cli_single")
        return {
            "configurable": {
                "thread_id": workflow_id,
                "profile": profile,
                "event_bus": event_bus,
                "repository": repository,
            }
        }
    return _create
