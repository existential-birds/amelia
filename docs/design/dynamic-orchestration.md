# Dynamic Orchestration Design

> Enabling adaptive workflows where a Planner agent composes and adjusts agent pipelines at runtime.
> Builds on the [Stateless Reducer Pattern](./stateless-reducer-pattern.md).

## Problem Statement

Amelia's current orchestrator uses a fixed workflow:

```
Architect → Human Approval → Developer ↔ Reviewer → Done
```

This creates friction for real-world software engineering tasks:

| Work Type | Problem with Fixed Flow |
|-----------|------------------------|
| Trivial fix (typo, config) | Full Architect planning is overkill |
| Bug investigation | Jumps to planning before understanding the problem |
| Complex feature | No way to bring in specialized analysis first |
| Security-sensitive change | Generic review misses domain-specific risks |

**Goal**: A meta-orchestrator where a Planner agent creates and adapts workflows from a toolkit of specialized agents.

## Design Principles

1. **Stateless**: Builds on frozen models, partial dict returns, reducers
2. **Composable**: Agents are independent units; Planner composes them
3. **Observable**: Workflow decisions are explicit in state, not implicit in code
4. **Interruptible**: Human approval configurable per-agent, not hardcoded

## Agent Toolkit

Starting with four agents (extensible later):

| Agent | Purpose | Inputs | Outputs |
|-------|---------|--------|---------|
| **Analyst** | Investigate before planning - debug, explore codebase, gather context | Issue | `AnalysisResult` with findings, recommendations |
| **Architect** | Create implementation plan with goal extraction | Issue + Analysis (optional) | `PlanOutput` with goal, markdown plan |
| **Developer** | Execute goal agentically using tool calls | Goal + context | `ToolCall`/`ToolResult` stream |
| **Reviewer** | Review code changes | Code diff + context | `ReviewResult` |

## State Model

Extends `ExecutionState` from stateless reducer pattern with workflow awareness:

