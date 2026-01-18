# Multiple Workflow Pipelines Design

**Goal:** Enable Amelia to orchestrate multiple workflow types beyond code implementation.

**Architecture:** Pipelines are distinct LangGraph subgraphs with their own state, agents, inputs, and outputs. A shared base state provides common orchestration fields. A hardcoded registry routes to pipelines by name.

---

## Implementation Status

| Phase | Status | PRs |
|-------|--------|-----|
| **Phase 1: Foundation** | **COMPLETE** | #295, #296, feat/pipeline-cleanup-262 |
| Phase 2: Brainstorming Sessions Backend | **DESIGNED** | - |
| Phase 3: Dashboard UI | Not started | - |
| Phase 4: Integration & Polish | Not started | - |

**Phase 2 design completed 2026-01-18:**
- See [Brainstorming Pipeline Design](./2026-01-18-brainstorming-pipeline-design.md) for detailed design
- Key decision: Direct chat sessions with driver continuity, NOT a LangGraph workflow
- Reuses existing WebSocket infrastructure for streaming
- Dedicated database tables for sessions, messages, artifacts
- ai-elements React components for chat UI

**Phase 1 completed 2026-01-18:**
- Created `amelia/pipelines/` package with `Pipeline` protocol and `BasePipelineState`
- Implemented `ImplementationPipeline` and `ReviewPipeline` (bonus: Review pipeline added)
- Created pipeline registry with `get_pipeline()` and `list_pipelines()`
- Migrated all callers to new pipeline locations
- Deleted legacy `orchestrator.py` and `state.py`
- 932 unit tests passing

---

## MVP Scope

**In scope:**
- Hardcoded pipeline registry (Implementation + Review)
- Shared base state with pipeline-specific extensions
- User selects pipeline type explicitly (dashboard UI)
- Brainstorming: chat-based sessions with driver continuity and Oracle research (NOT a LangGraph pipeline — see Phase 2 design)
- Implementation: current flow (Architect → Developer ↔ Reviewer)
- Session-to-pipeline handoff via "Plan and Queue" or "Just Queue"

**Out of scope:**
- Planner agent (automatic intent detection)
- Pipeline builder UI
- User-defined pipelines
- Additional pipeline types

---

## Pipeline Protocol and Registry

Each pipeline implements a common protocol:

```python
# amelia/pipelines/base.py
from typing import Protocol, TypeVar
from langgraph.graph.state import CompiledStateGraph

StateT = TypeVar("StateT", bound="BasePipelineState")

class Pipeline(Protocol[StateT]):
    """Protocol that all pipelines must implement."""

    name: str  # "implementation", "brainstorming"
    display_name: str  # "Implementation", "Brainstorming"
    description: str

    def create_graph(
        self,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> CompiledStateGraph: ...

    def get_initial_state(self, **kwargs) -> StateT: ...

    def get_state_class(self) -> type[StateT]: ...
```

The registry is a simple dict:

```python
# amelia/pipelines/registry.py
from amelia.pipelines.implementation import ImplementationPipeline
from amelia.pipelines.review import ReviewPipeline

PIPELINES: dict[str, type[Pipeline]] = {
    "implementation": ImplementationPipeline,
    "review": ReviewPipeline,
}

def get_pipeline(name: str) -> Pipeline:
    if name not in PIPELINES:
        raise ValueError(f"Unknown pipeline: {name}")
    return PIPELINES[name]()
```

---

## State Model

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

Each pipeline extends with its own fields:

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

Note: Brainstorming uses dedicated database tables instead of pipeline state. See [Phase 2 design](./2026-01-18-brainstorming-pipeline-design.md).

---

## Brainstorming Sessions

Brainstorming is implemented as direct chat sessions with Claude driver session continuity, NOT as a LangGraph pipeline. See [Brainstorming Pipeline Design](./2026-01-18-brainstorming-pipeline-design.md) for full details.

Key differences from pipelines:
- No LangGraph state machine — driver maintains conversation context via `session_id`
- Dedicated database tables: `brainstorm_sessions`, `brainstorm_messages`, `brainstorm_artifacts`
- Streams via existing WebSocket infrastructure
- Hands off to Implementation pipeline via artifact path

---

## Session-to-Pipeline Handoff

Brainstorming sessions hand off to implementation workflows via the artifact path (design document). The handoff creates a new implementation workflow with the design document attached.

See [Brainstorming Pipeline Design](./2026-01-18-brainstorming-pipeline-design.md) for handoff API details and flow.

---

## Implementation Pipeline Refactoring

The current orchestrator becomes the Implementation pipeline:

