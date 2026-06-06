"""Unit tests for StreamEventEmitter.

The emitter owns event sequencing and emission. These tests construct it
directly with a REAL EventBus (so broadcasts are observable) and a repository
mock at the database boundary. Assertions are on the WorkflowEvents the bus
actually broadcasts, not on patched internals.
"""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from amelia.pipelines.implementation.state import ImplementationState
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.orchestrator.event_emitter import StreamEventEmitter


@pytest.fixture
def repository() -> AsyncMock:
    """Repository mock at the database boundary.

    Returns high-fidelity values (e.g. int from get_max_event_sequence) and
    records the WorkflowEvent instances passed to save_event.
    """
    repo = AsyncMock(spec=WorkflowRepository)
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def event_bus() -> EventBus:
    """A real EventBus so broadcasts can be observed."""
    return EventBus()


@pytest.fixture
def recorded_events(event_bus: EventBus) -> list[WorkflowEvent]:
    """Capture every WorkflowEvent the emitter actually broadcasts."""
    events: list[WorkflowEvent] = []
    event_bus.subscribe(events.append)
    return events


@pytest.fixture
def emitter(repository: AsyncMock, event_bus: EventBus) -> StreamEventEmitter:
    """Construct the emitter directly with real bus + boundary repo mock."""
    return StreamEventEmitter(repository=repository, event_bus=event_bus)


