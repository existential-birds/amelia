# LangGraph Native Task Streaming Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace custom `stage_event_emitter` callbacks with LangGraph's native `stream_mode=["updates", "tasks"]` to emit STAGE_STARTED events when nodes begin execution.

**Architecture:** Switch from `stream_mode="updates"` to `stream_mode=["updates", "tasks"]`. When combined, LangGraph emits tuples of `(mode, data)`. The `"tasks"` mode provides `{"id": ..., "name": "node_name", ...}` events when nodes start. We'll emit STAGE_STARTED from the stream loop instead of inside each node.

**Tech Stack:** LangGraph 1.0+, Python 3.12+, asyncio

---

## Summary of Changes

1. Remove `StageEventEmitter` type and callback infrastructure
2. Change `stream_mode="updates"` → `stream_mode=["updates", "tasks"]` in 3 places
3. Update stream handling to parse tuple format `(mode, data)` and emit STAGE_STARTED on `"tasks"` events
4. Remove manual `stage_event_emitter("node_name")` calls from 5 orchestrator nodes
5. Update tests

---

### Task 1: Update Stream Mode in _run_workflow

**Files:**
- Modify: `amelia/server/orchestrator/service.py:846-890`
- Test: `tests/unit/server/orchestrator/test_service_stream_mode.py` (create)

**Step 1: Write the failing test for combined stream mode parsing**

```python
# tests/unit/server/orchestrator/test_service_stream_mode.py
"""Tests for LangGraph combined stream mode handling."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_repository():
    """Create mock workflow repository."""
    repo = AsyncMock()
    repo.get.return_value = MagicMock(current_stage=None)
    repo.update = AsyncMock()
    repo.set_status = AsyncMock()
    return repo


@pytest.fixture
def mock_event_bus():
    """Create mock event bus."""
    bus = MagicMock()
    bus.emit = AsyncMock()
    bus.emit_stream = MagicMock()
    return bus


class TestStreamModeTaskEvents:
    """Test handling of LangGraph tasks stream mode events."""

    @pytest.mark.asyncio
    async def test_tasks_event_emits_stage_started(
        self, mock_repository, mock_event_bus
    ):
        """Task events should emit STAGE_STARTED before node executes."""
        from amelia.server.orchestrator.service import OrchestratorService
        from amelia.server.models.events import EventType

        # Create service with mocks
        service = OrchestratorService(
            repository=mock_repository,
            event_bus=mock_event_bus,
        )

        # Simulate a tasks mode event
        task_event = {
            "id": "task-123",
            "name": "architect_node",
            "input": {},
            "triggers": ["start:issue"],
        }

        # Call the handler
        await service._handle_tasks_event("workflow-123", task_event)

        # Verify STAGE_STARTED was emitted
        mock_event_bus.emit.assert_called()
        call_args = mock_event_bus.emit.call_args
        event = call_args[0][0]
        assert event.event_type == EventType.STAGE_STARTED
        assert event.data["stage"] == "architect_node"


    @pytest.mark.asyncio
    async def test_combined_stream_mode_parses_tuples(
        self, mock_repository, mock_event_bus
    ):
        """Combined stream mode should parse (mode, data) tuples."""
        from amelia.server.orchestrator.service import OrchestratorService

        service = OrchestratorService(
            repository=mock_repository,
            event_bus=mock_event_bus,
        )

        # Simulate chunks from stream_mode=["updates", "tasks"]
        chunks = [
            ("tasks", {"id": "t1", "name": "architect_node", "input": {}, "triggers": []}),
            ("updates", {"architect_node": {"goal": "Test goal"}}),
        ]

        # Process each chunk
        for chunk in chunks:
            await service._handle_combined_stream_chunk("workflow-123", chunk)

        # Verify both handlers were called appropriately
        assert mock_event_bus.emit.call_count >= 2  # STAGE_STARTED + STAGE_COMPLETED
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_service_stream_mode.py -v`
Expected: FAIL with "AttributeError: 'OrchestratorService' has no attribute '_handle_tasks_event'"

**Step 3: Add _handle_tasks_event method**

Add to `amelia/server/orchestrator/service.py` after `_handle_stream_chunk` (around line 1555):

