# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Developer agent for agentic code execution.

This module provides the Developer agent that executes code changes using
autonomous tool-calling LLM execution rather than structured step-by-step plans.
"""
from collections.abc import AsyncIterator

from loguru import logger

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.core.state import AgentMessage, ExecutionState
from amelia.core.types import Profile, StreamEmitter
from amelia.drivers.api.events import ApiStreamEvent
from amelia.drivers.base import DriverInterface


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
    ) -> AsyncIterator[tuple[ExecutionState, ApiStreamEvent]]:
        """Execute development task agentically.

        Uses the driver's execute_agentic method to let the LLM autonomously
        decide what tools to use and when, rather than following a predefined
        step-by-step plan.

        Args:
            state: Current execution state with goal.
            profile: Execution profile with settings.

        Yields:
            Tuples of (updated_state, event) as execution progresses.

        Raises:
            ValueError: If ExecutionState has no goal set.
        """
        if not state.goal:
            raise ValueError("ExecutionState must have a goal set")

        cwd = profile.working_dir or "."

        tool_calls: list[ToolCall] = list(state.tool_calls)
        tool_results: list[ToolResult] = list(state.tool_results)
        last_tool_call_id: str | None = None

        # Build messages from state
        messages = self._build_messages(state, profile)

        async for event in self.driver.execute_agentic(
            messages=messages,
            cwd=cwd,
            session_id=state.driver_session_id,
            instructions=self._build_instructions(profile),
        ):
            # Track tool calls/results
            if event.type == "tool_use" and event.tool_name:
                call = ToolCall(
                    id=f"call-{len(tool_calls)}",
                    tool_name=event.tool_name,
                    tool_input=event.tool_input or {},
                )
                tool_calls.append(call)
                last_tool_call_id = call.id
                logger.debug(
                    "Tool call recorded",
                    tool_name=event.tool_name,
                    call_id=call.id,
                )

            elif event.type == "tool_result" and event.tool_name:
                # Use the last tool call ID for correlation, fall back to index-based ID
                result = ToolResult(
                    call_id=last_tool_call_id or f"call-{len(tool_results)}",
                    tool_name=event.tool_name,
                    output=event.tool_result or "",
                    success=True,
                )
                tool_results.append(result)
                logger.debug(
                    "Tool result recorded",
                    tool_name=event.tool_name,
                    call_id=result.call_id,
                )

            # Update state
            new_state = state.model_copy(update={
                "tool_calls": tool_calls.copy(),
                "tool_results": tool_results.copy(),
                "driver_session_id": event.session_id or state.driver_session_id,
                "agentic_status": "completed" if event.type == "result" else state.agentic_status,
                "final_response": event.result_text if event.type == "result" else state.final_response,
                "error": event.content if event.type == "error" else state.error,
            })

            yield new_state, event

    def _build_messages(
        self,
        state: ExecutionState,
        profile: Profile,
    ) -> list[AgentMessage]:
        """Build conversation messages for the driver.

        Args:
            state: Current execution state.
            profile: Execution profile.

        Returns:
            List of AgentMessage objects for the driver.
        """
        messages = []

        # System message with context
        system_prompt = self._build_system_prompt(profile, state)
        messages.append(AgentMessage(role="system", content=system_prompt))

        # User message with the goal
        user_prompt = f"Please complete the following task:\n\n{state.goal}"

        # Add review feedback if this is a review-fix iteration
        if state.last_review and not state.last_review.approved:
            feedback = "\n".join(f"- {c}" for c in state.last_review.comments)
            user_prompt += f"\n\nThe reviewer requested the following changes:\n{feedback}"

        messages.append(AgentMessage(role="user", content=user_prompt))

        return messages

    def _build_system_prompt(self, profile: Profile, state: ExecutionState) -> str:
        """Build system prompt for agentic execution.

        Args:
            profile: Execution profile.
            state: Current execution state.

        Returns:
            System prompt string.
        """
        prompt = f"""You are a skilled developer working on a codebase.
Your task is to complete the requested changes using the available tools.

Working directory: {profile.working_dir or '.'}

Available tools:
- run_shell_command: Execute shell commands (ls, cat, grep, git, npm, python, etc.)
- write_file: Create or overwrite files

Guidelines:
- Read files before modifying them to understand the existing code
- Make minimal, focused changes that address the task
- Follow existing code patterns and conventions in the codebase
- Run tests after making changes to verify they work
- Commit your changes when complete with a descriptive message
"""

        # Add plan context if available (from Architect)
        if state.plan_markdown:
            prompt += f"""

You have a detailed implementation plan to follow. Execute it using your tools.
Use your judgment to handle unexpected situations - the plan is a guide, not rigid steps.

---
IMPLEMENTATION PLAN:
---

{state.plan_markdown}
"""

        # Add design context if available (fallback if no plan)
        elif state.design:
            prompt += f"\n\nDesign Context:\n{state.design.raw_content}"

        # Add issue context if available (fallback if no plan)
        if state.issue and not state.plan_markdown:
            prompt += f"\n\nIssue: {state.issue.title}\n{state.issue.description}"

        return prompt

    def _build_instructions(self, profile: Profile) -> str | None:
        """Build runtime instructions for the agent.

        Args:
            profile: Execution profile.

        Returns:
            Instructions string or None.
        """
        return None  # Default to no extra instructions
