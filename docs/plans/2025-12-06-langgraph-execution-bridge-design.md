# LangGraph Execution Bridge Design

> **Status:** Approved (Revised)
> **Date:** 2025-12-06
> **Author:** Claude + Human collaboration
> **Revision:** Simplified checkpointing, retry config, added execution mode handling

## Overview

This design connects the server layer (FastAPI, SQLite, REST endpoints) to the existing core LangGraph orchestrator, implementing the missing `_run_workflow()` method in `OrchestratorService`.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Server Layer                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ REST API     │───▶│ Orchestrator │───▶│ EventBus     │──▶ WS │
│  │ (FastAPI)    │    │ Service      │    │              │       │
│  └──────────────┘    └──────┬───────┘    └──────────────┘       │
│                             │                                    │
│                    ┌────────▼────────┐                          │
│                    │ ExecutionBridge │  ◀── NEW (method)        │
│                    └────────┬────────┘                          │
│                             │                                    │
│                    ┌────────▼────────┐                          │
│                    │ langgraph-      │  ◀── PACKAGE             │
│                    │ checkpoint-     │                          │
│                    │ sqlite          │                          │
│                    └────────┬────────┘                          │
└─────────────────────────────┼───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                         Core Layer                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ LangGraph State Machine (existing)                        │   │
│  │ architect_node → human_approval → developer ↔ reviewer    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Components:**
- `ExecutionBridge` - Method in OrchestratorService that invokes LangGraph, handles interrupts, streams events
- `langgraph-checkpoint-sqlite` - Official LangGraph package for checkpoint persistence
- State composition - `ServerExecutionState.execution_state: ExecutionState`

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Human approval | Interrupt-based (`interrupt_before`) | LangGraph native, keeps core clean |
| Checkpoint persistence | `langgraph-checkpoint-sqlite` package | Battle-tested, handles serialization/migrations |
| State model | Composition (wrap `ExecutionState`) | Preserves architectural boundary |
| Event streaming | Map LangGraph → WorkflowEvent | Stable dashboard interface |
| Error handling | Auto-retry with exponential backoff | Resilience for transient failures |
| Retry config | Simplified (max_retries + base_delay) | Error classification is implementation concern, not config |
| CLI vs Server | Execution mode in graph config | Same graph code, different approval behavior |

## State Model

`ServerExecutionState` wraps `ExecutionState` via composition:

```python
class ServerExecutionState(BaseModel):
    # Server metadata
    id: str
    issue_id: str
    worktree_path: str
    worktree_name: str  # Derived from path
    workflow_status: WorkflowStatus = WorkflowStatus.PENDING
    started_at: datetime
    completed_at: datetime | None = None
    current_stage: str = "initializing"
    failure_reason: str | None = None

    # Core orchestration state - always present
    execution_state: ExecutionState
```

**Initialization:** All fields populated at workflow creation. Issue fetched immediately, `worktree_name` derived from path. No nullable fields except `completed_at` and `failure_reason`.

## Checkpoint Persistence

Use the official `langgraph-checkpoint-sqlite` package instead of custom implementation.

**Installation:**
```bash
uv add langgraph-checkpoint-sqlite
```

**Usage:**
```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Create checkpointer with dedicated file (separate from main DB)
checkpointer = AsyncSqliteSaver.from_conn_string("~/.amelia/checkpoints.db")

# Or share connection with existing database
async with aiosqlite.connect("~/.amelia/amelia.db") as conn:
    checkpointer = AsyncSqliteSaver(conn)
    graph = create_orchestrator_graph(checkpoint_saver=checkpointer)
```

**Why package over custom:**
- Handles checkpoint serialization (pickle with fallbacks)
- Manages schema migrations automatically
- Provides TTL-based cleanup via `AsyncSqliteSaver.setup(ttl=timedelta(days=7))`
- ~150 lines of code we don't need to write/test/maintain

**Thread ID:** Maps to `workflow_id` for checkpoint isolation.

