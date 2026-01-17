"""Developer agent for agentic code execution.

This module provides the Developer agent that executes code changes using
autonomous tool-calling LLM execution rather than structured step-by-step plans.
"""
from collections.abc import AsyncIterator

from loguru import logger

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.core.state import ExecutionState
from amelia.core.types import Profile
from amelia.drivers.base import AgenticMessageType, DriverInterface
from amelia.server.models.events import WorkflowEvent


class Developer:
    """Developer agent that executes code changes agentically.

    Uses LLM with tool access to autonomously complete coding tasks.
    Replaces the structured batch/step execution model with autonomous
    tool-calling execution.

    Attributes:
        driver: LLM driver interface for agentic execution.

    """

    def __init__(self, driver: DriverInterface):
        self.driver = driver

    async def run(
        self,
        state: ExecutionState,
        profile: Profile,
        workflow_id: str = "developer",
    ) -> AsyncIterator[tuple[ExecutionState, WorkflowEvent]]:
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

        Yields:
            Tuples of (updated_state, event) as execution progresses.

        Raises:
            ValueError: If ExecutionState has no goal set.

        """
        if not state.goal:
            raise ValueError("ExecutionState must have a goal set")

        cwd = profile.working_dir or "."
        prompt = self._build_prompt(state)

        tool_calls: list[ToolCall] = list(state.tool_calls)
        tool_results: list[ToolResult] = list(state.tool_results)
        current_state = state
        session_id = state.driver_session_id

        async for message in self.driver.execute_agentic(
            prompt=prompt,
            cwd=cwd,
            session_id=session_id,
            instructions=None,
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
                # Update session_id from result message
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
                continue  # Result is the final message

            if event:
                current_state = state.model_copy(update={
                    "tool_calls": tool_calls,
                    "tool_results": tool_results,
                    "driver_session_id": session_id,
                })
                yield current_state, event

    def _build_prompt(self, state: ExecutionState) -> str:
        """Build prompt combining goal, review feedback, and context.

        For multi-task execution, extracts only the current task section
        from the full plan and includes a progress breadcrumb.
        """
        parts = []

        if not state.plan_markdown:
            raise ValueError(
                "Developer requires plan_markdown. Architect must run first."
            )

        parts.append("""
You have a detailed implementation plan to follow. Execute it using your tools.
Use your judgment to handle unexpected situations - the plan is a guide, not rigid steps.

## CRITICAL: No Summary Files

DO NOT create any of the following files:
- TASK_*_COMPLETION.md, TASK_*_INDEX.md, TASK_*_SUMMARY.md
- IMPLEMENTATION_*.md, EXECUTION_*.md
- CODE_REVIEW*.md, FINAL_SUMMARY.md
- Any markdown file that summarizes progress, completion status, or documents work done

These files waste tokens and provide no value. The code changes ARE the deliverable.
Only create files explicitly listed in the plan's "Create:" directives.

---
IMPLEMENTATION PLAN:
---
""")

        from amelia.pipelines.implementation.utils import extract_task_section  # noqa: PLC0415

        total = state.total_tasks or 1
        current = state.current_task_index

        if total == 1:
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

        # Main task
        parts.append(f"\n\nPlease complete the following task:\n\n{state.goal}")

        # Review feedback (if this is a review-fix iteration)
        if state.last_review and not state.last_review.approved:
            feedback = "\n".join(f"- {c}" for c in state.last_review.comments)
            parts.append(f"\n\nThe reviewer requested the following changes:\n{feedback}")

        return "\n".join(parts)

