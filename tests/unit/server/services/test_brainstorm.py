"""Unit tests for BrainstormService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.server.models.events import EventDomain, EventType
from amelia.server.services.brainstorm import BrainstormService


@pytest.fixture
def brainstorm_service():
    """Create a BrainstormService with mocked dependencies."""
    repository = AsyncMock()
    event_bus = MagicMock()
    return BrainstormService(repository=repository, event_bus=event_bus)


def test_agentic_message_to_event_sets_brainstorm_domain(brainstorm_service):
    """Events from _agentic_message_to_event have domain=BRAINSTORM."""
    from amelia.drivers.base import AgenticMessage, AgenticMessageType

    msg = AgenticMessage(
        type=AgenticMessageType.RESULT,
        content="Hello world",
    )

    event = brainstorm_service._agentic_message_to_event(msg, "session-123")

    assert event.domain == EventDomain.BRAINSTORM
    assert event.event_type == EventType.BRAINSTORM_TEXT
    assert event.workflow_id == "session-123"
