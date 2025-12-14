# Stateless Reducer Pattern Design

> Addressing Factor 12 (Stateless Reducer) from the 12-Factor Agents methodology.
> Aligned with LangGraph v1.0+ best practices.

## Problem Statement

Amelia currently has mutable state patterns that violate the Stateless Reducer principle:

1. **In-place mutations**: `state.plan.tasks[idx].status = "completed"`
2. **Hidden driver state**: CLI/API sessions maintain state between calls
3. **Shell state**: Working directory tracked implicitly in subprocess

These patterns prevent:

- Time-travel debugging and replay
- Safe parallel workflow execution
- Stateless cloud deployment

## Critical Review Findings

An external review identified these critical issues with the initial design:

1. **Partial dict updates alone don't prevent lost updates** - Non-reduced fields still have last-write-wins per key. Fields like `task_outputs` using `{**state.task_outputs, ...}` can lose concurrent updates.

2. **Single DriverSession is not parallel-safe** - If multiple nodes call the driver concurrently, they race on a single session. Must scope sessions by agent/node.

3. **Replay determinism incomplete** - Moving Profile to configurable means checkpoints don't capture what profile was used. Need `profile_id` in state.

4. **Task status mutation anti-pattern** - Mutating `Task.status` in place violates immutability. Task status should be derived from a separate `task_results` dict.

These findings led to the hardened schema below.

## Design Principles

1. **LangGraph-native**: Leverage framework capabilities, don't reinvent
2. **Minimal custom code**: State helpers, not complex abstractions
3. **Partial updates**: Nodes return `dict`, never full state

## Design Decisions

### 1. Node Return Type: Partial Updates (dict)

**Critical**: Nodes must return **partial update dicts**, not full state objects.

Returning full state causes "Last Write Wins" race conditions when parallel nodes execute:

```python
# ANTI-PATTERN - violates parallelism safety
async def developer_node(state: ExecutionState) -> ExecutionState:
    # If reviewer runs in parallel, one overwrites the other
    return state.model_copy(update={...})

# CORRECT - safe for parallel execution
async def developer_node(state: ExecutionState) -> dict:
    # LangGraph merges partial updates automatically
    return {"plan": new_plan, "task_outputs": new_outputs}
```

### 2. Immutability: Pydantic Frozen Models

All state models become frozen with immutable updates via `.model_copy()`:

```python
# Before (mutable)
class Task(BaseModel):
    status: Literal["pending", "in_progress", "completed", "failed"]

state.plan.tasks[0].status = "completed"  # Mutation!

# After (immutable)
class Task(BaseModel, frozen=True):
    status: Literal["pending", "in_progress", "completed", "failed"]

# Raises FrozenInstanceError - caught at development time
state.plan.tasks[0].status = "completed"
```

### 3. Parallel-Safe State Definition

Use `Annotated` with reducers for fields that multiple parallel nodes may write to.

**Note**: Custom reducers (`dict_merge`, `set_union`) are required for parallel-safe merging beyond the built-in `add` reducer.

```python
# amelia/core/state.py
from __future__ import annotations
from datetime import datetime
from operator import add
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field

# Reducers for parallel-safe merging
def dict_merge(left: dict, right: dict) -> dict:
    """Shallow merge: right wins on key conflicts. Safe when keys are disjoint."""
    return {**(left or {}), **(right or {})}

def set_union(left: set, right: set) -> set:
    return (left or set()) | (right or set())


class TaskResult(BaseModel):
    """Result of executing a task. Stored in task_results dict."""
    model_config = ConfigDict(frozen=True)

    task_id: str
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"]
    output: str | None = None
    error: str | None = None
    completed_at: datetime | None = None


class DriverSession(BaseModel):
    """Session state for driver continuity. Scoped by agent/node."""
    model_config = ConfigDict(frozen=True)

    conversation_id: str | None = None
    model: str = "claude-sonnet-4-20250514"
    data: dict[str, Any] = Field(default_factory=dict)


class HistoryEntry(BaseModel):
    """Structured history entry for agent actions."""
    model_config = ConfigDict(frozen=True)

    ts: datetime = Field(default_factory=datetime.utcnow)
    actor: str  # agent/node name
    event: str  # e.g., "task_started", "review_completed"
    detail: dict[str, Any] = Field(default_factory=dict)


class ExecutionState(BaseModel):
    """Parallel-safe state for LangGraph orchestration.

    Design principles:
    - All models frozen=True (immutable)
    - Multi-writer fields have reducers (Annotated)
    - Profile accessed via config["configurable"]["profile"]
    - Task status derived from task_results, not mutated in plan

    Concurrency model:
    - task_results keys are disjoint (each task_id written by one node)
    - driver_sessions scoped by agent name (no shared session)
    - history append-only (safe under parallel execution)
    """
    model_config = ConfigDict(frozen=True)

    # --- Replay/identity metadata ---
    profile_id: str = ""  # Fingerprint of profile for replay audit

    # --- Domain data (single-writer, set during planning) ---
    issue: Issue | None = None
    design: Design | None = None
    plan: TaskDAG | None = None  # Immutable after Architect creates it

    # --- Task execution (parallel-safe via dict_merge, keys disjoint) ---
    task_results: Annotated[dict[str, TaskResult], dict_merge] = Field(default_factory=dict)

    # --- Driver sessions (scoped by agent, parallel-safe) ---
    driver_sessions: Annotated[dict[str, DriverSession], dict_merge] = Field(default_factory=dict)

    # --- Append-only logs (parallel-safe via add reducer) ---
    history: Annotated[list[HistoryEntry], add] = Field(default_factory=list)

    # --- Idempotency (tracks completed steps for replay) ---
    completed_steps: Annotated[set[str], set_union] = Field(default_factory=set)

    # --- Single-writer fields (no reducer needed) ---
    last_review: ReviewResult | None = None
    human_approved: bool | None = None
    workflow_status: Literal["running", "completed", "failed"] = "running"

    # --- Derived helper ---
    def get_task_status(self, task_id: str) -> str:
        """Get task status from task_results, defaulting to 'pending'."""
        if task_id in self.task_results:
            return self.task_results[task_id].status
        return "pending"
```