## CLI vs Server Execution Mode

The same graph must work for both CLI (blocking `typer.confirm`) and server (interrupt-based) contexts.

**Solution:** Pass execution mode via graph config, check in `human_approval_node`:

```python
# In amelia/core/orchestrator.py

def human_approval_node(state: ExecutionState, config: RunnableConfig) -> ExecutionState:
    """Handle human approval - behavior depends on execution mode."""

    execution_mode = config.get("configurable", {}).get("execution_mode", "cli")

    if execution_mode == "cli":
        # CLI mode: blocking prompt
        if state.plan:
            display_plan(state.plan)
        approved = typer.confirm("Do you approve this plan?", default=False)
        return state.model_copy(update={"human_approved": approved})

    else:
        # Server mode: approval comes from resumed state after interrupt
        # If human_approved is already set (from resume), use it
        # Otherwise, just return - the interrupt mechanism will pause here
        return state
```

**Graph creation with mode:**
```python
# CLI usage (existing)
config = {
    "configurable": {
        "thread_id": "cli-session",
        "execution_mode": "cli",
    }
}
result = await graph.ainvoke(initial_state, config=config)

# Server usage (new)
config = {
    "configurable": {
        "thread_id": workflow_id,
        "execution_mode": "server",
    }
}
async for event in graph.astream_events(
    state.execution_state,
    config=config,
    interrupt_before=["human_approval_node"],
):
    await self._handle_graph_event(workflow_id, event)
```

## Execution Bridge

The `_run_workflow()` implementation:

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Nodes that emit stage events
STAGE_NODES = frozenset({
    "architect_node",
    "human_approval_node",
    "developer_node",
    "reviewer_node",
})

async def _run_workflow(
    self,
    workflow_id: str,
    state: ServerExecutionState,
) -> None:
    """Execute workflow via LangGraph with interrupt support."""

    # 1. Create graph with checkpointer
    async with AsyncSqliteSaver.from_conn_string(
        str(self._checkpoint_path)
    ) as checkpointer:
        graph = create_orchestrator_graph(checkpoint_saver=checkpointer)

        # 2. Configure for server execution
        config = {
            "configurable": {
                "thread_id": workflow_id,
                "execution_mode": "server",
            }
        }

        # 3. Stream execution with event emission
        try:
            async for event in graph.astream_events(
                state.execution_state,
                config=config,
                interrupt_before=["human_approval_node"],
            ):
                await self._handle_graph_event(workflow_id, event)

        except GraphInterrupt:
            # Human approval required - checkpoint saved automatically
            await self._emit_approval_required(workflow_id, state)
            return  # Execution pauses here

        except Exception as e:
            await self._handle_execution_error(workflow_id, e)
            raise
```

## Human Approval Flow

```
1. Graph reaches human_approval_node
   └─▶ GraphInterrupt raised (checkpoint saved automatically)
   └─▶ _run_workflow() catches, emits APPROVAL_REQUIRED event
   └─▶ Workflow status → BLOCKED

2. Dashboard shows approval UI
   └─▶ User clicks Approve/Reject

3. REST API called
   └─▶ POST /workflows/{id}/approve  (or /reject)
   └─▶ OrchestratorService.approve_workflow()

4. Resume from checkpoint
   └─▶ Load checkpoint, update state.human_approved = True/False
   └─▶ graph.ainvoke(None, config)  # Resume with updated state
   └─▶ Graph continues to developer_node (or END if rejected)
```

**Resume implementation:**
```python
async def approve_workflow(self, workflow_id: str) -> None:
    """Resume workflow after approval."""
    async with AsyncSqliteSaver.from_conn_string(
        str(self._checkpoint_path)
    ) as checkpointer:
        graph = create_orchestrator_graph(checkpoint_saver=checkpointer)

        config = {
            "configurable": {
                "thread_id": workflow_id,
                "execution_mode": "server",
            }
        }

        # Update state with approval decision
        await graph.aupdate_state(
            config,
            {"human_approved": True},
        )

        # Resume execution
        async for event in graph.astream_events(None, config=config):
            await self._handle_graph_event(workflow_id, event)
