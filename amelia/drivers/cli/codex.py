"""Codex CLI driver using OpenAI's codex CLI.

This driver wraps the OpenAI Codex CLI, providing both single-turn generation
and agentic execution capabilities.
"""
from collections.abc import AsyncIterator, Iterator
from typing import Any

from pydantic import BaseModel

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

    async def _run_codex(self, prompt: str, **kwargs: Any) -> str:
        """Run codex CLI command and return output (not yet implemented)."""
        raise NotImplementedError("CodexCliDriver._run_codex() not yet implemented")

    def _run_codex_stream(self, prompt: str, **kwargs: Any) -> Iterator[dict[str, Any]]:
        """Run codex CLI command and stream events (not yet implemented)."""
        raise NotImplementedError("CodexCliDriver._run_codex_stream() not yet implemented")

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        schema: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> GenerateResult:
        """Generate a single-turn response (not yet implemented)."""
        raise NotImplementedError("CodexCliDriver.generate() not yet implemented")

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
        schema: type[BaseModel] | None = None,
        allowed_tools: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AgenticMessage]:
        """Execute agentic workflow (not yet implemented)."""
        raise NotImplementedError("CodexCliDriver.execute_agentic() not yet implemented")
        yield  # pragma: no cover

    async def cleanup_session(self, session_id: str) -> bool:
        """Clean up a driver session.

        CodexCliDriver has no persistent session state to clean.

        Args:
            session_id: The session identifier to clean up.

        Returns:
            False - no session state exists to clean.
        """
        return False

    def get_usage(self) -> DriverUsage | None:
        """Get usage statistics (not yet implemented)."""
        raise NotImplementedError("CodexCliDriver.get_usage() not yet implemented")
