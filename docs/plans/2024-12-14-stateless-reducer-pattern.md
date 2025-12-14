# Stateless Reducer Pattern Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan with parallel subagents per wave.

**Goal:** Refactor Amelia to follow the Stateless Reducer principle from 12-Factor Agents, enabling time-travel debugging, safe parallel execution, and stateless deployment.

**Architecture:** All Pydantic models become frozen (immutable). Nodes return partial `dict` updates instead of full state. **Task status is derived from a `task_results` dict (not stored in Task model) for parallel safety. Driver sessions are scoped by agent in a `driver_sessions` dict. Custom reducers (`dict_merge`, `set_union`) handle concurrent dict/set updates.** Profile is accessed via `config["configurable"]["profile"]` with `profile_id` stored in state for replay determinism. Native LangGraph checkpointers handle persistence.

**Tech Stack:** Python 3.12+, Pydantic v2 (frozen models), LangGraph v1.0+ (SqliteSaver, Annotated reducers), pytest-asyncio

---

## Execution Strategy: Parallel by File

```
WAVE 1 (parallel):  [A: types.py] ─────────────────┬─── [B: shell tools]
                           │                       │
WAVE 2 (parallel):  [C: state.py] ─────────┬─── [D: base.py]
                           │               │
WAVE 3:             [E: state_utils.py] ───┘
                           │
WAVE 4:             [F: orchestrator.py]
                           │
WAVE 5:             [G: exports + validation]
```

**Parallelization Rules:**
- Tasks in the same wave can run simultaneously via parallel subagents
- `WAIT_FOR: X` means task cannot start until X completes
- Each task owns its files completely - no partial modifications

---

## Critical Review Findings

An external review identified these issues requiring schema changes:

| Issue | Problem | Solution |
|-------|---------|----------|
| Dict fields not parallel-safe | `{**state.dict_field, ...}` loses concurrent updates | Use `dict_merge` reducer |
| Single DriverSession races | Parallel nodes overwrite each other's session | Scope by agent: `driver_sessions: dict[str, DriverSession]` |
| Task.status mutation | Violates immutability | Derive status from `task_results` dict |
| Replay without profile | Checkpoints don't capture config | Store `profile_id` in state |

These changes are incorporated in the tasks below.

---

## Wave 1: Foundation (Parallel)

### Task A: Add DriverSession to core/types.py

**WAIT_FOR:** None (can start immediately)

**Files:**
- Modify: `amelia/core/types.py`
- Modify: `tests/unit/test_types.py`

**Implementation - amelia/core/types.py:**

Add after the existing `Design` class:

```python
class DriverSession(BaseModel):
    """Session state for driver continuity. Scoped by agent/node."""
    model_config = ConfigDict(frozen=True)

    conversation_id: str | None = None
    model: str = "claude-sonnet-4-20250514"
    data: dict[str, Any] = Field(default_factory=dict)  # Provider-specific data
```

**Tests - tests/unit/test_types.py:**

Add to the existing test file:

```python
from pydantic import ValidationError


class TestDriverSession:
    """Tests for DriverSession immutability and defaults."""

    def test_driver_session_is_frozen(self):
        """DriverSession should be immutable."""
        from amelia.core.types import DriverSession

        session = DriverSession(conversation_id="conv-123", model="claude-sonnet-4-20250514")

        with pytest.raises(ValidationError):
            session.conversation_id = "new-id"

    def test_driver_session_defaults(self):
        """DriverSession has sensible defaults."""
        from amelia.core.types import DriverSession

        session = DriverSession()

        assert session.conversation_id is None
        assert session.model == "claude-sonnet-4-20250514"

    def test_driver_session_model_copy(self):
        """DriverSession can be copied with updates."""
        from amelia.core.types import DriverSession

        session = DriverSession(conversation_id="conv-123")
        updated = session.model_copy(update={"conversation_id": "conv-456"})

        assert session.conversation_id == "conv-123"  # Original unchanged
        assert updated.conversation_id == "conv-456"
```

**Verify:**
```bash
uv run pytest tests/unit/test_types.py::TestDriverSession -v
```

**Commit:**
```bash
git add amelia/core/types.py tests/unit/test_types.py
git commit -m "feat(types): add frozen DriverSession model"
```

---

### Task B: Add cwd parameter to shell executor

**WAIT_FOR:** None (can start immediately)

**Files:**
- Modify: `amelia/tools/shell_executor.py`
- Modify: `amelia/tools/safe_shell.py`
- Modify: `tests/unit/test_safe_shell_executor.py`

**Implementation - amelia/tools/shell_executor.py:**

Update `run_shell_command` function signature and body:

```python
from pathlib import Path


async def run_shell_command(
    command: str,
    timeout: int | None = 30,
    strict_mode: bool = False,
    cwd: Path | str | None = None,
) -> str:
    """
    Execute a shell command safely.

    This is a backward-compatible wrapper around SafeShellExecutor.execute().

    Args:
        command: The command to execute
        timeout: Maximum execution time in seconds
        strict_mode: If True, only allow commands in strict allowlist
        cwd: Working directory for command execution (default: current directory)

    Returns:
        Command stdout as string

    Raises:
        ValueError: If command is empty or has invalid syntax
        ShellInjectionError: If shell metacharacters are detected
        BlockedCommandError: If command is in blocklist
        DangerousCommandError: If command matches dangerous pattern
        CommandNotAllowedError: If strict mode and command not in allowlist
        RuntimeError: If command fails or times out
    """
    return await SafeShellExecutor.execute(
        command=command,
        timeout=timeout,
        strict_mode=strict_mode,
        cwd=cwd,
    )
```

