# amelia/tools/shell_executor.py
"""Shell command execution utilities."""

import asyncio
import shlex


async def run_shell_command(
    command: str,
    timeout: int | None = 30,
    cwd: str | None = None,
) -> str:
    """
    Execute a shell command.

    Args:
        command: The command to execute
        timeout: Maximum execution time in seconds
        cwd: Working directory to execute the command in (None for current directory)

    Returns:
        Command stdout as string

    Raises:
        ValueError: If command is empty or malformed (e.g., unclosed quotes)
        RuntimeError: If command fails or times out
    """
    if not command or not command.strip():
        raise ValueError("Command cannot be empty")

    args = shlex.split(command)

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

        if process.returncode != 0:
            error_msg = stderr.decode().strip() if stderr else "Command failed"
            raise RuntimeError(f"Command failed with exit code {process.returncode}: {error_msg}")

        return stdout.decode().strip()

    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError(f"Command timed out after {timeout} seconds") from None
