"""Unit tests for pipeline utilities."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from amelia.core.types import Profile
from amelia.pipelines.utils import extract_config_params


class TestExtractConfigParams:
    """Tests for extract_config_params utility."""

    def test_extracts_all_params(self) -> None:
        """Should extract event_bus, workflow_id, and profile from config."""
        mock_event_bus = MagicMock()
        mock_profile = MagicMock(spec=Profile)
        thread_id = str(uuid4())

        config = {
            "configurable": {
                "event_bus": mock_event_bus,
                "thread_id": thread_id,
                "profile": mock_profile,
            }
        }

        event_bus, workflow_id, profile = extract_config_params(config)

        assert event_bus is mock_event_bus
        assert workflow_id == thread_id
        assert profile is mock_profile

    def test_event_bus_optional(self) -> None:
        """Event bus should be optional (returns None if missing)."""
        mock_profile = MagicMock(spec=Profile)
        thread_id = str(uuid4())

        config = {
            "configurable": {
                "thread_id": thread_id,
                "profile": mock_profile,
            }
        }

        event_bus, workflow_id, profile = extract_config_params(config)

        assert event_bus is None
        assert workflow_id == thread_id

    def test_raises_on_missing_workflow_id(self) -> None:
        """Should raise ValueError if workflow_id (thread_id) is missing."""
        config = {"configurable": {"profile": MagicMock()}}

        with pytest.raises(ValueError, match="workflow_id"):
            extract_config_params(config)

    def test_raises_on_missing_profile(self) -> None:
        """Should raise ValueError if profile is missing."""
        config = {"configurable": {"thread_id": str(uuid4())}}

        with pytest.raises(ValueError, match="profile"):
            extract_config_params(config)
