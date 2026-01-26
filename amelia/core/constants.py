# amelia/core/constants.py
"""Constants used across the Amelia codebase."""

from datetime import date
from enum import StrEnum


class ToolName(StrEnum):
    """Standard tool names used across drivers."""

    # File operations
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    EDIT_FILE = "edit_file"
    NOTEBOOK_EDIT = "notebook_edit"
    GLOB = "glob"
    GREP = "grep"
    # Execution
    RUN_SHELL_COMMAND = "run_shell_command"
    # Agent orchestration
    TASK = "task"
    TASK_OUTPUT = "task_output"
    TASK_STOP = "task_stop"
    # Planning
    ENTER_PLAN_MODE = "enter_plan_mode"
    EXIT_PLAN_MODE = "exit_plan_mode"
    # Interaction
    ASK_USER_QUESTION = "ask_user_question"
    SKILL = "skill"
    # Task tracking
    TASK_CREATE = "task_create"
    TASK_GET = "task_get"
    TASK_UPDATE = "task_update"
    TASK_LIST = "task_list"
    # Web
    WEB_FETCH = "web_fetch"
    WEB_SEARCH = "web_search"


TOOL_NAME_ALIASES: dict[str, str] = {
    "Write": ToolName.WRITE_FILE,
    "Read": ToolName.READ_FILE,
    "Bash": ToolName.RUN_SHELL_COMMAND,
    "write": ToolName.WRITE_FILE,
    "read": ToolName.READ_FILE,
}


def normalize_tool_name(raw_name: str) -> str:
    """Normalize driver-specific tool name to standard ToolName.

    Args:
        raw_name: The raw tool name from a driver (e.g., "Write", "write").

    Returns:
        The normalized tool name (e.g., "write_file"), or raw_name if no alias exists.
    """
    return TOOL_NAME_ALIASES.get(raw_name, raw_name)


def resolve_plan_path(pattern: str, issue_key: str) -> str:
    """Resolve a plan path pattern to a concrete path.

    Supported placeholders:
    - {date}: Today's date in YYYY-MM-DD format
    - {issue_key}: The issue key, lowercased

    Args:
        pattern: Path pattern with placeholders.
        issue_key: The issue key (e.g., "TEST-123").

    Returns:
        Resolved path with placeholders substituted.
    """
    today = date.today().isoformat()
    normalized_key = issue_key.lower()
    return pattern.format(date=today, issue_key=normalized_key)
