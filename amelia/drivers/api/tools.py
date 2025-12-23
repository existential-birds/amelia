"""Tool definitions for pydantic-ai agentic execution."""
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import RunContext

from amelia.tools.safe_file import SafeFileWriter
from amelia.tools.safe_shell import SafeShellExecutor


@dataclass
class AgenticContext:
    """Context for agentic tool execution.

    Attributes:
        cwd: Working directory for command execution.
        allowed_dirs: Directories where file writes are permitted.
    """

    cwd: str
    allowed_dirs: list[str] | None = None

    def __post_init__(self) -> None:
        """Validate and normalize paths."""
        cwd_path = Path(self.cwd)
        if not cwd_path.exists():
            raise ValueError(f"Working directory does not exist: {self.cwd}")
        if not cwd_path.is_dir():
            raise ValueError(f"Working directory is not a directory: {self.cwd}")

        # Resolve and normalize
        self.cwd = str(cwd_path.resolve())

        if self.allowed_dirs:
            resolved = []
            for d in self.allowed_dirs:
                p = Path(d)
                if not p.exists():
                    raise ValueError(f"Allowed directory does not exist: {d}")
                resolved.append(str(p.resolve()))
            self.allowed_dirs = resolved


MAX_COMMAND_TIMEOUT = 300  # 5 minutes max
MAX_COMMAND_SIZE = 10_000  # 10KB max command


async def run_shell_command(
    ctx: RunContext[AgenticContext],
    command: str,
    timeout: int = 30,
) -> str:
    """Execute a shell command safely.

    Use this to run shell commands like ls, cat, grep, git, npm, python, etc.
    Commands are executed in the working directory with security restrictions.

    Args:
        ctx: Run context containing the working directory.
        command: The shell command to execute.
        timeout: Maximum execution time in seconds. Defaults to 30. Capped at 300.

    Returns:
        Command output (stdout) as a string.
    """
    # Validate command size to prevent memory exhaustion
    if len(command) > MAX_COMMAND_SIZE:
        raise ValueError(f"Command size ({len(command)} bytes) exceeds maximum ({MAX_COMMAND_SIZE} bytes)")

    # Validate and cap timeout
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    timeout = min(timeout, MAX_COMMAND_TIMEOUT)

    # SafeShellExecutor.execute is async - call directly
    return await SafeShellExecutor.execute(
        command=command,
        timeout=timeout,
        cwd=ctx.deps.cwd,
    )


async def write_file(
    ctx: RunContext[AgenticContext],
    file_path: str,
    content: str,
) -> str:
    """Write content to a file safely.

    Use this to create or overwrite files. The file path must be within
    the allowed directories (defaults to working directory).

    Args:
        ctx: Run context containing allowed directories.
        file_path: Absolute or relative path to the file to write.
        content: Content to write to the file.

    Returns:
        Success message confirming the write operation.
    """
    allowed_dirs = ctx.deps.allowed_dirs if ctx.deps.allowed_dirs else [ctx.deps.cwd]
    return await SafeFileWriter.write(
        file_path=file_path,
        content=content,
        allowed_dirs=allowed_dirs,
        base_dir=ctx.deps.cwd,
    )