```python
# amelia/pipelines/implementation/__init__.py

class ImplementationPipeline:
    """Pipeline for implementing code from issues/designs."""

    name = "implementation"
    display_name = "Implementation"
    description = "Build features and fix bugs with Architect → Developer ↔ Reviewer flow"

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

Migration:
1. Create `amelia/pipelines/` structure
2. Move `ExecutionState` → `ImplementationState` extending `BasePipelineState`
3. Move orchestrator graph code to `pipelines/implementation/graph.py`
4. Keep `amelia/core/orchestrator.py` as thin wrapper for backward compatibility

---

## Dashboard UI Changes

### Reusable Chat Component

```typescript
// dashboard/src/components/chat/ChatView.tsx

interface ChatViewProps {
  messages: Message[]
  onSendMessage: (content: string) => void
  isWaitingForResponse: boolean
  toolCalls?: ToolCall[]
}
```

### Pipeline Selection

Add pipeline selector to Quick Shot modal:

```typescript
// dashboard/src/components/QuickShotModal.tsx

<Select value={pipelineType} onValueChange={setPipelineType}>
  <SelectItem value="implementation">Implementation</SelectItem>
  <SelectItem value="brainstorming">Brainstorming</SelectItem>
</Select>

{pipelineType === "implementation" && <IssueInput ... />}
{pipelineType === "brainstorming" && <TopicInput ... />}
```

### Handoff Dialog

```typescript
// dashboard/src/components/HandoffDialog.tsx

<Dialog>
  <DialogTitle>Ready to implement?</DialogTitle>
  <Button onClick={() => handoff("plan_and_queue")}>Plan and Queue</Button>
  <Button variant="outline" onClick={() => handoff("just_queue")}>Just Queue</Button>
  <Button variant="ghost" onClick={close}>Not now</Button>
</Dialog>
```

---

## File Structure

### Implemented (Phase 1)

```
amelia/
├── pipelines/
│   ├── __init__.py                # Re-exports: Pipeline, BasePipelineState, get_pipeline
│   ├── base.py                    # PipelineMetadata, HistoryEntry, BasePipelineState, Pipeline protocol
│   ├── registry.py                # PIPELINES dict, get_pipeline(), list_pipelines()
│   ├── nodes.py                   # Shared nodes: call_developer_node, call_reviewer_node
│   ├── routing.py                 # Shared routing: route_after_review_or_task
│   ├── utils.py                   # Shared utilities: extract_config_params
│   │
│   ├── implementation/
│   │   ├── __init__.py            # Re-exports
│   │   ├── pipeline.py            # ImplementationPipeline class
│   │   ├── state.py               # ImplementationState, rebuild_implementation_state()
│   │   ├── graph.py               # create_implementation_graph()
│   │   ├── nodes.py               # call_architect_node, plan_validator_node, human_approval_node, next_task_node
│   │   ├── routing.py             # route_approval, route_after_task_review
│   │   └── utils.py               # extract_task_count, extract_task_section, commit_task_changes
│   │
│   └── review/
│       ├── __init__.py            # Re-exports
│       ├── pipeline.py            # ReviewPipeline class
│       ├── graph.py               # create_review_graph()
│       ├── nodes.py               # call_evaluation_node, review_approval_node
│       └── routing.py             # route_after_evaluation, route_after_fixes, route_after_end_approval
│
├── core/
│   ├── types.py                   # Design, ReviewResult, Severity (domain types)
│   └── extraction.py              # extract_structured() utility
```

### Planned (Phase 2+)

See [Phase 2 design](./2026-01-18-brainstorming-pipeline-design.md) for brainstorming file structure.

---

## Implementation Phases

### Phase 1: Foundation [COMPLETE]
- [x] Create `amelia/pipelines/` structure
- [x] Define `BasePipelineState` and `Pipeline` protocol
- [x] Create registry with Implementation + Review pipelines
- [x] Refactor current orchestrator → `ImplementationPipeline`
- [x] Create `ReviewPipeline` for `amelia review --local` workflow
- [x] Verify existing functionality still works (932 tests passing)

### Phase 2: Brainstorming Sessions Backend

See [Brainstorming Pipeline Design](./2026-01-18-brainstorming-pipeline-design.md) for detailed tasks and implementation plan.

### Phase 3: Dashboard UI
- Build reusable `ChatView` component
- Add pipeline selector to Quick Shot modal
- Create `BrainstormingView` using ChatView
- Create `HandoffDialog` component
- Wire up API calls

### Phase 4: Integration & Polish
- End-to-end testing of brainstorming flow
- Handoff to implementation flow
- Error handling and edge cases

---

## Related Issues

- Issue #98: Workflow orchestration with Planner agent (future: automatic intent detection)
- Issue #204: Spec Builder (could become a pipeline)
