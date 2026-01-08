# amelia/core/constants.py
"""Constants used across the Amelia codebase."""

import re
from datetime import date
from enum import StrEnum


class ToolName(StrEnum):
    """Standard tool names used across drivers.

    Attributes:
        RUN_SHELL_COMMAND: Execute a shell command in the worktree.
        WRITE_FILE: Write content to a file.
        READ_FILE: Read content from a file.
    """

    RUN_SHELL_COMMAND = "run_shell_command"
    WRITE_FILE = "write_file"
    READ_FILE = "read_file"


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


BLOCKED_SHELL_METACHARACTERS: tuple[str, ...] = (
    "|",
    ";",
    "&&",
    "||",
    "`",
    "$(",
    "${",
    ">",
    ">>",
    "<",
    "&",
    "\n",
)

BLOCKED_COMMANDS: frozenset[str] = frozenset({
    "sudo",
    "su",
    "doas",
    "pkexec",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init",
    "systemctl",
    "mkfs",
    "fdisk",
    "dd",
    "mount",
    "umount",
})

DANGEROUS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^rm\s+.*-[rf]*\s*/$", re.IGNORECASE),
    re.compile(r"^rm\s+.*-[rf]*\s*~", re.IGNORECASE),
    re.compile(r"^rm\s+.*-[rf]*\s*/home", re.IGNORECASE),
    re.compile(r"^rm\s+.*-[rf]*\s*/etc", re.IGNORECASE),
    re.compile(r"^rm\s+.*-[rf]*\s*/usr", re.IGNORECASE),
    re.compile(r"^rm\s+.*-[rf]*\s*/var", re.IGNORECASE),
    re.compile(r"curl\s+.*\|\s*sh", re.IGNORECASE),
    re.compile(r"curl\s+.*\|\s*bash", re.IGNORECASE),
    re.compile(r"wget\s+.*\|\s*sh", re.IGNORECASE),
    re.compile(r"wget\s+.*\|\s*bash", re.IGNORECASE),
    re.compile(r">\s*/etc/"),
    re.compile(r">\s*/usr/"),
    re.compile(r">\s*/var/"),
    re.compile(r">\s*/bin/"),
    re.compile(r">\s*/sbin/"),
    re.compile(r"chmod\s+777\s+/"),
    re.compile(r"chmod\s+-R\s+777\s+/"),
)

STRICT_MODE_ALLOWED_COMMANDS: frozenset[str] = frozenset({
    "git",
    "npm",
    "npx",
    "pnpm",
    "yarn",
    "bun",
    "pytest",
    "python",
    "python3",
    "pip",
    "uv",
    "ruff",
    "mypy",
    "black",
    "isort",
    "node",
    "make",
    "cargo",
    "go",
    "rustc",
    "gcc",
    "g++",
    "javac",
    "java",
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "echo",
    "printf",
    "mkdir",
    "cp",
    "mv",
    "rm",
    "touch",
    "pwd",
    "cd",
    "which",
    "whereis",
    "whoami",
    "date",
    "wc",
    "sort",
    "uniq",
    "diff",
    "patch",
    "tar",
    "gzip",
    "gunzip",
    "zip",
    "unzip",
    "curl",
    "wget",
    "ssh",
    "scp",
    "rsync",
})