**Implementation - amelia/tools/safe_shell.py:**

Update `SafeShellExecutor.execute()` class method to accept and use `cwd`:

```python
@classmethod
async def execute(
    cls,
    command: str,
    timeout: int | None = 30,
    strict_mode: bool = False,
    cwd: Path | str | None = None,
) -> str:
    """Execute a shell command safely.

    Args:
        command: The command to execute
        timeout: Maximum execution time in seconds
        strict_mode: If True, only allow commands in strict allowlist
        cwd: Working directory for command execution

    Returns:
        Command stdout as string
    """
    # ... existing validation code ...

    # Update the subprocess call to include cwd
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,  # Add this parameter
    )
    # ... rest of existing implementation ...
```

**Tests - tests/unit/test_safe_shell_executor.py:**

Add to the existing test file:

```python
class TestShellExecutorCwd:
    """Tests for explicit cwd parameter."""

    async def test_run_shell_command_with_explicit_cwd(self, tmp_path):
        """run_shell_command accepts explicit cwd parameter."""
        from amelia.tools.shell_executor import run_shell_command

        # Create a test file in tmp_path
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")

        result = await run_shell_command("cat test.txt", cwd=tmp_path)

        assert result.strip() == "hello"

    async def test_run_shell_command_cwd_none_uses_current(self):
        """run_shell_command with cwd=None uses current directory."""
        from amelia.tools.shell_executor import run_shell_command

        # pwd should work without explicit cwd
        result = await run_shell_command("pwd", cwd=None)

        assert len(result.strip()) > 0

    async def test_run_shell_command_cwd_as_string(self, tmp_path):
        """run_shell_command accepts cwd as string."""
        from amelia.tools.shell_executor import run_shell_command

        test_file = tmp_path / "test.txt"
        test_file.write_text("string-cwd-test")

        result = await run_shell_command("cat test.txt", cwd=str(tmp_path))

        assert result.strip() == "string-cwd-test"
```

**Verify:**
```bash
uv run pytest tests/unit/test_safe_shell_executor.py::TestShellExecutorCwd -v
```

**Commit:**
```bash
git add amelia/tools/shell_executor.py amelia/tools/safe_shell.py tests/unit/test_safe_shell_executor.py
git commit -m "feat(shell): add explicit cwd parameter for stateless execution"
```

---

## Wave 2: Core Models (Parallel)

### Task C: Make all state models frozen

**WAIT_FOR:** Task A (needs DriverSession import)

**Files:**
- Modify: `amelia/core/state.py`
- Modify: `tests/unit/test_state.py`

**Implementation - amelia/core/state.py:**

1. Add imports and custom reducers at top of file:

```python
from operator import add
from typing import Annotated, Any, Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

def dict_merge(left: dict, right: dict) -> dict:
    """Shallow merge reducer: right wins on key conflicts."""
    return {**(left or {}), **(right or {})}

def set_union(left: set, right: set) -> set:
    return (left or set()) | (right or set())
```

2. Add TaskResult and HistoryEntry models:

```python
class TaskResult(BaseModel):
    """Result of executing a task."""
    model_config = ConfigDict(frozen=True)

    task_id: str
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"]
    output: str | None = None
    error: str | None = None
    completed_at: datetime | None = None


class HistoryEntry(BaseModel):
    """Structured history entry for agent actions."""
    model_config = ConfigDict(frozen=True)

    ts: datetime = Field(default_factory=datetime.utcnow)
    actor: str
    event: str
    detail: dict[str, Any] = Field(default_factory=dict)
```

3. Update ALL model classes to be frozen:

```python
class TaskStep(BaseModel):
    """A single step within a task."""
    model_config = ConfigDict(frozen=True)
    # ... existing fields unchanged ...


class FileOperation(BaseModel):
    """File operation within a task."""
    model_config = ConfigDict(frozen=True)
    # ... existing fields unchanged ...


class Task(BaseModel):
    """Task specification. Status tracked separately in ExecutionState.task_results."""
    model_config = ConfigDict(frozen=True)

    id: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    # NOTE: 'status' removed - derived from ExecutionState.task_results


class TaskDAG(BaseModel):
    """Directed Acyclic Graph of tasks with dependency management."""
    model_config = ConfigDict(frozen=True)
    # ... existing fields and methods unchanged ...


class ReviewResult(BaseModel):
    """Result of a code review."""
    model_config = ConfigDict(frozen=True)
    # ... existing fields unchanged ...


class AgentMessage(BaseModel):
    """Message in agent conversation."""
    model_config = ConfigDict(frozen=True)
    # ... existing fields unchanged ...
```

4. Update ExecutionState with the hardened parallel-safe schema:

