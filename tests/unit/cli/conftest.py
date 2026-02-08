"""Shared fixtures for CLI tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock Database."""
    mock = MagicMock()
    mock.connect = AsyncMock()
    mock.close = AsyncMock()
    return mock


@pytest.fixture(autouse=True)
def _mock_migrator() -> Generator[None, None, None]:
    """Auto-mock Migrator so CLI tests don't need real PostgreSQL."""
    mock_cls = MagicMock()
    mock_cls.return_value.run = AsyncMock()
    mock_cls.return_value.initialize_prompts = AsyncMock()
    with patch("amelia.cli.config.Migrator", mock_cls):
        yield