```python
    async def _handle_tasks_event(
        self,
        workflow_id: str,
        task_data: dict[str, Any],
    ) -> None:
        """Handle a task event from stream_mode='tasks'.

        Task events are emitted when nodes start execution. We use this
        to emit STAGE_STARTED events, replacing the custom stage_event_emitter.

        Args:
            workflow_id: The workflow this task belongs to.
            task_data: Task event data with id, name, input, triggers.
        """
        node_name = task_data.get("name", "")
        if node_name in STAGE_NODES:
            await self._emit(
                workflow_id,
                EventType.STAGE_STARTED,
                f"Starting {node_name}",
                data={"stage": node_name},
            )

    async def _handle_combined_stream_chunk(
        self,
        workflow_id: str,
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
            await self._handle_tasks_event(workflow_id, data)
        elif mode == "updates":
            # Check for interrupt in updates mode
            if "__interrupt__" in data:
                # Return special marker to indicate interrupt
                return  # Caller handles interrupt separately
            await self._handle_stream_chunk(workflow_id, data)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_service_stream_mode.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/server/orchestrator/test_service_stream_mode.py amelia/server/orchestrator/service.py
git commit -m "$(cat <<'EOF'
feat(orchestrator): add handlers for combined stream mode

Add _handle_tasks_event and _handle_combined_stream_chunk methods
to support LangGraph's stream_mode=["updates", "tasks"].

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Update _run_workflow Stream Loop

**Files:**
- Modify: `amelia/server/orchestrator/service.py:846-890`
- Test: `tests/unit/server/orchestrator/test_service_stream_mode.py`

**Step 1: Write the failing test for interrupt detection in combined mode**

Add to `tests/unit/server/orchestrator/test_service_stream_mode.py`:

```python
    @pytest.mark.asyncio
    async def test_interrupt_detected_in_combined_mode(
        self, mock_repository, mock_event_bus
    ):
        """Interrupts in updates mode should still be detected."""
        from amelia.server.orchestrator.service import OrchestratorService

        service = OrchestratorService(
            repository=mock_repository,
            event_bus=mock_event_bus,
        )

        # Simulate interrupt chunk
        chunk = ("updates", {"__interrupt__": ({"value": "test"},)})

        # The interrupt should be detected
        is_interrupt = service._is_interrupt_chunk(chunk)
        assert is_interrupt is True

    @pytest.mark.asyncio
    async def test_non_interrupt_not_flagged(
        self, mock_repository, mock_event_bus
    ):
        """Regular updates should not be flagged as interrupts."""
        from amelia.server.orchestrator.service import OrchestratorService

        service = OrchestratorService(
            repository=mock_repository,
            event_bus=mock_event_bus,
        )

        # Regular update chunk
        chunk = ("updates", {"architect_node": {"goal": "Test"}})
        assert service._is_interrupt_chunk(chunk) is False

        # Tasks chunk
        chunk = ("tasks", {"id": "t1", "name": "architect_node"})
        assert service._is_interrupt_chunk(chunk) is False
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_service_stream_mode.py::TestStreamModeTaskEvents::test_interrupt_detected_in_combined_mode -v`
Expected: FAIL with "AttributeError: 'OrchestratorService' has no attribute '_is_interrupt_chunk'"

**Step 3: Add _is_interrupt_chunk method and update _run_workflow**

Add helper method to `amelia/server/orchestrator/service.py`:

```python
    def _is_interrupt_chunk(self, chunk: tuple[str, Any] | dict[str, Any]) -> bool:
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
        # Single mode (dict)
        return "__interrupt__" in chunk
