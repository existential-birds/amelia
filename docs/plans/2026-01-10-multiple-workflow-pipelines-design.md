# Multiple Workflow Pipelines Design

**Goal:** Enable Amelia to orchestrate multiple workflow types beyond code implementation.

**Architecture:** Pipelines are distinct LangGraph subgraphs with their own state, agents, inputs, and outputs. A shared base state provides common orchestration fields. A hardcoded registry routes to pipelines by name.

---

## MVP Scope

**In scope:**
- Hardcoded pipeline registry (Implementation + Brainstorming)
- Shared base state with pipeline-specific extensions
- User selects pipeline type explicitly (dashboard UI)
- Brainstorming: chat-based Brainstormer with research tools → Document Writer → handoff prompt
- Implementation: current flow (Architect → Developer ↔ Reviewer)
- Pipeline-to-pipeline handoff via "Plan and Queue" or "Just Queue"

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
from amelia.pipelines.brainstorming import BrainstormingPipeline

PIPELINES: dict[str, type[Pipeline]] = {
    "implementation": ImplementationPipeline,
    "brainstorming": BrainstormingPipeline,
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

```python
# amelia/pipelines/brainstorming/state.py
class BrainstormingState(BasePipelineState):
    """State for brainstorming pipeline."""
    pipeline_type: Literal["brainstorming"] = "brainstorming"

    topic: str
    conversation: list[Message] = Field(default_factory=list)
    design_sections: dict[str, str] = Field(default_factory=dict)
    design_doc_path: Path | None = None
    ready_for_handoff: bool = False
```

---

## Brainstorming Pipeline

### Graph Structure

```python
# amelia/pipelines/brainstorming/graph.py

def create_brainstorming_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:

    graph = StateGraph(BrainstormingState)

    graph.add_node("brainstormer", brainstormer_node)
    graph.add_node("document_writer", document_writer_node)

    graph.set_entry_point("brainstormer")

    graph.add_conditional_edges(
        "brainstormer",
        route_after_brainstormer,
        {
            "wait_for_user": END,
            "write_document": "document_writer",
        }
    )

    graph.add_edge("document_writer", END)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["brainstormer"],
    )

def route_after_brainstormer(state: BrainstormingState) -> str:
    if state.ready_for_handoff:
        return "write_document"
    return "wait_for_user"
```

### Brainstormer Agent

Chat agent with research tools:

```python
# amelia/pipelines/brainstorming/agents/brainstormer.py

class Brainstormer:
    """Conversational agent for exploring ideas and refining designs."""

    SYSTEM_PROMPT = """You help turn ideas into fully formed designs through collaborative dialogue.

## The Process

### Phase 1: Understanding the Idea
- First, check out the current project state (files, docs, recent commits) using your tools
- Ask questions ONE AT A TIME to refine the idea
- Prefer multiple choice questions when possible, but open-ended is fine too
- Only one question per message - if a topic needs more exploration, break it into multiple questions
- Focus on understanding: purpose, constraints, success criteria

### Phase 2: Exploring Approaches
- Propose 2-3 different approaches with trade-offs
- Present options conversationally with your recommendation and reasoning
- Lead with your recommended option and explain why

### Phase 3: Presenting the Design
- Once you believe you understand what you're building, present the design
- Break it into sections of 200-300 words
- Ask after each section: "Does this look right so far?"
- Cover: architecture, components, data flow, error handling, testing
- Be ready to go back and clarify if something doesn't make sense

### Phase 4: Completion
- When all sections are validated, ask: "Ready to document?"
- If user confirms, signal ready_for_handoff

## Key Principles
- **One question at a time** - Don't overwhelm with multiple questions
- **Multiple choice preferred** - Easier to answer than open-ended when possible
- **YAGNI ruthlessly** - Remove unnecessary features from all designs
- **Explore alternatives** - Always propose 2-3 approaches before settling
- **Incremental validation** - Present design in sections, validate each
- **Be flexible** - Go back and clarify when something doesn't make sense

## Tools Available
Use these to understand project context before and during brainstorming:
- research_codebase: Search code for patterns, examples, existing implementations
- explore_files: Read specific files to understand context
- web_search: Search for external references, libraries, best practices
"""

    TOOLS = [
        research_codebase,
        explore_files,
        web_search,
    ]
```

### Document Writer Agent

```python
# amelia/pipelines/brainstorming/agents/document_writer.py

class DocumentWriter:
    """Agent that writes validated design to a markdown file."""

    SYSTEM_PROMPT = """You are a technical writer producing design documents.

## Your Task
Take the validated design sections from the brainstorming conversation and write them as a clean markdown document.

## Output
Write to: docs/plans/YYYY-MM-DD-<topic>-design.md

## Structure
- Title and overview
- Each validated section, cleaned up for readability
- No new content - only organize and polish what was validated

## Writing Style

Follow Strunk & White and Orwell:

**Core principles:**
- Use active voice
- Put statements in positive form (avoid "not")
- Use definite, specific, concrete language
- Omit needless words
- Keep related words together
- Place emphatic words at end of sentence

**Orwell's rules:**
- Never use a long word where a short one will do
- If it is possible to cut a word out, always cut it out
- Never use the passive where you can use the active
- Never use jargon if you can think of an everyday equivalent

**Be ruthless.** Cut every word that doesn't earn its place.
"""
```

### Research Tools

Create these tools for the Brainstormer:

- `research_codebase`: Wrapper around grep/glob for searching code
- `explore_files`: Wrapper around file read for examining specific files
- `web_search`: Wrapper around web search for external references

---

## Pipeline-to-Pipeline Handoff

After Document Writer completes, the dashboard prompts for handoff:

```python
# amelia/server/api/routes/workflows.py

@router.post("/workflows/{workflow_id}/handoff")
async def handoff_to_implementation(
    workflow_id: str,
    request: HandoffRequest,
    repo: WorkflowRepository = Depends(get_repo),
):
    """Hand off completed brainstorming to implementation pipeline."""

    brainstorm_workflow = await repo.get_workflow(workflow_id)
    if brainstorm_workflow.pipeline_type != "brainstorming":
        raise HTTPException(400, "Can only hand off from brainstorming")
    if brainstorm_workflow.status != "completed":
        raise HTTPException(400, "Brainstorming must be completed")

    impl_workflow = await repo.create_workflow(
        pipeline_type="implementation",
        profile_id=brainstorm_workflow.profile_id,
        initial_state={
            "design": Design.from_file(brainstorm_workflow.design_doc_path),
            "issue": request.issue,
        },
    )

    if request.mode == "plan_and_queue":
        await orchestrator.start_planning(impl_workflow.id)

    return {"workflow_id": impl_workflow.id, "status": "created"}

class HandoffRequest(BaseModel):
    mode: Literal["plan_and_queue", "just_queue"]
    issue: Issue | None = None
```

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

```
amelia/
├── pipelines/
│   ├── __init__.py
│   ├── base.py                    # BasePipelineState, Pipeline protocol
│   ├── registry.py                # PIPELINES dict, get_pipeline()
│   │
│   ├── implementation/
│   │   ├── __init__.py            # ImplementationPipeline class
│   │   ├── state.py               # ImplementationState
│   │   └── graph.py               # create_implementation_graph()
│   │
│   └── brainstorming/
│       ├── __init__.py            # BrainstormingPipeline class
│       ├── state.py               # BrainstormingState
│       ├── graph.py               # create_brainstorming_graph()
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── brainstormer.py
│       │   └── document_writer.py
│       └── tools/
│           ├── __init__.py
│           ├── research_codebase.py
│           ├── explore_files.py
│           └── web_search.py
│
├── core/
│   └── orchestrator.py            # Thin wrapper, delegates to pipelines

dashboard/src/
├── components/
│   ├── chat/
│   │   ├── ChatView.tsx
│   │   ├── ChatMessage.tsx
│   │   ├── ChatInput.tsx
│   │   ├── ToolCallCard.tsx
│   │   └── index.ts
│   ├── QuickShotModal.tsx
│   ├── HandoffDialog.tsx
│   └── workflows/
│       ├── ImplementationView.tsx
│       └── BrainstormingView.tsx
```

---

## Implementation Phases

### Phase 1: Foundation
- Create `amelia/pipelines/` structure
- Define `BasePipelineState` and `Pipeline` protocol
- Create registry with just Implementation pipeline
- Refactor current orchestrator → `ImplementationPipeline`
- Verify existing functionality still works

### Phase 2: Brainstorming Pipeline Backend
- Create `BrainstormingState`
- Create Brainstormer agent with system prompt
- Create research tools (research_codebase, explore_files, web_search)
- Create DocumentWriter agent
- Create brainstorming graph with chat loop
- Add handoff endpoint

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