### 4. Profile via Configurable (Not State)

Profile contains static configuration that doesn't change during workflow execution. Moving it to LangGraph's `configurable` dictionary enables:

- **Single compiled graph, multiple profiles**: One graph serves simultaneous workflows with different configurations
- **Smaller state history**: Checkpoints don't redundantly store static config
- **Cleaner separation**: Mutable runtime state vs static configuration

```python
# amelia/core/orchestrator.py
from langchain_core.runnables import RunnableConfig

async def developer_node(state: ExecutionState, config: RunnableConfig) -> dict:
    """Developer agent node. Profile accessed via config, not state."""
    profile: Profile = config["configurable"]["profile"]
    driver = DriverFactory.get_driver(profile.driver)
    # ...

# Invocation with profile in config
config = {
    "configurable": {
        "profile": active_profile,
        "thread_id": f"issue-{issue.id}",
    }
}
result = await graph.ainvoke(initial_state, config=config)
```

### 5. State Helpers

Pure helper functions that calculate partial updates. These are simple utilities, not a complex pattern:

```python
# amelia/core/state_utils.py
from datetime import datetime
from amelia.core.state import TaskResult, HistoryEntry, DriverSession


def task_started(task_id: str) -> dict:
    """Return partial update for starting a task."""
    return {
        "task_results": {task_id: TaskResult(task_id=task_id, status="in_progress")},
        "history": [HistoryEntry(actor="developer", event="task_started", detail={"task_id": task_id})],
    }


def task_completed(task_id: str, output: str) -> dict:
    """Return partial update for completing a task."""
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
    """Return partial update for a failed task."""
    return {
        "task_results": {task_id: TaskResult(task_id=task_id, status="failed", error=error)},
        "history": [HistoryEntry(actor="developer", event="task_failed", detail={"task_id": task_id, "error": error})],
    }


def set_driver_session(scope: str, session: DriverSession) -> dict:
    """Return partial update for driver session (scoped by agent)."""
    return {"driver_sessions": {scope: session}}
```

### 6. Stateless Drivers

Drivers become pure functions with session state passed explicitly:

```python
# amelia/drivers/base.py
from amelia.core.types import DriverSession  # Import from core/types.py

class DriverResponse(BaseModel, frozen=True):
    """Immutable response including updated session."""
    content: str
    session: DriverSession
    usage: TokenUsage | None = None


class StatelessDriver(ABC):
    """Stateless driver interface."""

    @abstractmethod
    async def generate(
        self,
        messages: Sequence[AgentMessage],
        session: DriverSession,
        schema: type[BaseModel] | None = None,
    ) -> DriverResponse:
        """Generate response. Returns updated session for continuity."""
        ...
```

### 7. Stateless Shell Executor

Shell commands take explicit working directory:

```python
# amelia/tools/shell.py

class ShellResult(BaseModel, frozen=True):
    stdout: str
    stderr: str
    return_code: int


class StatelessShellExecutor:
    async def run(self, command: str, cwd: Path, timeout: float = 30.0) -> ShellResult:
        """Execute command in specified directory. No hidden state."""
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        return ShellResult(
            stdout=stdout.decode(),
            stderr=stderr.decode(),
            return_code=process.returncode,
        )
```

