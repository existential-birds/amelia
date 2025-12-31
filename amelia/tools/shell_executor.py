# amelia/tools/shell_executor.py
"""Shell command execution utilities.

This module provides backward-compatible wrappers around SafeShellExecutor
and SafeFileWriter for existing code that uses the old interface.
"""

from amelia.tools.safe_file import SafeFileWriter
from amelia.tools.safe_shell import SafeShellExecutor


async def run_shell_command(
    command: str,
    timeout: int | None = 30,
    strict_mode: bool = False,
    cwd: str | None = None,
) -> str:
    """
    Execute a shell command safely.

    This is a backward-compatible wrapper around SafeShellExecutor.execute().

    Args:
        command: The command to execute
        timeout: Maximum execution time in seconds
        strict_mode: If True, only allow commands in strict allowlist
        cwd: Working directory to execute the command in (None for current directory)

    Returns:
        Command stdout as string

    Raises:
        ValueError: If command is empty or has invalid syntax
        ShellInjectionError: If shell metacharacters are detected
        BlockedCommandError: If command is in blocklist
        DangerousCommandError: If command matches dangerous pattern
        CommandNotAllowedError: If strict mode and command not in allowlist
        RuntimeError: If command fails or times out
    """
    return await SafeShellExecutor.execute(
        command=command,
        timeout=timeout,
        strict_mode=strict_mode,
        cwd=cwd,
    )


async def write_file(file_path: str, content: str) -> str:
    """
    Write content to a file safely.

    This is a backward-compatible wrapper around SafeFileWriter.write().

    Args:
        file_path: Path to write to
        content: Content to write

    Returns:
        Success message

    Raises:
        ValueError: If path is empty
        PathTraversalError: If path escapes allowed directories
        OSError: If file cannot be written
    """
    return await SafeFileWriter.write(
        file_path=file_path,
        content=content,
    )