```

Update `_run_workflow` stream loop (around line 846-890):

```python
                async for chunk in graph.astream(
                    input_state,
                    config=config,
                    stream_mode=["updates", "tasks"],
                ):
                    # Combined mode returns (mode, data) tuples
                    if self._is_interrupt_chunk(chunk):
                        was_interrupted = True
                        mode, data = chunk
                        logger.info(
                            "Workflow paused for human approval",
                            workflow_id=workflow_id,
                            interrupt_data=data.get("__interrupt__"),
                        )
                        # Sync plan from LangGraph checkpoint to ServerExecutionState
                        # so it's available via REST API while blocked
                        await self._sync_plan_from_checkpoint(workflow_id, graph, config)
                        await self._emit(
                            workflow_id,
                            EventType.APPROVAL_REQUIRED,
                            "Plan ready for review - awaiting human approval",
                            data={"paused_at": "human_approval_node"},
                        )
                        # Emit extension hook for approval gate
                        await emit_workflow_event(
                            ExtWorkflowEventType.APPROVAL_REQUESTED,
                            workflow_id=workflow_id,
                            stage="human_approval_node",
                        )
                        await self._repository.set_status(workflow_id, "blocked")
                        # Emit PAUSED event for workflow being blocked
                        await emit_workflow_event(
                            ExtWorkflowEventType.PAUSED,
                            workflow_id=workflow_id,
                            stage="human_approval_node",
                        )
                        break
                    # Handle combined mode chunk
                    await self._handle_combined_stream_chunk(workflow_id, chunk)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_service_stream_mode.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/orchestrator/test_service_stream_mode.py
git commit -m "$(cat <<'EOF'
feat(orchestrator): switch _run_workflow to combined stream mode

Update stream_mode from "updates" to ["updates", "tasks"] to get
native task start events from LangGraph instead of custom callbacks.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Update approve_workflow Stream Loop

**Files:**
- Modify: `amelia/server/orchestrator/service.py:1307-1322`

**Step 1: Update the stream loop**

Change stream_mode and chunk handling in `approve_workflow` (around line 1307):

```python
                async for chunk in graph.astream(
                    None,  # Resume from checkpoint, no new input needed
                    config=config,
                    stream_mode=["updates", "tasks"],
                ):
                    # In agentic mode, no interrupts expected after initial approval
                    if self._is_interrupt_chunk(chunk):
                        mode, data = chunk
                        state = await graph.aget_state(config)
                        next_nodes = state.next if state else []
                        logger.warning(
                            "Unexpected interrupt after approval",
                            workflow_id=workflow_id,
                            next_nodes=next_nodes,
                        )
                        continue
                    await self._handle_combined_stream_chunk(workflow_id, chunk)
```

**Step 2: Run existing tests to verify no regression**

Run: `uv run pytest tests/unit/server/orchestrator/ -v -k "approve"`
Expected: PASS (existing tests should still pass)

**Step 3: Commit**

```bash
git add amelia/server/orchestrator/service.py
git commit -m "$(cat <<'EOF'
feat(orchestrator): switch approve_workflow to combined stream mode

Update stream_mode from "updates" to ["updates", "tasks"] for
workflow resumption after human approval.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Update _run_review_workflow Stream Loop

**Files:**
- Modify: `amelia/server/orchestrator/service.py:1102-1109`

**Step 1: Update the stream loop**

Change stream_mode and chunk handling in `_run_review_workflow` (around line 1102):

```python
                async for chunk in graph.astream(
                    initial_state,
                    config=config,
                    stream_mode=["updates", "tasks"],
                ):
                    # No interrupt handling - review graph runs autonomously
                    # But we still need to check for unexpected interrupts
                    if self._is_interrupt_chunk(chunk):
                        mode, data = chunk
                        logger.warning(
                            "Unexpected interrupt in review workflow",
                            workflow_id=workflow_id,
                        )
                        continue
                    # Emit stage events for each node
                    await self._handle_combined_stream_chunk(workflow_id, chunk)
```

**Step 2: Run existing tests to verify no regression**

Run: `uv run pytest tests/unit/server/orchestrator/ -v -k "review"`
Expected: PASS

**Step 3: Commit**

```bash
git add amelia/server/orchestrator/service.py
git commit -m "$(cat <<'EOF'
feat(orchestrator): switch _run_review_workflow to combined stream mode

Update stream_mode from "updates" to ["updates", "tasks"] for
review workflow execution.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Remove stage_event_emitter from Config

**Files:**
- Modify: `amelia/server/orchestrator/service.py:163-185` (remove method)
- Modify: `amelia/server/orchestrator/service.py:787-798` (remove from config)
- Modify: `amelia/server/orchestrator/service.py:1072-1084` (remove from config)
- Modify: `amelia/server/orchestrator/service.py:1265-1277` (remove from config)

