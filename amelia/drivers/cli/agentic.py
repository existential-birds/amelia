"""Claude Agentic CLI Driver for autonomous code execution."""

import asyncio
from collections.abc import AsyncIterator

from loguru import logger

from amelia.drivers.cli.base import CliDriver
from amelia.drivers.cli.claude import ClaudeStreamEvent


class ClaudeAgenticCliDriver(CliDriver):
    """Claude CLI Driver for fully autonomous agentic execution.

    Uses --dangerously-skip-permissions for YOLO mode where Claude
    executes tools autonomously. Tracks tool calls for observability.

    Attributes:
        tool_call_history: List of tool call events for audit logging.
        model: Claude model to use.
    """

    def __init__(
        self,
        model: str = "sonnet",
        timeout: int = 300,
        max_retries: int = 0
    ):
        """Initialize the agentic driver.

        Args:
            model: Claude model to use. Defaults to "sonnet".
            timeout: Maximum execution time in seconds. Defaults to 300 (5 min).
            max_retries: Number of retry attempts. Defaults to 0.
        """
        super().__init__(timeout=timeout, max_retries=max_retries)
        self.model = model
        self.tool_call_history: list[ClaudeStreamEvent] = []

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None
    ) -> AsyncIterator[ClaudeStreamEvent]:
        """Execute a prompt with full Claude Code tool access.

        Args:
            prompt: The task or instruction for Claude.
            cwd: Working directory for Claude Code context.
            session_id: Optional session ID to resume.

        Yields:
            ClaudeStreamEvent objects including tool executions.
        """
        cmd_args = [
            "claude", "-p",
            "--model", self.model,
            "--output-format", "stream-json",
            "--verbose",  # Required for stream-json with --print
            "--dangerously-skip-permissions"  # YOLO mode
        ]

        if session_id:
            cmd_args.extend(["--resume", session_id])
            logger.info(f"Resuming agentic session: {session_id}")

        logger.info(f"Starting agentic execution in {cwd}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )

            if process.stdin:
                process.stdin.write(prompt.encode())
                await process.stdin.drain()
                process.stdin.close()

            if process.stdout:
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break

                    event = ClaudeStreamEvent.from_stream_json(line.decode())
                    if event:
                        # Track tool calls for observability
                        if event.type == "tool_use":
                            self.tool_call_history.append(event)
                            logger.info(f"Tool call: {event.tool_name}")

                        yield event

            await process.wait()

            if process.returncode != 0:
                stderr_data = await process.stderr.read() if process.stderr else b""
                logger.error(f"Agentic execution failed: {stderr_data.decode()}")

        except Exception as e:
            logger.error(f"Error in agentic execution: {e}")
            yield ClaudeStreamEvent(type="error", content=str(e))

    def clear_tool_history(self) -> None:
        """Clear the tool call history."""
        self.tool_call_history = []
