"""Codex CLI driver using OpenAI's codex CLI.

This driver wraps the OpenAI Codex CLI, providing both single-turn generation
and agentic execution capabilities.
"""
from collections.abc import AsyncIterator
from typing import Any

from amelia.drivers.base import AgenticMessage, DriverUsage, DriverInterface, GenerateResult


class CodexCliDriver(DriverInterface):
    """CLI driver wrapping OpenAI's Codex CLI tool.

    This is a stub implementation. Full implementation will be added in a later task.
    """

    def __init__(self, model: str = "", cwd: str | None = None) -> None:
        """Initialize CodexCliDriver.

        Args:
            model: LLM model identifier.
            cwd: Working directory for command execution.
        """
        self.model = model
        self.cwd = cwd

    async def generate(
        self,
        prompt: str,
        *,
        tools: list[Any] | None = None,
        system: str | None = None,
    ) -> GenerateResult:
        """Generate a single-turn response (not yet implemented)."""
        raise NotImplementedError("CodexCliDriver.generate() not yet implemented")

    async def execute_agentic(
        self,
        user_prompt: str,
        *,
        system: str | None = None,
        tools: list[Any] | None = None,
        max_iterations: int = 50,
        max_tool_calls: int | None = None,
    ) -> AsyncIterator[AgenticMessage]:
        """Execute agentic workflow (not yet implemented)."""
        raise NotImplementedError("CodexCliDriver.execute_agentic() not yet implemented")

    async def cleanup_session(self, session_id: str) -> bool:
        """Clean up a driver session.

        CodexCliDriver has no persistent session state to clean.

        Args:
            session_id: The session identifier to clean up.

        Returns:
            False - no session state exists to clean.
        """
        return False

    def get_usage(self) -> DriverUsage:
        """Get usage statistics (not yet implemented)."""
        raise NotImplementedError("CodexCliDriver.get_usage() not yet implemented")
