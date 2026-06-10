"""Project ATIF trajectories into dashboard wire models.

The trajectory file keeps full fidelity; these projections produce the
``WorkflowEvent`` history and ``TokenSummary`` the dashboard already consumes.
Display strings are truncated via the emitter's ``_truncate_nested`` policy —
truncation here is presentation only and never touches the file.
"""
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from harbor.models.trajectories import ContentPart, Step, Trajectory

from amelia.server.models.events import EventLevel, EventType, WorkflowEvent
from amelia.server.models.tokens import TokenSummary, TokenUsage
from amelia.server.orchestrator.event_emitter import _truncate_nested


def _text(value: str | list[ContentPart] | None) -> str:
    """Flatten a harbor message/content value to plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return "\n".join(part.text for part in value if part.text)


def _step_timestamp(step: Step, fallback: datetime) -> datetime:
    """Parse the step's ISO timestamp, falling back when absent or invalid."""
    if step.timestamp is None:
        return fallback
    try:
        return datetime.fromisoformat(step.timestamp)
    except ValueError:
        return fallback


def _subagent_ref_ids(step: Step) -> list[str]:
    """Trajectory ids of embedded subagents referenced by a step's observation."""
    if step.observation is None:
        return []
    return [
        ref.trajectory_id
        for result in step.observation.results
        for ref in result.subagent_trajectory_ref or []
        if ref.trajectory_id is not None
    ]


def _make_event(
    *,
    workflow_id: uuid.UUID,
    agent: str,
    event_type: EventType,
    message: str,
    timestamp: datetime,
    tool_name: str | None = None,
    tool_input: dict[str, Any] | None = None,
    is_error: bool = False,
    model: str | None = None,
) -> WorkflowEvent:
    """Build a trace-level event in the same shape the live stream emits."""
    return WorkflowEvent(
        id=uuid4(),
        workflow_id=workflow_id,
        sequence=0,  # assigned by trajectory_to_events once flattening is done
        timestamp=timestamp,
        agent=agent,
        event_type=event_type,
        level=EventLevel.DEBUG,
        message=_truncate_nested(message),
        tool_name=tool_name,
        tool_input=tool_input,
        is_error=is_error,
        model=model,
    )


def _step_to_events(
    step: Step, agent: str, workflow_id: uuid.UUID, fallback_ts: datetime
) -> list[WorkflowEvent]:
    """Project one agent-source step into trace events (system/user are skipped)."""
    if step.source != "agent":
        return []
    timestamp = _step_timestamp(step, fallback_ts)
    events: list[WorkflowEvent] = []

    if step.reasoning_content:
        events.append(
            _make_event(
                workflow_id=workflow_id,
                agent=agent,
                event_type=EventType.CLAUDE_THINKING,
                message=step.reasoning_content,
                timestamp=timestamp,
                model=step.model_name,
            )
        )

    if step.tool_calls:
        for call in step.tool_calls:
            events.append(
                _make_event(
                    workflow_id=workflow_id,
                    agent=agent,
                    event_type=EventType.CLAUDE_TOOL_CALL,
                    message=f"Calling {call.function_name}",
                    timestamp=timestamp,
                    tool_name=call.function_name,
                    tool_input=_truncate_nested(call.arguments),
                    model=step.model_name,
                )
            )
        names_by_call_id = {c.tool_call_id: c.function_name for c in step.tool_calls}
        for result in step.observation.results if step.observation else []:
            tool_name = names_by_call_id.get(result.source_call_id or "")
            is_error = bool(result.extra and result.extra.get("is_error"))
            content = _text(result.content)
            if not content:
                verb = "failed" if is_error else "completed"
                content = f"Tool {tool_name or 'unknown'} {verb}"
            events.append(
                _make_event(
                    workflow_id=workflow_id,
                    agent=agent,
                    event_type=EventType.CLAUDE_TOOL_RESULT,
                    message=content,
                    timestamp=timestamp,
                    tool_name=tool_name,
                    is_error=is_error,
                    model=step.model_name,
                )
            )
    elif _text(step.message):
        events.append(
            _make_event(
                workflow_id=workflow_id,
                agent=agent,
                event_type=EventType.AGENT_OUTPUT,
                message=_text(step.message),
                timestamp=timestamp,
                is_error=bool(step.extra and step.extra.get("is_error")),
                model=step.model_name,
            )
        )

    return events


def trajectory_to_events(traj: Trajectory, workflow_id: uuid.UUID) -> list[WorkflowEvent]:
    """Project a workflow trajectory into the dashboard's event history.

    Parent and subagent steps are flattened in invocation order: each parent
    step that references an embedded subagent expands into that subagent's
    steps (system/user prompt steps skipped, reasoning to ``CLAUDE_THINKING``,
    tool calls to ``CLAUDE_TOOL_CALL``/``CLAUDE_TOOL_RESULT``, agent messages
    to ``AGENT_OUTPUT``). The agent name comes from the owning subagent
    trajectory.

    Args:
        traj: Trajectory to project (finalized file or live snapshot).
        workflow_id: Workflow the projected events belong to.

    Returns:
        Events with monotonically increasing sequence numbers from 1.
    """
    subagents = {
        sub.trajectory_id: sub
        for sub in traj.subagent_trajectories or []
        if sub.trajectory_id is not None
    }
    fallback_ts = datetime.now(UTC)
    events: list[WorkflowEvent] = []
    for parent_step in traj.steps:
        referenced = [
            subagents[ref_id]
            for ref_id in _subagent_ref_ids(parent_step)
            if ref_id in subagents
        ]
        if referenced:
            for sub in referenced:
                for step in sub.steps:
                    events.extend(
                        _step_to_events(step, sub.agent.name, workflow_id, fallback_ts)
                    )
        else:
            events.extend(
                _step_to_events(parent_step, traj.agent.name, workflow_id, fallback_ts)
            )
    for sequence, event in enumerate(events, start=1):
        event.sequence = sequence
    return events


def trajectory_to_token_summary(traj: Trajectory) -> TokenSummary:
    """Aggregate subagent final metrics into the dashboard token summary.

    Args:
        traj: Trajectory whose subagent ``final_metrics`` to aggregate.
        Subagents without final metrics (still-open invocations) are skipped.

    Returns:
        Token summary with one breakdown entry per metered subagent;
        an all-zero summary when no subagent has metrics.
    """
    try:
        workflow_id = uuid.UUID(traj.session_id) if traj.session_id else uuid4()
    except ValueError:
        workflow_id = uuid4()
    now = datetime.now(UTC)
    usages = [
        TokenUsage(
            workflow_id=workflow_id,
            agent=sub.agent.name,
            model=sub.agent.model_name or "unknown",
            input_tokens=sub.final_metrics.total_prompt_tokens or 0,
            output_tokens=sub.final_metrics.total_completion_tokens or 0,
            cache_read_tokens=sub.final_metrics.total_cached_tokens or 0,
            cost_usd=sub.final_metrics.total_cost_usd or 0.0,
            num_turns=max(sub.final_metrics.total_steps or 1, 1),
            timestamp=now,
        )
        for sub in traj.subagent_trajectories or []
        if sub.final_metrics is not None
    ]
    return TokenSummary.from_usages(usages) or TokenSummary()
