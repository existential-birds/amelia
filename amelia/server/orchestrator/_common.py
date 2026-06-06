"""Shared helpers for the orchestrator package.

This module holds symbols needed by both ``service.py`` and ``runner.py``.
It must not import from either of those modules so that both can import it
without creating an import cycle (``service.py`` imports ``runner.py``).
"""

import asyncio

import httpx
import openai
from httpx import TimeoutException

from amelia.core.exceptions import ModelProviderError


# Exceptions that warrant retry
TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    asyncio.TimeoutError,
    TimeoutException,
    ConnectionError,
    ModelProviderError,
    httpx.TransportError,
    openai.APIConnectionError,
)


async def get_git_head(cwd: str | None) -> str | None:
    """Get current git HEAD commit SHA.

    Args:
        cwd: Working directory for git command.

    Returns:
        Current HEAD commit SHA or None if not a git repo.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode().strip()
    except (FileNotFoundError, OSError):
        pass
    return None
