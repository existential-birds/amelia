"""Integration tests for tool name normalization in drivers.

These tests verify that tool name normalization works correctly in drivers,
mapping different tool name formats (PascalCase from CLI, lowercase from API)
to consistent ToolName enum values.

Note: Plan extraction now uses a fixed file path instead of parsing tool calls.
See test_orchestrator_plan_extraction.py for those tests.
"""

from amelia.core.constants import ToolName


def test_tool_name_enum_equality_with_string() -> None:
    """ToolName enum values should compare equal to their string values.

    StrEnum allows comparison with strings, which is used by drivers.
    """
    # StrEnum comparison works bidirectionally
    assert ToolName.WRITE_FILE == "write_file"
    assert ToolName.READ_FILE == "read_file"
    assert ToolName.RUN_SHELL_COMMAND == "run_shell_command"

    # But different values don't match
    assert ToolName.WRITE_FILE != "Write"
    assert ToolName.WRITE_FILE != "write"
    assert ToolName.WRITE_FILE != "WriteFile"


def test_normalize_tool_name_handles_all_driver_variants() -> None:
    """normalize_tool_name handles tool names from all drivers.

    Both CLI (PascalCase) and API (lowercase) driver tool names
    are normalized to standard ToolName values.
    """
    from amelia.core.constants import normalize_tool_name

    # Claude CLI driver uses PascalCase
    assert normalize_tool_name("Write") == ToolName.WRITE_FILE
    assert normalize_tool_name("Read") == ToolName.READ_FILE
    assert normalize_tool_name("Bash") == ToolName.RUN_SHELL_COMMAND

    # DeepAgents API driver uses lowercase
    assert normalize_tool_name("write") == ToolName.WRITE_FILE
    assert normalize_tool_name("read") == ToolName.READ_FILE
    # Note: DeepAgents uses execute() backend, not a "bash" tool name

    # Unknown names pass through unchanged
    assert normalize_tool_name("unknown_tool") == "unknown_tool"
    assert normalize_tool_name("custom") == "custom"
