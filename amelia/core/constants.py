# amelia/core/constants.py
"""Constants used across the Amelia codebase."""

import re
from enum import StrEnum


class ToolName(StrEnum):
    """Standard tool names used across drivers."""

    RUN_SHELL_COMMAND = "run_shell_command"
    WRITE_FILE = "write_file"
    READ_FILE = "read_file"


# Shell metacharacters that indicate shell injection attempts
# These are ALWAYS blocked regardless of security mode
BLOCKED_SHELL_METACHARACTERS: tuple[str, ...] = (
    "|",    # Pipe
    ";",    # Command separator
    "&&",   # AND operator
    "||",   # OR operator
    "`",    # Command substitution (backtick)
    "$(",   # Command substitution
    "${",   # Variable expansion
    ">",    # Redirect stdout
    ">>",   # Append stdout
    "<",    # Redirect stdin
    "&",    # Background execution
    "\n",   # Newline (command separator)
)

# Commands that are always blocked (privilege escalation, system control)
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

# Dangerous argument patterns (compiled regex)
# These patterns detect destructive or exfiltration attempts
DANGEROUS_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Destructive rm commands
    re.compile(r"^rm\s+.*-[rf]*\s*/$", re.IGNORECASE),           # rm -rf /
    re.compile(r"^rm\s+.*-[rf]*\s*~", re.IGNORECASE),            # rm -rf ~
    re.compile(r"^rm\s+.*-[rf]*\s*/home", re.IGNORECASE),        # rm -rf /home
    re.compile(r"^rm\s+.*-[rf]*\s*/etc", re.IGNORECASE),         # rm -rf /etc
    re.compile(r"^rm\s+.*-[rf]*\s*/usr", re.IGNORECASE),         # rm -rf /usr
    re.compile(r"^rm\s+.*-[rf]*\s*/var", re.IGNORECASE),         # rm -rf /var

    # Curl/wget piped to shell (common malware pattern)
    re.compile(r"curl\s+.*\|\s*sh", re.IGNORECASE),
    re.compile(r"curl\s+.*\|\s*bash", re.IGNORECASE),
    re.compile(r"wget\s+.*\|\s*sh", re.IGNORECASE),
    re.compile(r"wget\s+.*\|\s*bash", re.IGNORECASE),

    # Writing to system directories
    re.compile(r">\s*/etc/"),
    re.compile(r">\s*/usr/"),
    re.compile(r">\s*/var/"),
    re.compile(r">\s*/bin/"),
    re.compile(r">\s*/sbin/"),

    # Chmod 777 on system paths
    re.compile(r"chmod\s+777\s+/"),
    re.compile(r"chmod\s+-R\s+777\s+/"),
)

# For strict mode: default allowlist of safe commands
# Only used when security.shell_mode = "strict" in config
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
