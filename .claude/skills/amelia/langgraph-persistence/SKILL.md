---
name: langgraph-persistence
description: LangGraph persistence and human-in-loop patterns with checkpointing, interrupts, and state updates. Use when adding checkpoints, implementing approval flows, handling GraphInterrupt, or resuming paused workflows. Triggers on AsyncSqliteSaver, checkpoint, interrupt_before, GraphInterrupt, aupdate_state, thread_id, human approval.
---

# LangGraph Persistence & Human-in-Loop

Checkpointing, interrupts, and state resumption for stateful workflows.

## Quick Start

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import StateGraph, START, END

async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
    graph = StateGraph(MyState)
    graph.add_node("process", process_node)
    graph.add_edge(START, "process")
    graph.add_edge("process", END)

    app = graph.compile(checkpointer=checkpointer)

    # Use with thread_id for isolation
    config = {"configurable": {"thread_id": "user-123"}}
    result = await app.ainvoke({"data": "input"}, config)
```

## Thread ID for Isolation

```python
# Each thread has isolated state
config1 = {"configurable": {"thread_id": "conversation-1"}}
config2 = {"configurable": {"thread_id": "conversation-2"}}

# Different users/sessions get different threads
await app.ainvoke(state1, config1)  # Independent
await app.ainvoke(state2, config2)  # Independent

# Resume specific thread later
result = await app.ainvoke(None, config1)  # Continues from checkpoint
```

## Interrupts - Static (Compilation)

```python
from langgraph.types import Command

# Pause BEFORE node executes
app = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["approval_node"]
)

# Or pause AFTER node executes
app = graph.compile(
    checkpointer=checkpointer,
    interrupt_after=["draft_node"]
)

# Execution pauses at interrupt point
config = {"configurable": {"thread_id": "flow-1"}}
result = await app.ainvoke({"task": "draft"}, config)

# Check state
state = await app.aget_state(config)
print(state.next)  # Shows which node is next: ('approval_node',)
print(state.values)  # Current state values
```

## Interrupts - Dynamic (Function)

```python
from langgraph.types import interrupt, Command

def approval_node(state):
    """Node that pauses for human approval."""
    # Present info to user
    draft = state["draft"]

    # Pause execution, save to checkpoint
    approval = interrupt({"draft": draft, "message": "Please review"})

    # Execution resumes here with approval value
    if approval.get("approved"):
        return {"status": "approved", "final": draft}
    else:
        return {"status": "rejected", "reason": approval.get("reason")}

# Compile normally - interrupt() handles the pause
app = graph.compile(checkpointer=checkpointer)

# First invocation - pauses at interrupt()
config = {"configurable": {"thread_id": "task-1"}}
result = await app.ainvoke({"content": "..."}, config)

# Resume with Command
result = await app.ainvoke(
    Command(resume={"approved": True}),
    config
)
```

## Resume with State Updates

```python
# Check interrupted state
config = {"configurable": {"thread_id": "task-1"}}
state = await app.aget_state(config)

if state.next:  # Has pending nodes
    # Option 1: Resume with Command
    await app.ainvoke(Command(resume={"approved": True}), config)

    # Option 2: Update state then resume
    await app.aupdate_state(config, {"approved": True, "notes": "LGTM"})
    async for chunk in app.astream(None, config):
        print(chunk)
```

## Multiple Interrupts

```python
def review_node(state):
    # First interrupt - request changes
    changes = interrupt({"step": "review", "draft": state["draft"]})

    # Update based on changes
    updated = apply_changes(state["draft"], changes)

    # Second interrupt - final approval
    approval = interrupt({"step": "approve", "updated": updated})

    return {"final": updated if approval else state["draft"]}

# Resume provides values in order
config = {"configurable": {"thread_id": "multi-1"}}

# First run - pauses at first interrupt
await app.ainvoke({"draft": "..."}, config)

# Resume first interrupt
await app.ainvoke(Command(resume={"edits": "..."}), config)

# Resume second interrupt
await app.ainvoke(Command(resume={"approved": True}), config)
```

## Event Streaming

```python
# Stream all events during execution
async for event in app.astream_events({"input": "data"}, config, version="v2"):
    kind = event["event"]

    if kind == "on_chain_start":
        print(f"Starting: {event['name']}")

    elif kind == "on_chain_end":
        print(f"Finished: {event['name']}")
        print(f"Output: {event['data']['output']}")

    elif kind == "on_chat_model_stream":
        # Token-by-token streaming
        content = event["data"]["chunk"].content
        if content:
            print(content, end="", flush=True)

# Filter to specific node
async for event in app.astream_events(state, config, version="v2"):
    if event.get("name") == "process_node":
        print(event["data"])
```

## Common Patterns

| Pattern | Use Case |
|---------|----------|
| `interrupt_before` | Review before executing (approval gates) |
| `interrupt_after` | Review after executing (output validation) |
| `interrupt()` function | Dynamic pauses with context |
| `Command(resume=...)` | Provide values to resume |
| `aupdate_state()` | Modify state before resume |
| `aget_state()` | Check current position |
| `astream_events()` | Monitor execution progress |

## Gotchas

- **Forget thread_id**: Without thread_id, each run creates new state (no persistence)
- **Wrong interrupt order**: `interrupt()` calls match by index, order matters
- **Re-throw GraphInterrupt**: Don't catch GraphInterrupt without re-raising
- **Missing checkpointer**: Interrupts require a checkpointer to save state
- **Version mismatch**: Use `version="v2"` for astream_events (v1 is deprecated)

## Additional Documentation

- **Checkpointers**: See [references/checkpointers.md](references/checkpointers.md) for SQLite, Postgres, memory
- **Human-in-Loop**: See [references/human-in-loop.md](references/human-in-loop.md) for approval patterns
- **Streaming**: See [references/streaming.md](references/streaming.md) for astream_events details
