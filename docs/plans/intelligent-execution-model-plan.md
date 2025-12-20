# Implementation Plan: Intelligent Execution Model

> Transforming Developer from blind executor to intelligent plan follower with batch checkpoints and blocker handling.

## Overview

This plan implements the intelligent execution model design from `docs/design/intelligent-execution-model.md`. The implementation follows a 5-phase approach that maintains backwards compatibility while progressively adding new capabilities.

**Key deliverables:**
- New `PlanStep`, `ExecutionBatch`, `ExecutionPlan` schemas
- Blocker detection with `BlockerReport` and cascade skip handling
- Batch checkpoints with human approval workflow
- Git snapshot/revert capability
- Tiered pre-validation (filesystem checks for low-risk, LLM for high-risk)
- Trust level configuration in Profile
- Dashboard batch progress visualization

---

## Phase 1: Add Core Types (No Behavior Change)

**Goal:** Add all new types to the codebase without changing existing behavior. This allows incremental testing and ensures the type system is sound before implementation.

### Task 1.1: Add DeveloperStatus and TrustLevel enums to types.py

**File:** `amelia/core/types.py`

Add new enums:
```python
class DeveloperStatus(str, Enum):
    """Developer agent execution status."""
    EXECUTING = "executing"
    BATCH_COMPLETE = "batch_complete"
    BLOCKED = "blocked"
    ALL_DONE = "all_done"

class TrustLevel(str, Enum):
    """How much autonomy the Developer gets."""
    PARANOID = "paranoid"
    STANDARD = "standard"
    AUTONOMOUS = "autonomous"
```

**Tests:**
- Unit test enum values and string representation
- Test JSON serialization/deserialization

---

### Task 1.2: Add PlanStep model to state.py

**File:** `amelia/core/state.py`

Add `PlanStep` with all fields from design:
- `id`, `description`, `action_type`
- Code action fields: `file_path`, `code_change`
- Command action fields: `command`, `cwd`, `fallback_commands`
- Validation fields: `expect_exit_code`, `expected_output_pattern`, `validation_command`, `success_criteria`
- Execution hints: `risk_level`, `estimated_minutes`, `requires_human_judgment`
- Dependencies: `depends_on`
- TDD markers: `is_test_step`, `validates_step`

**Tests:**
- Test model creation with minimal fields
- Test model creation with all fields
- Test frozen immutability
- Test JSON serialization round-trip

---

### Task 1.3: Add ExecutionBatch and ExecutionPlan models to state.py

**File:** `amelia/core/state.py`

Add models:
```python
class ExecutionBatch(BaseModel):
    batch_number: int
    steps: tuple[PlanStep, ...]
    risk_summary: Literal["low", "medium", "high"]
    description: str = ""

class ExecutionPlan(BaseModel):
    goal: str
    batches: tuple[ExecutionBatch, ...]
    total_estimated_minutes: int
    tdd_approach: bool = True
```

**Tests:**
- Test batch creation with steps
- Test plan creation with batches
- Test empty plan edge case

---

### Task 1.4: Add BlockerReport model to state.py

**File:** `amelia/core/state.py`

Add `BlockerReport` with fields:
- `step_id`, `step_description`
- `blocker_type`: Literal including `"user_cancelled"`
- `error_message`
- `attempted_actions`: tuple[str, ...]
- `suggested_resolutions`: tuple[str, ...]

**Tests:**
- Test all blocker types
- Test creation with attempted actions

---

### Task 1.5: Add StepResult and BatchResult models to state.py

**File:** `amelia/core/state.py`

Add output truncation helper:
```python
MAX_OUTPUT_LINES = 100
MAX_OUTPUT_CHARS = 4000

def truncate_output(output: str | None) -> str | None:
    """Truncate command output to prevent state bloat."""
```

Add result models:
```python
class StepResult(BaseModel):
    step_id: str
    status: Literal["completed", "skipped", "failed", "cancelled"]
    output: str | None = None  # Truncated via validator
    error: str | None = None
    executed_command: str | None = None
    duration_seconds: float = 0.0
    cancelled_by_user: bool = False

class BatchResult(BaseModel):
    batch_number: int
    status: Literal["complete", "blocked", "partial"]
    completed_steps: tuple[StepResult, ...]
    blocker: BlockerReport | None = None
```