```python
class ExecutionState(BaseModel):
    """Parallel-safe state for LangGraph orchestration."""
    model_config = ConfigDict(frozen=True)

    # --- Replay/identity metadata ---
    profile_id: str = ""

    # --- Domain data (single-writer) ---
    issue: Issue | None = None
    design: Design | None = None
    plan: TaskDAG | None = None

    # --- Task execution (parallel-safe) ---
    task_results: Annotated[dict[str, TaskResult], dict_merge] = Field(default_factory=dict)
    current_task_id: str | None = None

    # --- Driver sessions (scoped by agent) ---
    driver_sessions: Annotated[dict[str, DriverSession], dict_merge] = Field(default_factory=dict)

    # --- Append-only logs ---
    history: Annotated[list[HistoryEntry], add] = Field(default_factory=list)

    # --- Idempotency ---
    completed_steps: Annotated[set[str], set_union] = Field(default_factory=set)

    # --- Single-writer fields ---
    last_review: ReviewResult | None = None
    human_approved: bool | None = None
    code_changes_for_review: str | None = None
    workflow_status: Literal["running", "completed", "failed"] = "running"

    def get_task_status(self, task_id: str) -> str:
        """Get status of a task from task_results."""
        if task_id in self.task_results:
            return self.task_results[task_id].status
        return "pending"

    def get_ready_tasks(self) -> list[Task]:
        """Get tasks ready to execute (pending with all dependencies completed)."""
        if not self.plan:
            return []
        completed_ids = {tid for tid, r in self.task_results.items() if r.status == "completed"}
        return [t for t in self.plan.tasks if self.get_task_status(t.id) == "pending"
                and all(d in completed_ids for d in t.dependencies)]
```

**Tests - tests/unit/test_state.py:**

Add comprehensive frozen model tests:

```python
from pydantic import ValidationError


class TestFrozenModels:
    """Tests for immutability of all state models."""

    def test_task_step_is_frozen(self):
        """TaskStep should be immutable."""
        from amelia.core.state import TaskStep

        step = TaskStep(description="Run tests", command="pytest")

        with pytest.raises(ValidationError):
            step.description = "New description"

    def test_file_operation_is_frozen(self):
        """FileOperation should be immutable."""
        from amelia.core.state import FileOperation

        op = FileOperation(path="src/main.py", operation="create")

        with pytest.raises(ValidationError):
            op.path = "new/path.py"

    def test_task_is_frozen(self):
        """Task should be immutable."""
        from amelia.core.state import Task

        task = Task(id="task-1", description="Test task")

        with pytest.raises(ValidationError):
            task.description = "New description"

    def test_task_model_copy_update(self):
        """Task can be copied with updated description."""
        from amelia.core.state import Task

        task = Task(id="task-1", description="Test task")
        updated = task.model_copy(update={"description": "Updated task"})

        assert task.description == "Test task"  # Original unchanged
        assert updated.description == "Updated task"

    def test_task_dag_is_frozen(self):
        """TaskDAG should be immutable."""
        from amelia.core.state import Task, TaskDAG

        task = Task(id="task-1", description="Test")
        dag = TaskDAG(tasks=[task], original_issue="Test issue")

        with pytest.raises(ValidationError):
            dag.original_issue = "New issue"

    def test_task_dag_model_copy_with_updated_tasks(self):
        """TaskDAG can be copied with updated task list."""
        from amelia.core.state import Task, TaskDAG

        task = Task(id="task-1", description="Test")
        dag = TaskDAG(tasks=[task], original_issue="Test issue")

        updated_task = task.model_copy(update={"description": "Updated"})
        updated_dag = dag.model_copy(update={"tasks": [updated_task]})

        assert dag.tasks[0].description == "Test"
        assert updated_dag.tasks[0].description == "Updated"

    def test_review_result_is_frozen(self):
        """ReviewResult should be immutable."""
        from amelia.core.state import ReviewResult

        result = ReviewResult(approved=True, feedback="LGTM")

        with pytest.raises(ValidationError):
            result.approved = False

    def test_agent_message_is_frozen(self):
        """AgentMessage should be immutable."""
        from amelia.core.state import AgentMessage

        msg = AgentMessage(role="user", content="Hello")

        with pytest.raises(ValidationError):
            msg.content = "New content"

    def test_execution_state_is_frozen(self):
        """ExecutionState should be immutable."""
        from amelia.core.state import ExecutionState

        state = ExecutionState()

        with pytest.raises(ValidationError):
            state.workflow_status = "completed"

    def test_execution_state_model_copy(self):
        """ExecutionState can be copied with updates."""
        from amelia.core.state import ExecutionState

        state = ExecutionState(workflow_status="running")
        updated = state.model_copy(update={"workflow_status": "completed"})

        assert state.workflow_status == "running"
        assert updated.workflow_status == "completed"

    def test_execution_state_has_driver_sessions_field(self):
        """ExecutionState has driver_sessions dict for scoped sessions."""
        from amelia.core.state import ExecutionState
        from amelia.core.types import DriverSession

        session = DriverSession(conversation_id="conv-123")
        state = ExecutionState(driver_sessions={"developer": session})

        assert "developer" in state.driver_sessions
        assert state.driver_sessions["developer"].conversation_id == "conv-123"

    def test_execution_state_has_task_results_field(self):
        """ExecutionState has task_results dict for parallel-safe status tracking."""
        from amelia.core.state import ExecutionState, TaskResult

        result = TaskResult(task_id="task-1", status="completed", output="Done")
        state = ExecutionState(task_results={"task-1": result})

        assert "task-1" in state.task_results
        assert state.task_results["task-1"].status == "completed"

    def test_execution_state_get_task_status(self):
        """ExecutionState.get_task_status derives status from task_results."""
        from amelia.core.state import ExecutionState, TaskResult

        result = TaskResult(task_id="task-1", status="in_progress")
        state = ExecutionState(task_results={"task-1": result})

        assert state.get_task_status("task-1") == "in_progress"
        assert state.get_task_status("task-2") == "pending"  # Not in results

    def test_execution_state_get_ready_tasks(self):
        """ExecutionState.get_ready_tasks returns pending tasks with met dependencies."""
        from amelia.core.state import ExecutionState, Task, TaskDAG, TaskResult

        task1 = Task(id="task-1", description="First")
        task2 = Task(id="task-2", description="Second", dependencies=["task-1"])
        dag = TaskDAG(tasks=[task1, task2], original_issue="Test")

        # task-1 not in results = pending, no deps = ready
        state = ExecutionState(plan=dag, task_results={})
        ready = state.get_ready_tasks()

        assert len(ready) == 1
        assert ready[0].id == "task-1"

    def test_execution_state_has_profile_id_field(self):
        """ExecutionState has profile_id for replay determinism."""
        from amelia.core.state import ExecutionState

        state = ExecutionState(profile_id="work-profile")

        assert state.profile_id == "work-profile"

    def test_execution_state_has_completed_steps_field(self):
        """ExecutionState has completed_steps set for idempotency."""
        from amelia.core.state import ExecutionState

        state = ExecutionState(completed_steps={"task:task-1", "task:task-2"})

        assert "task:task-1" in state.completed_steps
        assert len(state.completed_steps) == 2
```

