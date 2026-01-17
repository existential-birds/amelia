# Pipeline Foundation Design

**Goal:** Establish the pipeline abstraction layer that enables multiple workflow types in Amelia.

**Scope:** Phase 1 only - create the foundational `amelia/pipelines/` structure and refactor the existing orchestrator into the first pipeline. No new pipelines are added in this phase.

**Parent:** See [Multiple Workflow Pipelines Design (#260)](./2026-01-10-multiple-workflow-pipelines-design.md) for full context and future phases.

---

## Overview

This phase introduces three key abstractions:

1. **Pipeline Protocol** - Interface that all workflow types implement
2. **Base State** - Common fields shared across all pipelines
3. **Registry** - Simple dict mapping pipeline names to implementations

The existing orchestrator becomes `ImplementationPipeline`, the first (and initially only) pipeline in the registry.

---

## Pipeline Protocol

Each pipeline implements a common protocol:

```python
# amelia/pipelines/base.py
from typing import Protocol, TypeVar
from langgraph.graph.state import CompiledStateGraph

StateT = TypeVar("StateT", bound="BasePipelineState")

class Pipeline(Protocol[StateT]):
    """Protocol that all pipelines must implement."""

    name: str  # "implementation"
    display_name: str  # "Implementation"
    description: str

    def create_graph(
        self,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> CompiledStateGraph: ...

    def get_initial_state(self, **kwargs) -> StateT: ...

    def get_state_class(self) -> type[StateT]: ...
```

---

## Pipeline Registry

The registry is a simple dict that routes to pipelines by name:

```python
# amelia/pipelines/registry.py
from amelia.pipelines.implementation import ImplementationPipeline

PIPELINES: dict[str, type[Pipeline]] = {
    "implementation": ImplementationPipeline,
}

def get_pipeline(name: str) -> Pipeline:
    if name not in PIPELINES:
        raise ValueError(f"Unknown pipeline: {name}")
    return PIPELINES[name]()
```

Phase 1 includes only the Implementation pipeline. Future phases add entries here.

---

## Base State

Base state contains fields common to all workflows:

```python
# amelia/pipelines/base.py
class BasePipelineState(BaseModel):
    """Common state for all pipelines."""
    model_config = ConfigDict(frozen=True)

    # Identity
    workflow_id: str
    pipeline_type: str
    profile_id: str

    # Lifecycle
    status: Literal["pending", "running", "paused", "completed", "failed"]
    created_at: datetime
    updated_at: datetime

    # Observability
    history: Annotated[list[HistoryEntry], add] = Field(default_factory=list)

    # Human interaction
    pending_user_input: bool = False
    user_message: str | None = None
```

---

## Implementation Pipeline

The current orchestrator becomes the Implementation pipeline:

```python
# amelia/pipelines/implementation/__init__.py

class ImplementationPipeline:
    """Pipeline for implementing code from issues/designs."""

    name = "implementation"
    display_name = "Implementation"
    description = "Build features and fix bugs with Architect -> Developer <-> Reviewer flow"

    def get_state_class(self) -> type[ImplementationState]:
        return ImplementationState

    def create_graph(
        self,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> CompiledStateGraph:
        return create_implementation_graph(checkpointer)

    def get_initial_state(
        self,
        issue: Issue | None = None,
        design: Design | None = None,
        **kwargs,
    ) -> ImplementationState:
        return ImplementationState(
            issue=issue,
            design=design,
            **kwargs,
        )
```

Implementation state extends the base with pipeline-specific fields:

```python
# amelia/pipelines/implementation/state.py
class ImplementationState(BasePipelineState):
    """State for implementation pipeline."""
    pipeline_type: Literal["implementation"] = "implementation"

    issue: Issue | None = None
    design: Design | None = None
    plan_markdown: str | None = None
    goal: str | None = None
    last_review: ReviewResult | None = None
    review_iteration: int = 0
```

---

## Migration Steps

1. Create `amelia/pipelines/` directory structure
2. Define `BasePipelineState` and `Pipeline` protocol in `base.py`
3. Create registry with Implementation pipeline only
4. Move `ExecutionState` to `ImplementationState` extending `BasePipelineState`
5. Move orchestrator graph code to `pipelines/implementation/graph.py`
6. Keep `amelia/core/orchestrator.py` as thin wrapper for backward compatibility

---

## File Structure

```
amelia/
├── pipelines/
│   ├── __init__.py
│   ├── base.py                    # BasePipelineState, Pipeline protocol
│   ├── registry.py                # PIPELINES dict, get_pipeline()
│   │
│   └── implementation/
│       ├── __init__.py            # ImplementationPipeline class
│       ├── state.py               # ImplementationState
│       └── graph.py               # create_implementation_graph()
│
├── core/
│   └── orchestrator.py            # Thin wrapper, delegates to pipelines
```

---

## Success Criteria

1. **Protocol defined** - `Pipeline` protocol and `BasePipelineState` exist in `amelia/pipelines/base.py`
2. **Registry works** - `get_pipeline("implementation")` returns a valid `ImplementationPipeline`
3. **State hierarchy** - `ImplementationState` extends `BasePipelineState` with all current fields
4. **Graph relocated** - Implementation graph code lives in `pipelines/implementation/graph.py`
5. **Backward compatible** - All existing tests pass without modification
6. **CLI unchanged** - `amelia start`, `amelia review`, and server commands work as before

---

## Non-Goals

- Adding new pipelines (Phase 2+)
- Dashboard UI changes
- New agents or tools
- Handoff endpoints
