# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Shared fixtures for integration tests."""
import socket
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.core.types import Issue, Profile
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.events.connection_manager import ConnectionManager


@pytest.fixture
def find_free_port() -> Callable[[], int]:
    """Fixture that returns a function to find an available port for testing.

    Returns:
        A callable that returns an available port number.

    Example:
        def test_server(find_free_port):
            port = find_free_port()
            # Use port to start server
    """
    def _find_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port: int = s.getsockname()[1]
            return port
    return _find_port


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Create a mock EventBus with emit_stream tracking."""
    bus = MagicMock(spec=EventBus)
    bus.emit_stream = MagicMock()
    bus.emit = MagicMock()
    bus.set_connection_manager = MagicMock()
    return bus


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create a mock WorkflowRepository."""
    repo = AsyncMock(spec=WorkflowRepository)
    repo.create = AsyncMock()
    repo.get = AsyncMock()
    repo.update = AsyncMock()
    repo.set_status = AsyncMock()
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def test_profile() -> Profile:
    """Create a test profile."""
    return Profile(
        name="test_profile",
        driver="api:openai",
        tracker="noop",
        strategy="single",
    )


@pytest.fixture
def test_issue() -> Issue:
    """Create a test issue."""
    return Issue(
        id="TEST-123",
        title="Test Stream Integration",
        description="Verify stream events are emitted during workflow execution",
    )


@pytest.fixture
def test_settings(test_profile: Profile) -> MagicMock:
    """Create mock settings with test profile."""
    settings = MagicMock()
    settings.active_profile = "test_profile"
    settings.profiles = {"test_profile": test_profile}
    return settings


@pytest.fixture
def connection_manager() -> ConnectionManager:
    """Create a ConnectionManager instance."""
    return ConnectionManager()


@pytest.fixture
def event_bus(connection_manager: ConnectionManager) -> EventBus:
    """Create an EventBus with ConnectionManager attached."""
    bus = EventBus()
    bus.set_connection_manager(connection_manager)
    return bus
