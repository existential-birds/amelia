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
    "Read": ToolName.READ_FILE,
    "Write": ToolName.WRITE_FILE,
    "Edit": ToolName.EDIT_FILE,
    "NotebookEdit": ToolName.NOTEBOOK_EDIT,
    "Glob": ToolName.GLOB,
    "Grep": ToolName.GREP,
    "Bash": ToolName.RUN_SHELL_COMMAND,
    "Task": ToolName.TASK,
    "TaskOutput": ToolName.TASK_OUTPUT,
    "TaskStop": ToolName.TASK_STOP,
    "EnterPlanMode": ToolName.ENTER_PLAN_MODE,
    "ExitPlanMode": ToolName.EXIT_PLAN_MODE,
    "AskUserQuestion": ToolName.ASK_USER_QUESTION,
    "Skill": ToolName.SKILL,
    "TaskCreate": ToolName.TASK_CREATE,
    "TaskGet": ToolName.TASK_GET,
    "TaskUpdate": ToolName.TASK_UPDATE,
    "TaskList": ToolName.TASK_LIST,
    "WebFetch": ToolName.WEB_FETCH,
    "WebSearch": ToolName.WEB_SEARCH,
}

# Assumes 1:1 mapping — see test_canonical_to_cli_is_inverse_of_aliases
CANONICAL_TO_CLI: dict[str, str] = {v: k for k, v in TOOL_NAME_ALIASES.items()}

READONLY_TOOLS: tuple[ToolName, ...] = (
    ToolName.READ_FILE,
    ToolName.GLOB,
    ToolName.GREP,
    ToolName.WEB_FETCH,
    ToolName.WEB_SEARCH,
)


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
