import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, ValidationError

from amelia.core.constants import ToolName
from amelia.core.state import AgentMessage
from amelia.drivers.cli.base import CliDriver
from amelia.tools.safe_file import SafeFileWriter
from amelia.tools.safe_shell import SafeShellExecutor


ClaudeStreamEventType = Literal["assistant", "tool_use", "result", "error", "system"]

# Phrases that indicate Claude is asking for clarification rather than producing output
_CLARIFICATION_PHRASES = [
    "could you clarify",
    "can you provide",
    "i need more",
    "please provide",
    "before i can",
    "to help me understand",
    "i have a few questions",
    "could you tell me",
    "what type of",
    "which approach",
    "i need to know",
    "can you tell me",
    "i'd like to understand",
    "could you explain",
    "what is the",
    "what are the",
]


def _is_clarification_request(text: str) -> bool:
    """Detect if Claude is asking for clarification instead of producing output.

    Args:
        text: The text response from Claude.

    Returns:
        True if the response appears to be asking for clarification.
    """
    text_lower = text.lower()

    # Check for clarification phrases
    if any(phrase in text_lower for phrase in _CLARIFICATION_PHRASES):
        return True

    # Multiple questions strongly suggest a clarification request
    return text.count("?") >= 2


class ClaudeStreamEvent(BaseModel):
    """Event from Claude CLI stream-json output.

    Attributes:
        type: Event type (assistant, tool_use, result, error, system).
        content: Text content for assistant/error/system events.
        tool_name: Tool name for tool_use events.
        tool_input: Tool input parameters for tool_use events.
        session_id: Session ID from result events for session continuity.
    """
    type: ClaudeStreamEventType
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    session_id: str | None = None

    @classmethod
    def from_stream_json(cls, line: str) -> "ClaudeStreamEvent | None":
        """Parse a line from Claude CLI stream-json output.

        Args:
            line: Raw JSON line from stream output.

        Returns:
            Parsed event or None for empty lines, error event for malformed JSON.
        """
        stripped = line.strip()
        if not stripped:
            return None

        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as e:
            return cls(type="error", content=f"Failed to parse stream JSON: {e}")

        msg_type = data.get("type", "")

        # Handle result events (contain session_id)
        if msg_type == "result":
            return cls(
                type="result",
                session_id=data.get("session_id")
            )

        # Handle assistant messages (contain content blocks)
        if msg_type == "assistant":
            message = data.get("message", {})
            content_blocks = message.get("content", [])

            for block in content_blocks:
                block_type = block.get("type", "")

                if block_type == "text":
                    return cls(type="assistant", content=block.get("text", ""))

                if block_type == "tool_use":
                    return cls(
                        type="tool_use",
                        tool_name=block.get("name"),
                        tool_input=block.get("input")
                    )

        # Handle system messages
        if msg_type == "system":
            return cls(type="system", content=data.get("message", ""))

        # Unknown type - return as system event
        return cls(type="system", content=f"Unknown event type: {msg_type}")


