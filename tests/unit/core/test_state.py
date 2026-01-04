"""Tests for ExecutionState model."""
import pytest

from amelia.core.state import ExecutionState


class TestExecutionStateRawArchitectOutput:
    """Tests for raw_architect_output field."""

    def test_raw_architect_output_defaults_to_none(self) -> None:
        """raw_architect_output should default to None."""
        state = ExecutionState(profile_id="test")
        assert state.raw_architect_output is None

    def test_raw_architect_output_stores_string(self) -> None:
        """raw_architect_output should store markdown string."""
        markdown = "# Plan\n\n**Goal:** Do something"
        state = ExecutionState(profile_id="test", raw_architect_output=markdown)
        assert state.raw_architect_output == markdown

    def test_raw_architect_output_in_model_copy(self) -> None:
        """raw_architect_output should work with model_copy."""
        state = ExecutionState(profile_id="test")
        new_state = state.model_copy(update={"raw_architect_output": "# Updated"})
        assert new_state.raw_architect_output == "# Updated"
        assert state.raw_architect_output is None  # Original unchanged
