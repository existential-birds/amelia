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


def test_tool_name_aliases_covers_all_cli_sdk_names() -> None:
    """TOOL_NAME_ALIASES maps every CLI SDK name to its canonical name."""
    from amelia.core.constants import TOOL_NAME_ALIASES
    expected_cli_names = {
        "Read", "Write", "Edit", "NotebookEdit", "Glob", "Grep", "Bash",
        "Task", "TaskOutput", "TaskStop", "EnterPlanMode", "ExitPlanMode",
        "AskUserQuestion", "Skill", "TaskCreate", "TaskGet", "TaskUpdate",
        "TaskList", "WebFetch", "WebSearch",
    }
    assert set(TOOL_NAME_ALIASES.keys()) == expected_cli_names


def test_canonical_to_cli_is_inverse_of_aliases() -> None:
    """CANONICAL_TO_CLI maps every canonical name back to its CLI SDK name."""
    from amelia.core.constants import CANONICAL_TO_CLI, TOOL_NAME_ALIASES
    for cli_name, canonical in TOOL_NAME_ALIASES.items():
        assert CANONICAL_TO_CLI[canonical] == cli_name
    assert len(CANONICAL_TO_CLI) == len(TOOL_NAME_ALIASES), "Duplicate canonical names detected in TOOL_NAME_ALIASES"


def test_canonical_to_cli_covers_all_tool_names() -> None:
    """CANONICAL_TO_CLI has an entry for every ToolName enum member."""
    from amelia.core.constants import CANONICAL_TO_CLI
    for member in ToolName:
        assert member.value in CANONICAL_TO_CLI, f"Missing CANONICAL_TO_CLI entry for {member}"


def test_readonly_tools_contains_expected_tools() -> None:
    """READONLY_TOOLS preset includes only safe read/search tools."""
    from amelia.core.constants import READONLY_TOOLS
    expected = [
        ToolName.READ_FILE,
        ToolName.GLOB,
        ToolName.GREP,
        ToolName.WEB_FETCH,
        ToolName.WEB_SEARCH,
    ]
    assert expected == READONLY_TOOLS


def test_readonly_tools_excludes_write_and_exec() -> None:
    """READONLY_TOOLS must not include any write or execution tools."""
    from amelia.core.constants import READONLY_TOOLS
    dangerous = {
        ToolName.WRITE_FILE, ToolName.EDIT_FILE, ToolName.RUN_SHELL_COMMAND,
        ToolName.NOTEBOOK_EDIT,
    }
    assert not dangerous.intersection(READONLY_TOOLS)