**Verify:**
```bash
uv run pytest tests/unit/test_state.py::TestFrozenModels -v
```

**Commit:**
```bash
git add amelia/core/state.py tests/unit/test_state.py
git commit -m "feat(state): make all models frozen with Annotated reducers"
```

---

### Task D: Add DriverResponse and StatelessDriver to base.py

**WAIT_FOR:** Task A (needs DriverSession import)

**Files:**
- Modify: `amelia/drivers/base.py`
- Modify: `tests/unit/test_driver_factory.py`

**Implementation - amelia/drivers/base.py:**

Add after existing imports and before DriverInterface:

```python
from typing import Protocol, Sequence, Any
from collections.abc import AsyncIterator

from pydantic import BaseModel

from amelia.core.state import AgentMessage
from amelia.core.types import DriverSession


class TokenUsage(BaseModel, frozen=True):
    """Token usage statistics from a generation.

    Attributes:
        input_tokens: Number of input tokens used.
        output_tokens: Number of output tokens generated.
    """
    input_tokens: int = 0
    output_tokens: int = 0


class DriverResponse(BaseModel, frozen=True):
    """Immutable response from a driver including updated session.

    Attributes:
        content: The generated content/response.
        session: Updated session state for continuity.
        usage: Optional token usage statistics.
    """
    content: str
    session: DriverSession
    usage: TokenUsage | None = None


class StatelessDriver(Protocol):
    """Stateless driver protocol for Factor 12 compliance.

    All drivers should implement this protocol for stateless operation.
    Session state is passed explicitly and returned with responses.
    This enables time-travel debugging and safe parallel execution.
    """

    async def generate(
        self,
        messages: Sequence[AgentMessage],
        session: DriverSession,
        schema: type[BaseModel] | None = None,
    ) -> DriverResponse:
        """Generate a response from the model.

        Args:
            messages: Conversation history.
            session: Current session state (immutable).
            schema: Optional Pydantic model for structured output.

        Returns:
            DriverResponse with content and NEW session state.
        """
        ...
```

**Tests - tests/unit/test_driver_factory.py:**

Add to the existing test file:

```python
from pydantic import ValidationError


class TestDriverResponse:
    """Tests for DriverResponse immutability."""

    def test_driver_response_is_frozen(self):
        """DriverResponse should be immutable."""
        from amelia.drivers.base import DriverResponse
        from amelia.core.types import DriverSession

        response = DriverResponse(
            content="Hello",
            session=DriverSession(conversation_id="conv-123"),
        )

        with pytest.raises(ValidationError):
            response.content = "New content"

    def test_driver_response_has_required_fields(self):
        """DriverResponse requires content and session."""
        from amelia.drivers.base import DriverResponse
        from amelia.core.types import DriverSession

        response = DriverResponse(
            content="Test response",
            session=DriverSession(),
        )

        assert response.content == "Test response"
        assert response.session is not None
        assert response.usage is None  # Optional field

    def test_driver_response_with_usage(self):
        """DriverResponse can include token usage."""
        from amelia.drivers.base import DriverResponse, TokenUsage
        from amelia.core.types import DriverSession

        usage = TokenUsage(input_tokens=100, output_tokens=50)
        response = DriverResponse(
            content="Test",
            session=DriverSession(),
            usage=usage,
        )

        assert response.usage.input_tokens == 100
        assert response.usage.output_tokens == 50


class TestTokenUsage:
    """Tests for TokenUsage model."""

    def test_token_usage_is_frozen(self):
        """TokenUsage should be immutable."""
        from amelia.drivers.base import TokenUsage

        usage = TokenUsage(input_tokens=100, output_tokens=50)

        with pytest.raises(ValidationError):
            usage.input_tokens = 200

    def test_token_usage_defaults(self):
        """TokenUsage has zero defaults."""
        from amelia.drivers.base import TokenUsage

        usage = TokenUsage()

        assert usage.input_tokens == 0
        assert usage.output_tokens == 0


class TestStatelessDriverProtocol:
    """Tests for StatelessDriver protocol."""

    def test_stateless_driver_protocol_has_generate(self):
        """StatelessDriver protocol requires generate method with session."""
        from amelia.drivers.base import StatelessDriver
        import inspect

        assert hasattr(StatelessDriver, "generate")
        sig = inspect.signature(StatelessDriver.generate)
        assert "session" in sig.parameters
        assert "messages" in sig.parameters

    def test_stateless_driver_generate_returns_driver_response(self):
        """StatelessDriver.generate return type is DriverResponse."""
        from amelia.drivers.base import StatelessDriver, DriverResponse
        import typing

        hints = typing.get_type_hints(StatelessDriver.generate)
        assert hints.get("return") == DriverResponse
```