```python
# amelia/core/state.py
from __future__ import annotations
from datetime import datetime
from operator import add
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field


# --- Reducers (from stateless-reducer-pattern.md) ---
def dict_merge(left: dict, right: dict) -> dict:
    """Shallow merge: right wins on key conflicts."""
    return {**(left or {}), **(right or {})}

def set_union(left: set, right: set) -> set:
    return (left or set()) | (right or set())


# --- Workflow Types ---
AgentType = Literal["analyst", "architect", "developer", "reviewer"]
StepStatus = Literal["pending", "running", "completed", "failed", "skipped"]


class WorkflowStep(BaseModel):
    """A single step in the dynamic workflow."""
    model_config = ConfigDict(frozen=True)

    agent: AgentType
    status: StepStatus = "pending"
    reason: str  # Why this step was added (for observability)
    requires_approval: bool = False  # Overrides profile default if True


class WorkflowPlan(BaseModel):
    """Dynamic workflow created/modified by Planner."""
    model_config = ConfigDict(frozen=True)

    steps: tuple[WorkflowStep, ...]  # Immutable sequence
    current_step_index: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    replanned_count: int = 0


class ReplanRequest(BaseModel):
    """Signal from agent requesting workflow replan."""
    model_config = ConfigDict(frozen=True)

    requested_by: AgentType
    reason: str
    suggested_agents: tuple[AgentType, ...] = ()  # Optional hints


# --- Agent Outputs ---
class AgentOutputBase(BaseModel):
    """Base class for all agent outputs with confidence tracking."""
    model_config = ConfigDict(frozen=True)

    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    uncertainty_factors: tuple[str, ...] = ()


class AnalysisResult(BaseModel):
    """Output from Analyst agent."""
    model_config = ConfigDict(frozen=True)

    findings: str
    scope_assessment: Literal["trivial", "simple", "moderate", "complex"]
    recommended_agents: tuple[AgentType, ...] = ()
    relevant_files: tuple[str, ...] = ()


# TaskResult, ReviewResult already defined in stateless-reducer-pattern.md


# --- Extended ExecutionState ---
class ExecutionState(BaseModel):
    """Parallel-safe state with dynamic workflow support.

    Extends stateless reducer pattern with:
    - workflow: The current workflow plan
    - agent_outputs: Keyed outputs from each agent execution
    - replan_request: Signal for Planner to replan
    """
    model_config = ConfigDict(frozen=True)

    # --- Replay/identity metadata ---
    profile_id: str = ""

    # --- Domain data (single-writer) ---
    issue: Issue | None = None
    design: Design | None = None
    goal: str | None = None  # Goal extracted from Architect plan
    plan_markdown: str | None = None  # Markdown plan content
    plan_path: Path | None = None  # Where plan was saved

    # --- Dynamic workflow ---
    workflow: WorkflowPlan | None = None
    replan_request: ReplanRequest | None = None  # Set by agent, cleared by Planner

    # --- Agent outputs (parallel-safe, keys disjoint by step index) ---
    agent_outputs: Annotated[dict[str, Any], dict_merge] = Field(default_factory=dict)
    # Keys: "analyst_0", "architect_1", "developer_2", "reviewer_3", etc.

    # --- Agentic execution (tool call/result tracking) ---
    tool_calls: Annotated[list[ToolCall], add] = Field(default_factory=list)
    tool_results: Annotated[list[ToolResult], add] = Field(default_factory=list)

    # --- Driver sessions (scoped by agent) ---
    driver_sessions: Annotated[dict[str, DriverSession], dict_merge] = Field(default_factory=dict)

    # --- Append-only logs ---
    history: Annotated[list[HistoryEntry], add] = Field(default_factory=list)

    # --- Idempotency ---
    completed_steps: Annotated[set[str], set_union] = Field(default_factory=set)

    # --- Control flow ---
    pending_approval_for: AgentType | None = None  # Set when waiting for human
    human_approved: bool | None = None
    last_review: ReviewResult | None = None
    workflow_status: Literal["planning", "running", "awaiting_approval", "completed", "failed"] = "planning"

    # --- Helpers ---
    def get_current_step(self) -> WorkflowStep | None:
        """Get the current workflow step."""
        if not self.workflow or self.workflow.current_step_index >= len(self.workflow.steps):
            return None
        return self.workflow.steps[self.workflow.current_step_index]

    def get_agent_output(self, agent: AgentType, step_index: int | None = None) -> Any | None:
        """Get output from a specific agent execution."""
        if step_index is not None:
            return self.agent_outputs.get(f"{agent}_{step_index}")
        # Find most recent output for this agent type
        for i in range(len(self.workflow.steps) - 1, -1, -1) if self.workflow else []:
            key = f"{agent}_{i}"
            if key in self.agent_outputs:
                return self.agent_outputs[key]
        return None
```

## Graph Structure

```
                         ┌──────────────┐
           ┌────────────►│   planner    │◄───────────────┐
           │             └──────┬───────┘                │
           │                    │                        │
           │                    ▼                        │
           │             ┌──────────────┐                │
           │             │  dispatcher  │────────────────┤
           │             └──────┬───────┘                │
           │                    │                        │
           │    ┌───────┬───────┼───────┬────────┐       │
           │    ▼       ▼       ▼       ▼        │       │
           │ analyst architect developer reviewer │       │
           │    │       │       │       │        │       │
           │    └───────┴───────┴───────┴────────┘       │
           │                    │                        │
           │                    ▼                        │
           │             ┌──────────────┐                │
           │             │   reducer    │────────────────┘
           │             └──────┬───────┘        (replan)
           │                    │
           │                    ▼
           │             ┌──────────────┐
           └─────────────┤human_approval│ (conditional)
                         └──────┬───────┘
                                │
                                ▼
                               END
```

**Node Responsibilities:**

| Node | Purpose |
|------|---------|
| `planner` | Creates/updates `WorkflowPlan` based on issue + agent_outputs |
| `dispatcher` | Routes to next agent or human_approval based on workflow state |
| `analyst/architect/developer/reviewer` | Execute agent logic, return partial updates |
| `reducer` | Advances workflow, checks for replan requests |
| `human_approval` | Interrupt point for human decision |

## Planner Agent

### Context Strategy

