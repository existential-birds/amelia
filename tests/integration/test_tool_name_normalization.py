"""Integration tests for tool name normalization across drivers.

These tests verify that goal extraction works consistently regardless of
which driver produces the tool calls (CLI driver with normalized names,
or API driver with snake_case names).
"""

import pytest

from amelia.core.agentic_state import ToolCall
from amelia.core.constants import ToolName
from amelia.core.orchestrator import _extract_goal_from_markdown


@pytest.mark.asyncio
async def test_goal_extraction_with_normalized_tool_name() -> None:
    """Goal extraction works with normalized tool names from CLI driver.

    CLI driver now normalizes 'Write' → 'write_file', and the orchestrator
    checks for ToolName.WRITE_FILE, so this should work.
    """
    plan_content = """# Feature Plan

**Goal:** Add dark mode support

## Tasks
..."""

    # Simulate state from CLI driver (now normalized to write_file)
    tool_calls = [
        ToolCall(
            id="tool_cli_123",
            tool_name=ToolName.WRITE_FILE,  # Normalized by CLI driver
            tool_input={"file_path": "/tmp/plan.md", "content": plan_content},
        )
    ]

    # Extract using the orchestrator's logic
    extracted_content = None
    for tool_call in tool_calls:
        if tool_call.tool_name == ToolName.WRITE_FILE and isinstance(tool_call.tool_input, dict):
            file_path = tool_call.tool_input.get("file_path", "")
            content = tool_call.tool_input.get("content", "")
            if file_path.endswith(".md") and "**Goal:**" in content:
                extracted_content = content
                break

    assert extracted_content is not None
    goal = _extract_goal_from_markdown(extracted_content)
    assert goal == "Add dark mode support"


@pytest.mark.asyncio
async def test_goal_extraction_with_api_driver_tool_name() -> None:
    """Goal extraction works with API driver tool names (already snake_case).

    API drivers use 'write_file' directly, which matches ToolName.WRITE_FILE.
    """
    plan_content = """# API Feature

**Goal:** Implement REST endpoints

## Tasks
..."""

    # Simulate state from API driver (already uses write_file)
    tool_calls = [
        ToolCall(
            id="tool_api_456",
            tool_name="write_file",  # Direct string, API driver format
            tool_input={"file_path": "/tmp/plan.md", "content": plan_content},
        )
    ]

    extracted_content = None
    for tool_call in tool_calls:
        if tool_call.tool_name == ToolName.WRITE_FILE and isinstance(tool_call.tool_input, dict):
            file_path = tool_call.tool_input.get("file_path", "")
            content = tool_call.tool_input.get("content", "")
            if file_path.endswith(".md") and "**Goal:**" in content:
                extracted_content = content
                break

    assert extracted_content is not None
    goal = _extract_goal_from_markdown(extracted_content)
    assert goal == "Implement REST endpoints"


@pytest.mark.asyncio
async def test_tool_name_enum_equality_with_string() -> None:
    """ToolName enum values should compare equal to their string values.

    This is critical for the fix - StrEnum allows comparison with strings.
    """
    # StrEnum comparison works bidirectionally
    assert ToolName.WRITE_FILE == "write_file"
    assert ToolName.WRITE_FILE == "write_file"

    assert ToolName.READ_FILE == "read_file"
    assert ToolName.READ_FILE == "read_file"

    assert ToolName.RUN_SHELL_COMMAND == "run_shell_command"
    assert ToolName.RUN_SHELL_COMMAND == "run_shell_command"

    # But different values don't match
    assert ToolName.WRITE_FILE != "Write"
    assert ToolName.WRITE_FILE != "write"
    assert ToolName.WRITE_FILE != "WriteFile"