```

## Event Streaming

Map LangGraph events to existing WorkflowEvents:

```python
from amelia.server.models.events import EventType

async def _handle_graph_event(
    self,
    workflow_id: str,
    event: dict,
) -> None:
    """Translate LangGraph events to WorkflowEvents and emit."""

    event_type = event.get("event")
    node_name = event.get("name")

    if event_type == "on_chain_start":
        if node_name in STAGE_NODES:
            await self._emit(
                workflow_id,
                EventType.STAGE_STARTED,
                f"Starting {node_name}",
                data={"stage": node_name},
            )

    elif event_type == "on_chain_end":
        if node_name in STAGE_NODES:
            await self._emit(
                workflow_id,
                EventType.STAGE_COMPLETED,
                f"Completed {node_name}",
                data={"stage": node_name, "output": event.get("data")},
            )

    elif event_type == "on_chain_error":
        error = event.get("data", {}).get("error", "Unknown error")
        await self._emit(
            workflow_id,
            EventType.SYSTEM_ERROR,
            f"Error in {node_name}: {error}",
            data={"stage": node_name, "error": str(error)},
        )

    elif event_type == "on_llm_stream":
        # Only emit in verbose mode to avoid flooding
        if self._verbose_mode.get(workflow_id, False):
            chunk = event.get("data", {}).get("chunk", "")
            if chunk:
                await self._emit(
                    workflow_id,
                    EventType.SYSTEM_INFO,  # Or add LLM_TOKEN to EventType
                    chunk,
                    data={"type": "llm_token"},
                )
```

**Event mapping:**

| LangGraph Event | WorkflowEvent | When |
|-----------------|---------------|------|
| `on_chain_start` | `STAGE_STARTED` | Node begins |
| `on_chain_end` | `STAGE_COMPLETED` | Node finishes |
| `on_chain_error` | `SYSTEM_ERROR` | Node fails |
| `on_llm_stream` | `SYSTEM_INFO` | Verbose mode only |
| `GraphInterrupt` | `APPROVAL_REQUIRED` | Before approval node |

## Error Handling & Retry

Simplified retry with typed exception handling:

```python
import asyncio
from httpx import TimeoutException

# Exceptions that warrant retry
TRANSIENT_EXCEPTIONS = (
    asyncio.TimeoutError,
    TimeoutException,
    ConnectionError,
    # Add SDK-specific rate limit errors as needed
)

async def _run_workflow_with_retry(
    self,
    workflow_id: str,
    state: ServerExecutionState,
) -> None:
    """Execute workflow with automatic retry for transient failures."""

    retry_config = state.execution_state.profile.retry
    attempt = 0

    while attempt <= retry_config.max_retries:
        try:
            await self._run_workflow(workflow_id, state)
            return  # Success

        except TRANSIENT_EXCEPTIONS as e:
            attempt += 1
            if attempt > retry_config.max_retries:
                await self._mark_failed(workflow_id, f"Failed after {attempt} attempts: {e}")
                raise

            delay = min(
                retry_config.base_delay * (2 ** (attempt - 1)),
                60.0,  # Hard cap at 60s
            )
            logger.warning(
                f"Transient error (attempt {attempt}/{retry_config.max_retries}), "
                f"retrying in {delay}s",
                workflow_id=workflow_id,
                error=str(e),
            )
            await asyncio.sleep(delay)

        except Exception as e:
            # Non-transient error - fail immediately
            await self._mark_failed(workflow_id, str(e))
            raise