```python
class PlannerContextStrategy(ContextStrategy):
    """Compiles context for workflow planning."""

    SYSTEM_PROMPT = """You are a workflow planner for software engineering tasks.
Analyze work items and decide which agents are needed and in what order.

Available agents:
- analyst: Investigates codebases, debugs issues, gathers context. Use when problem is unclear.
- architect: Creates implementation plans with task breakdowns. Use for non-trivial features.
- developer: Executes implementation following TDD. Always needed for code changes.
- reviewer: Reviews code changes. Always needed after developer.

Guidelines:
- For trivial fixes (typos, config): [developer, reviewer]
- For bugs needing investigation: [analyst, developer, reviewer] or [analyst, architect, developer, reviewer]
- For clear features: [architect, developer, reviewer]
- For complex features: [analyst, architect, developer, reviewer]

When replanning:
- Consider what agents have already run (check agent_outputs)
- Don't repeat completed work unless explicitly needed
- Add agents if scope expanded, skip if scope reduced"""

    ALLOWED_SECTIONS = {"issue", "agent_outputs", "replan_request", "current_workflow"}

    def compile(self, state: ExecutionState) -> CompiledContext:
        sections = []

        # Issue (required)
        if state.issue:
            sections.append(ContextSection(
                name="issue",
                content=format_issue(state.issue),
                source="state.issue",
            ))

        # Agent outputs (for replanning context)
        if state.agent_outputs:
            outputs_md = format_agent_outputs(state.agent_outputs)
            sections.append(ContextSection(
                name="agent_outputs",
                content=outputs_md,
                source="state.agent_outputs",
            ))

        # Replan request (if present)
        if state.replan_request:
            sections.append(ContextSection(
                name="replan_request",
                content=f"**Requested by**: {state.replan_request.requested_by}\n"
                        f"**Reason**: {state.replan_request.reason}\n"
                        f"**Suggested agents**: {', '.join(state.replan_request.suggested_agents) or 'none'}",
                source="state.replan_request",
            ))

        # Current workflow (for replanning)
        if state.workflow:
            workflow_md = format_workflow(state.workflow)
            sections.append(ContextSection(
                name="current_workflow",
                content=workflow_md,
                source="state.workflow",
            ))

        return CompiledContext(system_prompt=self.SYSTEM_PROMPT, sections=sections)
```

### Output Schema

```python
class PlannerDecision(BaseModel):
    """Planner's workflow decision."""
    model_config = ConfigDict(frozen=True)

    reasoning: str  # Explanation for observability
    steps: tuple[PlannedStep, ...]


class PlannedStep(BaseModel):
    """A step in the planned workflow."""
    model_config = ConfigDict(frozen=True)

    agent: AgentType
    reason: str  # Why this agent at this position
```

## Plan Verification

Before Developer executes, verify the goal and plan scope:

```python
class PlanVerificationResult(BaseModel):
    """Result of plan verification."""
    model_config = ConfigDict(frozen=True)

    valid: bool
    violations: tuple[str, ...] = ()
    suggested_fixes: tuple[str, ...] = ()

async def verify_plan(goal: str, plan_markdown: str, codebase: CodebaseContext) -> PlanVerificationResult:
    """Verify plan before execution.

    Checks:
    - Goal is clear and actionable
    - Referenced files exist in codebase
    - Scope matches complexity estimate
    """
    ...
```

This addresses research finding: "LLMs can't plan, but can help planning in LLM-modulo frameworks" (Kambhampati et al. 2024).

### Planner Node

```python
async def planner_node(state: ExecutionState, config: RunnableConfig) -> dict:
    """Create or update workflow plan."""
    profile: Profile = config["configurable"]["profile"]
    driver = DriverFactory.get_driver(profile.driver)

    strategy = PlannerContextStrategy()
    context = strategy.compile(state)
    messages = strategy.to_messages(context)

    response = await driver.generate(
        messages=messages,
        session=state.driver_sessions.get("planner", DriverSession()),
        schema=PlannerDecision,
    )

    decision = PlannerDecision.model_validate_json(response.content)

    # Build workflow steps with approval requirements from profile
    steps = tuple(
        WorkflowStep(
            agent=step.agent,
            reason=step.reason,
            requires_approval=step.agent in profile.approval_required,
        )
        for step in decision.steps
    )

    # Determine if this is initial plan or replan
    replanned_count = (state.workflow.replanned_count + 1) if state.workflow else 0

    return {
        "workflow": WorkflowPlan(
            steps=steps,
            current_step_index=0,
            replanned_count=replanned_count,
        ),
        "replan_request": None,  # Clear the replan request
        "workflow_status": "running",
        "history": [HistoryEntry(
            actor="planner",
            event="workflow_planned",
            detail={
                "reasoning": decision.reasoning,
                "agents": [s.agent for s in steps],
                "is_replan": replanned_count > 0,
            },
        )],
        "driver_sessions": {"planner": response.session},
    }
```

