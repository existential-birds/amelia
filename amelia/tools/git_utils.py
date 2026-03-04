"""Git utilities for repository operations."""

import asyncio
from pathlib import Path

from loguru import logger


async def _run_git_command(
    command: str,
    repo_path: Path | None = None,
    check: bool = True,
    timeout: float = 60.0,
) -> str:
    """Run a git command and return stdout.

    Args:
        command: Git command to run (e.g., "git rev-parse HEAD")
        repo_path: Repository path (defaults to current directory)
        check: If True, raise RuntimeError on non-zero exit code
        timeout: Maximum time in seconds to wait for command (default: 60.0)

    Returns:
        Command stdout as string

    Raises:
        RuntimeError: If command fails and check=True, or if timeout occurs
    """
    cwd = repo_path or Path.cwd()

    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
    except TimeoutError as e:
        # Kill the process if it's still running
        try:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            pass  # Process already terminated
        raise RuntimeError(
            f"Git command timed out after {timeout} seconds: {command}"
        ) from e

    if check and process.returncode != 0:
        stderr_text = stderr.decode().strip()
        raise RuntimeError(
            f"Git command failed with exit code {process.returncode}: {stderr_text}"
        )

    return stdout.decode().strip()


async def get_current_commit(cwd: str | None = None) -> str | None:
    """Get the current HEAD commit SHA.

    Args:
        cwd: Working directory for git command.

    Returns:
        The current commit SHA, or None if not in a git repo.
    """
    try:
        repo_path = Path(cwd) if cwd else None
        result = await _run_git_command(
            "git rev-parse HEAD",
            repo_path=repo_path,
            check=True,
        )
        return result if result else None
    except RuntimeError:
        logger.warning("Failed to get current commit", cwd=cwd)
        return None
