---
title: "Design Example: Intelligent Execution Model"
description: Example design document showing how Amelia's Architect agent structures technical specifications
---

# Design Example: Intelligent Execution Model

::: info Artifact Type
This is an example **design document** produced by the Architect agent. Design documents define the technical approach for implementing a feature, including data models, state management, and integration points.

**Source:** [GitHub Issue #100](https://github.com/existential-birds/amelia/issues/100)
:::

---

> Transforming Developer from blind executor to intelligent plan follower with batch checkpoints and blocker handling.

## Problem Statement

Amelia's Developer agent currently has two execution modes, neither of which is ideal:

| Mode | Behavior | Problem |
|------|----------|---------|
| **Structured** | Blindly executes TaskStep commands | Crashes when `npm test` doesn't exist; no judgment |
| **Agentic** | Full LLM autonomy | No plan structure; unpredictable; hard to checkpoint |

The target behavior mirrors the `superpowers:writing-plans` + `superpowers:executing-plans` workflow:

1. **Detailed plans** with bite-sized tasks (2-5 min each), exact code, exact commands, expected output
2. **Intelligent execution** where an LLM follows the plan WITH judgment:
   - Reviews plan critically before starting
   - Validates steps before execution (e.g., checks if npm test exists)
   - Executes in batches with checkpoints for human review
   - Stops and asks when blocked (doesn't crash)

## Design Goals

1. **Intelligent Following**: LLM executes plan steps but validates and adapts
2. **Batch Checkpoints**: Pause every N tasks for human approval
3. **Blocker Handling**: Detect, report, and recover from blockers gracefully
4. **Adaptive Batching**: High-risk steps get isolated; low-risk can batch together
5. **Observable State**: Batch progress, blockers, approvals all visible in state

## Key Insight

The execution model is NOT a dumb script executor. It's an LLM that:

1. Reads detailed plan steps as guidance
2. Validates before executing (e.g., checks if npm test exists)
3. Tries fallback actions before declaring blockers
4. Stops and reports blockers instead of crashing
5. Pauses for review checkpoints between batches

**Blocker trigger**: Any situation where the agent would ask for human input to proceed.

## Plan Schema

The current `TaskStep`/`FileOperation` structure is too rigid. The new schema supports:

- Fallback commands when primary fails
- Exit code validation (primary) with optional output pattern (secondary)
- Risk levels for adaptive batching
- Explicit dependency graph
- Working directory per step
- TDD markers

```python
# amelia/core/state.py (additions)

class PlanStep(BaseModel):
    """A single step in an execution plan."""
    model_config = ConfigDict(frozen=True)

    id: str                           # Unique identifier for tracking
    description: str                  # Human-readable description
    action_type: Literal["code", "command", "validation", "manual"]

    # For code actions
    file_path: str | None = None
    code_change: str | None = None    # Exact code or diff

    # For command actions
    command: str | None = None
    cwd: str | None = None            # Working directory (relative to repo root)
    fallback_commands: tuple[str, ...] = ()     # Try these if primary fails

    # Validation (exit code is ALWAYS checked; these are additional)
    expect_exit_code: int = 0                   # Expected exit code (primary validation)
    expected_output_pattern: str | None = None  # Regex for stdout (secondary, stripped of ANSI)

    # For validation actions
    validation_command: str | None = None
    success_criteria: str | None = None

    # Execution hints
    risk_level: Literal["low", "medium", "high"] = "medium"
    estimated_minutes: int = 2
    requires_human_judgment: bool = False

    # Dependencies
    depends_on: tuple[str, ...] = ()  # Step IDs this depends on

    # TDD markers
    is_test_step: bool = False
    validates_step: str | None = None  # Step ID this validates


class ExecutionBatch(BaseModel):
    """A batch of steps to execute before checkpoint.

    Architect defines batches based on semantic grouping.
    System enforces size limits (max 5 low-risk, max 3 medium-risk).
    """
    model_config = ConfigDict(frozen=True)

    batch_number: int
    steps: tuple[PlanStep, ...]
    risk_summary: Literal["low", "medium", "high"]
    description: str = ""  # Optional: why these steps are grouped


class ExecutionPlan(BaseModel):
    """Complete plan with batched execution.

    Created by Architect, consumed by Developer.
    Batches are defined upfront for predictable checkpoints.
    """
    model_config = ConfigDict(frozen=True)

    goal: str
    batches: tuple[ExecutionBatch, ...]
    total_estimated_minutes: int
    tdd_approach: bool = True
```

### Validation Strategy

**Exit codes are primary.** The `expected_output_pattern` is optional and only used when:
- Exit code alone is insufficient (e.g., command exits 0 but output indicates failure)
- Pattern is applied to **stripped plain text** (ANSI codes removed)

```python
def validate_command_result(exit_code: int, stdout: str, step: PlanStep) -> bool:
    """Validate command result. Exit code is always checked first."""
    if exit_code != step.expect_exit_code:
        return False

    if step.expected_output_pattern:
        # Strip ANSI codes before matching
        clean_output = strip_ansi(stdout)
        if not re.search(step.expected_output_pattern, clean_output):
            return False

    return True
```

### Key Differences from Current TaskStep

| Current | New | Why |
|---------|-----|-----|
| No fallbacks | `fallback_commands` | Agent can try alternatives before blocking |
| No validation | `expect_exit_code` + optional `expected_output_pattern` | Exit codes primary; regex only when needed |
| No risk info | `risk_level` | Drives batch sizing and pre-validation depth |
| No working dir | `cwd` | Commands often need specific subdirectories |
| Implicit judgment | `requires_human_judgment` | Explicit blocker markers |
| Implicit deps | `depends_on` | Explicit dependency graph (enables cascade handling) |
| Flat list | Pre-batched | Architect creates semantic batches; system enforces limits |

## Batch Ownership (Hybrid Approach)

**Architect defines batches semantically.** The LLM groups steps that logically belong together (e.g., "setup db" + "run migration"). This preserves context for human reviewers.

**System enforces size limits.** To ensure predictable checkpoint frequency:

| Risk Level | Max Batch Size |
|------------|----------------|
| Low | 5 steps |
| Medium | 3 steps |
| High | 1 step (always isolated) |

If an Architect-defined batch exceeds limits, the system splits it with a warning:

```python
def validate_and_split_batches(plan: ExecutionPlan) -> ExecutionPlan:
    """Validate Architect batches and split if needed.

    Architect defines semantic groupings. System enforces size limits.
    """
    validated_batches = []
    warnings = []

    for batch in plan.batches:
        max_size = {"low": 5, "medium": 3, "high": 1}[batch.risk_summary]

        if len(batch.steps) <= max_size:
            validated_batches.append(batch)
        else:
            # Split oversized batch, preserving order
            warnings.append(f"Batch {batch.batch_number} exceeded {max_size} steps, splitting")
            for i in range(0, len(batch.steps), max_size):
                chunk = batch.steps[i:i + max_size]
                validated_batches.append(ExecutionBatch(
                    batch_number=len(validated_batches) + 1,
                    steps=chunk,
                    risk_summary=batch.risk_summary,
                    description=f"{batch.description} (part {i // max_size + 1})",
                ))

    return plan.model_copy(update={"batches": tuple(validated_batches)})
```

**Why hybrid?**
- Pure algorithm might split logical units (bad for human review)
- Pure LLM might create inconsistent batch sizes (bad for predictability)
- Hybrid gives semantic grouping with predictable checkpoints

## Blocker Detection & Handling

A blocker is triggered when the agent would need human input to proceed:

| Blocker Type | Trigger | Example |
|--------------|---------|---------|
| `command_failed` | Command fails and no fallback succeeds | `npm test` not found, tried `yarn test`, `pnpm test` |
| `validation_failed` | Code change doesn't pass validation | Tests fail after implementation |
| `needs_judgment` | Step marked `requires_human_judgment` | Security-sensitive change |
| `unexpected_state` | Pre-validation fails | File doesn't exist, dependency missing |
| `dependency_skipped` | A dependency was skipped/failed | Step B depends on Step A which was skipped |

```python
class BlockerReport(BaseModel):
    """Report when execution is blocked."""
    model_config = ConfigDict(frozen=True)

    step_id: str
    step_description: str
    blocker_type: Literal["command_failed", "validation_failed", "needs_judgment", "unexpected_state", "dependency_skipped"]
    error_message: str
    attempted_actions: tuple[str, ...]  # What the agent already tried
    suggested_resolutions: tuple[str, ...]  # Agent's suggestions for human (labeled as AI suggestions in UI)
```

### Cascading Skip Handling

When a step is skipped or fails, all dependent steps are automatically marked for skip:

```python
def get_cascade_skips(step_id: str, plan: ExecutionPlan) -> dict[str, str]:
    """Find all steps that depend on a skipped/failed step.

    Returns dict of step_id -> skip reason.
    """
    skips = {step_id: "skipped by user"}
    all_steps = [step for batch in plan.batches for step in batch.steps]

    # Iterate until no new skips found (handles transitive dependencies)
    changed = True
    while changed:
        changed = False
        for step in all_steps:
            if step.id not in skips and any(dep in skips for dep in step.depends_on):
                skips[step.id] = f"dependency {step.depends_on[0]} was skipped"
                changed = True

    return skips
```

### Blocker Resolution Flow

```
Developer executes batch
    │
    ├─[success]──► Batch Checkpoint (human reviews)
    │                   │
    │                   ├─[approved]──► Next Batch
    │                   └─[feedback]──► Developer adjusts, re-executes
    │
    └─[blocked]──► Blocker Report
                        │
                        ▼
                  Human Resolution
                        │
                        ├─[provides fix]──► Developer continues
                        ├─[skip step]──► Developer marks skipped + cascade skips
                        ├─[abort + keep changes]──► Workflow ends (default)
                        └─[abort + revert]──► Revert batch changes, workflow ends
```

## State Management

### New State Fields

```python
class DeveloperStatus(str, Enum):
    """Developer agent execution status."""
    EXECUTING = "executing"
    BATCH_COMPLETE = "batch_complete"    # Ready for checkpoint
    BLOCKED = "blocked"                  # Needs human help
    ALL_DONE = "all_done"                # All batches complete


class BatchApproval(BaseModel):
    """Record of human approval for a batch."""
    model_config = ConfigDict(frozen=True)

    batch_number: int
    approved: bool
    feedback: str | None = None
    approved_at: datetime


# Constants for output truncation
MAX_OUTPUT_LINES = 100
MAX_OUTPUT_CHARS = 4000


def truncate_output(output: str | None) -> str | None:
    """Truncate command output to prevent state bloat.

    Keeps first 50 lines + last 50 lines if output exceeds limit.
    """
    if not output:
        return output

    lines = output.split("\n")
    if len(lines) <= MAX_OUTPUT_LINES:
        truncated = output
    else:
        # Keep first 50 + last 50 lines
        first = lines[:50]
        last = lines[-50:]
        truncated = "\n".join(first + [f"\n... ({len(lines) - 100} lines truncated) ...\n"] + last)

    if len(truncated) > MAX_OUTPUT_CHARS:
        truncated = truncated[:MAX_OUTPUT_CHARS] + f"\n... (truncated at {MAX_OUTPUT_CHARS} chars)"

    return truncated


class StepResult(BaseModel):
    """Result of executing a single step."""
    model_config = ConfigDict(frozen=True)

    step_id: str
    status: Literal["completed", "skipped", "failed"]
    output: str | None = None           # Truncated to prevent state bloat
    error: str | None = None
    executed_command: str | None = None  # Actual command run (may differ from plan if fallback)
    duration_seconds: float = 0.0

    @field_validator("output", mode="before")
    @classmethod
    def truncate(cls, v: str | None) -> str | None:
        return truncate_output(v)


class BatchResult(BaseModel):
    """Result of executing a batch."""
    model_config = ConfigDict(frozen=True)

    batch_number: int
    status: Literal["complete", "blocked", "partial"]
    completed_steps: tuple[StepResult, ...]
    blocker: BlockerReport | None = None


class GitSnapshot(BaseModel):
    """Git state snapshot for potential revert."""
    model_config = ConfigDict(frozen=True)

    head_commit: str              # git rev-parse HEAD before batch
    dirty_files: tuple[str, ...]  # Files modified before batch started
    stash_ref: str | None = None  # If we stashed changes
```

## Orchestrator Integration

### Updated Graph (Hybrid Approval Flow)

Developer yields to orchestrator for batch checkpoints and blocker resolution:

```
                                    ┌─────────────────┐
                                    │                 │
                                    ▼                 │
Issue → PM → Architect → Plan Approval → Developer ───┼──→ Reviewer → Done
                              ▲            │          │
                              │            │          │
                              │            ▼          │
                              │    Batch Checkpoint ──┘
                              │            │
                              │            ▼
                              └─── Blocker Resolution
```

### Routing Logic

```python
def route_after_developer(state: ExecutionState) -> str:
    """Route based on Developer status."""
    if state.developer_status == DeveloperStatus.ALL_DONE:
        return "reviewer"
    elif state.developer_status == DeveloperStatus.BATCH_COMPLETE:
        return "batch_approval"
    elif state.developer_status == DeveloperStatus.BLOCKED:
        return "blocker_resolution"
    else:
        raise ValueError(f"Unexpected status: {state.developer_status}")
```

## Trust Level Configuration

Profile includes `trust_level` to control checkpoint frequency:

```python
class TrustLevel(str, Enum):
    """How much autonomy the Developer gets."""
    PARANOID = "paranoid"      # Approve every step
    STANDARD = "standard"      # Approve batches (default)
    AUTONOMOUS = "autonomous"  # Auto-approve low/medium, stop only for high-risk or blockers
```

### Trust Level Behavior

| Level | Low-Risk Batch | Medium-Risk Batch | High-Risk Batch | Blocker |
|-------|----------------|-------------------|-----------------|---------|
| Paranoid | Checkpoint each step | Checkpoint each step | Checkpoint each step | Always stop |
| Standard | Checkpoint after batch | Checkpoint after batch | Checkpoint after batch | Always stop |
| Autonomous | Auto-approve | Auto-approve | Checkpoint | Always stop |

## Migration Path

### Phase 1: Add Types (No Behavior Change)

1. Add new types to `amelia/core/state.py`:
   - `PlanStep`, `ExecutionBatch`, `ExecutionPlan`
   - `BlockerReport`, `StepResult`, `BatchResult`, `BatchApproval`
   - `DeveloperStatus` enum, `TrustLevel` enum
   - `GitSnapshot` for revert capability

2. Add execution config to `Profile`:
   - `trust_level: TrustLevel = TrustLevel.STANDARD`
   - `batch_checkpoint_enabled: bool = True`

### Phase 2: Update Architect

1. Update `ArchitectContextStrategy` with new prompts
2. Update output schema to `ExecutionPlan`
3. Add `validate_and_split_batches()` helper

### Phase 3: Refactor Developer

1. Remove `_execute_structured` vs `_execute_agentic` split
2. Implement single `_execute_batch` method with tiered pre-validation
3. Add fallback handling with exit code validation
4. Add blocker detection, cascade skip handling
5. Add git snapshot/revert capability

### Phase 4: Update Orchestrator

1. Add `batch_approval_node` and `blocker_resolution_node`
2. Update routing with `route_after_developer`
3. Add `interrupt_before` for new approval nodes

### Phase 5: Dashboard Integration

1. Batch progress visualization
2. Blocker UI with resolution options
3. Step-level execution timeline
4. Trust level selector in settings

## Success Criteria

- [ ] Developer validates steps before execution (doesn't blindly crash)
- [ ] Developer tries fallback commands before blocking
- [ ] Exit codes are primary validation; regex only when specified
- [ ] Batch checkpoints pause for human review (respects trust_level)
- [ ] Blockers report what was tried and suggest resolutions
- [ ] Cascade skips handled correctly (dependent steps auto-skipped)
- [ ] High-risk steps isolated in their own batches
- [ ] Git revert works for batch-level changes
- [ ] State tracks batch progress, blockers, approvals, skipped steps
- [ ] Output truncation prevents state bloat
- [ ] Existing fixed orchestration mode still works
- [ ] All existing tests pass

## Example Workflow

### Issue: "Add user logout endpoint"

**Architect produces:**

```yaml
goal: "Add user logout endpoint with session invalidation"
tdd_approach: true
total_estimated_minutes: 25
batches:
  - batch_number: 1
    risk_summary: low
    steps:
      - id: "1.1"
        description: "Write logout endpoint test"
        action_type: code
        file_path: tests/test_auth.py
        code_change: |
          def test_logout_invalidates_session():
              ...
        is_test_step: true
        risk_level: low

  - batch_number: 2
    risk_summary: medium
    steps:
      - id: "2.1"
        description: "Implement logout endpoint"
        action_type: code
        file_path: src/auth/routes.py
        code_change: |
          @router.post("/logout")
          async def logout(session: Session = Depends(get_session)):
              ...
        validates_step: null
        risk_level: medium
        depends_on: ["1.1"]

      - id: "2.2"
        description: "Run tests"
        action_type: command
        command: "pytest tests/test_auth.py -v"
        fallback_commands: ["python -m pytest tests/test_auth.py -v"]
        expected_output_pattern: "passed"
        risk_level: low
        depends_on: ["2.1"]
```

**Execution flow:**

1. Developer executes Batch 1 (test step)
2. &rarr; Batch Checkpoint: Human reviews test looks correct
3. Developer executes Batch 2 (implementation + validation)
4. &rarr; Batch Checkpoint: Human reviews implementation
5. &rarr; Reviewer: Full code review
6. &rarr; Done

**If `pytest` not found:**

1. Developer tries `pytest tests/test_auth.py -v` &rarr; fails
2. Developer tries `python -m pytest tests/test_auth.py -v` &rarr; success
3. Continues without blocking

**If tests fail:**

1. Developer detects validation failure
2. Reports blocker with:
   - What failed: "pytest returned non-zero"
   - What was tried: `["pytest tests/test_auth.py -v"]`
   - Suggestions: `["Check test assertions", "Review implementation logic"]`
3. Human provides fix or skips
4. Developer continues

## Resolved Design Questions

1. **Should Architect or Developer calculate batches?** &rarr; Hybrid: Architect defines semantic groups, system enforces size limits
2. **How to handle partial batch completion on resume?** &rarr; Track `skipped_step_ids` in state, skip on resume
3. **Should auto-approve be configurable per batch risk level?** &rarr; Yes, via `trust_level` in Profile
4. **Regex validation brittleness?** &rarr; Exit codes are primary; regex optional and applied to stripped text
5. **Pre-validation latency?** &rarr; Tiered: filesystem checks for low-risk, LLM only for high-risk
6. **Git dirty state on abort?** &rarr; Snapshot before batch; offer "Keep changes" (default) or "Revert batch"
7. **Cascading failures?** &rarr; Auto-skip steps whose dependencies were skipped/failed