class ClaudeCliDriver(CliDriver):
    """Claude CLI Driver interacts with the Claude model via the local 'claude' CLI tool.

    Attributes:
        model: Claude model to use (sonnet, opus, haiku).
        skip_permissions: Whether to use --dangerously-skip-permissions flag.
        allowed_tools: List of allowed tool names (passed via --allowedTools).
        disallowed_tools: List of disallowed tool names (passed via --disallowedTools).
        tool_call_history: List of tool calls made during agentic execution.
    """

    def __init__(
        self,
        model: str = "sonnet",
        timeout: int = 30,
        max_retries: int = 0,
        skip_permissions: bool = False,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
    ):
        """Initialize the Claude CLI driver.

        Args:
            model: Claude model to use. Defaults to "sonnet".
            timeout: Maximum execution time in seconds. Defaults to 30.
            max_retries: Number of retry attempts. Defaults to 0.
            skip_permissions: Skip permission prompts. Defaults to False.
            allowed_tools: List of allowed tool names. Defaults to None.
            disallowed_tools: List of disallowed tool names. Defaults to None.
        """
        super().__init__(timeout, max_retries)
        self.model = model
        self.skip_permissions = skip_permissions
        self.allowed_tools = allowed_tools
        self.disallowed_tools = disallowed_tools
        self.tool_call_history: list[ClaudeStreamEvent] = []

    def _convert_messages_to_prompt(self, messages: list[AgentMessage]) -> str:
        """Convert a list of AgentMessages into a single string prompt.

        System messages are excluded as they are handled separately via CLI flags.

        Args:
            messages: List of AgentMessage objects to convert.

        Returns:
            A formatted string with each message prefixed by its role.
        """
        prompt_parts = []
        for msg in messages:
            if msg.role == "system":
                continue  # System messages handled separately
            role_str = msg.role.upper() if msg.role else "USER"
            content = msg.content or ""
            prompt_parts.append(f"{role_str}: {content}")

        return "\n\n".join(prompt_parts)

    async def _generate_impl(
        self,
        messages: list[AgentMessage],
        schema: type[BaseModel] | None = None,
        **kwargs: Any
    ) -> Any:
        """Generates a response using the 'claude' CLI.

        Args:
            messages: Conversation history.
            schema: Optional Pydantic model for structured output.
            **kwargs: Driver-specific parameters:
                - session_id: Optional session ID to resume a previous conversation.
                - cwd: Optional working directory for Claude CLI context.

        Returns:
            Either a string (if no schema) or an instance of the schema.
        """
        session_id = kwargs.get("session_id")
        cwd = kwargs.get("cwd")

        # Extract system messages for separate handling
        system_messages = [m for m in messages if m.role == "system"]

        full_prompt = self._convert_messages_to_prompt(messages)

        # Build the command - we use -p for print mode (non-interactive)
        cmd_args = ["claude", "-p", "--model", self.model]

        # Add permission flags
        if self.skip_permissions:
            cmd_args.append("--dangerously-skip-permissions")
        if self.allowed_tools:
            cmd_args.extend(["--allowedTools", ",".join(self.allowed_tools)])
        if self.disallowed_tools:
            cmd_args.extend(["--disallowedTools", ",".join(self.disallowed_tools)])

        # Add system prompt if present
        if system_messages:
            system_prompt = "\n\n".join(m.content for m in system_messages if m.content)
            cmd_args.extend(["--append-system-prompt", system_prompt])

        # Add resume support
        if session_id:
            cmd_args.extend(["--resume", session_id])
            logger.info(f"Resuming Claude session: {session_id}")

        if schema:
            # Generate JSON schema
            json_schema = json.dumps(schema.model_json_schema())
            cmd_args.extend(["--json-schema", json_schema])
            # If schema is provided, we might want to force json output format if the CLI supports it strictly,
            # but --json-schema usually implies structured output.
            # The help says: --output-format <format> ... "json" (single result)
            cmd_args.extend(["--output-format", "json"])

        # Create subprocess
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )

            # Write prompt to stdin
            if process.stdin:
                process.stdin.write(full_prompt.encode())
                await process.stdin.drain()
                process.stdin.close()

            stdout_buffer = []
            stderr_buffer = []

            async def read_stdout() -> None:
                """Read stdout line by line and append to buffer with debug logging."""
                if process.stdout is not None:
                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            break
                        text = line.decode()
                        logger.opt(raw=True).debug(text)
                        stdout_buffer.append(text)

            async def read_stderr() -> None:
                """Read stderr stream and append to buffer."""
                if process.stderr is not None:
                    data = await process.stderr.read()
                    stderr_buffer.append(data.decode())

            # Run readers concurrently
            await asyncio.gather(read_stdout(), read_stderr())
            await process.wait()
            
            stdout_str = "".join(stdout_buffer).strip()
            stderr_str = "".join(stderr_buffer).strip()

            if process.returncode != 0:
                raise RuntimeError(f"Claude CLI failed with return code {process.returncode}. Stderr: {stderr_str}")

            if schema:
                try:
                    # Parse JSON output
                    data = json.loads(stdout_str)
                    
                    # Unwrap Claude CLI result wrapper if present
                    if isinstance(data, dict) and data.get("type") == "result":
                        if data.get("subtype") == "success":
                            # Extract the actual model output
                            # It should be in 'structured_output' for --json-schema calls
                            if "structured_output" in data:
                                data = data["structured_output"]
                            elif "result" in data:
                                # Fallback: try to parse result as JSON
                                result_content = data["result"]
                                if isinstance(result_content, str):
                                    try:
                                        data = json.loads(result_content)
                                    except json.JSONDecodeError:
                                        # Model returned text instead of structured JSON
                                        preview = result_content[:500] + "..." if len(result_content) > 500 else result_content
                                        session_id = data.get("session_id")

                                        if _is_clarification_request(result_content):
                                            # Claude is asking for clarification
                                            session_info = f" (session_id: {session_id})" if session_id else ""
                                            raise RuntimeError(
                                                f"Claude requested clarification instead of producing structured output{session_info}.\n\n"
                                                f"This typically happens when the issue/prompt lacks sufficient detail.\n"
                                                f"Consider providing more context in the issue description.\n\n"
                                                f"Claude's questions:\n{preview}"
                                            ) from None
                                        else:
                                            # Generic text response (not clarification)
                                            raise RuntimeError(
                                                f"Claude CLI returned text instead of structured JSON.\n"
                                                f"Expected: JSON matching the requested schema\n"
                                                f"Received: {preview}"
                                            ) from None
                                elif isinstance(result_content, (dict, list)):
                                    data = result_content
                                else:
                                    raise RuntimeError(f"Unexpected result type from Claude CLI: {type(result_content)}")
                        else:
                            # If subtype is error or something else, we should probably error out
                            # using the error info in the wrapper
                            errors = data.get("errors", [])
                            raise RuntimeError(f"Claude CLI reported error: {data.get('subtype')} - {errors}")

                    # Fix: If the model expects a wrapped "tasks" list but CLI returns a raw list, wrap it.
                    # This is a common issue with some models/CLI interactions.
                    if isinstance(data, list) and "tasks" in schema.model_fields:
                         data = {"tasks": data}

                    return schema.model_validate(data)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"Failed to parse JSON from Claude CLI output: {stdout_str}. Error: {e}") from e
                except ValidationError as e:
                    raise RuntimeError(f"Claude CLI output did not match schema: {e}") from e
            else:
                # Return raw text
                return stdout_str

        except Exception as e:
            # Log the error or re-raise appropriately. 
            # For the driver interface, we might want to wrap it or just let it bubble up.
            raise RuntimeError(f"Error executing Claude CLI: {e}") from e

    async def _execute_tool_impl(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute a tool locally using safe utilities.

        Args:
            tool_name: Name of the tool to execute (e.g., "run_shell_command", "write_file").
            **kwargs: Tool-specific parameters:
                - command: Shell command string (for run_shell_command).
                - file_path: Target file path (for write_file).
                - content: File content to write (for write_file).

        Returns:
            Tool execution result (varies by tool type).

        Raises:
            ValueError: If required arguments are missing.
            NotImplementedError: If tool_name is not supported.
        """
        if tool_name == ToolName.RUN_SHELL_COMMAND:
            command = kwargs.get("command")
            if not command:
                raise ValueError("run_shell_command requires a 'command' argument.")
            return await SafeShellExecutor.execute(command, timeout=self.timeout)

        elif tool_name == ToolName.WRITE_FILE:
            file_path = kwargs.get("file_path")
            content = kwargs.get("content", "")
            if not file_path:
                raise ValueError("write_file requires a 'file_path' argument.")
            return await SafeFileWriter.write(file_path, content)

        else:
            raise NotImplementedError(f"Tool '{tool_name}' not implemented for ClaudeCliDriver.")

    async def generate_stream(
        self,
        messages: list[AgentMessage],
        session_id: str | None = None,
        cwd: str | None = None
    ) -> AsyncIterator[ClaudeStreamEvent]:
        """Generate a streaming response from Claude CLI.

        Args:
            messages: History of conversation messages.
            session_id: Optional session ID to resume a previous conversation.
            cwd: Optional working directory for Claude CLI context.

        Yields:
            ClaudeStreamEvent objects as they are parsed from the stream.
        """
        # Extract system messages
        system_messages = [m for m in messages if m.role == "system"]
        full_prompt = self._convert_messages_to_prompt(messages)

        cmd_args = ["claude", "-p", "--verbose", "--model", self.model, "--output-format", "stream-json"]

        # Add permission flags
        if self.skip_permissions:
            cmd_args.append("--dangerously-skip-permissions")
        if self.allowed_tools:
            cmd_args.extend(["--allowedTools", ",".join(self.allowed_tools)])
        if self.disallowed_tools:
            cmd_args.extend(["--disallowedTools", ",".join(self.disallowed_tools)])

        # Add system prompt if present
        if system_messages:
            system_prompt = "\n\n".join(m.content for m in system_messages if m.content)
            cmd_args.extend(["--append-system-prompt", system_prompt])

        if session_id:
            cmd_args.extend(["--resume", session_id])
            logger.info(f"Resuming Claude session: {session_id}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )

            if process.stdin:
                process.stdin.write(full_prompt.encode())
                await process.stdin.drain()
                process.stdin.close()

            # Stream stdout line by line
            if process.stdout:
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break

                    event = ClaudeStreamEvent.from_stream_json(line.decode())
                    if event:
                        yield event

            await process.wait()

            if process.returncode != 0:
                stderr_data = await process.stderr.read() if process.stderr else b""
                logger.error(f"Claude CLI failed: {stderr_data.decode()}")

        except Exception as e:
            logger.error(f"Error in Claude CLI streaming: {e}")
            yield ClaudeStreamEvent(type="error", content=str(e))

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None
    ) -> AsyncIterator[ClaudeStreamEvent]:
        """Execute prompt with full autonomous tool access (YOLO mode).

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
            "--verbose",
            "--dangerously-skip-permissions"
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