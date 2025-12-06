# Routing Patterns

Advanced conditional edge and routing patterns for LangGraph state machines.

## Basic Conditional Edges

```python
from langgraph.graph import StateGraph, END

def router(state: State) -> str:
    """Return destination node name as string."""
    if state["count"] > 10:
        return "high"
    return "low"

graph.add_conditional_edges(
    "source_node",
    router,
    {
        "high": "high_handler",
        "low": "low_handler"
    }
)
```

**Router function rules:**
1. Must return string matching a key in the mapping dict
2. Receives full state as argument
3. Should be pure (no side effects)
4. Can return END to terminate

## Multi-way Branching

```python
def multi_router(state: State) -> str:
    """Route to different nodes based on status."""
    if state["error"]:
        return "error"
    if state["count"] == 0:
        return "empty"
    if state["count"] > 100:
        return "large"
    return "normal"

graph.add_conditional_edges(
    "processor",
    multi_router,
    {
        "error": "error_handler",
        "empty": "empty_handler",
        "large": "large_processor",
        "normal": "normal_processor"
    }
)
```

## Routing to END

```python
def maybe_finish(state: State) -> str:
    """Continue or finish based on state."""
    if state["finished"]:
        return "done"
    if state["count"] >= state["max_count"]:
        return "done"
    return "continue"

graph.add_conditional_edges(
    "worker",
    maybe_finish,
    {
        "done": END,
        "continue": "worker"  # Loop back
    }
)
```

## Cycles and Loops

**Self-loops** (same node):

```python
def loop_or_exit(state: State) -> str:
    """Loop until condition met."""
    return "continue" if state["count"] < 100 else "exit"

graph.add_conditional_edges(
    "worker",
    loop_or_exit,
    {
        "continue": "worker",  # Back to self
        "exit": "finalizer"
    }
)
```

**Multi-node cycles:**

```python
# Developer ↔ Reviewer cycle
graph.add_conditional_edges(
    "developer",
    lambda s: "done" if s["tasks_complete"] else "review",
    {
        "done": "reviewer",
        "review": "reviewer"
    }
)

graph.add_conditional_edges(
    "reviewer",
    lambda s: "done" if s["review_approved"] else "retry",
    {
        "done": END,
        "retry": "developer"  # Back to developer
    }
)
```

**Preventing infinite loops:**

```python
def safe_router(state: State) -> str:
    """Router with iteration limit."""
    if state["iteration"] > state["max_iterations"]:
        return "timeout"
    if state["completed"]:
        return "success"
    return "continue"

graph.add_conditional_edges(
    "worker",
    safe_router,
    {
        "timeout": "timeout_handler",
        "success": END,
        "continue": "worker"
    }
)

def worker_node(state: State) -> dict:
    """Increment iteration counter."""
    return {
        "iteration": state["iteration"] + 1,
        "completed": check_completion(state)
    }
```

## Dynamic Routing

**Route based on field value:**

```python
def dynamic_router(state: State) -> str:
    """Route to node named in state."""
    return state["next_node"]

graph.add_conditional_edges(
    "dispatcher",
    dynamic_router,
    {
        "agent_a": "agent_a_node",
        "agent_b": "agent_b_node",
        "agent_c": "agent_c_node",
        "done": END
    }
)

def agent_a_node(state: State) -> dict:
    """Agent A sets next destination."""
    result = process_a(state)
    return {
        "data": result,
        "next_node": "agent_b"  # Dynamic routing
    }
```

## Conditional Edge with Lambda

```python
# Inline router for simple logic
graph.add_conditional_edges(
    "check_status",
    lambda s: "approved" if s["human_approved"] else "rejected",
    {
        "approved": "developer",
        "rejected": END
    }
)

# Multiple conditions
graph.add_conditional_edges(
    "validator",
    lambda s: "error" if s["error"] else ("empty" if not s["data"] else "valid"),
    {
        "error": "error_handler",
        "empty": "empty_handler",
        "valid": "processor"
    }
)
```

## Fan-out Pattern (Not Directly Supported)

LangGraph doesn't support parallel execution from one node. Use sequential routing instead:

```python
# Instead of parallel fan-out, do sequential processing
graph.add_edge("source", "worker_1")
graph.add_edge("worker_1", "worker_2")
graph.add_edge("worker_2", "worker_3")
graph.add_edge("worker_3", "aggregator")
```

For true parallelism, use external orchestration or spawn subgraphs.

## Error Handling Routes