**Verify:**
```bash
uv run pytest tests/unit/test_driver_factory.py -k "DriverResponse or TokenUsage or StatelessDriver" -v
```

**Commit:**
```bash
git add amelia/drivers/base.py tests/unit/test_driver_factory.py
git commit -m "feat(drivers): add frozen DriverResponse and StatelessDriver protocol"
```

---

## Wave 3: State Utilities

### Task E: Create state_utils.py with all helpers

**WAIT_FOR:** Task C (needs frozen state models)

**Files:**
- Create: `amelia/core/state_utils.py`
- Create: `tests/unit/test_state_utils.py`

**Implementation - amelia/core/state_utils.py:**

```python
"""Pure helper functions for immutable state updates.

These functions return partial update dicts or new model instances.
They never mutate their inputs. Use these in LangGraph nodes to
create partial state updates that are safe for parallel execution.

Example usage in a node:
    async def developer_node(state: ExecutionState) -> dict:
        # ... do work ...
        return task_completed(task.id, output)
"""
from datetime import datetime
from amelia.core.state import TaskResult, HistoryEntry, DriverSession


def task_started(task_id: str) -> dict:
    """Return partial update for starting a task.

    Args:
        task_id: ID of the task to start.

    Returns:
        Dict with task_results and history updates.

    Example:
        return task_started(task.id)
    """
    return {
        "task_results": {task_id: TaskResult(task_id=task_id, status="in_progress")},
        "history": [HistoryEntry(actor="developer", event="task_started", detail={"task_id": task_id})],
    }


def task_completed(task_id: str, output: str) -> dict:
    """Return partial update for completing a task.

    Args:
        task_id: ID of the completed task.
        output: Output/result from the task execution.

    Returns:
        Dict with task_results, history, and completed_steps updates.

    Example:
        return task_completed(task.id, result.output)
    """
    return {
        "task_results": {task_id: TaskResult(
            task_id=task_id,
            status="completed",
            output=output,
            completed_at=datetime.utcnow(),
        )},
        "history": [HistoryEntry(actor="developer", event="task_completed", detail={"task_id": task_id})],
        "completed_steps": {f"task:{task_id}"},
    }


def task_failed(task_id: str, error: str) -> dict:
    """Return partial update for a failed task.

    Args:
        task_id: ID of the failed task.
        error: Error message describing the failure.

    Returns:
        Dict with task_results and history updates.

    Example:
        return {**task_failed(task.id, str(e)), "workflow_status": "failed"}
    """
    return {
        "task_results": {task_id: TaskResult(task_id=task_id, status="failed", error=error)},
        "history": [HistoryEntry(actor="developer", event="task_failed", detail={"task_id": task_id, "error": error})],
    }


def set_driver_session(scope: str, session: DriverSession) -> dict:
    """Return partial update for driver session (scoped by agent).

    Args:
        scope: Agent/node scope for the session (e.g., "developer", "reviewer").
        session: Updated driver session.

    Returns:
        Dict with driver_sessions update.

    Example:
        return set_driver_session("developer", response.session)
    """
    return {"driver_sessions": {scope: session}}
```

**Tests - tests/unit/test_state_utils.py:**