## Dispatcher Node

Routes to next agent or control flow based on workflow state:

```python
def dispatcher_node(state: ExecutionState, config: RunnableConfig) -> Command:
    """Route to next step in workflow."""
    profile: Profile = config["configurable"]["profile"]

    # Check if workflow complete
    if not state.workflow or state.workflow.current_step_index >= len(state.workflow.steps):
        return Command(goto=END, update={"workflow_status": "completed"})

    current_step = state.workflow.steps[state.workflow.current_step_index]

    # Check if approval required for this agent
    needs_approval = (
        current_step.requires_approval or
        current_step.agent in profile.approval_required
    )

    if needs_approval and state.human_approved is None:
        return Command(
            goto="human_approval",
            update={
                "pending_approval_for": current_step.agent,
                "workflow_status": "awaiting_approval",
            },
        )

    # Confidence-based escalation (research: "self-assess confidence scores")
    prev_output = state.get_agent_output(current_step.agent)
    if prev_output and hasattr(prev_output, 'confidence'):
        if prev_output.confidence < profile.escalation_threshold:
            return Command(
                goto="human_approval",
                update={
                    "pending_approval_for": current_step.agent,
                    "workflow_status": "awaiting_approval",
                    "history": [HistoryEntry(
                        actor="dispatcher",
                        event="confidence_escalation",
                        detail={"confidence": prev_output.confidence, "agent": current_step.agent},
                    )],
                },
            )

    # Route to agent
    return Command(goto=f"{current_step.agent}_node")
```

## Reducer Node

Advances workflow and checks for replanning:

```python
def reducer_node(state: ExecutionState) -> Command:
    """Advance workflow and check for replan triggers."""

    # Check if replan requested
    if state.replan_request:
        return Command(goto="planner_node")

    # Check if current agent failed
    current_step = state.get_current_step()
    if current_step and current_step.status == "failed":
        # TDAG pattern: adapt when subtasks fail
        if state.workflow and state.workflow.replanned_count < profile.max_replans:
            return Command(
                goto="planner_node",
                update={
                    "replan_request": ReplanRequest(
                        requested_by=current_step.agent,
                        reason=f"Agent {current_step.agent} failed, attempting recovery",
                        suggested_agents=(),
                    ),
                },
            )
        return Command(goto=END, update={"workflow_status": "failed"})

    # Advance to next step
    if state.workflow:
        new_workflow = state.workflow.model_copy(update={
            "current_step_index": state.workflow.current_step_index + 1,
        })
        return Command(
            goto="dispatcher_node",
            update={"workflow": new_workflow, "human_approved": None},
        )

    return Command(goto=END)
```

## Agent Nodes

Each agent follows the same pattern:

```python
async def analyst_node(state: ExecutionState, config: RunnableConfig) -> dict:
    """Analyst agent - investigates before planning."""
    profile: Profile = config["configurable"]["profile"]
    step_index = state.workflow.current_step_index

    driver = DriverFactory.get_driver(profile.driver)
    session = state.driver_sessions.get("analyst", DriverSession())

    strategy = AnalystContextStrategy()
    context = strategy.compile(state)
    messages = strategy.to_messages(context)

    response = await driver.generate(
        messages=messages,
        session=session,
        schema=AnalysisResult,
    )

    result = AnalysisResult.model_validate_json(response.content)

    # Determine if replan needed based on findings
    replan_request = None
    if result.scope_assessment == "complex" and "architect" not in [
        s.agent for s in state.workflow.steps
    ]:
        replan_request = ReplanRequest(
            requested_by="analyst",
            reason=f"Scope is {result.scope_assessment}, recommend adding architect",
            suggested_agents=("architect",),
        )

    return {
        "agent_outputs": {f"analyst_{step_index}": result},
        "replan_request": replan_request,
        "driver_sessions": {"analyst": response.session},
        "history": [HistoryEntry(
            actor="analyst",
            event="analysis_completed",
            detail={
                "scope": result.scope_assessment,
                "files_found": len(result.relevant_files),
            },
        )],
        "completed_steps": {f"analyst:{step_index}"},
    }
```