**Step 1: Remove _create_stage_event_emitter method**

Delete lines 163-185 from `amelia/server/orchestrator/service.py`:

```python
    # DELETE THIS METHOD ENTIRELY
    def _create_stage_event_emitter(self, workflow_id: str) -> StageEventEmitter:
        """Create a stage event emitter callback for nodes to signal stage start.
        ...
        """
        async def emit_stage_started(stage_name: str) -> None:
            ...
        return emit_stage_started
```

**Step 2: Remove stage_event_emitter from config dictionaries**

In `_run_workflow` (around line 787-798), remove the stage_event_emitter lines:

```python
            stream_emitter = self._create_stream_emitter()
            # DELETE: stage_event_emitter = self._create_stage_event_emitter(workflow_id)
            config: RunnableConfig = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                    "stream_emitter": stream_emitter,
                    # DELETE: "stage_event_emitter": stage_event_emitter,
                    "profile": profile,
                    "repository": self._repository,
                    "prompts": prompts,
                }
            }
```

Apply same change to `_run_review_workflow` (around line 1072) and `approve_workflow` (around line 1265).

**Step 3: Remove StageEventEmitter import**

Update imports at top of `amelia/server/orchestrator/service.py`:

```python
from amelia.core import (
    ExecutionState,
    Profile,
    # DELETE: StageEventEmitter,
    StreamEmitter,
    StreamEvent,
)
```

**Step 4: Run tests to verify no regression**

Run: `uv run pytest tests/unit/server/orchestrator/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/orchestrator/service.py
git commit -m "$(cat <<'EOF'
refactor(orchestrator): remove stage_event_emitter from service

Stage events are now emitted via LangGraph's tasks stream mode
instead of custom callbacks passed through config.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Remove stage_event_emitter from Orchestrator Nodes

**Files:**
- Modify: `amelia/core/orchestrator.py:40-68` (update _extract_config_params)
- Modify: `amelia/core/orchestrator.py:153-157` (remove from plan_validator_node)
- Modify: `amelia/core/orchestrator.py:255-260` (remove from call_architect_node)
- Modify: `amelia/core/orchestrator.py:537-542` (remove from call_developer_node)
- Modify: `amelia/core/orchestrator.py:607-612` (remove from call_reviewer_node)
- Modify: `amelia/core/orchestrator.py:683-687` (remove from call_evaluation_node)

**Step 1: Update _extract_config_params**

```python
def _extract_config_params(
    config: RunnableConfig | None,
) -> tuple[StreamEmitter | None, str, Profile]:
    """Extract stream_emitter, workflow_id, and profile from config.

    Extracts values from config.configurable dictionary. workflow_id is required.

    Args:
        config: Optional RunnableConfig with configurable parameters.

    Returns:
        Tuple of (stream_emitter, workflow_id, profile).

    Raises:
        ValueError: If workflow_id (thread_id) or profile is not provided.
    """
    config = config or {}
    configurable = config.get("configurable", {})
    stream_emitter = configurable.get("stream_emitter")
    workflow_id = configurable.get("thread_id")
    profile = configurable.get("profile")

    if not workflow_id:
        raise ValueError("workflow_id (thread_id) is required in config.configurable")
    if not profile:
        raise ValueError("profile is required in config.configurable")

    return stream_emitter, workflow_id, profile
```

**Step 2: Update all node functions**

For each node (plan_validator_node, call_architect_node, call_developer_node, call_reviewer_node, call_evaluation_node):

1. Change unpacking from 4 values to 3:
   ```python
   # Before
   stream_emitter, stage_event_emitter, workflow_id, profile = _extract_config_params(config)

   # After
   stream_emitter, workflow_id, profile = _extract_config_params(config)
   ```

2. Remove the stage_event_emitter call:
   ```python
   # DELETE these lines from each node
   if stage_event_emitter:
       await stage_event_emitter("node_name")
   ```

**Step 3: Remove StageEventEmitter import**

```python
from amelia.core.types import (
    ExecutionState,
    Profile,
    # DELETE: StageEventEmitter,
    StreamEmitter,
    StreamEvent,
    StreamEventType,
)
```

**Step 4: Update test in test_orchestrator_helpers.py**

```python
def test_extract_config_params_returns_values():
    """Test that _extract_config_params extracts correct values."""
    config = {
        "configurable": {
            "stream_emitter": None,
            "thread_id": "test-workflow-id",
            "profile": mock_profile,
        }
    }
    stream_emitter, workflow_id, extracted_profile = _extract_config_params(config)

    assert workflow_id == "test-workflow-id"
    assert extracted_profile == mock_profile
    assert stream_emitter is None