### 8. Native LangGraph Persistence

Use LangGraph's native checkpointers for all persistence and replay:

```python
# amelia/core/orchestrator.py
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

class Orchestrator:
    def __init__(self, persist: bool = False):
        if persist:
            self.checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
        else:
            self.checkpointer = InMemorySaver()

    def build_graph(self) -> StateGraph:
        builder = StateGraph(ExecutionState)
        builder.add_node("architect", architect_node)
        builder.add_node("developer", developer_node)
        builder.add_node("reviewer", reviewer_node)
        # ... edges ...
        return builder.compile(checkpointer=self.checkpointer)

    def get_history(self, thread_id: str):
        """Time-travel debugging via native LangGraph API."""
        config = {"configurable": {"thread_id": thread_id}}
        return list(self.graph.get_state_history(config))
```

### 9. Node Implementation

Standard node functions - no wrappers, no decorators:

```python
# amelia/core/orchestrator.py
from langchain_core.runnables import RunnableConfig

async def developer_node(state: ExecutionState, config: RunnableConfig) -> dict:
    """Developer agent node. Returns partial update dict."""
    from amelia.core.state_utils import task_started, task_completed, task_failed, set_driver_session

    profile: Profile = config["configurable"]["profile"]
    task = state.get_ready_tasks()[0]  # Now a method on ExecutionState

    # Get scoped driver session
    session = state.driver_sessions.get("developer", DriverSession())

    driver = DriverFactory.get_driver(profile.driver)
    response = await driver.generate(
        messages=build_developer_messages(task),
        session=session,
        schema=DeveloperResponse,
    )

    result = DeveloperResponse.model_validate_json(response.content)

    # Return partial updates with scoped session
    return {
        **task_completed(task.id, result.output),
        **set_driver_session("developer", response.session),
    }
```

## Migration Strategy

### Phase 1: Foundation

1. Modify `amelia/core/state.py`:
   - Add `frozen=True` to all models
   - Add `Annotated[list, add]` to `messages` and `agent_history`

2. Create `amelia/core/state_utils.py`:
   - Simple helper functions returning `dict`

### Phase 2: Node Refactor

1. Update all nodes in `amelia/core/orchestrator.py`:
   - Change return type to `dict`
   - Use state helpers for updates

### Phase 3: Driver & Tools

1. Implement `StatelessDriver` interface
2. Refactor drivers to accept/return session
3. Refactor shell to accept explicit cwd

### Phase 4: Persistence

1. Add `SqliteSaver` option to orchestrator
2. Add CLI command: `amelia history --thread <id>`

## Files to Modify

| File | Changes |
|------|---------|
| `amelia/core/state.py` | Add `TaskResult`, `HistoryEntry`, frozen models, reducers, remove `Task.status` |
| `amelia/core/state_utils.py` | Update helpers to use `task_results` pattern |
| `amelia/core/orchestrator.py` | Nodes use `state.get_ready_tasks()`, scoped sessions |
| `amelia/drivers/base.py` | Stateless driver interface with `DriverResponse` |
| `amelia/drivers/cli_driver.py` | Implement stateless pattern |
| `amelia/drivers/api_driver.py` | Implement stateless pattern |
| `amelia/tools/shell.py` | Accept explicit cwd parameter |

## Summary

| Concept | Pattern |
|---------|---------|
| **Node Return** | `dict` (partial update) |
| **Task Status** | Derived from `task_results` dict, not stored in Task |
| **Driver Sessions** | Scoped: `driver_sessions: dict[str, DriverSession]` |
| **Parallelism** | `Annotated` with `add`, `dict_merge`, `set_union` reducers |
| **Replay Safety** | `profile_id` + `completed_steps` set |
| **Profile Config** | `config["configurable"]["profile"]` |
| **Persistence** | Native LangGraph checkpointer |

## Success Criteria

- [ ] All Pydantic models have `frozen=True`
- [ ] All nodes return `dict` partial updates
- [ ] All nodes access Profile via `config["configurable"]["profile"]`
- [ ] Task status derived from `task_results`, not stored in `Task.status`
- [ ] Driver sessions scoped by agent in `driver_sessions` dict
- [ ] `profile_id` stored in state for replay determinism
- [ ] `completed_steps` set tracks idempotency
- [ ] Custom reducers (`dict_merge`, `set_union`) defined and used
- [ ] List fields use `Annotated[list, add]` for parallel safety
- [ ] `graph.get_state_history()` works for replay
- [ ] Parallel workflow tests pass without race conditions
