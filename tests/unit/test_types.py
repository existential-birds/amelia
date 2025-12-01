"""Tests for core types."""

from amelia.core.types import ExecutionMode


def test_execution_mode_literal_values():
    """ExecutionMode should accept 'structured' and 'agentic'."""
    mode1: ExecutionMode = "structured"
    mode2: ExecutionMode = "agentic"
    assert mode1 == "structured"
    assert mode2 == "agentic"
