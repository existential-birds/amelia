# RunnableConfig Patterns

Configuration patterns for LangGraph execution, checkpointing, and custom runtime parameters.

## Basic RunnableConfig

```python
from langchain_core.runnables import RunnableConfig

config: RunnableConfig = {
    "configurable": {
        "thread_id": "session-123",  # Required for checkpointing
    }
}

result = app.invoke(initial_state, config=config)
```

## Thread ID for Checkpointing

Thread IDs isolate checkpoint state across different workflow runs:

```python
# Different workflows use different thread IDs
config_workflow_1 = {
    "configurable": {"thread_id": "workflow-abc-123"}
}

config_workflow_2 = {
    "configurable": {"thread_id": "workflow-xyz-789"}
}

# Each maintains separate checkpoint state
result_1 = app.invoke(state_1, config=config_workflow_1)
result_2 = app.invoke(state_2, config=config_workflow_2)

# Resume from checkpoint
result_1_resumed = app.invoke(None, config=config_workflow_1)
```

**Thread ID conventions:**
- Use workflow/session identifiers
- Keep unique per independent execution
- Use consistent format (e.g., `workflow-{id}`, `session-{uuid}`)

## Custom Config Keys

Add custom keys to `configurable` dict for runtime parameters:

```python
config = {
    "configurable": {
        "thread_id": "session-123",
        "execution_mode": "cli",      # Custom: CLI vs server
        "retry_limit": 3,              # Custom: max retries
        "debug": True,                 # Custom: debug flag
        "user_id": "user-456"          # Custom: context
    }
}
```

## Accessing Config in Nodes

Nodes must accept `config: RunnableConfig` parameter:

```python
from langchain_core.runnables import RunnableConfig

def node_with_config(state: State, config: RunnableConfig) -> dict:
    """Access config in node function."""
    # Extract custom keys
    mode = config.get("configurable", {}).get("execution_mode", "default")
    retry_limit = config.get("configurable", {}).get("retry_limit", 3)
    thread_id = config.get("configurable", {}).get("thread_id")

    # Use in logic
    if mode == "cli":
        # CLI-specific behavior
        pass
    elif mode == "server":
        # Server-specific behavior
        pass

    return {"count": state["count"] + 1}
```

**Signature options:**
```python
# With config
def node(state: State, config: RunnableConfig) -> dict:
    pass

# Without config (if not needed)
def simple_node(state: State) -> dict:
    pass

# Async with config
async def async_node(state: State, config: RunnableConfig) -> dict:
    pass
```

## Execution Mode Pattern

Use config to switch behavior between CLI and server:

```python
def human_approval_node(state: State, config: RunnableConfig) -> dict:
    """Different approval flows for CLI vs server."""
    mode = config.get("configurable", {}).get("execution_mode", "cli")

    if mode == "cli":
        # CLI: blocking prompt
        import typer
        approved = typer.confirm("Approve plan?", default=False)
        return {"human_approved": approved}

    elif mode == "server":
        # Server: approval from resumed state (after interrupt)
        # If already set (from resume), use it; otherwise wait for interrupt
        if state.get("human_approved") is not None:
            return {}  # Already approved/rejected
        return {}  # Wait for interrupt + resume

    else:
        raise ValueError(f"Unknown execution mode: {mode}")
```

**Graph compilation with interrupt:**
```python
# Server mode uses interrupt_before for human approval
app = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_approval_node"]
)

# CLI mode doesn't interrupt (blocking prompt instead)
app_cli = graph.compile(checkpointer=checkpointer)
```

## Checkpoint Configuration

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# In-memory checkpointing (dev/testing)
memory_saver = InMemorySaver()
app = graph.compile(checkpointer=memory_saver)

# SQLite checkpointing (production)
async def create_app():
    checkpointer = AsyncSqliteSaver.from_conn_string("checkpoints.db")
    await checkpointer.setup()  # Initialize schema
    return graph.compile(checkpointer=checkpointer)

# With TTL cleanup
async def create_app_with_ttl():
    from datetime import timedelta
    checkpointer = AsyncSqliteSaver.from_conn_string("checkpoints.db")
    await checkpointer.setup(ttl=timedelta(days=7))  # Auto-delete old checkpoints
    return graph.compile(checkpointer=checkpointer)
```

## Interrupt Patterns

**Interrupt before node:**
```python
app = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_approval", "critical_decision"]
)

config = {"configurable": {"thread_id": "session-123"}}

# First invoke: runs until interrupt
result = app.invoke(initial_state, config)
# Execution pauses at "human_approval"

# User reviews and approves
# Update state externally or pass approval in resumed state

# Resume: continues from checkpoint
result = app.invoke(None, config)  # None = resume from checkpoint
```

**Interrupt after node:**
```python
app = graph.compile(
    checkpointer=checkpointer,
    interrupt_after=["review_node"]
)

# Pauses AFTER review_node completes
```

## Resuming from Checkpoints

```python
config = {"configurable": {"thread_id": "session-123"}}

# Initial run
result = app.invoke(initial_state, config)

# Later: resume from checkpoint
# Pass None as state to resume from last checkpoint
resumed_result = app.invoke(None, config)

