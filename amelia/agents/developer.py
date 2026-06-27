"""Developer agent for agentic code execution.

This module provides the Developer agent that executes code changes using
autonomous tool-calling LLM execution rather than structured step-by-step plans.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from amelia.agents._driver_init import init_agent_driver
from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.agents.tool_profiles import resolve_agent_tools
from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.core.types import AgentConfig, Profile, collect_rejected_comments
from amelia.drivers.base import AgenticMessageType
from amelia.pipelines.implementation.context_compaction import (
    DEFAULT_COMPACTION_THRESHOLD,
    DEFAULT_KEEP_LAST_N_TURNS,
    compact_implementation_context,
    should_compact_context,
)
from amelia.server.models.events import WorkflowEvent
from amelia.tools.registry import ToolContext


if TYPE_CHECKING:
    from amelia.pipelines.implementation.state import ImplementationState
    from amelia.sandbox.provider import SandboxProvider


def _parse_compaction_threshold() -> float:
    """Parse and validate the context compaction threshold from env config.

    Reads ``AMELIA_CONTEXT_COMPACTION_THRESHOLD`` (default
    :data:`DEFAULT_COMPACTION_THRESHOLD`). The value must be a float in the
    interval ``(0, 1]`` — values outside that range produce nonsensical
    compaction behavior.

    Raises:
        ValueError: If the env value is non-numeric or out of range.

    Returns:
        Validated compaction threshold.
    """
    raw = os.environ.get(
        "AMELIA_CONTEXT_COMPACTION_THRESHOLD",
        str(DEFAULT_COMPACTION_THRESHOLD),
    )
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"AMELIA_CONTEXT_COMPACTION_THRESHOLD must be a number in (0, 1], "
            f"got {raw!r}"
        ) from exc
    if not 0 < value <= 1:
        raise ValueError(
            f"AMELIA_CONTEXT_COMPACTION_THRESHOLD must be in (0, 1], got {value}"
        )
    return value


def _parse_keep_last_turns() -> int:
    """Parse and validate the keep-last-turns config from env.

    Reads ``AMELIA_CONTEXT_KEEP_LAST_TURNS`` (default
    :data:`DEFAULT_KEEP_LAST_N_TURNS`). Must be an integer >= 1.

    Raises:
        ValueError: If the env value is non-numeric or < 1.

    Returns:
        Validated keep-last-turns count.
    """
    raw = os.environ.get(
        "AMELIA_CONTEXT_KEEP_LAST_TURNS",
        str(DEFAULT_KEEP_LAST_N_TURNS),
    )
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"AMELIA_CONTEXT_KEEP_LAST_TURNS must be an integer >= 1, got {raw!r}"
        ) from exc
    if value < 1:
        raise ValueError(
            f"AMELIA_CONTEXT_KEEP_LAST_TURNS must be >= 1, got {value}"
        )
    return value


class Developer:
    """Developer agent that executes code changes agentically.

    Uses LLM with tool access to autonomously complete coding tasks.
    Replaces the structured batch/step execution model with autonomous
    tool-calling execution.

    Attributes:
        driver: LLM driver interface for agentic execution.

    """

    # Single source of truth for system prompt is PROMPT_DEFAULTS
    SYSTEM_PROMPT = PROMPT_DEFAULTS["developer.system"].content

    def __init__(
        self,
        config: AgentConfig,
        prompts: dict[str, str] | None = None,
        sandbox_provider: SandboxProvider | None = None,
        tool_context: ToolContext | None = None,
    ):
        """Initialize the Developer agent.

        Args:
            config: Agent configuration with driver, model, and options.
            prompts: Optional dict mapping prompt IDs to custom content.
                Supports key: "developer.system".
            sandbox_provider: Optional shared sandbox provider for sandbox reuse.
            tool_context: Optional runtime context for factory tools. When set,
                the agent restricts its tools to the "developer" profile via
                :func:`resolve_agent_tools`; when ``None`` (default), no
                restriction is applied (backward compatible).
        """
        _init = init_agent_driver(
            config,
            prompts=prompts,
            sandbox_provider=sandbox_provider,
        )
        self.driver = _init.driver
        self.options = _init.options
        self._prompts = _init.prompts
        self._tool_context = tool_context

    @property
    def system_prompt(self) -> str:
        """Get the system prompt for developer execution."""
        return self._prompts.get("developer.system", self.SYSTEM_PROMPT)

    async def run(
        self,
        state: ImplementationState,
        profile: Profile,
        workflow_id: uuid.UUID,
        *,
        prompt_builder: Callable[[ImplementationState], str] | None = None,
        instructions: str | None = None,
    ) -> AsyncIterator[tuple[ImplementationState, WorkflowEvent]]:
        """Execute development task agentically.

        Uses the driver's execute_agentic method to let the LLM autonomously
        decide what tools to use and when, rather than following a predefined
        step-by-step plan.

        All drivers now yield the unified AgenticMessage type, so this method
        handles all driver types uniformly.

        Args:
            state: Current execution state with goal.
            profile: Execution profile with settings.
            workflow_id: Unique workflow identifier for streaming events.
            prompt_builder: Optional callable that builds the user prompt instead
                of :meth:`_build_prompt` (e.g. review-fix flows without a plan).
            instructions: Optional system instructions override for the driver;
                defaults to :attr:`system_prompt`.

        Yields:
            Tuples of (updated_state, event) as execution progresses.

        Raises:
            ValueError: If ImplementationState has no goal set.

        """
        if not state.goal:
            raise ValueError("ImplementationState must have a goal set")

        compaction_threshold = _parse_compaction_threshold()
        keep_last_turns = _parse_keep_last_turns()

        cwd = profile.repo_root
        prompt = (
            prompt_builder(state) if prompt_builder is not None else self._build_prompt(state)
        )
        agent_instructions = instructions if instructions is not None else self.system_prompt

        # Resolve the developer's tool profile when a ToolContext is available.
        # Without one, pass no restriction (backward compatible).
        agentic_kwargs: dict[str, Any] = {}
        if self._tool_context is not None:
            agentic_kwargs["allowed_tools"] = [
                t.name for t in resolve_agent_tools("developer", self._tool_context)
            ]
            agentic_kwargs["tool_context"] = self._tool_context

        tool_calls: list[ToolCall] = []
        tool_results: list[ToolResult] = []
        current_state = state
        session_id = state.driver_session_id

        async for message in self.driver.execute_agentic(
            prompt=prompt,
            cwd=cwd,
            session_id=session_id,
            instructions=agent_instructions,
            **agentic_kwargs,
        ):
            event: WorkflowEvent | None = None

            if message.type == AgenticMessageType.THINKING:
                event = message.to_workflow_event(workflow_id=workflow_id, agent="developer")

            elif message.type == AgenticMessageType.TOOL_CALL:
                call = ToolCall(
                    id=message.tool_call_id or f"call-{len(tool_calls)}",
                    tool_name=message.tool_name or "unknown",
                    tool_input=message.tool_input or {},
                )
                tool_calls.append(call)
                logger.debug(
                    "Tool call recorded",
                    tool_name=message.tool_name,
                    call_id=call.id,
                )
                event = message.to_workflow_event(workflow_id=workflow_id, agent="developer")

            elif message.type == AgenticMessageType.TOOL_RESULT:
                result = ToolResult(
                    call_id=message.tool_call_id or f"call-{len(tool_results)}",
                    tool_name=message.tool_name or "unknown",
                    output=message.tool_output or "",
                    success=not message.is_error,
                )
                tool_results.append(result)
                logger.debug(
                    "Tool result recorded",
                    call_id=result.call_id,
                )
                event = message.to_workflow_event(workflow_id=workflow_id, agent="developer")

            elif message.type == AgenticMessageType.RESULT:
                if message.session_id:
                    session_id = message.session_id

                is_complete = not message.is_error
                event = message.to_workflow_event(workflow_id=workflow_id, agent="developer")

                current_state = state.model_copy(update={
                    "tool_calls": tool_calls,
                    "tool_results": tool_results,
                    "driver_session_id": session_id,
                    "agentic_status": "completed" if is_complete else "failed",
                    "final_response": message.content if is_complete else None,
                    "error": message.content if message.is_error else None,
                })
                yield current_state, event

                usage = self.driver.get_usage()
                if should_compact_context(
                    state.model_copy(update={
                        "tool_calls": [*state.tool_calls, *tool_calls],
                        "tool_results": [*state.tool_results, *tool_results],
                    }),
                    context_utilization=usage.context_utilization if usage else None,
                    threshold=compaction_threshold,
                    keep_last_n_turns=keep_last_turns,
                ):
                    current_state, compaction_event = compact_implementation_context(
                        state.model_copy(update={
                            "tool_calls": [*state.tool_calls, *tool_calls],
                            "tool_results": [*state.tool_results, *tool_results],
                            "driver_session_id": session_id,
                            "agentic_status": "completed" if is_complete else "failed",
                            "final_response": message.content if is_complete else None,
                            "error": message.content if message.is_error else None,
                        }),
                        keep_last_n_turns=keep_last_turns,
                        reason=(
                            f"context utilization {usage.context_utilization:.1%} "
                            f"crossed threshold {compaction_threshold:.1%}"
                            if usage and usage.context_utilization is not None
                            else "context threshold crossed"
                        ),
                    )
                    if compaction_event is not None:
                        yield current_state, compaction_event
                continue  # Result is the final message

            if event:
                current_state = state.model_copy(update={
                    "tool_calls": tool_calls,
                    "tool_results": tool_results,
                    "driver_session_id": session_id,
                })
                yield current_state, event

    def _build_prompt(self, state: ImplementationState) -> str:
        """Build prompt combining goal, review feedback, and context.

        For multi-task execution, extracts only the current task section
        from the full plan and includes a progress breadcrumb.
        """
        parts = []

        if not state.plan_markdown:
            raise ValueError(
                "Developer requires plan_markdown. Architect must run first."
            )

        from amelia.pipelines.implementation.utils import extract_task_section  # noqa: PLC0415

        total = state.total_tasks
        current = state.current_task_index

        # The static "no summary files" guidance and the plan-as-guide framing now
        # live in the developer.system prompt (sent once per session) instead of
        # being re-sent in every per-task user message — see issue #639.
        if total == 1:
            parts.append("Executing Task 1 of 1:\n\n")
            parts.append(state.plan_markdown)
        else:
            task_section = extract_task_section(state.plan_markdown, current)
            task_num = current + 1
            if current > 0:
                parts.append(
                    f"Tasks 1-{current} of {total} completed. "
                    f"Now executing Task {task_num}:\n\n"
                )
            else:
                parts.append(f"Executing Task 1 of {total}:\n\n")
            parts.append(task_section)
            # No standalone goal append: extract_task_section already includes the
            # plan header (which carries the **Goal:** line state.goal was derived
            # from), so re-appending it would duplicate context every task.

        rejected_comments = collect_rejected_comments(state.last_reviews)
        if rejected_comments:
            feedback = "\n".join(f"- {c}" for c in rejected_comments)
            parts.append(f"\n\nThe reviewer requested the following changes:\n{feedback}")

        return "\n".join(parts)
