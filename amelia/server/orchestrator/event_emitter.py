"""Stream event emission for the orchestrator.

The module-level functions are pure mappings over stream chunks and node
output. ``StreamEventEmitter`` owns the stateful emission seam: per-workflow
in-memory sequencing plus broadcast over the event bus. The event stream is
transient — nothing is persisted. Keeping all of this here lets the emission
seam be tested in isolation from the service.
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from loguru import logger

from amelia.pipelines.implementation.utils import extract_task_title
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.trajectory.truncation import truncate_nested


STAGE_NODES: frozenset[str] = frozenset({
    "architect_node",
    "plan_validator_node",
    "human_approval_node",
    "developer_node",
    "reviewer_node",
    "evaluation_node",
})


def summarize_stage_output(output: dict[str, Any] | None) -> dict[str, Any] | None:
    """Summarize node output for STAGE_COMPLETED events.

    Replaces large lists (tool_calls, tool_results) with counts and truncates
    long strings (including in nested structures) to keep event payloads on
    the bus small.

    Args:
        output: Raw node output dictionary.

    Returns:
        A summarized copy of the output, or None if input is None.
    """
    if output is None:
        return None

    result: dict[str, Any] = {}
    for key, value in output.items():
        if key in ("tool_calls", "tool_results") and isinstance(value, list):
            result[f"{key}_count"] = len(value)
        else:
            result[key] = truncate_nested(value)
    return result


def is_interrupt_chunk(chunk: tuple[str, Any] | dict[str, Any]) -> bool:
    """Check if a stream chunk represents an interrupt.

    Works with both combined mode (tuple) and single mode (dict).

    Args:
        chunk: Stream chunk from astream().

    Returns:
        True if this chunk contains an interrupt signal.
    """
    if isinstance(chunk, tuple):
        mode, data = chunk
        if mode == "updates" and isinstance(data, dict):
            return "__interrupt__" in data
        return False
    return "__interrupt__" in chunk


class StreamEventEmitter:
    """Owns workflow event emission and per-workflow sequencing.

    Assigns a monotonically increasing in-memory sequence number per workflow
    (starting at 1) and broadcasts each event over the event bus. The stream
    is transient — events are never persisted. Also maps LangGraph stream
    chunks to the events they imply.
    """

    def __init__(self, event_bus: EventBus) -> None:
        """Initialize the emitter.

        Args:
            event_bus: Event bus for broadcasting workflow events.
        """
        self._event_bus = event_bus
        # workflow_id -> next sequence
        self._sequence_counters: dict[uuid.UUID, int] = {}

    def forget(self, workflow_id: uuid.UUID) -> None:
        """Drop per-workflow sequence state after a workflow task completes.

        Args:
            workflow_id: The workflow whose sequence state should be purged.
        """
        self._sequence_counters.pop(workflow_id, None)

    async def emit(
        self,
        workflow_id: uuid.UUID,
        event_type: EventType,
        message: str,
        agent: str = "system",
        data: dict[str, object] | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> WorkflowEvent:
        """Emit a workflow event.

        Creates an event with a monotonically increasing in-memory sequence
        number (starting at 1 per workflow) and broadcasts it via event bus.

        Args:
            workflow_id: The workflow this event belongs to.
            event_type: Type of event.
            message: Human-readable message.
            agent: Source agent (default: "system").
            data: Optional structured payload.
            correlation_id: Optional ID for tracing related events.

        Returns:
            The emitted WorkflowEvent.
        """
        # Synchronous read-modify-write: atomic under asyncio's single thread.
        sequence = self._sequence_counters.get(workflow_id, 1)
        self._sequence_counters[workflow_id] = sequence + 1

        event = WorkflowEvent(
            id=uuid4(),
            workflow_id=workflow_id,
            sequence=sequence,
            timestamp=datetime.now(UTC),
            agent=agent,
            event_type=event_type,
            message=message,
            data=data,
            correlation_id=correlation_id,
        )

        self._event_bus.emit(event)

        logger.debug(
            "Event emitted",
            workflow_id=workflow_id,
            event_type=event_type.value,
            sequence=sequence,
        )

        return event

    async def handle_stream_chunk(
        self,
        workflow_id: uuid.UUID,
        chunk: dict[str, Any],
    ) -> None:
        """Handle an updates chunk from astream(stream_mode=['updates', 'tasks']).

        With combined stream mode, updates chunks map node names to their
        state updates. We emit STAGE_COMPLETED after each node that's in
        STAGE_NODES.

        Note: STAGE_STARTED events are emitted by handle_tasks_event when
        task events arrive from the tasks stream mode.

        Args:
            workflow_id: The workflow this chunk belongs to.
            chunk: Dict mapping node names to state updates.
        """
        for node_name, output in chunk.items():
            if node_name in STAGE_NODES:
                # Some nodes (e.g. human_approval_node) produce None output
                if output is None:
                    await self.emit(
                        workflow_id,
                        EventType.STAGE_COMPLETED,
                        f"Completed {node_name}",
                        agent=node_name.removesuffix("_node"),
                        data={"stage": node_name},
                    )
                    continue

                # output is always a dict here (node state update from LangGraph)
                summarized = summarize_stage_output(output)
                assert summarized is not None

                await self._emit_agent_messages(workflow_id, node_name, summarized)

                await self.emit(
                    workflow_id,
                    EventType.STAGE_COMPLETED,
                    f"Completed {node_name}",
                    agent=node_name.removesuffix("_node"),
                    data={"stage": node_name, "output": summarized},
                )

            if node_name == "next_task_node":
                total_tasks = output.get("total_tasks")
                if total_tasks is not None:
                    # The output contains the NEW index, so completed task is index - 1
                    new_index = output.get("current_task_index", 0)
                    completed_index = new_index - 1 if new_index > 0 else 0

                    await self.emit(
                        workflow_id,
                        EventType.TASK_COMPLETED,
                        f"Completed Task {completed_index + 1}/{total_tasks}",
                        agent="system",
                        data={
                            "task_index": completed_index,
                            "total_tasks": total_tasks,
                        },
                    )

    async def handle_tasks_event(
        self,
        workflow_id: uuid.UUID,
        task_data: dict[str, Any],
    ) -> None:
        """Handle a task event from stream_mode='tasks'.

        LangGraph emits two types of task events:
        - Task START: {id, name, input, triggers} - when node begins
        - Task RESULT: {id, name, error, result, interrupts} - when node completes

        We only process START events for STAGE_STARTED. Result events are
        ignored since STAGE_COMPLETED is handled via "updates" mode.

        Args:
            workflow_id: The workflow this task belongs to.
            task_data: Task event data from LangGraph.
        """
        if "input" not in task_data:
            return

        node_name = task_data.get("name", "")
        if node_name in STAGE_NODES:
            await self.emit(
                workflow_id,
                EventType.STAGE_STARTED,
                f"Starting {node_name}",
                agent=node_name.removesuffix("_node"),
                data={"stage": node_name},
            )

        if node_name == "developer_node":
            input_state = task_data.get("input")
            # input_state is an ImplementationState Pydantic model from LangGraph.
            # Access attributes directly, not via .get() which doesn't exist on Pydantic models.
            if input_state is not None and getattr(input_state, "total_tasks", None) is not None:
                total_tasks = input_state.total_tasks
                task_index = input_state.current_task_index
                plan_markdown = input_state.plan_markdown or ""
                task_title = extract_task_title(plan_markdown, task_index) or "Unknown"

                await self.emit(
                    workflow_id,
                    EventType.TASK_STARTED,
                    f"Starting Task {task_index + 1}/{total_tasks}: {task_title}",
                    agent="developer",
                    data={
                        "task_index": task_index,
                        "total_tasks": total_tasks,
                        "task_title": task_title,
                    },
                )

    async def handle_combined_stream_chunk(
        self,
        workflow_id: uuid.UUID,
        chunk: tuple[str, Any],
    ) -> None:
        """Handle a chunk from stream_mode=['updates', 'tasks'].

        Combined stream mode emits tuples of (mode, data). We route each
        to the appropriate handler.

        Args:
            workflow_id: The workflow this chunk belongs to.
            chunk: Tuple of (mode_name, data).
        """
        mode, data = chunk
        if mode == "tasks":
            await self.handle_tasks_event(workflow_id, data)
        elif mode == "updates":
            # Interrupts handled by caller via is_interrupt_chunk check
            if "__interrupt__" in data:
                return
            await self.handle_stream_chunk(workflow_id, data)

    async def _emit_agent_messages(
        self,
        workflow_id: uuid.UUID,
        node_name: str,
        output: dict[str, Any],
    ) -> None:
        """Emit detailed agent messages based on node output.

        Args:
            workflow_id: The workflow ID.
            node_name: Name of the node that produced this output.
            output: State updates from the node.
        """
        if node_name == "architect_node":
            await self._emit_architect_messages(workflow_id, output)
        elif node_name == "plan_validator_node":
            await self._emit_validator_messages(workflow_id, output)
        elif node_name == "developer_node":
            await self._emit_developer_messages(workflow_id, output)
        elif node_name == "reviewer_node":
            await self._emit_reviewer_messages(workflow_id, output)
        elif node_name == "evaluation_node":
            await self._emit_evaluator_messages(workflow_id, output)

    async def _emit_architect_messages(
        self,
        workflow_id: uuid.UUID,
        output: dict[str, Any],
    ) -> None:
        """Emit messages for architect node output.

        Args:
            workflow_id: The workflow ID.
            output: State updates from the architect node.
        """
        goal = output.get("goal")
        plan_markdown = output.get("plan_markdown")

        if goal:
            await self.emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                f"Goal: {goal}",
                agent="architect",
                data={"goal": goal, "has_plan": plan_markdown is not None},
            )

    async def _emit_validator_messages(
        self,
        workflow_id: uuid.UUID,
        output: dict[str, Any],
    ) -> None:
        """Emit messages for plan validator node output.

        Args:
            workflow_id: The workflow ID.
            output: State updates from the validator node.
        """
        goal = output.get("goal")
        key_files = output.get("key_files", [])

        if goal:
            await self.emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                f"Plan validated: {goal}",
                agent="plan_validator",
                data={"goal": goal, "key_files_count": len(key_files)},
            )

    async def _emit_developer_messages(
        self,
        workflow_id: uuid.UUID,
        output: dict[str, Any],
    ) -> None:
        """Emit messages for developer node output.

        Args:
            workflow_id: The workflow ID.
            output: State updates from the developer node.
        """
        status = output.get("agentic_status")
        final_response = output.get("final_response")

        if status == "completed" and final_response:
            await self.emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                "Development complete",
                agent="developer",
                data={"status": status},
            )
        elif status == "failed":
            error = output.get("error", "Unknown error")
            await self.emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                f"Development failed: {error}",
                agent="developer",
                data={"status": status, "error": error},
            )

    async def _emit_reviewer_messages(
        self,
        workflow_id: uuid.UUID,
        output: dict[str, Any],
    ) -> None:
        """Emit messages for reviewer node output.

        Args:
            workflow_id: The workflow ID.
            output: State updates from the reviewer node.
        """
        last_reviews = output.get("last_reviews")
        if not last_reviews:
            return

        for review in last_reviews:
            approved = review.approved
            severity = review.severity
            issue_count = len(review.comments) if review.comments else 0
            persona = review.reviewer_persona or "reviewer"

            await self.emit(
                workflow_id,
                EventType.AGENT_MESSAGE,
                f"Review ({persona}) {'approved' if approved else 'requested changes'} "
                f"({severity} severity, {issue_count} issues)",
                agent="reviewer",
                data={
                    "approved": approved,
                    "severity": severity,
                    "issue_count": issue_count,
                    "reviewer_persona": persona,
                },
            )

    async def _emit_evaluator_messages(
        self,
        workflow_id: uuid.UUID,
        output: dict[str, Any],
    ) -> None:
        """Emit messages for evaluator node output.

        Args:
            workflow_id: The workflow ID.
            output: State updates from the evaluator node.
        """
        evaluation_result = output.get("evaluation_result")
        if not evaluation_result:
            return

        # Node returns EvaluationResult Pydantic model directly
        to_implement = len(evaluation_result.items_to_implement)
        rejected = len(evaluation_result.items_rejected)
        deferred = len(evaluation_result.items_deferred)
        clarify = len(evaluation_result.items_needing_clarification)

        summary_parts = []
        if to_implement:
            summary_parts.append(f"{to_implement} to implement")
        if rejected:
            summary_parts.append(f"{rejected} rejected")
        if deferred:
            summary_parts.append(f"{deferred} deferred")
        if clarify:
            summary_parts.append(f"{clarify} need clarification")

        message = f"Evaluation: {', '.join(summary_parts)}" if summary_parts else "Evaluation complete"

        await self.emit(
            workflow_id,
            EventType.AGENT_MESSAGE,
            message,
            agent="evaluator",
            data={
                "to_implement": to_implement,
                "rejected": rejected,
                "deferred": deferred,
                "needs_clarification": clarify,
            },
        )