# Or update state and resume
updated_state = {**result, "human_approved": True}
resumed_result = app.invoke(updated_state, config)
```

## Streaming with Config

```python
config = {
    "configurable": {
        "thread_id": "session-123",
        "debug": True
    }
}

# Stream events
for event in app.stream(initial_state, config):
    # event = {"node_name": {"field": "value", ...}}
    for node_name, node_output in event.items():
        print(f"{node_name}: {node_output}")

# Async streaming
async for event in app.astream(initial_state, config):
    print(event)
```

## Config Defaults and Validation

```python
def get_config_value(config: RunnableConfig, key: str, default: Any) -> Any:
    """Helper to extract config with default."""
    return config.get("configurable", {}).get(key, default)

def validate_config(config: RunnableConfig) -> None:
    """Validate required config keys."""
    configurable = config.get("configurable", {})

    if "thread_id" not in configurable:
        raise ValueError("thread_id required in config.configurable")

    if "execution_mode" in configurable:
        valid_modes = {"cli", "server"}
        if configurable["execution_mode"] not in valid_modes:
            raise ValueError(f"execution_mode must be one of {valid_modes}")

# Use in node
def node(state: State, config: RunnableConfig) -> dict:
    validate_config(config)
    mode = get_config_value(config, "execution_mode", "cli")
    return {"mode": mode}
```

## Shared vs Per-Invocation Config

**Shared config** (same for all invocations):
```python
app = graph.compile(checkpointer=checkpointer)

shared_config = {"configurable": {"execution_mode": "server"}}

# All invocations use shared config
result1 = app.invoke(state1, config=shared_config)
result2 = app.invoke(state2, config=shared_config)
```

**Per-invocation config** (different per call):
```python
# Different thread IDs for isolation
config1 = {"configurable": {"thread_id": "session-1"}}
config2 = {"configurable": {"thread_id": "session-2"}}

result1 = app.invoke(state1, config=config1)
result2 = app.invoke(state2, config=config2)
```

## Callback Configuration

```python
from langchain_core.callbacks import BaseCallbackHandler

class LoggingCallback(BaseCallbackHandler):
    def on_chain_start(self, serialized, inputs, **kwargs):
        print(f"Chain started: {inputs}")

    def on_chain_end(self, outputs, **kwargs):
        print(f"Chain ended: {outputs}")

config = {
    "configurable": {"thread_id": "session-123"},
    "callbacks": [LoggingCallback()]
}

result = app.invoke(initial_state, config=config)
```

## Recursion Limit

Prevent infinite loops with recursion limit:

```python
config = {
    "configurable": {"thread_id": "session-123"},
    "recursion_limit": 50  # Max node executions
}

# Raises RecursionError if limit exceeded
result = app.invoke(initial_state, config=config)
```

## Config in Conditional Edges

Routers cannot directly access config. Pass needed values via state:

```python
# Instead of this (doesn't work):
def router(state: State, config: RunnableConfig) -> str:
    mode = config["configurable"]["execution_mode"]  # ERROR
    return "cli" if mode == "cli" else "server"

# Do this (works):
def node_before_router(state: State, config: RunnableConfig) -> dict:
    """Set mode in state for router."""
    mode = config.get("configurable", {}).get("execution_mode", "cli")
    return {"execution_mode": mode}

def router(state: State) -> str:
    """Router uses state, not config."""
    return state["execution_mode"]

graph.add_node("setup", node_before_router)
graph.add_conditional_edges("setup", router, {...})
```

## Environment-Specific Configs

```python
import os

def get_config_for_env() -> RunnableConfig:
    """Build config based on environment."""
    env = os.getenv("ENV", "dev")

    if env == "production":
        return {
            "configurable": {
                "execution_mode": "server",
                "retry_limit": 5,
                "debug": False
            }
        }
    else:
        return {
            "configurable": {
                "execution_mode": "cli",
                "retry_limit": 3,
                "debug": True
            }
        }

config = get_config_for_env()
config["configurable"]["thread_id"] = "session-123"
result = app.invoke(initial_state, config=config)
```

## Best Practices

1. **Always set thread_id** when using checkpointing
2. **Use descriptive keys** for custom config (not `c1`, `c2`)
3. **Provide defaults** when reading custom keys
4. **Validate config** in first node or helper function
5. **Document custom keys** in docstrings or README
6. **Pass config explicitly** - don't rely on global state
7. **Isolate configs** - one thread_id per independent workflow
8. **Handle missing config** gracefully with defaults

## Common Patterns

| Pattern | Use Case |
|---------|----------|
| `thread_id` | Checkpoint isolation |
| `execution_mode` | CLI vs server behavior |
| `debug` | Verbose logging toggle |
| `retry_limit` | Max retry attempts |
| `user_id` | User context for multi-tenant |
| `timeout` | Operation timeouts |
| `dry_run` | Test mode without side effects |

## Anti-Patterns to Avoid

1. **Hardcoded thread IDs:** Always generate unique per workflow
2. **Mutable config:** Don't modify config dict after creation
3. **Config in routers:** Routers can't access config - use state
4. **Missing defaults:** Always provide fallback for custom keys
5. **Global config:** Don't use module-level config variables
6. **Sensitive data:** Don't put secrets in config - use env vars