## Human Approval Configuration

In `Profile`:

```python
class Profile(BaseModel):
    """Profile configuration."""
    model_config = ConfigDict(frozen=True)

    name: str
    driver: str
    tracker: str = "noop"
    working_dir: str | None = None

    # Dynamic orchestration settings
    orchestration_mode: Literal["fixed", "dynamic"] = "fixed"
    approval_required: frozenset[AgentType] = frozenset({"architect"})

    # Planner can escalate approval for specific workflows
    auto_approve_trivial: bool = True  # Skip approval for trivial scope

    # Research-informed additions
    max_replans: int = 3  # Prevent infinite replan loops
    escalation_threshold: float = 0.7  # Confidence below this triggers human approval
    max_agent_output_tokens: int = 2000  # Research: subagents return condensed summaries
```

Human approval node with `interrupt_before`:

```python
async def human_approval_node(state: ExecutionState) -> dict:
    """Human approval checkpoint. Graph interrupts before this node."""
    # When resumed, human_approved will be set via state update
    if state.human_approved:
        return {
            "workflow_status": "running",
            "history": [HistoryEntry(
                actor="human",
                event="approved",
                detail={"agent": state.pending_approval_for},
            )],
        }
    else:
        return {
            "workflow_status": "failed",
            "history": [HistoryEntry(
                actor="human",
                event="rejected",
                detail={"agent": state.pending_approval_for},
            )],
        }
```

## Graph Construction

```python
def create_dynamic_orchestrator_graph(
    checkpoint_saver: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any]:
    """Create dynamic orchestrator with Planner-driven workflow."""

    workflow = StateGraph(ExecutionState)

    # Add nodes
    workflow.add_node("planner_node", planner_node)
    workflow.add_node("dispatcher_node", dispatcher_node)
    workflow.add_node("analyst_node", analyst_node)
    workflow.add_node("architect_node", architect_node)
    workflow.add_node("developer_node", developer_node)
    workflow.add_node("reviewer_node", reviewer_node)
    workflow.add_node("reducer_node", reducer_node)
    workflow.add_node("human_approval_node", human_approval_node)

    # Entry point
    workflow.set_entry_point("planner_node")

    # Planner -> Dispatcher
    workflow.add_edge("planner_node", "dispatcher_node")

    # Dispatcher routes via Command (dynamic routing)
    # Agent nodes -> Reducer
    for agent in ["analyst", "architect", "developer", "reviewer"]:
        workflow.add_edge(f"{agent}_node", "reducer_node")

    # Reducer routes via Command (to dispatcher or planner or END)
    # Human approval -> Dispatcher (after approval decision)
    workflow.add_edge("human_approval_node", "dispatcher_node")

    return workflow.compile(
        checkpointer=checkpoint_saver,
        interrupt_before=["human_approval_node"],
    )
```

## Example Workflows

### Trivial Bug Fix

```
Issue: "Fix typo in README.md"

Planner decides: [developer, reviewer]
  → developer_node (no approval needed)
  → reducer_node
  → dispatcher_node
  → reviewer_node
  → reducer_node
  → dispatcher_node
  → END (completed)
```

### Bug Investigation

```
Issue: "Login fails intermittently"

Planner decides: [analyst, developer, reviewer]
  → analyst_node
  → reducer_node (analyst found it's a race condition, simple fix)
  → dispatcher_node
  → developer_node
  → reducer_node
  → dispatcher_node
  → reviewer_node
  → reducer_node
  → END (completed)
```

### Complex Feature with Replan

