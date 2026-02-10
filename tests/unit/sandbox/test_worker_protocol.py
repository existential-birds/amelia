"""Tests for the USAGE message type added to the worker protocol."""

import pytest

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverUsage,
)


class TestUsageMessageType:
    """Tests for USAGE enum value and AgenticMessage.usage field."""

    def test_usage_enum_value_exists(self) -> None:
        assert AgenticMessageType.USAGE.value == "usage"

    def test_usage_enum_is_valid_string(self) -> None:
        assert AgenticMessageType("usage") == AgenticMessageType.USAGE

    def test_agentic_message_usage_field_default_none(self) -> None:
        msg = AgenticMessage(type=AgenticMessageType.RESULT, content="done")
        assert msg.usage is None

    def test_agentic_message_with_usage(self) -> None:
        usage = DriverUsage(input_tokens=100, output_tokens=50, model="test-model")
        msg = AgenticMessage(
            type=AgenticMessageType.USAGE,
            usage=usage,
        )
        assert msg.type == AgenticMessageType.USAGE
        assert msg.usage is not None
        assert msg.usage.input_tokens == 100
        assert msg.usage.output_tokens == 50

    def test_usage_message_json_roundtrip(self) -> None:
        usage = DriverUsage(
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.003,
            model="anthropic/claude-sonnet-4-5",
        )
        msg = AgenticMessage(type=AgenticMessageType.USAGE, usage=usage)
        json_str = msg.model_dump_json()
        restored = AgenticMessage.model_validate_json(json_str)
        assert restored.type == AgenticMessageType.USAGE
        assert restored.usage == usage

    def test_usage_message_not_in_workflow_event_mapping(self) -> None:
        """USAGE messages should raise KeyError in to_workflow_event — they are
        consumed by the driver, never reaching the event bus."""
        msg = AgenticMessage(type=AgenticMessageType.USAGE)
        with pytest.raises(KeyError):
            msg.to_workflow_event(workflow_id="wf-1", agent="developer")