**Tests:**
- Test output truncation with various sizes
- Test StepResult with all status values
- Test BatchResult with blocker

---

### Task 1.6: Add GitSnapshot and BatchApproval models to state.py

**File:** `amelia/core/state.py`

Add models:
```python
class GitSnapshot(BaseModel):
    head_commit: str
    dirty_files: tuple[str, ...]
    stash_ref: str | None = None

class BatchApproval(BaseModel):
    batch_number: int
    approved: bool
    feedback: str | None = None
    approved_at: datetime
```

**Tests:**
- Test GitSnapshot creation
- Test BatchApproval with and without feedback

---

### Task 1.7: Extend ExecutionState with new fields

**File:** `amelia/core/state.py`

Add new fields to `ExecutionState`:
```python
# New execution plan
execution_plan: ExecutionPlan | None = None

# Batch tracking
current_batch_index: int = 0
batch_results: Annotated[list[BatchResult], add] = Field(default_factory=list)

# Developer status (import from types)
developer_status: DeveloperStatus = DeveloperStatus.EXECUTING

# Blocker handling
current_blocker: BlockerReport | None = None
blocker_resolution: str | None = None

# Approval tracking
batch_approvals: Annotated[list[BatchApproval], add] = Field(default_factory=list)

# Skip tracking
skipped_step_ids: Annotated[set[str], set_union] = Field(default_factory=set)

# Git state
git_snapshot_before_batch: GitSnapshot | None = None
```

**Tests:**
- Test state creation with new fields
- Test reducer annotations work correctly (add, set_union)
- Test backwards compatibility with existing tests

---

### Task 1.8: Add trust_level to Profile

**File:** `amelia/core/config.py`

Add to Profile model:
```python
trust_level: TrustLevel = TrustLevel.STANDARD
batch_checkpoint_enabled: bool = True
```

**Tests:**
- Test Profile with default trust level
- Test Profile with each trust level
- Test Profile YAML serialization

---

## Phase 2: Add Git Utilities

**Goal:** Implement git snapshot and revert capabilities needed for batch-level rollback.

### Task 2.1: Create git_utils.py with snapshot functions

**File:** `amelia/tools/git_utils.py` (new file)

Implement:
```python
async def take_git_snapshot(repo_path: Path | None = None) -> GitSnapshot:
    """Capture git state before batch execution."""

async def revert_to_git_snapshot(
    snapshot: GitSnapshot,
    repo_path: Path | None = None
) -> None:
    """Revert to pre-batch state. Only reverts batch-changed files."""

async def get_batch_changed_files(
    snapshot: GitSnapshot,
    repo_path: Path | None = None
) -> set[str]:
    """Get files changed since snapshot."""
```

**Tests:**
- Test snapshot captures HEAD and dirty files
- Test revert restores batch-changed files
- Test revert preserves user's manual changes
- Integration test with actual git operations

---

### Task 2.2: Add strip_ansi utility for output validation

**File:** `amelia/tools/git_utils.py` or `amelia/core/utils.py`

Implement:
```python
def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
```

**Tests:**
- Test strips color codes
- Test strips cursor movement codes
- Test preserves plain text

---

## Phase 3: Update Architect

**Goal:** Update Architect to produce `ExecutionPlan` with semantic batching.

### Task 3.1: Add validate_and_split_batches helper

**File:** `amelia/agents/architect.py`

Implement batch validation:
```python
def validate_and_split_batches(plan: ExecutionPlan) -> tuple[ExecutionPlan, list[str]]:
    """Validate Architect batches and split if needed.

    Returns (validated_plan, warnings).
    Enforces: low=5, medium=3, high=1 max batch sizes.
    """
```

**Tests:**
- Test batch within limits passes through
- Test oversized low-risk batch splits correctly
- Test high-risk steps always isolated
- Test warnings generated for splits

---

### Task 3.2: Create ExecutionPlan output schema

