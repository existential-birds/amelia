"""Shared fixtures for CLI tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock Database."""
    mock = MagicMock()
    mock.connect = AsyncMock()
    mock.close = AsyncMock()
    mock.ensure_schema = AsyncMock()
    return mock