```
Issue: "Add OAuth2 support"

Planner decides: [analyst, architect, developer, reviewer]
  → analyst_node
  → reducer_node (analyst: scope is complex, need security review)
  → replan_request set
  → planner_node (replan)

Planner replans: [architect, developer, security_reviewer, reviewer]
  → dispatcher_node
  → architect_node (approval required)
  → human_approval_node (interrupt)
  ... human approves ...
  → dispatcher_node
  → developer_node
  → reducer_node
  → ... continues ...
```

## Migration Path

### Phase 1: Add Types (No Behavior Change)

1. Add new types to `amelia/core/state.py`:
   - `WorkflowStep`, `WorkflowPlan`, `ReplanRequest`
   - `AnalysisResult`
   - New fields on `ExecutionState`

2. Add `orchestration_mode` to `Profile`

### Phase 2: Implement Planner

1. Create `amelia/agents/planner.py`:
   - `PlannerContextStrategy`
   - `Planner` class

2. Create `amelia/agents/analyst.py`:
   - `AnalystContextStrategy`
   - `Analyst` class

### Phase 3: Build Dynamic Graph

1. Create `amelia/core/dynamic_orchestrator.py`:
   - `planner_node`, `dispatcher_node`, `reducer_node`
   - Wrap existing agents for dynamic flow
   - `create_dynamic_orchestrator_graph()`

2. Update `amelia/core/orchestrator.py`:
   - Factory function that picks fixed vs dynamic based on profile

### Phase 4: CLI Integration

1. Update CLI to support `--orchestration-mode dynamic`
2. Add profile field `orchestration_mode: dynamic`
3. Dashboard updates for workflow visualization

## Files to Create/Modify

| File | Changes |
|------|---------|
| `amelia/core/state.py` | Add workflow types, extend ExecutionState with agentic fields |
| `amelia/core/agentic_state.py` | ToolCall, ToolResult, AgenticStatus types |
| `amelia/core/types.py` | Add `AgentType`, `StepStatus` literals |
| `amelia/agents/planner.py` | New: Planner agent |
| `amelia/agents/analyst.py` | New: Analyst agent |
| `amelia/core/dynamic_orchestrator.py` | New: Dynamic graph construction |
| `amelia/core/orchestrator.py` | Factory for fixed vs dynamic |
| `amelia/core/config.py` | Add `approval_required` to Profile |
| `tests/unit/test_planner.py` | New: Planner tests |
| `tests/unit/test_dynamic_orchestrator.py` | New: Dynamic flow tests |

## Success Criteria

- [ ] Planner correctly routes trivial issues to [developer, reviewer]
- [ ] Planner adds analyst for unclear/investigation issues
- [ ] Planner adds architect for non-trivial features
- [ ] Replan triggers when agent requests it
- [ ] Human approval interrupts at configured agents
- [ ] Workflow state is fully observable in history
- [ ] Fixed orchestration mode still works unchanged
- [ ] All existing tests pass
- [ ] New workflow patterns have test coverage

## Research Foundation

This design is informed by industry research on agentic AI systems:

| Pattern | Research Finding | Implementation |
|---------|------------------|----------------|
| Orchestrator-Worker | 90.2% improvement over single agent (Anthropic) | Planner → specialized agents |
| Dynamic Decomposition | Outperforms static planning (TDAG) | ReplanRequest mechanism |
| Confidence Routing | "Self-assess confidence scores" (LangChain survey) | escalation_threshold in Profile |
| Plan Verification | "LLMs can't plan alone" (Kambhampati 2024) | verify_plan step |
| Failure Recovery | TDAG "adapts when subtasks fail" | Failure-triggered replanning |

See `/Users/ka/Downloads/knowledge_agents_research.md` for full research analysis.

## Open Questions

1. **Should Planner have retry limits for replanning?** Yes, max_replans=3 prevents infinite loops
2. **How to handle partial agent failure?** Failure-triggered replanning with retry counter, fail workflow after max_replans
3. **Should we support parallel agent execution?** Phase 8 will add sectioning (parallel independent tasks) and voting (same task multiple times for consensus)
4. **How to visualize workflow in dashboard?** (React Flow integration)