**File:** `amelia/agents/architect.py`

Add new response model:
```python
class ExecutionPlanOutput(BaseModel):
    """Structured output for execution plan generation."""
    plan: ExecutionPlan
    reasoning: str
```

**Tests:**
- Test schema validation
- Test plan output parsing

---

### Task 3.3: Update ArchitectContextStrategy with new prompts

**File:** `amelia/agents/architect.py`

Update `get_task_generation_system_prompt` and `get_task_generation_user_prompt` with:
- Step granularity guidance (2-5 min)
- Risk assessment criteria
- Batching rules
- TDD approach instructions
- Fallback command guidance

**Tests:**
- Test prompt generation includes new guidance
- Test prompts include risk level definitions

---

### Task 3.4: Add plan generation method to Architect

**File:** `amelia/agents/architect.py`

Add method:
```python
async def generate_execution_plan(
    self,
    issue: Issue,
    state: ExecutionState,
) -> ExecutionPlan:
    """Generate batched execution plan for an issue."""
```

This coexists with existing `_generate_task_dag` for backwards compatibility.

**Tests:**
- Test generates valid ExecutionPlan
- Test batches respect risk limits
- Test TDD steps ordered correctly
- Integration test with mock LLM

---

## Phase 4: Refactor Developer

**Goal:** Transform Developer into intelligent plan follower with tiered pre-validation and blocker handling.

### Task 4.1: Add ValidationResult model

**File:** `amelia/agents/developer.py`

Add internal model:
```python
class ValidationResult(BaseModel):
    """Result of pre-validating a step."""
    ok: bool
    issue: str | None = None
    attempted: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
```

**Tests:**
- Test ValidationResult creation

---

### Task 4.2: Implement filesystem checks

**File:** `amelia/agents/developer.py`

Add method:
```python
async def _filesystem_checks(self, step: PlanStep) -> ValidationResult:
    """Fast filesystem checks without LLM."""
```

Checks:
- File exists for code actions
- Command available for command actions
- Working directory exists

**Tests:**
- Test file existence check
- Test command availability check (which)
- Test returns ok=True when all pass

---

### Task 4.3: Implement tiered pre-validation

**File:** `amelia/agents/developer.py`

Add method:
```python
async def _pre_validate_step(
    self,
    step: PlanStep,
    state: ExecutionState
) -> ValidationResult:
    """Tiered pre-validation based on step risk."""
```

Logic:
- Always run filesystem checks
- Low-risk: filesystem only
- High-risk: filesystem + LLM semantic validation
- Medium-risk: filesystem (LLM at batch level)

**Tests:**
- Test low-risk skips LLM
- Test high-risk calls LLM
- Test returns early on filesystem failure

---

### Task 4.4: Implement command result validation

**File:** `amelia/agents/developer.py`

Add function:
```python
def validate_command_result(
    exit_code: int,
    stdout: str,
    step: PlanStep
) -> bool:
    """Validate command result. Exit code is always checked first."""
```

**Tests:**
- Test exit code validation
- Test regex pattern matching on stripped output
- Test passes when pattern is None

---

### Task 4.5: Implement execute_step_with_fallbacks

**File:** `amelia/agents/developer.py`

Add method:
```python
async def _execute_step_with_fallbacks(
    self,
    step: PlanStep,
    state: ExecutionState
) -> StepResult:
    """Execute step, trying fallbacks if primary fails."""
```

**Tests:**
- Test primary command succeeds
- Test fallback used when primary fails
- Test all fallbacks fail returns failed result
- Test code action with validation command

---

### Task 4.6: Implement cascade skip detection

**File:** `amelia/agents/developer.py`

Add function:
```python
def get_cascade_skips(
    step_id: str,
    plan: ExecutionPlan,
    skip_reasons: dict[str, str]
) -> dict[str, str]:
    """Find all steps that depend on a skipped/failed step."""
```

**Tests:**
- Test simple dependency skip
- Test transitive dependency skip
- Test no cascade when no dependencies

---

### Task 4.7: Implement _execute_batch method

**File:** `amelia/agents/developer.py`

