---
name: langgraph-graphs
description: LangGraph state machine patterns with StateGraph, nodes, edges, and conditional routing. Use when building graph-based workflows, defining state with TypedDict, adding nodes/edges, or configuring conditional routing. Triggers on StateGraph, add_node, add_edge, add_conditional_edges, TypedDict, RunnableConfig, langgraph.
---

# LangGraph State Machine Patterns

Build stateful, multi-step workflows using LangGraph's StateGraph. Ideal for agent orchestration, multi-step processing, and conditional workflows.

## Quick Start

```python
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

class State(TypedDict):
    messages: list[str]
    count: int

def process_node(state: State) -> dict:
    """Node functions return partial state updates."""
    return {"count": state["count"] + 1}

def router(state: State) -> str:
    """Router functions return edge name."""
    return "continue" if state["count"] < 5 else "finish"

# Build graph
graph = StateGraph(State)
graph.add_node("process", process_node)
graph.add_edge(START, "process")
graph.add_conditional_edges(
    "process",
    router,
    {"continue": "process", "finish": END}
)

# Compile and run
app = graph.compile()
result = app.invoke({"messages": [], "count": 0})
```

## State Definition

State must be a `TypedDict` or Pydantic `BaseModel`:

```python
from typing import TypedDict, Annotated
from operator import add
from pydantic import BaseModel

# TypedDict (recommended for simple state)
class State(TypedDict):
    messages: Annotated[list, add]  # Reducer: append messages
    count: int
    data: dict

# Pydantic BaseModel (for validation)
class ValidatedState(BaseModel):
    messages: list[str]
    count: int = 0  # Default values
```

**Reducers** control how state updates are merged:
- Without reducer: new value replaces old
- With reducer: function combines old + new values

See [references/state-patterns.md](references/state-patterns.md) for advanced patterns.

## Node Functions

Nodes receive state and return partial updates:

```python
def node_fn(state: State) -> dict:
    """Return dict with fields to update."""
    return {
        "count": state["count"] + 1,
        "messages": ["new message"]
    }

# Access config for thread_id, custom keys
from langchain_core.runnables import RunnableConfig

def node_with_config(state: State, config: RunnableConfig) -> dict:
    thread_id = config.get("configurable", {}).get("thread_id")
    mode = config.get("configurable", {}).get("execution_mode", "default")
    return {"count": state["count"] + 1}
```

**Common patterns:**
- Async nodes: `async def node_fn(state: State) -> dict`
- Error handling: Raise exceptions or return error state
- No return: Return empty dict `{}` for no state change

## Edges

**Static edges** connect nodes directly:

```python
graph.add_edge("node_a", "node_b")  # Always go node_a → node_b
graph.add_edge(START, "first_node")  # Entry point
graph.add_edge("last_node", END)     # Exit point

# Entry point shorthand
graph.set_entry_point("first_node")  # Same as add_edge(START, "first_node")
```

**Conditional edges** use router functions:

```python
def router(state: State) -> str:
    """Return destination node name."""
    if state["count"] > 10:
        return "process_large"
    return "process_small"

graph.add_conditional_edges(
    "source_node",
    router,
    {
        "process_large": "large_handler",
        "process_small": "small_handler"
    }
)

# Router can return END
def maybe_finish(state: State) -> str:
    return "done" if state["finished"] else "continue"

graph.add_conditional_edges(
    "check_node",
    maybe_finish,
    {"done": END, "continue": "next_node"}
)
```

**Cycles** are allowed - routers can loop:

```python
graph.add_conditional_edges(
    "worker",
    lambda state: "continue" if state["count"] < 100 else "finish",
    {"continue": "worker", "finish": END}  # Loop back to self
)
```

See [references/routing.md](references/routing.md) for complex patterns.

## Compilation

```python
# Basic compilation
app = graph.compile()

# With checkpointing (persistence)
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
app = graph.compile(checkpointer=checkpointer)

# With SQLite checkpointing
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async def create_app():
    checkpointer = AsyncSqliteSaver.from_conn_string("checkpoints.db")
    return graph.compile(checkpointer=checkpointer)
```

**Interrupts** pause execution for human approval:

```python
# Interrupt before specific nodes
app = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_approval_node"]
)

# Resume after approval
config = {"configurable": {"thread_id": "session-123"}}
result = app.invoke(initial_state, config)  # Pauses at interrupt
# ... human reviews ...
result = app.invoke(None, config)  # Resumes from checkpoint
```

## Invocation

```python
# Sync invocation
result = app.invoke({"messages": [], "count": 0})

# Async invocation
result = await app.ainvoke({"messages": [], "count": 0})

# With config
config = {
    "configurable": {
        "thread_id": "session-123",  # Required for checkpointing
        "execution_mode": "cli",      # Custom keys
    }
}
result = app.invoke(initial_state, config=config)

# Streaming events
for event in app.stream(initial_state, config):
    print(event)  # {"node_name": {"count": 1, ...}}
```

See [references/config.md](references/config.md) for RunnableConfig patterns.

## Common Patterns

**Multi-agent orchestration:**

```python
class AgentState(TypedDict):
    messages: Annotated[list, add]
    next_agent: str

graph = StateGraph(AgentState)
graph.add_node("planner", planner_agent)
graph.add_node("executor", executor_agent)
graph.add_node("reviewer", reviewer_agent)

graph.set_entry_point("planner")
graph.add_conditional_edges(
    "planner",
    lambda s: s["next_agent"],
    {"executor": "executor", "done": END}
)
graph.add_conditional_edges(
    "executor",
    lambda s: s["next_agent"],
    {"reviewer": "reviewer", "planner": "planner"}
)
graph.add_edge("reviewer", END)
```

**Error handling:**

```python
class State(TypedDict):
    data: dict
    error: str | None

def safe_node(state: State) -> dict:
    try:
        result = process_data(state["data"])
        return {"data": result, "error": None}
    except Exception as e:
        return {"error": str(e)}

graph.add_conditional_edges(
    "process",
    lambda s: "error" if s["error"] else "success",
    {"error": "error_handler", "success": END}
)
```

## Reference Files

- **[state-patterns.md](references/state-patterns.md)**: State definition, reducers, Annotated types, nested state
- **[routing.md](references/routing.md)**: Conditional edges, branching, cycles, multiple destinations
- **[config.md](references/config.md)**: RunnableConfig, thread_id, custom config keys, passing config through nodes

## Best Practices

1. **State size:** Keep state minimal - store IDs, not full objects
2. **Node atomicity:** Each node should do one logical step
3. **Idempotency:** Nodes should be safe to retry (use checkpointing)
4. **Router simplicity:** Router functions should be pure (no side effects)
5. **Type safety:** Use TypedDict or Pydantic for state validation
6. **Error handling:** Use conditional edges to route errors, not exceptions
7. **Checkpointing:** Always use thread_id with checkpointing for isolation

## Common Gotchas

- **Missing fields:** State updates are merged, not replaced. Omitted fields keep old values.
- **Reducer vs replace:** Without Annotated reducer, lists/dicts are replaced, not merged.
- **END is special:** Must import from `langgraph.graph`, not a string "END".
- **Router return value:** Must match keys in conditional edge mapping exactly.
- **Config access:** Must accept `config: RunnableConfig` parameter to access it.
- **Async mixing:** Don't mix sync/async nodes - graph executor handles this, but be consistent.