```python
"""Tests for state utility functions."""
import pytest


class TestTaskStarted:
    """Tests for task_started helper."""

    def test_returns_partial_update(self):
        """task_started returns dict with task_results and history."""
        from amelia.core.state_utils import task_started

        update = task_started("task-1")

        assert "task_results" in update
        assert "task-1" in update["task_results"]
        assert update["task_results"]["task-1"].status == "in_progress"
        assert "history" in update
        assert len(update["history"]) == 1
        assert update["history"][0].event == "task_started"

    def test_task_started_history_entry(self):
        """task_started creates HistoryEntry with correct details."""
        from amelia.core.state_utils import task_started

        update = task_started("task-1")
        entry = update["history"][0]

        assert entry.actor == "developer"
        assert entry.event == "task_started"
        assert entry.detail["task_id"] == "task-1"


class TestTaskCompleted:
    """Tests for task_completed helper."""

    def test_returns_partial_update(self):
        """task_completed returns dict with task_results, history, completed_steps."""
        from amelia.core.state_utils import task_completed

        update = task_completed("task-1", "Task output here")

        assert "task_results" in update
        assert "task-1" in update["task_results"]
        assert update["task_results"]["task-1"].status == "completed"
        assert update["task_results"]["task-1"].output == "Task output here"
        assert "history" in update
        assert "completed_steps" in update
        assert "task:task-1" in update["completed_steps"]

    def test_task_completed_sets_timestamp(self):
        """task_completed sets completed_at timestamp."""
        from amelia.core.state_utils import task_completed

        update = task_completed("task-1", "Done")
        result = update["task_results"]["task-1"]

        assert result.completed_at is not None

    def test_task_completed_history_entry(self):
        """task_completed creates HistoryEntry with correct details."""
        from amelia.core.state_utils import task_completed

        update = task_completed("task-1", "Done")
        entry = update["history"][0]

        assert entry.actor == "developer"
        assert entry.event == "task_completed"
        assert entry.detail["task_id"] == "task-1"


class TestTaskFailed:
    """Tests for task_failed helper."""

    def test_returns_partial_update(self):
        """task_failed returns dict with failed status and error in task_results."""
        from amelia.core.state_utils import task_failed

        update = task_failed("task-1", "Something went wrong")

        assert "task_results" in update
        assert update["task_results"]["task-1"].status == "failed"
        assert update["task_results"]["task-1"].error == "Something went wrong"
        assert "history" in update

    def test_task_failed_history_entry(self):
        """task_failed creates HistoryEntry with error details."""
        from amelia.core.state_utils import task_failed

        update = task_failed("task-1", "Error message")
        entry = update["history"][0]

        assert entry.actor == "developer"
        assert entry.event == "task_failed"
        assert entry.detail["task_id"] == "task-1"
        assert entry.detail["error"] == "Error message"


class TestSetDriverSession:
    """Tests for set_driver_session helper."""

    def test_returns_partial_update(self):
        """set_driver_session returns dict with scoped session."""
        from amelia.core.state_utils import set_driver_session
        from amelia.core.types import DriverSession

        session = DriverSession(conversation_id="conv-123")
        update = set_driver_session("developer", session)

        assert "driver_sessions" in update
        assert "developer" in update["driver_sessions"]
        assert update["driver_sessions"]["developer"].conversation_id == "conv-123"

    def test_scopes_by_agent(self):
        """set_driver_session uses scope parameter as dict key."""
        from amelia.core.state_utils import set_driver_session
        from amelia.core.types import DriverSession

        session = DriverSession(conversation_id="conv-456")
        update = set_driver_session("reviewer", session)

        assert "reviewer" in update["driver_sessions"]
        assert update["driver_sessions"]["reviewer"].conversation_id == "conv-456"
```

**Verify:**
```bash
uv run pytest tests/unit/test_state_utils.py -v
```

**Commit:**
```bash
git add amelia/core/state_utils.py tests/unit/test_state_utils.py
git commit -m "feat(state_utils): add pure helper functions for immutable state updates"
```

---

## Wave 4: Integration

### Task F: Refactor orchestrator with state helpers and checkpointer

**WAIT_FOR:** Task E (needs state_utils helpers)

**Files:**
- Modify: `amelia/core/orchestrator.py`
- Modify: `tests/unit/test_orchestrator_developer_node.py`
- Modify: `tests/unit/test_orchestrator_interrupt.py`

**Implementation - amelia/core/orchestrator.py:**

1. Add imports at top:

```python
from langgraph.checkpoint.base import BaseCheckpointSaver
from amelia.core.state_utils import with_task_status, task_started, task_completed, task_failed
```

2. Update `call_developer_node` to use state helpers and scoped sessions:

```python
from langchain_core.runnables import RunnableConfig

async def call_developer_node(state: ExecutionState, config: RunnableConfig) -> dict[str, Any]:
    """Orchestrator node for the Developer agent to execute tasks.

    Executes ready tasks using pure state helpers for immutable updates.
    Returns partial dict for LangGraph state merge.

    Args:
        state: Current execution state containing the plan and tasks.
        config: LangGraph config containing profile in configurable.

    Returns:
        Partial state dict with task results (task_results, history, etc.).
    """
    from amelia.core.state_utils import task_started, task_completed, task_failed, set_driver_session

    profile: Profile = config["configurable"]["profile"]
    logger.info("Orchestrator: Calling Developer to execute tasks.")

    if not state.plan or not state.plan.tasks:
        logger.info("Orchestrator: No plan or tasks to execute.")
        return {}

    ready_tasks = state.get_ready_tasks()  # Method on ExecutionState now

    if not ready_tasks:
        logger.info("Orchestrator: No ready tasks found to execute in this iteration.")
        return {}

    logger.info(f"Orchestrator: Executing {len(ready_tasks)} ready tasks.")

    # Get scoped driver session for this agent
    session = state.driver_sessions.get("developer", DriverSession())

    driver = DriverFactory.get_driver(profile.driver)
    developer = Developer(driver, execution_mode=profile.execution_mode)

    # Accumulate updates
    updates: dict[str, Any] = {}

    for task in ready_tasks:
        logger.info(f"Orchestrator: Developer executing task {task.id}")

        # Mark as started
        updates = {**updates, **task_started(task.id)}

        try:
            # Execute task
            result = await developer.execute_current_task(state, task)

            if result.get("status") == "completed":
                output_content = result.get("output", "No output")
                updates = {**updates, **task_completed(task.id, output_content)}
                logger.info("Task completed", task_id=task.id, output=output_content)

                # Update session if returned
                if "session" in result:
                    updates = {**updates, **set_driver_session("developer", result["session"])}
            else:
                error_msg = result.get("error", "Unknown")
                updates = {**updates, **task_failed(task.id, error_msg)}
                logger.error("Task failed", task_id=task.id, error=error_msg)

        except Exception as e:
            updates = {**updates, **task_failed(task.id, str(e))}
            logger.error(f"Task {task.id} failed: {e}")

            # Fail fast in agentic mode
            if profile.execution_mode == "agentic":
                return {**updates, "workflow_status": "failed"}

    return updates
```