Add method:
```python
async def _execute_batch(
    self,
    batch: ExecutionBatch,
    state: ExecutionState
) -> BatchResult:
    """Execute a batch with LLM judgment."""
```

Flow:
1. Take git snapshot
2. Review batch (medium/high risk only)
3. For each step: check cascade skips, pre-validate, execute with fallbacks
4. Return BatchResult

**Tests:**
- Test successful batch execution
- Test blocked on pre-validation failure
- Test blocked on command failure
- Test cascade skips handled

---

### Task 4.8: Implement blocker recovery

**File:** `amelia/agents/developer.py`

Add method:
```python
async def _recover_from_blocker(
    self,
    state: ExecutionState
) -> BatchResult:
    """Continue execution after human resolves blocker."""
```

**Tests:**
- Test recovery with fix instruction
- Test recovery continues from blocked step

---

### Task 4.9: Update Developer.run for intelligent execution

**File:** `amelia/agents/developer.py`

Refactor `execute_current_task` (or add new `run` method):
```python
async def run(self, state: ExecutionState) -> dict:
    """Main execution - follows plan with judgment."""
```

This replaces `_execute_structured` vs `_execute_agentic` split.

**Tests:**
- Test all batches complete returns ALL_DONE
- Test batch complete returns BATCH_COMPLETE
- Test blocked returns BLOCKED with blocker
- Test blocker resolution path

---

## Phase 5: Update Orchestrator

**Goal:** Add batch checkpoint and blocker resolution nodes to the graph.

### Task 5.1: Implement batch_approval_node

**File:** `amelia/core/orchestrator.py`

Add node function:
```python
async def batch_approval_node(state: ExecutionState) -> dict:
    """Human reviews completed batch. Graph interrupts before this node."""
```

**Tests:**
- Test approved path
- Test feedback path
- Test resets human_approved

---

### Task 5.2: Implement blocker_resolution_node

**File:** `amelia/core/orchestrator.py`

Add node function:
```python
async def blocker_resolution_node(state: ExecutionState) -> dict:
    """Human resolves blocker. Graph interrupts before this node."""
```

Handle:
- "skip" → mark step skipped, cascade
- "abort" → keep changes, end workflow
- "abort_revert" → revert batch, end workflow
- fix instruction → pass to Developer

**Tests:**
- Test skip path
- Test abort path
- Test abort_revert path
- Test fix instruction path

---

### Task 5.3: Implement route_after_developer

**File:** `amelia/core/orchestrator.py`

Add routing function:
```python
def route_after_developer(state: ExecutionState) -> str:
    """Route based on Developer status."""
```

Returns: "reviewer", "batch_approval", or "blocker_resolution"

**Tests:**
- Test ALL_DONE routes to reviewer
- Test BATCH_COMPLETE routes to batch_approval
- Test BLOCKED routes to blocker_resolution

---

### Task 5.4: Implement should_checkpoint helper

**File:** `amelia/core/orchestrator.py`

Add function:
```python
def should_checkpoint(batch: ExecutionBatch, profile: Profile) -> bool:
    """Determine if we should pause for human approval."""
```

Logic based on trust_level.

**Tests:**
- Test PARANOID always checkpoints
- Test STANDARD always checkpoints
- Test AUTONOMOUS only checkpoints high-risk

---

### Task 5.5: Update create_orchestrator_graph

**File:** `amelia/core/orchestrator.py`

Add new nodes and edges:
- Add `batch_approval_node`
- Add `blocker_resolution_node`
- Update routing from developer node
- Add `interrupt_before` for approval nodes

Ensure backwards compatibility with existing fixed orchestration mode.

**Tests:**
- Test graph creation includes new nodes
- Test interrupts configured correctly
- Test existing workflow still works

---

## Phase 6: Dashboard Integration (Optional - Can Be Separate PR)

**Goal:** Visualize batch progress and provide blocker resolution UI.

### Task 6.1: Create AgentProgressBar component

**File:** `dashboard/src/components/AgentProgressBar.tsx`

Compact horizontal stepper showing: PM → Architect → Developer → Reviewer

