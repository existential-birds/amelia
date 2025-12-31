"""Developer agent for agentic code execution.

This module provides the Developer agent that executes code changes using
autonomous tool-calling LLM execution rather than structured step-by-step plans.
"""
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from loguru import logger

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.core.state import ExecutionState
from amelia.core.types import Profile, StreamEmitter, StreamEvent, StreamEventType
from amelia.drivers.base import DriverInterface


if TYPE_CHECKING:
    from amelia.drivers.api.deepagents import ApiDriver
    from amelia.drivers.cli.claude import ClaudeCliDriver


class Developer:
    """Developer agent that executes code changes agentically.

    Uses LLM with tool access to autonomously complete coding tasks.
    Replaces the structured batch/step execution model with autonomous
    tool-calling execution.

    Attributes:
        driver: LLM driver interface for agentic execution.
    """

    def __init__(
        self,
        driver: DriverInterface,
        stream_emitter: StreamEmitter | None = None,
    ):
        """Initialize the Developer agent.

        Args:
            driver: LLM driver interface for agentic execution.
            stream_emitter: Optional callback for streaming events.
        """
        self.driver = driver
        self._stream_emitter = stream_emitter

    async def run(
        self,
        state: ExecutionState,
        profile: Profile,
        workflow_id: str = "developer",
    ) -> AsyncIterator[tuple[ExecutionState, StreamEvent]]:
        """Execute development task agentically.

        Uses the driver's execute_agentic method to let the LLM autonomously
        decide what tools to use and when, rather than following a predefined
        step-by-step plan.

        The method dispatches to driver-specific handlers based on the driver type:
        - ClaudeCliDriver: Yields claude_agent_sdk.types.Message
        - ApiDriver: Yields langchain_core.messages.BaseMessage

        Args:
            state: Current execution state with goal.
            profile: Execution profile with settings.
            workflow_id: Unique workflow identifier for streaming events.

        Yields:
            Tuples of (updated_state, event) as execution progresses.

        Raises:
            ValueError: If ExecutionState has no goal set.
            TypeError: If driver type is not supported.
        """
        if not state.goal:
            raise ValueError("ExecutionState must have a goal set")

        # Import drivers for isinstance checks (runtime imports to avoid circular deps)
        from amelia.drivers.api.deepagents import ApiDriver  # noqa: PLC0415
        from amelia.drivers.cli.claude import ClaudeCliDriver  # noqa: PLC0415

        if isinstance(self.driver, ClaudeCliDriver):
            async for result in self._run_with_cli_driver(
                state, profile, workflow_id, self.driver
            ):
                yield result
        elif isinstance(self.driver, ApiDriver):
            async for result in self._run_with_api_driver(
                state, profile, workflow_id, self.driver
            ):
                yield result
        else:
            raise TypeError(f"Unsupported driver type: {type(self.driver).__name__}")

    async def _run_with_cli_driver(
        self,
        state: ExecutionState,
        profile: Profile,
        workflow_id: str,
        driver: "ClaudeCliDriver",
    ) -> AsyncIterator[tuple[ExecutionState, StreamEvent]]:
        """Execute development task using the CLI driver.

        Args:
            state: Current execution state.
            profile: Execution profile.
            workflow_id: Workflow identifier for events.
            driver: The ClaudeCliDriver instance.

        Yields:
            Tuples of (updated_state, event) as execution progresses.
        """
        from claude_agent_sdk.types import (  # noqa: PLC0415
            AssistantMessage,
            ResultMessage,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
        )

        cwd = profile.working_dir or "."
        prompt = self._build_prompt(state, profile)

        tool_calls: list[ToolCall] = list(state.tool_calls)
        tool_results: list[ToolResult] = list(state.tool_results)
        current_state = state
        session_id = state.driver_session_id

        async for message in driver.execute_agentic(
            prompt=prompt,
            cwd=cwd,
            session_id=session_id,
            instructions=self._build_instructions(profile),
        ):
            event: StreamEvent | None = None

            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        event = StreamEvent(
                            type=StreamEventType.CLAUDE_THINKING,
                            content=block.text,
                            timestamp=datetime.now(UTC),
                            agent="developer",
                            workflow_id=workflow_id,
                        )
                    elif isinstance(block, ToolUseBlock):
                        call = ToolCall(
                            id=f"call-{len(tool_calls)}",
                            tool_name=block.name,
                            tool_input=block.input if isinstance(block.input, dict) else {},
                        )
                        tool_calls.append(call)
                        logger.debug(
                            "Tool call recorded",
                            tool_name=block.name,
                            call_id=call.id,
                        )
                        event = StreamEvent(
                            type=StreamEventType.CLAUDE_TOOL_CALL,
                            content=None,
                            timestamp=datetime.now(UTC),
                            agent="developer",
                            workflow_id=workflow_id,
                            tool_name=block.name,
                            tool_input=block.input if isinstance(block.input, dict) else None,
                        )
                    elif isinstance(block, ToolResultBlock):
                        content = block.content if isinstance(block.content, str) else str(block.content)
                        result = ToolResult(
                            call_id=f"call-{len(tool_results)}",
                            tool_name="unknown",  # ToolResultBlock doesn't have name
                            output=content,
                            success=not block.is_error,
                        )
                        tool_results.append(result)
                        logger.debug(
                            "Tool result recorded",
                            call_id=result.call_id,
                        )
                        event = StreamEvent(
                            type=StreamEventType.CLAUDE_TOOL_RESULT,
                            content=content,
                            timestamp=datetime.now(UTC),
                            agent="developer",
                            workflow_id=workflow_id,
                        )

                    if event:
                        current_state = state.model_copy(update={
                            "tool_calls": tool_calls.copy(),
                            "tool_results": tool_results.copy(),
                            "driver_session_id": session_id,
                        })
                        yield current_state, event

            elif isinstance(message, ResultMessage):
                session_id = message.session_id
                is_complete = not message.is_error

                event = StreamEvent(
                    type=StreamEventType.AGENT_OUTPUT,
                    content=message.result,
                    timestamp=datetime.now(UTC),
                    agent="developer",
                    workflow_id=workflow_id,
                )

                current_state = state.model_copy(update={
                    "tool_calls": tool_calls.copy(),
                    "tool_results": tool_results.copy(),
                    "driver_session_id": session_id,
                    "agentic_status": "completed" if is_complete else "failed",
                    "final_response": message.result if is_complete else None,
                    "error": message.result if message.is_error else None,
                })
                yield current_state, event

    async def _run_with_api_driver(
        self,
        state: ExecutionState,
        profile: Profile,
        workflow_id: str,
        driver: "ApiDriver",
    ) -> AsyncIterator[tuple[ExecutionState, StreamEvent]]:
        """Execute development task using the API driver.

        Args:
            state: Current execution state.
            profile: Execution profile.
            workflow_id: Workflow identifier for events.
            driver: The ApiDriver instance.

        Yields:
            Tuples of (updated_state, event) as execution progresses.
        """
        from langchain_core.messages import AIMessage, ToolMessage  # noqa: PLC0415

        cwd = profile.working_dir or "."
        prompt = self._build_prompt(state, profile)

        # Set the cwd on the driver for agentic execution
        driver.cwd = cwd

        tool_calls: list[ToolCall] = list(state.tool_calls)
        tool_results: list[ToolResult] = list(state.tool_results)
        current_state = state
        last_message: AIMessage | None = None

        async for message in driver.execute_agentic(prompt=prompt):
            event: StreamEvent | None = None

            if isinstance(message, AIMessage):
                last_message = message
                content = message.content

                # Handle text content
                if isinstance(content, str) and content:
                    event = StreamEvent(
                        type=StreamEventType.CLAUDE_THINKING,
                        content=content,
                        timestamp=datetime.now(UTC),
                        agent="developer",
                        workflow_id=workflow_id,
                    )
                elif isinstance(content, list):
                    # Handle list of content blocks
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                event = StreamEvent(
                                    type=StreamEventType.CLAUDE_THINKING,
                                    content=block.get("text", ""),
                                    timestamp=datetime.now(UTC),
                                    agent="developer",
                                    workflow_id=workflow_id,
                                )
                            elif block.get("type") == "tool_use":
                                tool_name = block.get("name", "unknown")
                                tool_input = block.get("input", {})
                                call = ToolCall(
                                    id=f"call-{len(tool_calls)}",
                                    tool_name=tool_name,
                                    tool_input=tool_input if isinstance(tool_input, dict) else {},
                                )
                                tool_calls.append(call)
                                logger.debug(
                                    "Tool call recorded",
                                    tool_name=tool_name,
                                    call_id=call.id,
                                )
                                event = StreamEvent(
                                    type=StreamEventType.CLAUDE_TOOL_CALL,
                                    content=None,
                                    timestamp=datetime.now(UTC),
                                    agent="developer",
                                    workflow_id=workflow_id,
                                    tool_name=tool_name,
                                    tool_input=tool_input if isinstance(tool_input, dict) else None,
                                )

                # Handle tool_calls from AIMessage
                if message.tool_calls:
                    for tc in message.tool_calls:
                        call = ToolCall(
                            id=tc.get("id") or f"call-{len(tool_calls)}",
                            tool_name=tc.get("name") or "unknown",
                            tool_input=tc.get("args") or {},
                        )
                        tool_calls.append(call)
                        logger.debug(
                            "Tool call recorded",
                            tool_name=call.tool_name,
                            call_id=call.id,
                        )
                        event = StreamEvent(
                            type=StreamEventType.CLAUDE_TOOL_CALL,
                            content=None,
                            timestamp=datetime.now(UTC),
                            agent="developer",
                            workflow_id=workflow_id,
                            tool_name=call.tool_name,
                            tool_input=call.tool_input,
                        )

            elif isinstance(message, ToolMessage):
                content = message.content if isinstance(message.content, str) else str(message.content)
                result = ToolResult(
                    call_id=message.tool_call_id or f"call-{len(tool_results)}",
                    tool_name=message.name or "unknown",
                    output=content,
                    success=True,
                )
                tool_results.append(result)
                logger.debug(
                    "Tool result recorded",
                    tool_name=result.tool_name,
                    call_id=result.call_id,
                )
                event = StreamEvent(
                    type=StreamEventType.CLAUDE_TOOL_RESULT,
                    content=content,
                    timestamp=datetime.now(UTC),
                    agent="developer",
                    workflow_id=workflow_id,
                )

            if event:
                current_state = state.model_copy(update={
                    "tool_calls": tool_calls.copy(),
                    "tool_results": tool_results.copy(),
                })
                yield current_state, event

        # Mark as completed after all messages are processed
        if last_message:
            final_content = last_message.content
            if isinstance(final_content, list):
                final_content = "".join(
                    b.get("text", "") if isinstance(b, dict) else str(b)
                    for b in final_content
                )
            elif not isinstance(final_content, str):
                final_content = str(final_content)

            final_event = StreamEvent(
                type=StreamEventType.AGENT_OUTPUT,
                content=final_content,
                timestamp=datetime.now(UTC),
                agent="developer",
                workflow_id=workflow_id,
            )
            current_state = state.model_copy(update={
                "tool_calls": tool_calls.copy(),
                "tool_results": tool_results.copy(),
                "agentic_status": "completed",
                "final_response": final_content,
            })
            yield current_state, final_event

    def _build_prompt(self, state: ExecutionState, profile: Profile) -> str:
        """Build the prompt for agentic execution.

        Combines the goal, review feedback (if any), and context into a single
        prompt string for the driver.

        Args:
            state: Current execution state with goal and context.
            profile: Execution profile with settings.

        Returns:
            Complete prompt string for the driver.
        """
        parts = []

        # Context section
        parts.append(f"Working directory: {profile.working_dir or '.'}")

        # Plan context (from Architect)
        if state.plan_markdown:
            parts.append("""
You have a detailed implementation plan to follow. Execute it using your tools.
Use your judgment to handle unexpected situations - the plan is a guide, not rigid steps.

---
IMPLEMENTATION PLAN:
---
""")
            parts.append(state.plan_markdown)

        # Design context (fallback if no plan)
        elif state.design:
            parts.append(f"\nDesign Context:\n{state.design.raw_content}")

        # Issue context (fallback if no plan)
        if state.issue and not state.plan_markdown:
            parts.append(f"\nIssue: {state.issue.title}\n{state.issue.description}")

        # Main task
        parts.append(f"\n\nPlease complete the following task:\n\n{state.goal}")

        # Review feedback (if this is a review-fix iteration)
        if state.last_review and not state.last_review.approved:
            feedback = "\n".join(f"- {c}" for c in state.last_review.comments)
            parts.append(f"\n\nThe reviewer requested the following changes:\n{feedback}")

        return "\n".join(parts)

    def _build_instructions(self, profile: Profile) -> str | None:
        """Build runtime instructions for the agent.

        Args:
            profile: Execution profile.

        Returns:
            Instructions string or None.
        """
        return None  # Default to no extra instructions