3. Update `create_orchestrator_graph` to accept checkpointer:

```python
def create_orchestrator_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledGraph:
    """Create the orchestrator state graph.

    Args:
        checkpointer: Optional checkpointer for persistence and time-travel debugging.
            Use MemorySaver for development, SqliteSaver for production.

    Returns:
        Compiled LangGraph state machine.
    """
    builder = StateGraph(ExecutionState)

    # Add nodes
    builder.add_node("architect", call_architect_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("developer", call_developer_node)
    builder.add_node("reviewer", call_reviewer_node)

    # Add edges
    builder.add_edge(START, "architect")
    builder.add_conditional_edges(
        "architect",
        route_approval,
        {"needs_approval": "human_approval", "approved": "developer"},
    )
    builder.add_conditional_edges(
        "human_approval",
        route_approval,
        {"approved": "developer", "rejected": END},
    )
    builder.add_conditional_edges(
        "developer",
        should_continue_developer,
        {"continue": "reviewer", "done": END, "failed": END},
    )
    builder.add_conditional_edges(
        "reviewer",
        should_continue_review_loop,
        {"continue": "developer", "approved": END},
    )

    return builder.compile(checkpointer=checkpointer)
```

4. Add `get_state_history` helper function:

```python
def get_state_history(graph: CompiledGraph, thread_id: str) -> list:
    """Get state history for time-travel debugging.

    Args:
        graph: Compiled orchestrator graph with checkpointer.
        thread_id: Thread identifier for the execution.

    Returns:
        List of historical state snapshots (newest first).

    Example:
        history = get_state_history(graph, "issue-123")
        for snapshot in history:
            print(f"State at {snapshot.created_at}: {snapshot.values}")
    """
    config = {"configurable": {"thread_id": thread_id}}
    return list(graph.get_state_history(config))
```

**Tests - tests/unit/test_orchestrator_developer_node.py:**

Add to existing file:

```python
class TestDeveloperNodeStateless:
    """Tests for stateless developer node behavior."""

    async def test_developer_node_returns_partial_dict(
        self,
        mock_profile_work,
        mock_task_factory,
        mock_task_dag_factory,
        mock_execution_state_factory,
        mock_async_driver_factory,
        mocker,
    ):
        """Developer node returns partial dict update, not full state."""
        from amelia.core.orchestrator import call_developer_node

        task = mock_task_factory(id="task-1")
        dag = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(plan=dag)
        config = {"configurable": {"profile": mock_profile_work}}

        mock_driver = mock_async_driver_factory(
            generate_return={"status": "completed", "output": "Done"}
        )
        mocker.patch(
            "amelia.core.orchestrator.DriverFactory.get_driver",
            return_value=mock_driver,
        )
        mocker.patch(
            "amelia.agents.developer.Developer.execute_current_task",
            return_value={"status": "completed", "output": "Done"},
        )

        result = await call_developer_node(state, config)

        # Verify partial dict returned with task_results
        assert isinstance(result, dict)
        assert "task_results" in result
        # Should NOT contain profile (that's in config, not state)
        assert "profile" not in result
        assert "issue" not in result

    async def test_developer_node_includes_history(
        self,
        mock_profile_work,
        mock_task_factory,
        mock_task_dag_factory,
        mock_execution_state_factory,
        mock_async_driver_factory,
        mocker,
    ):
        """Developer node includes history for Annotated reducer."""
        from amelia.core.orchestrator import call_developer_node

        task = mock_task_factory(id="task-1")
        dag = mock_task_dag_factory(tasks=[task])
        state = mock_execution_state_factory(plan=dag)
        config = {"configurable": {"profile": mock_profile_work}}

        mock_driver = mock_async_driver_factory(
            generate_return={"status": "completed", "output": "Task output"}
        )
        mocker.patch(
            "amelia.core.orchestrator.DriverFactory.get_driver",
            return_value=mock_driver,
        )
        mocker.patch(
            "amelia.agents.developer.Developer.execute_current_task",
            return_value={"status": "completed", "output": "Task output"},
        )

        result = await call_developer_node(state, config)

        assert "history" in result
        assert isinstance(result["history"], list)
        assert len(result["history"]) > 0

    async def test_developer_node_uses_scoped_session(
        self,
        mock_profile_work,
        mock_task_factory,
        mock_task_dag_factory,
        mock_execution_state_factory,
        mock_async_driver_factory,
        mocker,
    ):
        """Developer node retrieves scoped driver session."""
        from amelia.core.orchestrator import call_developer_node
        from amelia.core.types import DriverSession

        task = mock_task_factory(id="task-1")
        dag = mock_task_dag_factory(tasks=[task])
        session = DriverSession(conversation_id="dev-conv-123")
        state = mock_execution_state_factory(plan=dag, driver_sessions={"developer": session})
        config = {"configurable": {"profile": mock_profile_work}}

        mock_driver = mock_async_driver_factory(
            generate_return={"status": "completed", "output": "Done"}
        )
        mocker.patch(
            "amelia.core.orchestrator.DriverFactory.get_driver",
            return_value=mock_driver,
        )
        mocker.patch(
            "amelia.agents.developer.Developer.execute_current_task",
            return_value={"status": "completed", "output": "Done"},
        )

        result = await call_developer_node(state, config)

        # Session should be retrieved from state.driver_sessions["developer"]
        assert "task_results" in result
```

