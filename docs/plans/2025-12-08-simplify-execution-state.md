# Simplify ExecutionState Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove unnecessary state accumulation by streaming messages to the web UI via the existing event bus, simplifying review_results to a single field, and generalizing session ID support for any CLI driver.

**Parallelization Note:** Tasks 2, 3, and 5 all modify `amelia/core/state.py`. Tasks 4 and 5 both modify `amelia/core/orchestrator.py`. To avoid merge conflicts, execute in these batches:
- Batch 1: Task 1 || Task 2 (parallel - no file conflicts)
- Batch 2: Task 3 (blocks remaining)
- Batch 3: Task 3.5 (update test fixtures - critical for preventing ~50 test failures)
- Batch 4: Task 4 || Task 7 (parallel - different files: orchestrator.py vs server/models)
- Batch 5: Task 5 (sequential after Task 4 - same file orchestrator.py)
- Batch 6: Task 6 (depends on Tasks 1 and 5)
- Batch 7: Task 8 (final verification)

**CRITICAL DEPENDENCY:** Task 3 (changing review_results → last_review in state.py) must complete BEFORE Tasks 4 and 5 because both depend on the new field name. Task 3.5 must complete before Tasks 4-8 to update test fixtures that reference old field names. Tasks 4 and 5 CANNOT run in parallel as both modify orchestrator.py. Task 6 depends on Task 5 (messages field removal).

**Architecture:** Replace accumulating `messages: list[AgentMessage]` with real-time `WorkflowEvent` broadcasts via `EventBus`. The server already has WebSocket infrastructure (`/ws/events`) that streams `WorkflowEvent` to the dashboard. Simplify `review_results: list[ReviewResult]` to `last_review: ReviewResult | None` since only the last result drives decisions. Rename `claude_session_id` to `driver_session_id` for driver-agnostic session continuity.

**Tech Stack:** Python 3.12+, Pydantic, LangGraph, EventBus + WebSocket (existing)

**Maximum Parallel Agents:** 2 (peak is 2 agents in Batch 4, but Tasks 4-5 must be sequential due to shared file)
**Critical Path:** Task 3 → Task 3.5 → Task 4 → Task 5 → Task 6 → Task 8
**Estimated Time Savings from Parallelization:** ~5-10% (limited parallelization due to file dependencies)

---

## Task 1: Add Event Types for Agent Messages

**Files:**
- Modify: `amelia/server/models/events.py`
- Create: `tests/unit/server/models/test_events.py` (file does not exist yet)
- Create: `tests/unit/server/models/__init__.py` (if not exists)

**Context:** The existing `EventType` enum needs new types for agent messages. Currently `messages: list[AgentMessage]` accumulates in state but is never used for LLM context—only for audit trail. We'll stream these via the existing `EventBus` → WebSocket infrastructure.

**NOTE:** Consider reusing STAGE_STARTED/STAGE_COMPLETED event types with data payloads instead of creating new event types (TASK_STARTED/TASK_COMPLETED). This reduces event type bloat while maintaining flexibility via the data field. This is an optional improvement.

**Step 1: Write the failing test**

```python
# tests/unit/server/models/test_events.py
"""Tests for event models."""
import pytest

from amelia.server.models.events import EventType


class TestEventType:
    """Tests for EventType enum."""

    def test_agent_message_event_type_exists(self) -> None:
        """Verify AGENT_MESSAGE event type is defined."""
        assert EventType.AGENT_MESSAGE == "agent_message"

    def test_task_started_event_type_exists(self) -> None:
        """Verify TASK_STARTED event type is defined."""
        assert EventType.TASK_STARTED == "task_started"

    def test_task_completed_event_type_exists(self) -> None:
        """Verify TASK_COMPLETED event type is defined."""
        assert EventType.TASK_COMPLETED == "task_completed"

    def test_task_failed_event_type_exists(self) -> None:
        """Verify TASK_FAILED event type is defined."""
        assert EventType.TASK_FAILED == "task_failed"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_events.py -v`
Expected: FAIL with `AttributeError: 'EventType' object has no attribute 'AGENT_MESSAGE'`

**Step 3: Add new event types**

In `amelia/server/models/events.py`, add to the `EventType` enum (after the Review cycle section):

```python
    # Agent messages (replaces in-state message accumulation)
    AGENT_MESSAGE = "agent_message"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_events.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/events.py tests/unit/server/models/test_events.py
git commit -m "feat(events): add event types for agent messages

Add AGENT_MESSAGE, TASK_STARTED, TASK_COMPLETED, TASK_FAILED.
These replace in-state message accumulation with WebSocket streaming."
```

