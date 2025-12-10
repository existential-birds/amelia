# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Shared fixtures for server tests."""

from datetime import datetime
from typing import Any

import pytest

from amelia.server.models.events import EventType, WorkflowEvent


@pytest.fixture
def make_event():
    """Factory fixture for creating WorkflowEvent instances with sensible defaults.

    Returns:
        A function that creates WorkflowEvent instances with default values
        that can be overridden via keyword arguments.

    Example:
        def test_something(make_event):
            event = make_event(agent="developer", event_type=EventType.FILE_CREATED)
            assert event.agent == "developer"
    """

    def _make_event(**overrides: Any) -> WorkflowEvent:
        """Create a WorkflowEvent with sensible defaults."""
        defaults: dict[str, Any] = {
            "id": "event-123",
            "workflow_id": "wf-456",
            "sequence": 1,
            "timestamp": datetime(2025, 1, 1, 12, 0, 0),
            "agent": "system",
            "event_type": EventType.WORKFLOW_STARTED,
            "message": "Test event",
        }
        return WorkflowEvent(**{**defaults, **overrides})

    return _make_event
