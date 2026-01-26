"""Tests for amelia.core.constants."""

from datetime import date

from amelia.core.constants import ToolName, normalize_tool_name


def test_resolve_plan_path_substitutes_placeholders():
    from amelia.core.constants import resolve_plan_path

    pattern = "docs/plans/{date}-{issue_key}.md"
    result = resolve_plan_path(pattern, "TEST-123")
    today = date.today().isoformat()
    assert result == f"docs/plans/{today}-test-123.md"


def test_resolve_plan_path_handles_custom_pattern():
    from amelia.core.constants import resolve_plan_path

    pattern = ".amelia/plans/{issue_key}.md"
    result = resolve_plan_path(pattern, "JIRA-456")
    assert result == ".amelia/plans/jira-456.md"


def test_normalize_tool_name_handles_all_driver_variants() -> None:
    """normalize_tool_name handles tool names from all drivers.

    Both CLI (PascalCase) and API (lowercase) driver tool names
    are normalized to standard ToolName values.
    """
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


def test_tool_name_enum_has_all_canonical_names() -> None:
    """ToolName enum defines all 20 canonical tool names."""
    expected = {
        "read_file", "write_file", "edit_file", "notebook_edit",
        "glob", "grep", "run_shell_command", "task", "task_output",
        "task_stop", "enter_plan_mode", "exit_plan_mode",
        "ask_user_question", "skill", "task_create", "task_get",
        "task_update", "task_list", "web_fetch", "web_search",
    }
    actual = {member.value for member in ToolName}
    assert actual == expected