---

## Task 2: Generalize Session ID in State

**Files:**
- Modify: `amelia/core/state.py:186` (rename field)
- Modify: `amelia/server/models/state.py` (if exists)
- Test: `tests/unit/core/test_state.py`

**Context:** `claude_session_id` is Claude-specific. We need `driver_session_id` that works for any CLI driver (Claude, Gemini, Codex, etc.) that supports session resume.

**Step 1: Write the failing test**

```python
# tests/unit/core/test_state.py (add to existing file or create)
"""Tests for ExecutionState."""
import pytest

from amelia.core.state import ExecutionState


class TestExecutionStateSessionId:
    """Tests for driver_session_id field."""

    def test_driver_session_id_defaults_to_none(self, mock_profile_factory) -> None:
        """Verify driver_session_id is None by default."""
        profile = mock_profile_factory()
        state = ExecutionState(profile=profile)
        assert state.driver_session_id is None

    def test_driver_session_id_can_be_set(self, mock_profile_factory) -> None:
        """Verify driver_session_id can be assigned."""
        profile = mock_profile_factory()
        state = ExecutionState(
            profile=profile,
            driver_session_id="session-abc-123",
        )
        assert state.driver_session_id == "session-abc-123"

    # NOTE: No hasattr test needed - mypy catches undefined field references
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_state.py::TestExecutionStateSessionId -v`
Expected: FAIL with `AttributeError` (field doesn't exist yet or old name still present)

**Step 3: Rename field in state.py**

In `amelia/core/state.py`, change line ~186:

```python
# Before:
claude_session_id: str | None = None

# After:
driver_session_id: str | None = None
```

Update the docstring in the class (around line 175):

```python
# Before:
#     claude_session_id: Session ID for Claude CLI session continuity.

# After:
#     driver_session_id: Session ID for CLI driver session continuity (works with any driver).
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_state.py::TestExecutionStateSessionId -v`
Expected: PASS

**Step 5: Search and update all references**

Run: `uv run ruff check amelia --select F821,F841` to find undefined/unused references.

Search for all usages:
```bash
grep -rn "claude_session_id" amelia/ tests/
```

**Known locations to update:**
- `tests/unit/test_state_models.py` (lines 100, 102, 109) - test assertions referencing `claude_session_id`

Update all occurrences to `driver_session_id`.

**Step 6: Commit**

```bash
git add amelia/core/state.py tests/unit/core/test_state.py
git commit -m "refactor(state): rename claude_session_id to driver_session_id

Generalize session ID field to support any CLI driver (Claude, Gemini, etc.)
that implements session resume functionality."
```

---

## Task 3: Simplify review_results to last_review

**Files:**
- Modify: `amelia/core/state.py:183` (change field)
- Modify: `amelia/main.py:287-294` (CLI output - **CRITICAL: must update**)
- Test: `tests/unit/core/test_state.py`

**Context:** Currently `review_results: list[ReviewResult]` accumulates all reviews, but only `state.review_results[-1].approved` is ever checked. Simplify to `last_review: ReviewResult | None`.

**NOTE:** The orchestrator updates (orchestrator.py) are handled in Task 4. This task focuses on state.py and main.py.

**Step 1: Write the failing test**

```python
# tests/unit/core/test_state.py (add to existing tests)
class TestExecutionStateLastReview:
    """Tests for last_review field (replaces review_results list)."""

    def test_last_review_defaults_to_none(self, mock_profile_factory) -> None:
        """Verify last_review is None by default."""
        profile = mock_profile_factory()
        state = ExecutionState(profile=profile)
        assert state.last_review is None

    def test_last_review_can_be_set(self, mock_profile_factory) -> None:
        """Verify last_review accepts a ReviewResult."""
        from amelia.core.state import ReviewResult

        profile = mock_profile_factory()
        review = ReviewResult(
            reviewer_persona="security",
            approved=True,
            comments=["LGTM"],
            severity="low",
        )
        state = ExecutionState(profile=profile, last_review=review)
        assert state.last_review is not None
        assert state.last_review.approved is True

    # NOTE: No hasattr test needed - mypy catches undefined field references
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_state.py::TestExecutionStateLastReview -v`
Expected: FAIL

**Step 3: Update state.py**

In `amelia/core/state.py`, change line ~183:

```python
# Before:
review_results: list[ReviewResult] = Field(default_factory=list)

# After:
last_review: ReviewResult | None = None
```

Update the docstring (around line 172):

```python
# Before:
#     review_results: List of review results from code reviews.

# After:
#     last_review: Most recent review result (only latest matters for decisions).
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_state.py::TestExecutionStateLastReview -v`
Expected: PASS

**Step 5: Search and update additional references**

Search for all usages outside the orchestrator (orchestrator updates are in Task 4):
```bash
grep -rn "review_results" amelia/ tests/ --include="*.py" | grep -v orchestrator
```

**Known locations to update:**
- `amelia/main.py` (lines 287-294) - CLI output displaying review results (8-line block)

Update pattern:
```python
# Before:
if state.review_results:
    last_review = state.review_results[-1]

# After:
if state.last_review:
    last_review = state.last_review
```

**Step 6: Commit state change**

```bash
git add amelia/core/state.py amelia/main.py tests/unit/core/test_state.py
git commit -m "refactor(state): simplify review_results list to last_review

Only the last review result is used for workflow decisions.
Accumulating a list was unnecessary overhead in state/checkpoints."
```

---

## Task 3.5: Update Test Fixtures for New State Structure

**Files:**
- Modify: `tests/conftest.py` (mock_execution_state_factory)
- Modify: Any test files using old field names

**Context:** Test fixtures reference old field names (`messages`, `review_results`). Must update before Tasks 4-8 to prevent ~50 test failures.

**Step 1: Update mock_execution_state_factory**

In `tests/conftest.py`, update the factory to use new field names:
- Remove `messages=[]` parameter
- Change `review_results=[]` to `last_review=None`

**Step 2: Search for test file updates**

Run: `grep -rn "messages=\|review_results=" tests/`

Update all occurrences to use new field structure.

**Step 3: Commit**

```bash
git add tests/
git commit -m "test(fixtures): update for simplified ExecutionState fields

Remove messages parameter, change review_results to last_review."
```

---

## Task 4: Update Orchestrator for last_review

**Files:**
- Modify: `amelia/core/orchestrator.py`
- Test: `tests/unit/test_orchestrator_review_loop.py` (update existing file)

**Context:** The orchestrator writes to `review_results` (append) and reads `review_results[-1]`. Update both patterns.

**IMPORTANT:** These tests should be added to the existing `tests/unit/test_orchestrator_review_loop.py` file which already has comprehensive tests for `should_continue_review_loop()`. Do NOT create a new test file.

**Step 1: Write the failing test**

```python
# tests/unit/test_orchestrator_review_loop.py (add to existing file)
"""Tests for orchestrator review handling."""
import pytest

from amelia.core.orchestrator import should_continue_review_loop
from amelia.core.state import ExecutionState, ReviewResult, TaskDAG, Task


class TestShouldContinueReviewLoop:
    """Tests for should_continue_review_loop routing function."""

    def test_returns_end_when_no_review(self, mock_profile_factory) -> None:
        """No review yet means workflow should end."""
        profile = mock_profile_factory()
        state = ExecutionState(profile=profile, last_review=None)
        assert should_continue_review_loop(state) == "end"

    def test_returns_end_when_approved(self, mock_profile_factory) -> None:
        """Approved review means workflow should end."""
        profile = mock_profile_factory()
        review = ReviewResult(
            reviewer_persona="test",
            approved=True,
            comments=[],
            severity="low",
        )
        state = ExecutionState(profile=profile, last_review=review)
        assert should_continue_review_loop(state) == "end"

    def test_returns_re_evaluate_when_rejected_with_ready_tasks(
        self, mock_profile_factory, mock_task_factory
    ) -> None:
        """Rejected review with pending tasks should re-evaluate."""
        profile = mock_profile_factory()
        review = ReviewResult(
            reviewer_persona="test",
            approved=False,
            comments=["Fix the bug"],
            severity="medium",
        )
        plan = TaskDAG(
            tasks=[mock_task_factory(id="t1", description="Fix bug", status="pending")],
            original_issue="test issue",
        )
        state = ExecutionState(
            profile=profile,
            last_review=review,
            plan=plan,
        )
        assert should_continue_review_loop(state) == "re_evaluate"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_orchestrator_review_loop.py::TestShouldContinueReviewLoop -v`
Expected: FAIL (orchestrator still uses `review_results[-1]`)

**Step 3: Update orchestrator.py**

Find the reviewer_node (around line 157) and update:

```python
# Before (around line 160):
review_results = state.review_results + [review_result]
return ExecutionState(
    ...
    review_results=review_results,
    ...
)

# After:
return ExecutionState(
    ...
    last_review=review_result,
    ...
)
```

Find `should_continue_review_loop` (around line 288-308) and update:

```python
# Before:
def should_continue_review_loop(state: ExecutionState) -> str:
    if state.review_results and not state.review_results[-1].approved:
        if state.plan and state.plan.get_ready_tasks():
            return "re_evaluate"
        return "end"
    return "end"

# After:
def should_continue_review_loop(state: ExecutionState) -> Literal["re_evaluate", "end"]:
    """Determine if review loop should continue based on last review."""
    if state.last_review and not state.last_review.approved:
        if state.plan and state.plan.get_ready_tasks():
            return "re_evaluate"
        return "end"
    return "end"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_orchestrator_review_loop.py::TestShouldContinueReviewLoop -v`
Expected: PASS

**Step 5: Update any other review_results references**

Search for remaining references:
```bash
grep -rn "review_results" amelia/
```

Update each occurrence to use `last_review`.

**Step 6: Commit**

```bash
git add amelia/core/orchestrator.py tests/unit/test_orchestrator_review_loop.py
git commit -m "refactor(orchestrator): use last_review instead of review_results list

Update reviewer_node to set last_review directly.
Update should_continue_review_loop to check last_review.approved."
```

---

## Task 5: Remove messages from ExecutionState

**Files:**
- Modify: `amelia/core/state.py:184` (remove field)
- Modify: `amelia/core/orchestrator.py` (replace message appends with logging)
- Test: `tests/unit/core/test_orchestrator.py`

**Context:** The `messages` field is never used for LLM context or decisions. Replace with workflow logging from Task 1.

**Step 1: Find all messages field references**

**NOTE:** No explicit test needed for messages field removal. Type checking via `mypy amelia` will catch any code that references `state.messages` after removal. This is verified in Task 8.

Run: `grep -rn "state\.messages\|\.messages.*=" amelia/` to find references that need updating.

**Step 2: Remove messages field from state.py**

In `amelia/core/state.py`, remove line ~184:

```python
# Remove this line:
messages: list[AgentMessage] = Field(default_factory=list)
```

Remove from docstring (around line 173):

```python
# Remove:
#     messages: Conversation history between agents.
```

**Step 3: Verify removal with type check**

Run: `uv run mypy amelia/core/state.py`
Expected: No errors related to messages field

**Step 4: Commit state change**

```bash
git add amelia/core/state.py tests/unit/core/test_state.py
git commit -m "refactor(state): remove messages list from ExecutionState

Messages were only used for audit logging, not LLM context.
Workflow events are now logged externally via workflow_logger."
```

---

## Task 6: Stream Agent Messages via Existing `_emit()` Method

**Files:**
- Modify: `amelia/server/orchestrator/service.py` (server mode uses existing `_emit()`)
- Modify: `amelia/core/orchestrator.py` (CLI mode uses loguru fallback)
- Test: `tests/unit/server/orchestrator/test_service.py`

**Context:** All places that appended to `state.messages` now broadcast via `EventBus` (server mode) or log via loguru (CLI mode). The EventBus streams to the dashboard via WebSocket.

**IMPORTANT:** The `OrchestratorService` already has a well-designed `_emit()` method (`service.py:465-526`) that handles:
- Sequence number generation with thread-safe locking
- WorkflowEvent construction with UUID and timestamp
- Repository persistence
- EventBus broadcasting via `self._event_bus.emit(event)` (synchronous)

**DO NOT create a new wrapper method.** Use `_emit()` directly.

**Step 1: Write the failing test**

```python
# tests/unit/server/orchestrator/test_service.py (add to existing tests)
"""Tests for agent message event emission."""
import pytest
from unittest.mock import AsyncMock

from amelia.server.models.events import EventType, WorkflowEvent
from amelia.server.event_bus import EventBus


class TestAgentMessageEvents:
    """Tests for agent message event emission via _emit()."""

    async def test_emit_agent_message_event(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_event_bus: EventBus,  # REAL EventBus, not MagicMock
    ) -> None:
        """Verify _emit() broadcasts AGENT_MESSAGE events."""
        received: list[WorkflowEvent] = []
        mock_event_bus.subscribe(lambda e: received.append(e))

        await orchestrator._emit(
            workflow_id="wf-123",
            event_type=EventType.AGENT_MESSAGE,
            message="Test message",
            agent="architect",
            data={"test": "data"},
        )

        # Verify behavior: event was received by subscriber
        assert len(received) == 1
        assert received[0].event_type == EventType.AGENT_MESSAGE
        assert received[0].agent == "architect"
        assert received[0].message == "Test message"

    async def test_emit_task_started_event(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_event_bus: EventBus,
    ) -> None:
        """Verify _emit() can emit TASK_STARTED events."""
        received: list[WorkflowEvent] = []
        mock_event_bus.subscribe(lambda e: received.append(e))

        await orchestrator._emit(
            workflow_id="wf-123",
            event_type=EventType.TASK_STARTED,
            message="Starting task: Implement feature",
            agent="developer",
            data={"task_id": "t1"},
        )

        assert len(received) == 1
        assert received[0].event_type == EventType.TASK_STARTED
        assert received[0].data == {"task_id": "t1"}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py::TestAgentMessageEvents -v`
Expected: FAIL with `AttributeError: 'EventType' object has no attribute 'AGENT_MESSAGE'` (until Task 1 is complete)

**IMPORTANT:** These tests verify that the new event types work with _emit().
The _emit() mechanism itself is already thoroughly tested in test_service.py.
For orchestrator integration, prefer mocking _emit() and verifying it was called
with correct parameters rather than retesting the full event emission pipeline.

Alternative test pattern:
```python
async def test_architect_emits_agent_message(orchestrator, ...):
    orchestrator._emit = AsyncMock()
    # ... trigger architect processing
    orchestrator._emit.assert_called_with(
        workflow_id=ANY,
        event_type=EventType.AGENT_MESSAGE,
        message=ANY,
        agent="architect",
        data=ANY,
    )
```

**Step 3: Update server orchestrator to use _emit() for agent messages**

**Locations to update in amelia/server/orchestrator/service.py:**

1. `_run_workflow()` method - where workflow graph is executed
2. After calling `architect_node()` - emit AGENT_MESSAGE with plan summary
3. Before/after calling `developer_node()` - emit TASK_STARTED/TASK_COMPLETED
4. After calling `reviewer_node()` - emit REVIEW_COMPLETED (already exists, verify)

Search for existing message accumulation patterns:
```bash
grep -n "messages.*AgentMessage" amelia/server/orchestrator/service.py
```

Replace each occurrence with an appropriate _emit() call.

In `amelia/server/orchestrator/service.py`, replace message accumulation with `_emit()` calls:

```python
# In architect processing (where plan is generated):
# BEFORE: messages = state.messages + [AgentMessage(...)]
# AFTER: Use existing _emit() method
await self._emit(
    workflow_id=workflow_id,
    event_type=EventType.AGENT_MESSAGE,
    message=f"Generated plan with {len(plan.tasks)} tasks",
    agent="architect",
    data={"task_count": len(plan.tasks)},
)

# In developer processing (task start):
await self._emit(
    workflow_id=workflow_id,
    event_type=EventType.TASK_STARTED,
    message=f"Starting task: {task.description}",
    agent="developer",
    data={"task_id": task.id},
)

# After task completion:
await self._emit(
    workflow_id=workflow_id,
    event_type=EventType.TASK_COMPLETED,  # or TASK_FAILED
    message=f"Task completed: {task.id}",
    agent="developer",
    data={"task_id": task.id, "status": task.status},
)

# In reviewer processing:
await self._emit(
    workflow_id=workflow_id,
    event_type=EventType.REVIEW_COMPLETED,
    message=f"Review {'approved' if approved else 'rejected'}",
    agent="reviewer",
    data={"approved": approved, "comments": comments},
)
```

**Step 4: Update CLI orchestrator to use loguru**

In `amelia/core/orchestrator.py`, replace message appends with structured logging:

```python
from loguru import logger

# Instead of: messages = state.messages + [AgentMessage(...)]
logger.info(
    "Architect generated plan",
    workflow_id=state.issue.key if state.issue else "cli",
    agent="architect",
    task_count=len(plan.tasks),
)

# For task execution:
logger.info(
    "Task started",
    workflow_id=state.issue.key if state.issue else "cli",
    agent="developer",
    task_id=task.id,
    description=task.description,
)

# After task completion:
logger.info(
    "Task completed",
    workflow_id=state.issue.key if state.issue else "cli",
    agent="developer",
    task_id=task.id,
    status=task.status,
)
```

**Step 5: Remove messages from ExecutionState returns**

Remove `messages=...` from all `ExecutionState(...)` constructor calls in both orchestrators.

**Step 6: Run tests to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/ -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/server/orchestrator/service.py amelia/core/orchestrator.py tests/unit/server/orchestrator/test_service.py
git commit -m "refactor(orchestrator): stream agent messages via existing _emit()

Server mode: Uses existing _emit() method to broadcast via EventBus.
CLI mode: Logs via loguru for audit trail.
Removes message accumulation from ExecutionState."
```

---

## Task 7: Update Server Models and Dashboard Event Handling

**Files:**
- Check: `amelia/server/models/state.py`
- Modify if `ServerExecutionState` extends or mirrors `ExecutionState`
- Check: `dashboard/src/` for WebSocket event handlers

**IMPORTANT:** Verify the dashboard handles new EventType values gracefully. The WebSocket connection receives WorkflowEvent objects - ensure the frontend doesn't break on unknown event types.

**Step 0: Write failing test for ServerExecutionState sync**

```python
# tests/unit/server/models/test_state.py (add to existing tests)
def test_server_execution_state_syncs_with_core_field_changes(mock_profile_factory):
    """ServerExecutionState properly wraps ExecutionState with new last_review field."""
    from amelia.core.state import ExecutionState, ReviewResult
    from amelia.server.models.state import ServerExecutionState

    review = ReviewResult(
        reviewer_persona="test",
        approved=True,
        comments=["LGTM"],
        severity="low",
    )
    core_state = ExecutionState(profile=mock_profile_factory(), last_review=review)
    server_state = ServerExecutionState(
        id="wf-123",
        issue_id="ISSUE-123",
        worktree_path="/tmp",
        worktree_name="test",
        execution_state=core_state,
    )
    assert server_state.execution_state.last_review == review
```

Run: `uv run pytest tests/unit/server/models/test_state.py::test_server_execution_state_syncs_with_core_field_changes -v`
Expected: FAIL if ServerExecutionState has its own state model with old field names

**Step 1: Check if server has its own state model**

```bash
grep -n "messages\|review_results\|claude_session_id" amelia/server/models/state.py
```

**Step 2: Apply same changes if found**

- Remove `messages` field
- Change `review_results` → `last_review`
- Change `claude_session_id` → `driver_session_id`

**Step 3: Check dashboard event handling**

Search for event type handling in the dashboard:
```bash
grep -rn "event_type\|EventType\|WORKFLOW_\|STAGE_" dashboard/src/
```

Verify the dashboard handles unknown event types gracefully (e.g., logs them rather than crashing). If the dashboard uses a switch/case on event types, add cases for:
- `AGENT_MESSAGE`
- `TASK_STARTED`
- `TASK_COMPLETED`
- `TASK_FAILED`

**Step 4: Run server tests**

Run: `uv run pytest tests/unit/server/ -v`

**Step 5: Commit if changes made**

```bash
git add amelia/server/models/state.py dashboard/src/
git commit -m "refactor(server): align ServerExecutionState with simplified core state

Also ensures dashboard handles new event types gracefully."
```

---

## Task 8: Run Full Test Suite and Type Check

**Files:** All modified files

**Step 1: Run linting**

Run: `uv run ruff check amelia tests --fix`
Expected: No errors (or auto-fixed)

**Step 2: Run type checking**

Run: `uv run mypy amelia`
Expected: No errors

**Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All tests pass

**Step 4: Fix any failures**

Address type errors or test failures from the refactor.

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: fix linting and type errors from state simplification"
```

---

## Summary of Changes

| Before | After | Rationale |
|--------|-------|-----------|
| `messages: list[AgentMessage]` | Removed (EventBus → WebSocket) | Never used for LLM context; now streams to dashboard |
| `review_results: list[ReviewResult]` | `last_review: ReviewResult \| None` | Only last result checked for decisions |
| `claude_session_id: str \| None` | `driver_session_id: str \| None` | Generalize for any CLI driver (Claude, Gemini, Codex) |

**Benefits:**
- Smaller checkpoint size (no growing lists in state)
- Real-time dashboard updates via existing WebSocket infrastructure
- Cleaner state model focused on decision-relevant data
- Audit trail preserved in structured logs (CLI) or events (server)
- Ready for multi-driver session support (future CLI drivers)

**Architecture After Refactor:**

```
Orchestrator Node
    │
    ├─ Server Mode ──→ EventBus.emit(WorkflowEvent)
    │                       │
    │                       ▼
    │               ConnectionManager.broadcast()
    │                       │
    │                       ▼
    │               WebSocket → Dashboard
    │
    └─ CLI Mode ───→ loguru.info() → stdout/file
```