```

**Step 5: Run tests**

Run: `uv run pytest tests/unit/core/test_orchestrator_helpers.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/core/orchestrator.py tests/unit/core/test_orchestrator_helpers.py
git commit -m "$(cat <<'EOF'
refactor(orchestrator): remove stage_event_emitter from nodes

Nodes no longer need to manually emit STAGE_STARTED events.
LangGraph's tasks stream mode handles this automatically.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Remove StageEventEmitter Type Definition

**Files:**
- Modify: `amelia/core/types.py:170-174` (remove type alias)
- Modify: `amelia/core/__init__.py:12,26` (remove export)

**Step 1: Remove type alias from types.py**

Delete from `amelia/core/types.py`:

```python
# DELETE these lines (around 170-174)
StageEventEmitter = Callable[[str], Awaitable[None]]
"""Type alias for async stage event emitter function.

Takes the stage name (e.g., "architect_node") and emits a STAGE_STARTED event.
"""
```

**Step 2: Remove export from __init__.py**

Update `amelia/core/__init__.py`:

```python
# In docstring, DELETE line 12:
#     StageEventEmitter: Callback for emitting STAGE_STARTED events from nodes.

# In imports, DELETE line 26:
#     StageEventEmitter as StageEventEmitter,
```

**Step 3: Run full test suite to verify no remaining references**

Run: `uv run pytest tests/ -v`
Expected: PASS

**Step 4: Run type checker**

Run: `uv run mypy amelia`
Expected: PASS with no errors about StageEventEmitter

**Step 5: Commit**

```bash
git add amelia/core/types.py amelia/core/__init__.py
git commit -m "$(cat <<'EOF'
refactor(core): remove StageEventEmitter type

This type is no longer needed as STAGE_STARTED events are now
emitted from the stream loop using LangGraph's tasks mode.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Update Documentation

**Files:**
- Modify: `amelia/server/orchestrator/service.py` (update docstrings)

**Step 1: Update _handle_stream_chunk docstring**

```python
    async def _handle_stream_chunk(
        self,
        workflow_id: str,
        chunk: dict[str, Any],
    ) -> None:
        """Handle an updates chunk from astream(stream_mode=['updates', 'tasks']).

        With combined stream mode, updates chunks map node names to their
        state updates. We emit STAGE_COMPLETED after each node that's in
        STAGE_NODES.

        Note: STAGE_STARTED events are emitted by _handle_tasks_event when
        task events arrive from the tasks stream mode.

        Args:
            workflow_id: The workflow this chunk belongs to.
            chunk: Dict mapping node names to state updates.
        """
```

**Step 2: Run linter**

Run: `uv run ruff check amelia/server/orchestrator/service.py`
Expected: PASS

**Step 3: Commit**

```bash
git add amelia/server/orchestrator/service.py
git commit -m "$(cat <<'EOF'
docs(orchestrator): update docstrings for combined stream mode

Document the new streaming architecture using LangGraph's
native tasks mode for STAGE_STARTED events.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Run Full Test Suite and Fix Any Failures

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`

**Step 2: Fix any failures**

Address any test failures that arise from the refactoring.

**Step 3: Run type checker**

Run: `uv run mypy amelia`

**Step 4: Run linter**

Run: `uv run ruff check amelia tests`

**Step 5: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "$(cat <<'EOF'
test: fix tests for combined stream mode refactoring

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

---

## Testing Checklist

- [ ] Unit tests pass: `uv run pytest tests/unit/ -v`
- [ ] Integration tests pass: `uv run pytest tests/integration/ -v`
- [ ] Type checker passes: `uv run mypy amelia`
- [ ] Linter passes: `uv run ruff check amelia tests`
- [ ] Manual test: Start a workflow and verify STAGE_STARTED events appear in dashboard before nodes complete