```python
def error_aware_router(state: State) -> str:
    """Route errors to dedicated handler."""
    if state.get("error"):
        return "error"
    if state.get("retry_count", 0) >= 3:
        return "max_retries"
    if state.get("result"):
        return "success"
    return "process"

graph.add_conditional_edges(
    "task_node",
    error_aware_router,
    {
        "error": "error_handler",
        "max_retries": "failure_node",
        "success": END,
        "process": "task_node"  # Retry
    }
)

def task_node(state: State) -> dict:
    """Task with error handling."""
    try:
        result = risky_operation(state)
        return {"result": result, "error": None}
    except Exception as e:
        return {
            "error": str(e),
            "retry_count": state.get("retry_count", 0) + 1
        }
```

## State-based Routing

```python
class State(TypedDict):
    stage: str  # "planning" | "executing" | "reviewing"
    approved: bool
    error: str | None

def stage_router(state: State) -> str:
    """Route based on current workflow stage."""
    if state["stage"] == "planning":
        return "plan"
    if state["stage"] == "executing":
        if state["error"]:
            return "error"
        return "execute"
    if state["stage"] == "reviewing":
        return "approve" if state["approved"] else "reject"
    return "unknown"

graph.add_conditional_edges(
    "orchestrator",
    stage_router,
    {
        "plan": "planner",
        "execute": "executor",
        "error": "error_handler",
        "approve": END,
        "reject": "planner",  # Re-plan
        "unknown": END
    }
)
```

## Complex Routing Logic

```python
def complex_router(state: State) -> str:
    """Multi-factor routing decision."""
    # Check preconditions
    if not state.get("initialized"):
        return "init"

    # Error states
    if state.get("error"):
        if state["retry_count"] < 3:
            return "retry"
        return "fail"

    # Progress states
    if state["current_task_id"]:
        tasks_done = all(
            t["status"] == "completed"
            for t in state["tasks"]
        )
        if tasks_done:
            return "review"
        return "execute"

    # Default
    return "plan"

graph.add_conditional_edges(
    "dispatcher",
    complex_router,
    {
        "init": "initializer",
        "retry": "executor",
        "fail": "failure_handler",
        "review": "reviewer",
        "execute": "executor",
        "plan": "planner"
    }
)
```

## Guard Clauses in Routers

```python
def guarded_router(state: State) -> str:
    """Router with defensive checks."""
    # Guard: check required fields exist
    if not state.get("plan"):
        return "error"

    # Guard: validate state
    if state["count"] < 0:
        return "error"

    # Main routing logic
    ready_tasks = [t for t in state["plan"]["tasks"] if t["status"] == "ready"]
    if ready_tasks:
        return "execute"

    completed = all(t["status"] == "completed" for t in state["plan"]["tasks"])
    if completed:
        return "finish"

    # No ready tasks, not complete = blocked
    return "blocked"

graph.add_conditional_edges(
    "orchestrator",
    guarded_router,
    {
        "execute": "executor",
        "finish": END,
        "blocked": "error_handler",
        "error": "error_handler"
    }
)
```

## Debugging Routers

```python
from loguru import logger

def logged_router(state: State) -> str:
    """Router with debug logging."""
    result = "continue" if state["count"] < 10 else "finish"
    logger.debug(
        f"Router decision: {result} (count={state['count']})"
    )
    return result
```

## Best Practices

1. **Pure functions:** Routers should not mutate state or have side effects
2. **Explicit mappings:** Avoid dynamic string construction in return values
3. **Guard clauses:** Check for required fields before routing logic
4. **Iteration limits:** Always include max iteration checks for cycles
5. **Error routes:** Provide explicit error handling routes
6. **Logging:** Log routing decisions for debugging
7. **Type hints:** Router signature should be `(State) -> str`
8. **Coverage:** Ensure all possible return values are in mapping dict

## Common Patterns

| Pattern | Use Case |
|---------|----------|
| Simple if/else | Two destinations |
| Multi-way | 3+ destinations |
| Self-loop | Retry/iteration |
| Cycle | Multi-node workflow loops |
| Dynamic | Next node from state |
| Guard clauses | Defensive routing |
| Error routing | Failure handling |

## Anti-Patterns to Avoid

1. **Missing END mapping:** Forgetting to map return value to END
2. **Typos in mapping keys:** Return "succes" but map "success"
3. **Infinite loops:** No exit condition in cycles
4. **Side effects:** Mutating state in router function
5. **Catching all errors:** Using bare except in routers
6. **Non-deterministic:** Routers that return different values for same state
