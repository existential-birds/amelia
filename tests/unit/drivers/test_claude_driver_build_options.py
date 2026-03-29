"""Tests for ClaudeCliDriver._build_options method."""
from unittest.mock import patch

import pytest

from amelia.core.types import AgentConfig, DriverType
from amelia.drivers.cli.claude import ClaudeCliDriver


@pytest.fixture
def mock_driver() -> ClaudeCliDriver:
    """Create a ClaudeCliDriver instance with mocked environment."""
    config = AgentConfig(driver=DriverType.CLAUDE, model="sonnet", options={})
    with patch("amelia.drivers.cli.claude._build_sanitized_env", return_value={}):
        driver = ClaudeCliDriver(model=config.model)
    return driver


class TestBuildOptionsCustomToolNames:
    """Tests for _build_options with custom/unknown tool names."""

    def test_custom_tool_name_does_not_raise(self, mock_driver: ClaudeCliDriver) -> None:
        """_build_options with allowed_tools=['submit_evaluation'] should NOT raise ValueError.

        Custom tool names (e.g. MCP tool names like submit_evaluation) must pass through
        as-is without raising ValueError.
        """
        with patch("amelia.drivers.cli.claude._build_sanitized_env", return_value={}):
            options = mock_driver._build_options(allowed_tools=["submit_evaluation"])

        assert options.allowed_tools is not None
        assert "submit_evaluation" in options.allowed_tools

    def test_canonical_tool_name_still_maps_to_cli_name(self, mock_driver: ClaudeCliDriver) -> None:
        """_build_options with known canonical name 'read_file' should map to 'Read'.

        Existing canonical -> CLI name mapping must be preserved.
        """
        with patch("amelia.drivers.cli.claude._build_sanitized_env", return_value={}):
            options = mock_driver._build_options(allowed_tools=["read_file"])

        assert options.allowed_tools is not None
        assert "Read" in options.allowed_tools
        assert "read_file" not in options.allowed_tools

    def test_mixed_canonical_and_custom_tool_names(self, mock_driver: ClaudeCliDriver) -> None:
        """_build_options with mixed canonical + custom names returns both correctly.

        'read_file' maps to 'Read', 'submit_evaluation' passes through unchanged.
        """
        with patch("amelia.drivers.cli.claude._build_sanitized_env", return_value={}):
            options = mock_driver._build_options(
                allowed_tools=["read_file", "submit_evaluation"]
            )

        assert options.allowed_tools is not None
        assert "Read" in options.allowed_tools
        assert "submit_evaluation" in options.allowed_tools
        assert "read_file" not in options.allowed_tools