async def test_handle_stream_chunk_emits_summarized_stage_completed(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """STAGE_COMPLETED output is summarized (counts, not raw lists)."""
    wf_id = uuid4()
    big = {
        "tool_calls": [{"id": str(i)} for i in range(100)],
        "tool_results": [{"output": f"r{i}"} for i in range(100)],
        "agentic_status": "completed",
    }
    await emitter.handle_stream_chunk(wf_id, {"developer_node": big})

    stage = [e for e in recorded_events if e.event_type == EventType.STAGE_COMPLETED]
    assert len(stage) == 1
    assert stage[0].data is not None
    output = stage[0].data["output"]
    assert output["tool_calls_count"] == 100
    assert output["tool_results_count"] == 100
    assert "tool_calls" not in output
    assert "tool_results" not in output
    assert output["agentic_status"] == "completed"


async def test_handle_stream_chunk_none_output_emits_stage_completed(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """Nodes like human_approval_node produce None output but still complete."""
    wf_id = uuid4()
    await emitter.handle_stream_chunk(wf_id, {"human_approval_node": None})

    stage = [e for e in recorded_events if e.event_type == EventType.STAGE_COMPLETED]
    assert len(stage) == 1
    assert stage[0].data is not None
    assert stage[0].data["stage"] == "human_approval_node"
    assert "output" not in stage[0].data
    # No AGENT_MESSAGE for None output.
    assert not [e for e in recorded_events if e.event_type == EventType.AGENT_MESSAGE]


async def test_handle_stream_chunk_emits_developer_agent_message(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """developer_node completion emits a summarizing AGENT_MESSAGE."""
    wf_id = uuid4()
    output = {
        "agentic_status": "completed",
        "final_response": "all done",
        "tool_calls": [{"id": "1"}],
    }
    await emitter.handle_stream_chunk(wf_id, {"developer_node": output})

    agent_msgs = [e for e in recorded_events if e.event_type == EventType.AGENT_MESSAGE]
    assert len(agent_msgs) == 1
    assert agent_msgs[0].agent == "developer"
    assert agent_msgs[0].message == "Development complete"


async def test_handle_stream_chunk_emits_task_completed(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """next_task_node completion emits TASK_COMPLETED with the finished index."""
    wf_id = uuid4()
    chunk = {
        "next_task_node": {
            "current_task_index": 1,
            "total_tasks": 5,
        }
    }
    await emitter.handle_stream_chunk(wf_id, chunk)

    task_events = [e for e in recorded_events if e.event_type == EventType.TASK_COMPLETED]
    assert len(task_events) == 1
    assert task_events[0].message == "Completed Task 1/5"
    assert task_events[0].data is not None
    assert task_events[0].data["task_index"] == 0
    assert task_events[0].data["total_tasks"] == 5


async def test_handle_tasks_event_emits_stage_started(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """A task START event emits STAGE_STARTED for stage nodes."""
    wf_id = uuid4()
    await emitter.handle_tasks_event(
        wf_id,
        {"name": "architect_node", "input": {}, "triggers": ["start:issue"]},
    )

    started = [e for e in recorded_events if e.event_type == EventType.STAGE_STARTED]
    assert len(started) == 1
    assert started[0].data is not None
    assert started[0].data["stage"] == "architect_node"
    assert started[0].agent == "architect"


async def test_handle_tasks_event_result_ignored(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """Task RESULT events (no 'input') emit nothing."""
    wf_id = uuid4()
    await emitter.handle_tasks_event(
        wf_id,
        {"name": "architect_node", "result": {"goal": "g"}, "interrupts": []},
    )
    assert recorded_events == []


async def test_handle_tasks_event_emits_task_started_for_developer(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """developer_node start with a Pydantic state emits TASK_STARTED too."""
    wf_id = uuid4()
    input_state = ImplementationState(
        workflow_id=uuid4(),
        profile_id="test",
        created_at=datetime.now(UTC),
        status="running",
        total_tasks=3,
        current_task_index=1,
        plan_markdown="### Task 1: First\n### Task 2: Second task\n### Task 3: Third",
    )
    await emitter.handle_tasks_event(
        wf_id, {"name": "developer_node", "input": input_state}
    )

    types = [e.event_type for e in recorded_events]
    assert EventType.STAGE_STARTED in types
    task_started = next(e for e in recorded_events if e.event_type == EventType.TASK_STARTED)
    assert task_started.message == "Starting Task 2/3: Second task"
    assert task_started.data is not None
    assert task_started.data["task_index"] == 1
    assert task_started.data["total_tasks"] == 3
    assert task_started.data["task_title"] == "Second task"
    assert task_started.agent == "developer"


async def test_handle_combined_stream_chunk_routes_both_modes(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """Combined (mode, data) tuples route to tasks and updates handlers."""
    wf_id = uuid4()
    for chunk in [
        ("tasks", {"name": "architect_node", "input": {}, "triggers": []}),
        ("updates", {"architect_node": {"goal": "Test goal"}}),
    ]:
        await emitter.handle_combined_stream_chunk(wf_id, chunk)

    types = [e.event_type for e in recorded_events]
    assert EventType.STAGE_STARTED in types
    assert EventType.STAGE_COMPLETED in types


async def test_handle_combined_stream_chunk_skips_interrupts(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """Interrupt updates are skipped (handled by the caller)."""
    wf_id = uuid4()
    await emitter.handle_combined_stream_chunk(
        wf_id, ("updates", {"__interrupt__": ({"value": "test"},)})
    )
    assert recorded_events == []


async def test_emit_persists_and_broadcasts(
    emitter: StreamEventEmitter,
    repository: AsyncMock,
    recorded_events: list[WorkflowEvent],
) -> None:
    """emit persists via repo and broadcasts the same WorkflowEvent via bus."""
    wf_id = uuid4()
    returned = await emitter.emit(wf_id, EventType.WORKFLOW_STARTED, "Test message")

    repository.save_event.assert_called_once()
    saved = repository.save_event.call_args[0][0]
    assert isinstance(saved, WorkflowEvent)
    assert saved.event_type == EventType.WORKFLOW_STARTED
    assert saved.message == "Test message"
    assert saved.sequence == 1
    assert saved.agent == "system"
    assert recorded_events == [saved]
    assert returned == saved


async def test_emit_sequence_is_monotonic_per_workflow(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """Sequence numbers increment per workflow."""
    wf_id = uuid4()
    await emitter.emit(wf_id, EventType.WORKFLOW_STARTED, "a")
    await emitter.emit(wf_id, EventType.STAGE_STARTED, "b")
    assert [e.sequence for e in recorded_events] == [1, 2]


async def test_emit_independent_sequences_across_workflows(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """Different workflows keep independent sequence counters."""
    wf1, wf2 = uuid4(), uuid4()
    await emitter.emit(wf1, EventType.WORKFLOW_STARTED, "wf1 e1")
    await emitter.emit(wf2, EventType.WORKFLOW_STARTED, "wf2 e1")
    await emitter.emit(wf1, EventType.STAGE_STARTED, "wf1 e2")

    by_wf: dict[uuid.UUID, list[int]] = {}
    for e in recorded_events:
        by_wf.setdefault(e.workflow_id, []).append(e.sequence)
    assert by_wf[wf1] == [1, 2]
    assert by_wf[wf2] == [1]


async def test_emit_resumes_from_db_max_sequence(
    emitter: StreamEventEmitter,
    repository: AsyncMock,
    recorded_events: list[WorkflowEvent],
) -> None:
    """First emit seeds the counter from the repository max sequence."""
    repository.get_max_event_sequence.return_value = 42
    wf_id = uuid4()
    await emitter.emit(wf_id, EventType.WORKFLOW_STARTED, "Resume")

    repository.get_max_event_sequence.assert_called_once_with(wf_id)
    assert recorded_events[0].sequence == 43


async def test_emit_concurrent_same_workflow_unique_sequences(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """Concurrent emits for the same workflow get unique sequences."""
    wf_id = uuid4()
    await asyncio.gather(
        emitter.emit(wf_id, EventType.FILE_CREATED, "File 1"),
        emitter.emit(wf_id, EventType.FILE_CREATED, "File 2"),
        emitter.emit(wf_id, EventType.FILE_CREATED, "File 3"),
    )
    sequences = sorted(e.sequence for e in recorded_events)
    assert sequences == [1, 2, 3]


async def test_emit_concurrent_lock_creation_race(
    emitter: StreamEventEmitter,
    repository: AsyncMock,
    recorded_events: list[WorkflowEvent],
) -> None:
    """Concurrent first emits must not duplicate sequences via a lock race."""
    original_get_max: Callable[[uuid.UUID], object] = repository.get_max_event_sequence

    async def slow_get_max(workflow_id: uuid.UUID) -> int:
        await asyncio.sleep(0.01)
        result = await original_get_max(workflow_id)
        return int(result)  # type: ignore[arg-type]

    repository.get_max_event_sequence = slow_get_max  # type: ignore[method-assign]

    wf_id = uuid4()
    await asyncio.gather(
        *(emitter.emit(wf_id, EventType.FILE_CREATED, f"File {i}") for i in range(10))
    )
    sequences = sorted(e.sequence for e in recorded_events)
    assert sequences == list(range(1, 11))


async def test_forget_purges_sequence_state(
    emitter: StreamEventEmitter,
    recorded_events: list[WorkflowEvent],
) -> None:
    """forget() clears a workflow's sequence counter and lock."""
    wf_id = uuid4()
    await emitter.emit(wf_id, EventType.WORKFLOW_STARTED, "a")
    assert wf_id in emitter._sequence_counters
    assert wf_id in emitter._sequence_locks

    emitter.forget(wf_id)
    assert wf_id not in emitter._sequence_counters
    assert wf_id not in emitter._sequence_locks

    # After forget, the next emit re-seeds from the repo (starts again at 1).
    await emitter.emit(wf_id, EventType.STAGE_STARTED, "b")
    assert recorded_events[-1].sequence == 1
