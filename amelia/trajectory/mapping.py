"""Pure mapping from amelia driver messages to ATIF trajectory models.

Converts an ``AgenticMessage`` stream into harbor ATIF ``Step`` objects and
``DriverUsage`` into ATIF ``Metrics``. Content passes through verbatim — no
truncation or summarization, ever.
"""
from harbor.models.trajectories import (
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
)

from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage


def map_messages(messages: list[AgenticMessage], start_id: int) -> list[Step]:
    """Map an AgenticMessage stream to ATIF steps with sequential ids.

    Args:
        messages: Driver messages in stream order.
        start_id: step_id assigned to the first produced step; subsequent
            steps increment by one.

    Returns:
        ATIF steps, all with ``source="agent"``. A TOOL_CALL opens a step;
        a TOOL_RESULT with matching ``tool_call_id`` attaches to that step's
        observation. THINKING maps to ``reasoning_content``; RESULT maps to
        ``message`` (``extra["is_error"]`` set when the result is an error).
        USAGE messages are skipped — metrics are handled by the recorder.

    Raises:
        ValueError: If a TOOL_RESULT has no matching open TOOL_CALL step.
    """
    steps: list[Step] = []
    open_tool_steps: dict[str, Step] = {}

    for msg in messages:
        if msg.type == AgenticMessageType.USAGE:
            continue

        if msg.type == AgenticMessageType.TOOL_CALL:
            call_id = msg.tool_call_id or f"call-{start_id + len(steps)}"
            step = Step(
                step_id=start_id + len(steps),
                source="agent",
                message="",
                model_name=msg.model,
                tool_calls=[
                    ToolCall(
                        tool_call_id=call_id,
                        function_name=msg.tool_name or "unknown",
                        arguments=msg.tool_input or {},
                    )
                ],
            )
            steps.append(step)
            open_tool_steps[call_id] = step

        elif msg.type == AgenticMessageType.TOOL_RESULT:
            step = open_tool_steps.get(msg.tool_call_id or "")
            if step is None:
                raise ValueError(
                    f"TOOL_RESULT with tool_call_id={msg.tool_call_id!r} has no "
                    "matching TOOL_CALL in this message stream"
                )
            result = ObservationResult(
                source_call_id=msg.tool_call_id,
                content=msg.tool_output,
                extra={"is_error": True} if msg.is_error else None,
            )
            if step.observation is None:
                step.observation = Observation(results=[result])
            else:
                step.observation.results.append(result)

        elif msg.type == AgenticMessageType.THINKING:
            steps.append(
                Step(
                    step_id=start_id + len(steps),
                    source="agent",
                    message="",
                    model_name=msg.model,
                    reasoning_content=msg.content,
                )
            )

        else:  # AgenticMessageType.RESULT
            steps.append(
                Step(
                    step_id=start_id + len(steps),
                    source="agent",
                    message=msg.content or msg.tool_output or "",
                    model_name=msg.model,
                    extra={"is_error": True} if msg.is_error else None,
                )
            )

    return steps


def usage_to_metrics(u: DriverUsage, cost: float | None) -> Metrics:
    """Map driver usage to ATIF metrics, fields 1:1.

    Args:
        u: Accumulated usage reported by the driver.
        cost: Resolved cost in USD; falls back to ``u.cost_usd`` when None.

    Returns:
        ATIF metrics with token counts and cost.
    """
    return Metrics(
        prompt_tokens=u.input_tokens,
        completion_tokens=u.output_tokens,
        cached_tokens=u.cache_read_tokens,
        cost_usd=cost if cost is not None else u.cost_usd,
    )