**Tests - tests/unit/test_orchestrator_interrupt.py:**

Add to existing file:

```python
class TestOrchestratorCheckpointer:
    """Tests for checkpointer integration."""

    def test_create_orchestrator_graph_accepts_checkpointer(self):
        """create_orchestrator_graph accepts optional checkpointer."""
        from amelia.core.orchestrator import create_orchestrator_graph
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        graph = create_orchestrator_graph(checkpointer=checkpointer)

        assert graph is not None

    def test_create_orchestrator_graph_without_checkpointer(self):
        """create_orchestrator_graph works without checkpointer."""
        from amelia.core.orchestrator import create_orchestrator_graph

        graph = create_orchestrator_graph()

        assert graph is not None

    def test_get_state_history_returns_list(self):
        """get_state_history returns list of states."""
        from amelia.core.orchestrator import create_orchestrator_graph, get_state_history
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        graph = create_orchestrator_graph(checkpointer=checkpointer)

        history = get_state_history(graph, "test-thread-123")

        # Empty history for new thread is valid
        assert isinstance(history, list)
```

**Verify:**
```bash
uv run pytest tests/unit/test_orchestrator_developer_node.py tests/unit/test_orchestrator_interrupt.py -v
```

**Commit:**
```bash
git add amelia/core/orchestrator.py tests/unit/test_orchestrator_developer_node.py tests/unit/test_orchestrator_interrupt.py
git commit -m "refactor(orchestrator): use state helpers and add checkpointer support"
```

---

## Wave 5: Cleanup and Validation

### Task G: Update exports and run full validation

**WAIT_FOR:** Tasks A, B, C, D, E, F (all previous tasks)

**Files:**
- Modify: `amelia/core/__init__.py`
- Modify: `amelia/drivers/__init__.py`

**Implementation - amelia/core/__init__.py:**

Add new exports:

```python
from amelia.core.state_utils import (
    with_task_status,
    task_started,
    task_completed,
    task_failed,
)
from amelia.core.orchestrator import get_state_history

# Add to __all__ if it exists, or ensure they're importable
```

**Implementation - amelia/drivers/__init__.py:**

Add new exports:

```python
from amelia.drivers.base import (
    DriverInterface,
    DriverResponse,
    StatelessDriver,
    TokenUsage,
)
```

**Validation Steps:**

1. Run type checker:
```bash
uv run mypy amelia
```

2. Run linter:
```bash
uv run ruff check amelia tests
uv run ruff check --fix amelia tests
```

3. Run full test suite:
```bash
uv run pytest
```

4. Verify imports work:
```bash
uv run python -c "from amelia.core import with_task_status, task_completed; print('Core imports OK')"
uv run python -c "from amelia.drivers import DriverResponse, StatelessDriver; print('Driver imports OK')"
uv run python -c "from amelia.core.types import DriverSession; print('Types imports OK')"
```

**Commit:**
```bash
git add -A
git commit -m "chore: export new stateless types and validate implementation"
```

---

## Execution Summary

| Wave | Tasks | Parallel Subagents | Dependencies |
|------|-------|-------------------|--------------|
| **1** | A, B | 2 | None |
| **2** | C, D | 2 | Wave 1 (A only) |
| **3** | E | 1 | Wave 2 (C only) |
| **4** | F | 1 | Wave 3 |
| **5** | G | 1 | All previous |

**Total: 7 tasks, 5 waves, max 2 parallel subagents**

**Critical Path:** A → C → E → F → G (5 sequential steps)
**Parallel Gain:** B runs with A; D runs with C

## Success Criteria

- [ ] All Pydantic models have `frozen=True` (or `model_config = ConfigDict(frozen=True)`)
- [ ] All nodes return `dict` partial updates
- [ ] Task status derived from `task_results`, not stored in `Task.status`
- [ ] Driver sessions scoped by agent in `driver_sessions` dict
- [ ] `profile_id` stored in state for replay determinism
- [ ] `completed_steps` set tracks idempotency
- [ ] Custom reducers (`dict_merge`, `set_union`) defined
- [ ] `get_ready_tasks()` is a method on ExecutionState
- [ ] List fields use `Annotated[list, add]` for parallel safety
- [ ] Dict fields use `Annotated[dict, dict_merge]` for parallel safety
- [ ] Set fields use `Annotated[set, set_union]` for parallel safety
- [ ] All nodes access Profile via `config["configurable"]["profile"]`
- [ ] ExecutionState has no `profile` field (only `profile_id`)
- [ ] `get_state_history()` works for time-travel debugging
- [ ] `uv run mypy amelia` passes
- [ ] `uv run ruff check amelia tests` passes
- [ ] `uv run pytest` passes (all tests green)
