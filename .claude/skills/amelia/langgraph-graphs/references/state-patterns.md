# State Patterns

Advanced state definition patterns for LangGraph state machines.

## TypedDict vs Pydantic BaseModel

**TypedDict** (recommended for most cases):
```python
from typing import TypedDict, Annotated
from operator import add

class State(TypedDict):
    messages: Annotated[list[str], add]
    count: int
    data: dict
```

**Pydantic BaseModel** (when you need validation):
```python
from pydantic import BaseModel, Field, field_validator

class State(BaseModel):
    messages: list[str] = Field(default_factory=list)
    count: int = 0
    data: dict = Field(default_factory=dict)

    @field_validator("count")
    @classmethod
    def validate_count(cls, v: int) -> int:
        if v < 0:
            raise ValueError("count must be non-negative")
        return v
```

**When to use which:**
- TypedDict: Simple state, no validation, performance-critical
- BaseModel: Complex validation, default values, nested models

## Reducer Patterns

Reducers control how state updates are merged using `Annotated[Type, reducer_fn]`.

**Built-in reducers:**

```python
from operator import add
from typing import Annotated

class State(TypedDict):
    # List append (most common)
    messages: Annotated[list[str], add]

    # Also works for tuples, strings
    tags: Annotated[tuple[str, ...], add]
    log: Annotated[str, add]  # String concatenation
```

**Custom reducers:**

```python
def merge_dicts(old: dict, new: dict) -> dict:
    """Merge dicts, new values override old."""
    return {**old, **new}

def merge_sets(old: set, new: set) -> set:
    """Union of sets."""
    return old | new

def accumulate_max(old: int, new: int) -> int:
    """Keep maximum value."""
    return max(old, new)

class State(TypedDict):
    config: Annotated[dict, merge_dicts]
    seen_ids: Annotated[set, merge_sets]
    max_score: Annotated[int, accumulate_max]
```

**How reducers work:**

```python
# Initial state
state = {"messages": ["hello"]}

# Node returns
return {"messages": ["world"]}

# With Annotated[list, add] reducer:
# result = ["hello"] + ["world"] = ["hello", "world"]

# Without reducer (default replacement):
# result = ["world"]
```

## Nested State Patterns

**Flat structure** (recommended):

```python
class State(TypedDict):
    user_id: str
    user_name: str
    task_id: str
    task_status: str
```

**Nested dictionaries** (avoid unless necessary):

```python
class State(TypedDict):
    user: dict  # {"id": "...", "name": "..."}
    task: dict  # {"id": "...", "status": "..."}

def update_node(state: State) -> dict:
    # Must manually merge nested dicts
    return {
        "task": {**state["task"], "status": "completed"}
    }
```

**Nested Pydantic models** (when validation is critical):

```python
from pydantic import BaseModel

class User(BaseModel):
    id: str
    name: str

class Task(BaseModel):
    id: str
    status: str

class State(BaseModel):
    user: User
    task: Task

def update_node(state: State) -> dict:
    # Pydantic handles nested updates
    updated_task = state.task.model_copy(update={"status": "completed"})
    return {"task": updated_task}
```

## State Validation

**Runtime validation with Pydantic:**

```python
from pydantic import BaseModel, field_validator, model_validator

class State(BaseModel):
    count: int
    items: list[str]

    @field_validator("count")
    @classmethod
    def count_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("count must be >= 0")
        return v

    @model_validator(mode="after")
    def check_consistency(self) -> "State":
        if self.count != len(self.items):
            raise ValueError("count must match items length")
        return self
```

**Validation in nodes:**

```python
class State(TypedDict):
    count: int

def validate_and_process(state: State) -> dict:
    if state["count"] < 0:
        raise ValueError("Invalid count")
    return {"count": state["count"] + 1}
```

## Optional Fields

**TypedDict with optional fields:**

```python
from typing import TypedDict, NotRequired

class State(TypedDict):
    required_field: str
    optional_field: NotRequired[str]  # Python 3.11+

# Or use total=False
class PartialState(TypedDict, total=False):
    optional_a: str
    optional_b: int
```

**Pydantic with optional fields:**

```python
class State(BaseModel):
    required_field: str
    optional_field: str | None = None
    with_default: int = 0
```

## Channel-based Reducers (Advanced)

For fine-grained control over state updates:

```python
from langgraph.graph import StateGraph
from langgraph.channels import LastValue, Topic

# LastValue: replacement (default behavior)
# Topic: append-only list

class State(TypedDict):
    # Using built-in behavior
    messages: Annotated[list[str], add]  # Append
    count: int  # Replace (LastValue is default)
```

## State Composition

Break complex state into logical sections:

```python
class ExecutionState(TypedDict):
    # Core workflow
    status: str
    current_step: str

class DataState(TypedDict):
    # Data processing
    input_data: dict
    output_data: dict

class CombinedState(ExecutionState, DataState):
    # Combines both via inheritance
    pass

# Or use explicit composition
class FullState(TypedDict):
    execution: ExecutionState
    data: DataState
```

## Default Values

**TypedDict** (no built-in defaults):

```python
def create_initial_state() -> State:
    """Factory function for default state."""
    return {
        "messages": [],
        "count": 0,
        "data": {}
    }
```

**Pydantic** (native defaults):

```python
class State(BaseModel):
    messages: list[str] = Field(default_factory=list)
    count: int = 0
    data: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=lambda: {"mode": "default"})
```

## State Access Patterns

**Read-only access:**

```python
def readonly_node(state: State) -> dict:
    # Read state, return minimal update
    value = state["count"]
    return {}  # No changes
```

**Partial updates:**

```python
def partial_update(state: State) -> dict:
    # Only update what changed
    return {"count": state["count"] + 1}
    # Other fields unchanged
```

**Full replacement (rare):**

```python
# With TypedDict, return all fields to replace state
def full_replace(state: State) -> State:
    return {
        "messages": ["reset"],
        "count": 0,
        "data": {}
    }
```

## Performance Considerations

1. **State size:** Large state is serialized for checkpoints - keep minimal
2. **Nested objects:** Avoid deep nesting - harder to update and serialize
3. **Pydantic overhead:** Validation adds cost - use TypedDict for hot paths
4. **Reducer complexity:** Custom reducers run on every update - keep simple

## Best Practices

1. Use TypedDict unless you need Pydantic validation
2. Prefer `Annotated[list, add]` for accumulating lists
3. Keep state flat when possible
4. Use factory functions for default TypedDict state
5. Validate state in nodes, not just at boundaries
6. Document reducer behavior in type annotations
7. Avoid storing large objects - use IDs and fetch when needed
