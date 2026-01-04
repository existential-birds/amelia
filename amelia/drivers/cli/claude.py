"""Claude CLI driver using the claude-agent-sdk.

This driver wraps the Claude CLI via the official claude-agent-sdk package,
providing both single-turn generation and agentic execution capabilities.
"""
import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, query
from claude_agent_sdk.types import (
    AssistantMessage,
    Message,
    ResultMessage,
    StreamEvent as SDKStreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from loguru import logger
from pydantic import BaseModel, ValidationError

from amelia.drivers.base import AgenticMessage, AgenticMessageType, GenerateResult
from amelia.logging import log_claude_result


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from text if present.

    Handles common patterns like:
    - ```json\n{...}\n```
    - ```\n{...}\n```

    Args:
        text: Text that may contain markdown code fences.

    Returns:
        Text with code fences stripped, or original text if no fences found.
    """
    stripped = text.strip()

    # Check for fenced code block pattern
    if stripped.startswith("```"):
        lines = stripped.split("\n")

        # Find the opening fence (first line starting with ```)
        if lines and lines[0].startswith("```"):
            # Find the closing fence
            end_idx = -1
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end_idx = i
                    break

            if end_idx > 0:
                # Extract content between fences
                content_lines = lines[1:end_idx]
                return "\n".join(content_lines).strip()

    return text


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

    Checks for common clarification phrases and multiple question marks
    to identify when Claude needs more information from the user.

    Args:
        text: The text response from Claude to analyze.

    Returns:
        True if the response appears to be requesting clarification, False otherwise.
    """
    text_lower = text.lower()

    # Check for clarification phrases
    if any(phrase in text_lower for phrase in _CLARIFICATION_PHRASES):
        return True

    # Multiple questions strongly suggest a clarification request
    return text.count("?") >= 2


def _log_sdk_message(message: Message | SDKStreamEvent) -> None:
    """Log SDK message using the existing log_claude_result function.

    Args:
        message: Message or StreamEvent from claude-agent-sdk to log.
    """
    if isinstance(message, SDKStreamEvent):
        # SDK StreamEvent contains progress updates, log at debug level
        event_type = message.event.get("type", "unknown")
        logger.debug(
            "SDK StreamEvent received",
            event_type=event_type,
            session_id=message.session_id,
        )
        return

    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                log_claude_result(
                    result_type="assistant",
                    content=block.text,
                )
            elif isinstance(block, ToolUseBlock):
                log_claude_result(
                    result_type="tool_use",
                    tool_name=block.name,
                    tool_input=block.input,
                )
            elif isinstance(block, ToolResultBlock):
                content = block.content if isinstance(block.content, str) else str(block.content)
                log_claude_result(
                    result_type="result",
                    result_text=content,
                    subtype="error" if block.is_error else "success",
                )

    elif isinstance(message, ResultMessage):
        log_claude_result(
            result_type="result",
            session_id=message.session_id,
            result_text=message.result,
            subtype="error" if message.is_error else "success",
            duration_ms=message.duration_ms,
            num_turns=message.num_turns,
            cost_usd=message.total_cost_usd,
        )


class ClaudeCliDriver:
    """Claude CLI Driver using the claude-agent-sdk.

    This driver wraps the Claude CLI via the official SDK, providing both
    single-turn generation (via generate()) and autonomous agentic execution
    (via execute_agentic()).

    Attributes:
        model: Claude model to use (sonnet, opus, haiku).
        skip_permissions: Whether to bypass permission prompts.
        allowed_tools: List of allowed tool names.
        disallowed_tools: List of disallowed tool names.
        tool_call_history: List of tool calls made during agentic execution.
    """

    def __init__(
        self,
        model: str = "sonnet",
        skip_permissions: bool = False,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
    ):
        """Initialize the Claude CLI driver.

        Args:
            model: Claude model to use. Defaults to "sonnet".
            skip_permissions: Skip permission prompts. Defaults to False.
            allowed_tools: List of allowed tool names. Defaults to None.
            disallowed_tools: List of disallowed tool names. Defaults to None.
        """
        self.model = model
        self.skip_permissions = skip_permissions
        self.allowed_tools = allowed_tools or []
        self.disallowed_tools = disallowed_tools or []
        self.tool_call_history: list[ToolUseBlock] = []
        self.last_result_message: ResultMessage | None = None

    def _build_options(
        self,
        cwd: str | None = None,
        session_id: str | None = None,
        system_prompt: str | None = None,
        schema: type[BaseModel] | None = None,
        bypass_permissions: bool = False,
    ) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions from driver configuration.

        Args:
            cwd: Working directory for Claude CLI context.
            session_id: Optional session ID to resume a previous conversation.
            system_prompt: Optional system prompt to append.
            schema: Optional Pydantic model for structured output.
            bypass_permissions: Whether to bypass permission prompts for this call.

        Returns:
            Configured ClaudeAgentOptions instance.
        """
        # Determine permission mode
        permission_mode: Literal["default", "acceptEdits", "plan", "bypassPermissions"] | None = None
        if bypass_permissions or self.skip_permissions:
            permission_mode = "bypassPermissions"

        # Build output format for schema if provided
        # Note: SDK expects "schema" key, not "json_schema"
        output_format = None
        if schema:
            output_format = {
                "type": "json_schema",
                "schema": schema.model_json_schema(),
            }

        return ClaudeAgentOptions(
            model=self.model,
            cwd=cwd,
            permission_mode=permission_mode,
            system_prompt=system_prompt,
            resume=session_id,
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            output_format=output_format,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        schema: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> GenerateResult:
        """Generate a response using the claude-agent-sdk.

        Args:
            prompt: The user prompt to send to the model.
            system_prompt: Optional system prompt for context/instructions.
            schema: Optional Pydantic model for structured output.
            **kwargs: Driver-specific parameters:
                - session_id: Optional session ID to resume a previous conversation.
                - cwd: Optional working directory for Claude CLI context.

        Returns:
            GenerateResult tuple of (output, session_id):
            - output: str (if no schema) or instance of the schema
            - session_id: str if returned from SDK, None otherwise

        Raises:
            RuntimeError: If Claude CLI fails or returns unexpected output.
        """
        session_id = kwargs.get("session_id")
        cwd = kwargs.get("cwd")
        session_id_result: str | None = None

        options = self._build_options(
            cwd=cwd,
            session_id=session_id,
            system_prompt=system_prompt,
            schema=schema,
        )

        try:
            # Collect all messages
            result_message: ResultMessage | None = None
            assistant_content: list[str] = []

            async for message in query(prompt=prompt, options=options):
                _log_sdk_message(message)

                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            assistant_content.append(block.text)

                elif isinstance(message, ResultMessage):
                    result_message = message
                    session_id_result = message.session_id
                    # Store for token usage extraction
                    self.last_result_message = message

            if result_message is None:
                raise RuntimeError("Claude SDK did not return a result message")

            if result_message.is_error:
                raise RuntimeError(f"Claude SDK reported error: {result_message.result}")

            # Handle structured output
            if schema:
                # Try structured_output first (preferred for schema requests)
                if result_message.structured_output is not None:
                    data = result_message.structured_output
                elif result_message.result:
                    # Fallback: try to parse result as JSON
                    # Strip markdown code fences if present (Claude sometimes wraps JSON in ```)
                    try:
                        stripped_result = _strip_markdown_fences(result_message.result)
                        data = json.loads(stripped_result)
                    except json.JSONDecodeError:
                        # Model returned text instead of structured JSON
                        result_text = result_message.result
                        preview = result_text[:500] + "..." if len(result_text) > 500 else result_text

                        if _is_clarification_request(result_text):
                            session_info = f" (session_id: {session_id_result})" if session_id_result else ""
                            raise RuntimeError(
                                f"Claude requested clarification instead of producing structured output{session_info}.\n\n"
                                f"This typically happens when the issue/prompt lacks sufficient detail.\n"
                                f"Consider providing more context in the issue description.\n\n"
                                f"Claude's questions:\n{preview}"
                            ) from None
                        else:
                            raise RuntimeError(
                                f"Claude SDK returned text instead of structured JSON.\n"
                                f"Expected: JSON matching the requested schema\n"
                                f"Received: {preview}"
                            ) from None
                else:
                    raise RuntimeError("Claude SDK returned no output for schema request")

                # Fix: If the model expects a wrapped "tasks" list but CLI returns a raw list, wrap it.
                if isinstance(data, list) and "tasks" in schema.model_fields:
                    data = {"tasks": data}

                try:
                    return (schema.model_validate(data), session_id_result)
                except ValidationError as e:
                    raise RuntimeError(f"Claude SDK output did not match schema: {e}") from e
            else:
                # Return raw text result
                if result_message.result:
                    return (result_message.result, session_id_result)
                elif assistant_content:
                    return ("\n".join(assistant_content), session_id_result)
                else:
                    return ("", session_id_result)

        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"Error executing Claude SDK: {e}") from e

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None,
        instructions: str | None = None,
        schema: type[BaseModel] | None = None,
    ) -> AsyncIterator[AgenticMessage]:
        """Execute prompt with full autonomous tool access using ClaudeSDKClient.

        Uses the claude-agent-sdk ClaudeSDKClient for agentic execution, which
        provides interrupt support, hooks, and session continuity.

        Args:
            prompt: The user prompt to execute.
            cwd: Working directory for Claude Code context.
            session_id: Optional session ID to resume.
            instructions: Runtime instructions for the agent. Passed via system_prompt.
            schema: Optional Pydantic model for structured output. When provided,
                the agent's final response will be constrained to match this schema.

        Yields:
            AgenticMessage for each event (thinking, tool_call, tool_result, result).
        """
        options = self._build_options(
            cwd=cwd,
            session_id=session_id,
            system_prompt=instructions,
            schema=schema,
            bypass_permissions=True,  # Agentic execution always bypasses permissions
        )

        logger.info(f"Starting agentic execution in {cwd}")

        last_tool_name: str | None = None  # Track for tool_result messages

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)
                async for message in client.receive_response():
                    _log_sdk_message(message)

                    # Skip SDK StreamEvent objects - they are progress updates
                    # that don't need to be passed to the developer agent
                    if isinstance(message, SDKStreamEvent):
                        continue

                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                yield AgenticMessage(
                                    type=AgenticMessageType.THINKING,
                                    content=block.text,
                                )
                            elif isinstance(block, ToolUseBlock):
                                # Track tool calls in history
                                self.tool_call_history.append(block)
                                last_tool_name = block.name
                                yield AgenticMessage(
                                    type=AgenticMessageType.TOOL_CALL,
                                    tool_name=block.name,
                                    tool_input=block.input,
                                    tool_call_id=block.id,
                                )
                            elif isinstance(block, ToolResultBlock):
                                content = block.content if isinstance(block.content, str) else str(block.content)
                                yield AgenticMessage(
                                    type=AgenticMessageType.TOOL_RESULT,
                                    tool_name=last_tool_name,
                                    tool_output=content,
                                    is_error=block.is_error or False,
                                )

                    elif isinstance(message, ResultMessage):
                        # Store ResultMessage for token usage extraction
                        self.last_result_message = message
                        yield AgenticMessage(
                            type=AgenticMessageType.RESULT,
                            content=message.result,
                            session_id=message.session_id,
                            is_error=message.is_error,
                        )

        except Exception as e:
            logger.error(f"Error in agentic execution: {e}")
            raise

    def clear_tool_history(self) -> None:
        self.tool_call_history = []
