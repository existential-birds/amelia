"""Tests for orchestrator helper functions.

Note: Plan extraction tests are in test_orchestrator_plan_extraction.py
"""

from unittest.mock import MagicMock

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.orchestrator import _extract_config_params
from amelia.core.types import Profile


class TestExtractConfigParams:
    """Tests for _extract_config_params helper."""

    def test_extracts_profile_from_config(self) -> None:
        """Should extract profile from config.configurable.profile."""
        profile = Profile(name="test", driver="cli:claude", model="sonnet")
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-123",
                "profile": profile,
            }
        }
        event_bus, stage_event_emitter, workflow_id, extracted_profile = _extract_config_params(config)
        assert extracted_profile == profile
        assert workflow_id == "wf-123"
        assert event_bus is None
        assert stage_event_emitter is None

    def test_extracts_emitters_from_config(self) -> None:
        """Should extract event_bus and stage emitter when provided."""
        mock_event_bus = MagicMock()

        async def mock_stage(name: str) -> None:
            pass

        profile = Profile(name="test", driver="cli:claude", model="sonnet")
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-123",
                "profile": profile,
                "event_bus": mock_event_bus,
                "stage_event_emitter": mock_stage,
            }
        }
        event_bus, stage, wf_id, prof = _extract_config_params(config)
        assert event_bus is mock_event_bus
        assert stage is mock_stage
        assert wf_id == "wf-123"
        assert prof == profile

    def test_raises_if_profile_missing(self) -> None:
        """Should raise ValueError if profile not in config."""
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-123",
            }
        }
        with pytest.raises(ValueError, match="profile is required"):
            _extract_config_params(config)