**Tests:**
- Test renders all agent stages
- Test highlights current stage
- Test completed stages show checkmark

---

### Task 6.2: Create BatchNode component

**File:** `dashboard/src/components/flow/BatchNode.tsx`

Container node for batch visualization showing:
- Batch number
- Risk level badge
- Description
- Contains StepNodes

**Tests:**
- Test renders batch info
- Test risk level styling

---

### Task 6.3: Create StepNode component

**File:** `dashboard/src/components/flow/StepNode.tsx`

Individual step node showing:
- Step description
- Status icon
- Elapsed time (when running)
- Cancel button (when running)

**Tests:**
- Test renders step info
- Test status icons
- Test cancel button visibility

---

### Task 6.4: Create CheckpointMarker component

**File:** `dashboard/src/components/flow/CheckpointMarker.tsx`

Visual separator between batches showing approval status.

**Tests:**
- Test shows pending state
- Test shows approved state
- Test shows rejected state with feedback

---

### Task 6.5: Create BatchStepCanvas component

**File:** `dashboard/src/components/BatchStepCanvas.tsx`

React Flow canvas with horizontal swimlane layout for batches.

**Tests:**
- Test renders batches as swimlanes
- Test step nodes connected within batch
- Test checkpoint markers between batches

---

### Task 6.6: Create BlockerResolutionDialog component

**File:** `dashboard/src/components/BlockerResolutionDialog.tsx`

Modal for blocker resolution with options:
- Retry step
- Skip step (shows cascade warning)
- Provide fix instruction
- Abort (keep changes)
- Abort (revert batch)

**Tests:**
- Test renders blocker details
- Test all resolution options
- Test cascade skip preview

---

### Task 6.7: Create CancelStepDialog component

**File:** `dashboard/src/components/CancelStepDialog.tsx`

Confirmation dialog for cancelling a running step.

**Tests:**
- Test shows warning message
- Test confirm triggers cancel
- Test dismiss keeps running

---

### Task 6.8: Integrate components into main layout

**File:** `dashboard/src/pages/ExecutionPage.tsx` (or equivalent)

Wire up:
- AgentProgressBar at top
- BatchStepCanvas as main content
- BlockerResolutionDialog when blocked
- CancelStepDialog on cancel click

**Tests:**
- Integration test with mock state
- Test state transitions update UI

---

## Integration Tests

### Task I.1: Test full execution flow with checkpoints

**File:** `tests/integration/test_batch_execution.py`

Test scenarios:
- Happy path: all batches complete
- Batch rejected with feedback
- Blocker with skip resolution
- Blocker with abort resolution
- Blocker with fix resolution

---

### Task I.2: Test blocker recovery flow

**File:** `tests/integration/test_blocker_recovery.py`

Test:
- Command failure → human fix → continue
- Validation failure → skip → cascade
- Abort with revert restores files

---

### Task I.3: Test trust level variations

**File:** `tests/integration/test_trust_levels.py`

Test:
- PARANOID mode checkpoints every step
- STANDARD mode checkpoints every batch
- AUTONOMOUS mode auto-approves low/medium risk

---

## Success Criteria Checklist

- [ ] Developer validates steps before execution (doesn't blindly crash)
- [ ] Developer tries fallback commands before blocking
- [ ] Exit codes are primary validation; regex only when specified
- [x] Batch checkpoints pause for human review (respects trust_level)
- [ ] Blockers report what was tried and suggest resolutions
- [ ] Cascade skips handled correctly (dependent steps auto-skipped)
- [ ] High-risk steps isolated in their own batches
- [ ] Git revert works for batch-level changes
- [ ] State tracks batch progress, blockers, approvals, skipped steps
- [ ] Output truncation prevents state bloat
- [ ] Existing fixed orchestration mode still works
- [ ] All existing tests pass

---

## Notes

- Phase 6 (Dashboard) can be implemented as a separate PR after backend is stable
- Each task should have tests written first (TDD approach per CLAUDE.md)
- Maintain backwards compatibility throughout - existing `TaskDAG` workflow must continue to work
- The `execution_plan` field coexists with `task_dag` during migration