```

**Error classification:**

| Error Type | Examples | Behavior |
|------------|----------|----------|
| Transient | `TimeoutError`, `ConnectionError`, rate limits | Retry with exponential backoff |
| Permanent | `ValueError`, `KeyError`, auth failures | Fail immediately |

## Configuration Schema

Simplified retry configuration:

```yaml
profiles:
  work:
    driver: api:openai
    tracker: jira
    retry:
      max_retries: 3
      base_delay: 1.0

  enterprise:
    driver: cli:claude
    tracker: github
    retry:
      max_retries: 5
      base_delay: 2.0
```

**Model addition:**

```python
class RetryConfig(BaseModel):
    """Retry configuration for transient failures."""
    max_retries: int = Field(default=3, ge=0, le=10)
    base_delay: float = Field(default=1.0, ge=0.1, le=30.0)

class Profile(BaseModel):
    name: str
    driver: DriverType
    tracker: TrackerType = "none"
    strategy: StrategyType = "single"
    execution_mode: ExecutionMode = "structured"
    plan_output_dir: str = "docs/plans"
    working_dir: str | None = None
    retry: RetryConfig = Field(default_factory=RetryConfig)
```

## Testing Strategy

**Test structure:**

```
tests/
├── unit/
│   ├── server/
│   │   └── orchestrator/
│   │       ├── test_execution_bridge.py  # _run_workflow with mocked graph
│   │       ├── test_event_mapping.py     # LangGraph → WorkflowEvent
│   │       └── test_retry_logic.py       # Backoff, error classification
│   └── core/
│       ├── test_retry_config.py          # RetryConfig validation
│       └── test_human_approval_node.py   # CLI vs server mode
├── integration/
│   ├── test_approval_flow.py             # Interrupt → approve → resume
│   ├── test_checkpoint_recovery.py       # Restart mid-workflow
│   └── test_concurrent_workflows.py      # Multiple workflows isolated
```

**TDD approach:**

| Component | Test First | Then Implement |
|-----------|------------|----------------|
| `RetryConfig` | Validation, defaults, bounds | Pydantic model |
| `human_approval_node` | CLI mode prompts, server mode passes through | Mode detection |
| `_run_workflow` | Mock graph, verify events emitted | Execution bridge |
| Event mapping | Each LangGraph event → correct WorkflowEvent | `_handle_graph_event` |
| Approval flow | Mock interrupt, verify resume with state | Full cycle |
| Error handling | Transient vs permanent classification | Retry wrapper |

## Implementation Order

1. **Add dependency** - `uv add langgraph-checkpoint-sqlite`
2. **RetryConfig model** - Add to `amelia/core/types.py`
3. **Update human_approval_node** - Add execution mode detection in `amelia/core/orchestrator.py`
4. **State model update** - Add `execution_state` to `ServerExecutionState`
5. **Event mapping** - Add `STAGE_NODES` constant and `_handle_graph_event()` to service
6. **Execution bridge** - Implement `_run_workflow()` with checkpointer
7. **Retry wrapper** - Add `_run_workflow_with_retry()`
8. **Approval flow** - Update `approve_workflow()` / `reject_workflow()` to resume graph
9. **Integration tests** - Full workflow cycles

## Checkpoint Cleanup

The `langgraph-checkpoint-sqlite` package supports TTL-based cleanup:

```python
# During server startup (lifespan)
async with AsyncSqliteSaver.from_conn_string(checkpoint_path) as saver:
    await saver.setup(ttl=timedelta(days=7))  # Auto-cleanup old checkpoints
```

For manual cleanup of completed workflows:
```python
# After workflow completes successfully
await checkpointer.adelete(config)
```

## Future: PostgreSQL Migration

Migration path when scaling:

1. `uv add langgraph-checkpoint-postgres`
2. Add `checkpoint_backend: sqlite | postgres` to server config
3. Factory function selects implementation:
   ```python
   def get_checkpointer(config: ServerConfig):
       if config.checkpoint_backend == "postgres":
           return AsyncPostgresSaver.from_conn_string(config.postgres_url)
       return AsyncSqliteSaver.from_conn_string(config.checkpoint_path)
   ```
4. No changes to `OrchestratorService` - same interface
