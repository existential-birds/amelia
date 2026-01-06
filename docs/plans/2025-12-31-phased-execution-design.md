# Phased Execution for Developer Agent

**Status**: Ready for Implementation

## Problem

Large tasks cause context degradation. As the Developer session accumulates tool calls, file reads, and corrections, LLM quality drops - forcing human intervention.

The root cause is **context bloat**: each tool call adds tokens, file contents pile up, and correction cycles compound the problem. Even with fresh sessions per subtask, naive handoff strategies can reintroduce bloat by passing full plans and accumulated history to each subagent.

## Solution

Phased execution with **Python orchestration**. The Architect decomposes work into subtasks with explicit dependencies. A **Python orchestration loop** iterates through phases, spawning **fresh phase agent sessions** that each run with scoped context. Git serves as the handoff mechanism between phases.

## Goals

- **Hands-off**: System runs autonomously until completion or unrecoverable failure
- **Context-fresh**: Each subtask starts with clean context (plan + current repo state)
- **Self-correcting**: Reviewer feedback triggers phase retry with fresh context
- **Fail-safe**: Halt on failure or 2 failed review attempts - never leave a mess

## Non-Goals

- Maximum parallelism (correctness over speed)
- Complex merge resolution (Architect ensures disjoint work)

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Task decomposition | Architect-driven | Architect already analyzes codebase; natural place for planning |
| Context handoff | Git + plan | Code is source of truth; plan provides strategic context |
| Subtask execution | Sequential within phase | Subtasks in a phase run one after another; simpler, avoids file conflicts |
| Phase execution | Parallel where independent | Phases with no dependencies can run concurrently; phases with dependencies run sequentially |
| Failure handling | Halt everything | Stop clean rather than build on broken foundations |
| Review timing | After each phase | Catches issues at natural sync points |
| Review rejection | Retry phase once | Fresh context + feedback; halt after 2 failures |
| Orchestration | Python loop | Deterministic, testable, cheaper than LLM orchestration; most failures are predictable |
| Commit strategy | One commit per phase | Enables clean retry; subtasks work on uncommitted changes |
| TDD enforcement | Test-first subtasks | Tests written before implementation; Architect structures dependencies accordingly |
| Context strategy | Signposting | Simple prompts tell agents where to look; agents pull context with tools |

## Architecture

### Orchestration Architecture

The phased execution model uses **Python orchestration** with **fresh LLM sessions per phase**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Python Orchestration + Phase Agents                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                      PYTHON ORCHESTRATOR                              │  │
│  │                      (Deterministic loop)                             │  │
│  │                                                                       │  │
│  │  • Reads approved plan, computes phase execution order                │  │
│  │  • Iterates through phases (parallel where independent)               │  │
│  │  • Spawns fresh phase agent sessions with scoped context              │  │
│  │  • Handles failures: retry once with error context, then halt         │  │
│  │  • Commits after each successful phase                                │  │
│  │  • Updates ExecutionState for dashboard/recovery                      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                          │                                                  │
│                          │ spawns (fresh session each time)                 │
│                          ▼                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Phase 1    │  │  Phase 2    │  │  Phase 3    │  │  Phase N    │        │
│  │   Agent     │  │   Agent     │  │   Agent     │  │   Agent     │        │
│  │  Session    │  │  Session    │  │  Session    │  │  Session    │        │
│  │             │  │             │  │             │  │             │        │
│  │ • Fresh     │  │ • Fresh     │  │ • Fresh     │  │ • Fresh     │        │
│  │   context   │  │   context   │  │   context   │  │   context   │        │
│  │ • Subtasks  │  │ • Subtasks  │  │ • Subtasks  │  │ • Subtasks  │        │
│  │   run seq.  │  │   run seq.  │  │   run seq.  │  │   run seq.  │        │
│  │ • Returns   │  │ • Returns   │  │ • Returns   │  │ • Returns   │        │
│  │   report    │  │   report    │  │   report    │  │   report    │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Python Orchestrator Implementation

```python
async def execute_phased_plan(
    plan: PhasedPlanOutput,
    profile: Profile,
    cwd: Path,
) -> ExecutionResult:
    """Execute a phased plan with fresh agent sessions per phase.

    Handles retry logic, commits, and state updates.
    """
    initialize_execution_dir(cwd, plan)
    completed_phases: list[PhaseReport] = []

    for phase_index, phase_subtasks in enumerate(plan.phases):
        pre_commit = git_rev_parse("HEAD")

        # Build scoped context for this phase
        context = build_phase_context(
            phase_index=phase_index,
            subtasks=phase_subtasks,
            prior_summaries=[p.summary for p in completed_phases],
        )

        # Spawn fresh agent session
        report = await spawn_phase_agent(phase_subtasks, context, profile, cwd)

        if report.status == "failed":
            # Retry once with error context
            retry_context = prepare_retry_context(report.error_context, phase_index, attempt=2)
            reset_to_commit(pre_commit)
            report = await spawn_phase_agent(phase_subtasks, context + retry_context, profile, cwd)

            if report.status == "failed":
                raise PhaseFailure(f"Phase {phase_index} failed after retry: {report.error_context}")

        # Commit phase changes
        commit_phase(phase_index, report)
        await generate_phase_summary(phase_index, report, pre_commit)
        completed_phases.append(report)

    return ExecutionResult(phases=completed_phases, status="completed")
```

#### Phase Agent Sessions

Each phase runs in a **fresh agent session** with a simple "signposting" prompt that tells the agent what to do and where to find context:

```python
def build_phase_agent_prompt(
    execution_dir: str,
    phase_index: int,
    subtasks: list[Subtask],
    retry_context: str | None = None,
) -> str:
    """Build a simple signposting prompt for a phase agent.

    Args:
        execution_dir: The execution directory name (e.g., "2026-01-05-ISSUE-123-add-user-auth")

    Agents have tool access—they can Read files, Grep for patterns,
    and run git commands. The prompt just tells them where to look.
    """
    prompt = f"""You are executing Phase {phase_index} of a phased development plan.

## Your Assignment
Execute the following subtasks IN ORDER:

{format_subtasks(subtasks)}

## Where to Find Context
- Full plan: `docs/amelia/{execution_dir}/plan.md`
- Prior phase summaries: `docs/amelia/{execution_dir}/phase-{{N}}/summary.md`
- Use `git log --oneline -10` to see prior work
- Use `git diff HEAD~1` to see the last phase's changes

## Instructions
1. Execute each subtask sequentially
2. If a subtask fails, report the failure and stop
3. After all subtasks complete, provide a summary of what was accomplished
4. Do NOT commit - the orchestrator handles commits
"""
    if retry_context:
        prompt += f"""
{retry_context}
"""
    return prompt
```

The prompt is intentionally minimal—agents pull what they need using their tools.

#### Phase Agent Reports

Phase agents return structured reports that the Python orchestrator uses for state management:

```python
class PhaseReport(BaseModel):
    """Report from a phase agent session."""
    phase_index: int
    status: Literal["completed", "failed", "partial"]
    subtasks_completed: list[str]
    subtasks_failed: list[str]
    summary: str
    error_context: str | None = None
    files_changed: list[str]
```

The Python orchestrator uses these reports to:
- Update `ExecutionState` for dashboard display
- Decide whether to retry (simple rule: retry once on failure)
- Generate phase summaries for downstream context
- Commit changes after successful phases

### Architect Plan Format

```python
class SubtaskType(str, Enum):
    TEST = "test"                # Write tests (red phase)
    IMPL = "impl"                # Write implementation (green phase)
    REFACTOR = "refactor"        # Refactor (optional cleanup)

@dataclass
class Subtask:
    id: str                      # e.g., "1a", "1b", "2a"
    title: str                   # Human-readable name
    description: str             # What this subtask accomplishes
    type: SubtaskType            # test, impl, or refactor
    depends_on: list[str]        # Subtask IDs that must complete first
    files_touched: list[str]     # Expected files (for conflict detection)

@dataclass
class PhasedPlanOutput:
    goal: str                    # Overall goal (existing)
    plan_markdown: str           # Full plan document (existing)
    subtasks: list[Subtask]      # Ordered list of subtasks
    phases: list[list[str]]      # Computed from dependencies
                                 # e.g., [["1"], ["2a", "2b", "2c"], ["3"]]
```

Example (TDD ordering - tests before implementation):
```
Subtasks:
  1a. "Write User model tests"       → type: test → depends: []    → phase 1
  1b. "Write Post model tests"       → type: test → depends: []    → phase 1
  2a. "Implement User model"         → type: impl → depends: [1a]  → phase 2
  2b. "Implement Post model"         → type: impl → depends: [1b]  → phase 2
  3a. "Write API endpoint tests"     → type: test → depends: [2a,2b] → phase 3
  3b. "Write CLI command tests"      → type: test → depends: [2a,2b] → phase 3
  4a. "Implement API endpoints"      → type: impl → depends: [3a]  → phase 4
  4b. "Implement CLI commands"       → type: impl → depends: [3b]  → phase 4
  5.  "Write integration tests"      → type: test → depends: [4a,4b] → phase 5

Phase execution model:
- Subtasks within each phase run SEQUENTIALLY (1a → 1b, 2a → 2b, etc.)
- Phases 1 and 2 have dependencies (2a depends on 1a), so they run sequentially
- Phases 4a and 4b are independent (different dependency chains), so phase 4 could
  be split into two parallel phases if the Architect structures it that way
```

The Architect ensures each implementation subtask depends on its corresponding test subtask, enforcing the red-green TDD cycle at the task decomposition level. Subtasks within a phase execute sequentially, while independent phases can execute in parallel.

### TDD Workflow

The phased execution model naturally supports TDD by structuring dependencies so tests run before implementation:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TDD Flow per Feature                            │
├─────────────────────────────────────────────────────────────────────────┤
│  Phase N:   Write tests (RED)                                           │
│             └── Tests exist but fail (no implementation yet)            │
│                                                                         │
│  Phase N+1: Write implementation (GREEN)                                │
│             └── Minimal code to make tests pass                         │
│                                                                         │
│  Phase N+2: Refactor (optional)                                         │
│             └── Clean up while keeping tests green                      │
└─────────────────────────────────────────────────────────────────────────┘
```

**Architect prompt guidance** for TDD decomposition:

```
When decomposing tasks into subtasks:
1. For each new feature/component, create a TEST subtask first
2. Create an IMPL subtask that depends on the TEST subtask
3. Tests should be written to fail initially (red phase)
4. Implementation should be minimal to pass tests (green phase)
5. Optional REFACTOR subtasks can follow implementation

Example pattern:
  "Write X tests" (type: test) → "Implement X" (type: impl) → "Refactor X" (type: refactor)
```

**Test subtask expectations**:
- Test subtask runs, writes tests, tests fail (expected - no impl yet)
- Subtask succeeds if tests are syntactically valid and would test the right behavior
- The Reviewer checks test quality, not test passage

**Impl subtask expectations**:
- Implementation subtask runs, writes code to pass tests
- Tests from prior phase should now pass
- The Reviewer checks both implementation quality and test passage

**Validation rule**: The phase executor validates that every `impl` subtask has at least one `test` subtask in its dependency chain. This catches Architect plans that skip the test-first discipline.

```python
def validate_tdd_ordering(subtasks: list[Subtask]) -> None:
    """Ensure every impl subtask depends on a test subtask."""
    subtask_map = {s.id: s for s in subtasks}

    for subtask in subtasks:
        if subtask.type == SubtaskType.IMPL:
            # Walk dependency chain looking for a test
            if not has_test_dependency(subtask, subtask_map):
                raise TDDViolationError(
                    f"Impl subtask '{subtask.id}' has no test dependency. "
                    "TDD requires tests before implementation."
                )
```

### Context Engineering

**Key insight**: Agents have tool access (Read, Grep, Glob, git commands) regardless of driver type. They can gather context as needed. This means we shift from complex "context engineering" (pushing elaborate prompts) to simple **"context signposting"** (telling agents where to find things).

| Pattern | Application |
|---------|-------------|
| **Offloading** | Store full plan and state in filesystem; agents pull what they need |
| **Restorable compression** | Summaries include git refs so agents can recover full content with `git show` |
| **Error preservation** | On retry, keep full error traces visible—failed attempts help models avoid repetition |
| **Controlled variation** | Vary prompt framing on retry to break repetitive patterns |

#### Filesystem-Based State

Each execution gets its own directory under `docs/amelia/` for auditability and to avoid gitignore issues. Agents use their tool access to read files as needed:

```
docs/amelia/<YYYY-MM-DD>-<TRACKER-ID>-<slug>/
├── plan.md                    # Full Architect plan (written once)
├── execution-state.json       # Phase/subtask status for recovery/dashboard
├── phase-1/
│   ├── summary.md             # Compact summary with git refs (generated post-phase)
│   └── review-feedback.md     # Reviewer comments if retry needed
├── phase-2/
│   ├── summary.md
│   └── review-feedback.md
└── ...
```

Example: `docs/amelia/2026-01-05-ISSUE-123-add-user-authentication/`

**Explicit paths (orchestrator-controlled, agents read these):**
- `docs/amelia/{execution_dir}/plan.md` - full architect plan
- `docs/amelia/{execution_dir}/phase-{N}/summary.md` - phase summary with git refs
- `docs/amelia/{execution_dir}/phase-{N}/review-feedback.md` - reviewer feedback (on retry)
- `docs/amelia/{execution_dir}/execution-state.json` - phase/subtask status

Where `{execution_dir}` = `<YYYY-MM-DD>-<TRACKER-ID>-<slug>` (e.g., `2026-01-05-ISSUE-123-add-user-authentication`)

This enables "pull on demand" - prompts are simple signposts, agents read what they need.

#### Phase Summaries

After each phase commits, generate a compact summary for downstream phases. **Critical**: summaries must include restoration references so downstream phases can recover full context if needed:

```python
async def generate_phase_summary(
    execution_dir: str,
    phase_index: int,
    subtasks: list[Subtask],
    pre_commit: str,
    post_commit: str,
) -> str:
    """Generate compact summary with restoration references.

    Args:
        execution_dir: The execution directory name (e.g., "2026-01-05-ISSUE-123-add-user-auth")
    """
    diff_stat = git_diff_stat(pre_commit, post_commit)
    files_changed = extract_files_from_diff(diff_stat)
    test_files = [f for f in files_changed if "test" in f.lower()]

    summary = f"""## Phase {phase_index} Summary

**Completed subtasks:**
{chr(10).join(f"- [{s.type.value}] {s.title}" for s in subtasks)}

**Files changed:** {', '.join(files_changed)}

**Restoration references:**
- Full diff: `git diff {pre_commit}..{post_commit}`
- Commit: `git show {post_commit}`
- Test files created: {', '.join(test_files) if test_files else 'None'}

**Key changes:**
{generate_change_summary(pre_commit, post_commit)}
"""

    summary_path = f"docs/amelia/{execution_dir}/phase-{phase_index}/summary.md"
    write_file(summary_path, summary)
    return summary_path
```

The restoration references ensure information is never irreversibly lost—downstream phases can `git show` or `git diff` to recover full details when the summary is insufficient.

Context growth becomes **O(phases)** not **O(total_tokens)** because summaries are compact and agents pull full details only when needed.

#### Feedback for Retry (Error Preservation)

On retry, preserving full error context improves recovery—failed attempts help models avoid repetition and update their beliefs about what doesn't work. The key: keep errors visible and tell the agent where to find more context.

```python
def prepare_retry_context(
    execution_dir: str,
    raw_feedback: str,
    phase_index: int,
    attempt: int,
) -> str:
    """Preserve full errors and point to feedback file.

    Args:
        execution_dir: The execution directory name (e.g., "2026-01-05-ISSUE-123-add-user-auth")
    """
    # Vary framing on retry to break repetitive patterns
    retry_framing = [
        "The previous approach failed. A different strategy is needed.",
        "Review the errors carefully before proceeding differently.",
        "The prior attempt had issues. Consider an alternative approach.",
    ]

    return f"""## Retry Attempt {attempt}

{retry_framing[(attempt - 1) % len(retry_framing)]}

### Previous Attempt Errors

{raw_feedback}

Full feedback at: `docs/amelia/{execution_dir}/phase-{phase_index}/review-feedback.md`
Use `git diff HEAD~1` to see what changed in the failed attempt.
"""
```

This follows the Manus insight: "leave the wrong turns in the context." Error recovery requires seeing what failed.

### Execution Flow

The phased execution uses a **Python orchestration loop** that spawns fresh agent sessions:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Python Orchestration Flow                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. INITIALIZATION                                                          │
│     Python reads approved plan, computes phase dependency graph             │
│     Creates docs/amelia/{execution_dir}/ directory structure                │
│                                                                             │
│  2. PHASE ITERATION                                                         │
│     for phase in topological_order(plan.phases):                            │
│         if phase.dependencies_complete():                                   │
│             spawn_phase_agent(phase)                                        │
│                                                                             │
│  3. SPAWN PHASE AGENTS (parallel where independent)                         │
│     ┌─────────────────────────┐  ┌─────────────────────────┐               │
│     │ spawn_phase_agent(1)    │  │ spawn_phase_agent(2)    │               │
│     │ → Fresh agent session   │  │ → Fresh agent session   │               │
│     │ → Subtasks run seq.     │  │ → Subtasks run seq.     │               │
│     │ → Returns PhaseReport   │  │ → Returns PhaseReport   │               │
│     └─────────────────────────┘  └─────────────────────────┘               │
│                                                                             │
│  4. HANDLE RESULTS (deterministic rules)                                    │
│     if report.status == "completed":                                        │
│         commit_phase(phase_index)                                           │
│         generate_summary(phase_index)                                       │
│     elif report.status == "failed" and attempt < 2:                         │
│         reset_to_pre_commit()                                               │
│         retry with error context                                            │
│     else:                                                                   │
│         raise PhaseFailure("halt execution")                                │
│                                                                             │
│  5. STATE UPDATES                                                           │
│     Update ExecutionState (frozen model copy)                               │
│     Yield StreamEvents for dashboard                                        │
│                                                                             │
│  6. COMPLETION                                                              │
│     All phases complete → return ExecutionResult                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Parallelism Model

```
┌──────────────────────────────────────────────────────────────────┐
│  Phase Group 1 (parallel)     Phase Group 2 (sequential after 1) │
│  ┌─────────────┐  ┌─────────────┐    ┌─────────────┐             │
│  │  Phase 1    │  │  Phase 2    │    │   Phase 3   │             │
│  │  Agent      │  │  Agent      │ →  │   Agent     │             │
│  │ (subtasks   │  │ (subtasks   │    │  (subtasks  │             │
│  │  run seq.)  │  │  run seq.)  │    │   run seq.) │             │
│  └─────────────┘  └─────────────┘    └─────────────┘             │
│                                                                  │
│  Subtasks within phase: SEQUENTIAL (agent executes one by one)   │
│  Independent phases: PARALLEL (Python spawns via asyncio.gather) │
│  Dependent phases: SEQUENTIAL (Python waits for deps)            │
└──────────────────────────────────────────────────────────────────┘
```

The Python orchestrator computes phase dependencies at startup and uses `asyncio.gather` to run independent phases concurrently.

#### State Updates

The Python orchestrator updates `ExecutionState` after each phase completes:

```python
# Python orchestrator creates state updates using frozen model pattern
def update_phase_state(
    state: ExecutionState,
    phase_index: int,
    report: PhaseReport,
) -> ExecutionState:
    """Update execution state after phase completion."""
    updated_phase = PhaseState(
        phase_index=phase_index,
        status=report.status,
        subtasks=tuple(
            SubtaskState(subtask_id=s, status="completed")
            for s in report.subtasks_completed
        ),
    )
    return state.model_copy(update={
        "phase_states": state.phase_states + (updated_phase,),
        "current_phase_index": phase_index + 1,
    })
```

### Phase Agent Spawning

The Python orchestrator spawns **fresh phase agent sessions**—each running with scoped context. The phase agent executes subtasks sequentially within its session:

```python
async def spawn_phase_agent(
    phase_index: int,
    subtasks: list[Subtask],
    plan: PhasedPlanOutput,
    profile: Profile,
    cwd: Path,
    retry_context: str | None = None,
) -> AsyncIterator[AgenticMessage]:
    """Spawn a fresh agent session to execute a phase.

    The phase agent:
    1. Receives its subtask assignments with scoped context
    2. Executes subtasks sequentially within its session
    3. Reports completion/failure back to orchestrator

    Yields AgenticMessage events for UI streaming.
    """
    # Fresh driver instance = fresh agent session
    driver = DriverFactory.get_driver(profile.driver)

    # Build phase agent prompt with scoped context
    prompt = build_phase_agent_prompt(
        phase_index=phase_index,
        subtasks=subtasks,
        prior_phase_summaries=get_prior_summaries(phase_index),
        retry_context=retry_context,
    )

    # Phase agent executes its subtasks
    async for message in driver.execute_agentic(prompt, cwd):
        yield AgenticMessage(
            type=message.type,
            content=message.content,
            metadata={"phase_index": phase_index},
        )
```

#### Subtask Execution Within Phase Agent

Within a phase agent session, subtasks execute **sequentially**. The phase agent manages this internally—it doesn't spawn separate sessions per subtask. This keeps context costs lower while ensuring subtask ordering.

**Token savings**: The prompt stays small (~200-400 tokens) regardless of plan complexity. Agents pull context from the filesystem as needed rather than receiving it all upfront.

### Commit Strategy

Subtasks within a phase run **sequentially** on the same working directory. Each subtask sees the file changes from prior subtasks in the same phase. We use **one commit per phase** to enable clean retries:

1. **Subtasks make file changes only** - no commits during subtask execution
2. **Subtasks run sequentially** - each subtask can read/build on prior subtask changes
3. **Phase executor commits** - after all subtasks complete successfully, create a single commit
4. **Reviewer reviews the phase commit** - diffs against pre-phase HEAD
5. **On retry, reset is clean** - `git reset --hard pre_commit` discards all uncommitted changes

```python
async def handle_phase_completion(
    phase_index: int,
    phase_report: PhaseReport,
    pre_commit: str,
) -> str:
    """Handle completion of a phase agent session.

    Called by Python orchestrator after phase agent reports success.
    Commits changes and generates summary for downstream phases.

    Returns the post-commit SHA.
    """
    if phase_report.status != "completed":
        raise PhaseNotComplete(phase_index, phase_report)

    # Single commit for the entire phase
    subtask_titles = ", ".join(phase_report.subtasks_completed)
    git_add(".")
    git_commit(f"Phase {phase_index}: {subtask_titles}")

    post_commit = git_rev_parse("HEAD")

    # Generate summary with restoration references for downstream phases
    await generate_phase_summary(
        phase_index,
        phase_report.files_changed,
        pre_commit,
        post_commit,
    )

    return post_commit
```

### Phase Review with Retry

The Python orchestrator handles retry logic with simple, deterministic rules:

```python
async def execute_phase_with_retry(
    phase_index: int,
    subtasks: list[Subtask],
    context: str,
    profile: Profile,
    cwd: Path,
    max_attempts: int = 2,
) -> PhaseReport:
    """Execute a phase with retry on failure.

    Simple rules:
    - On failure, retry once with error context
    - On second failure, raise PhaseFailure to halt execution
    """
    pre_commit = git_rev_parse("HEAD")

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            # Reset to pre-phase state
            git_reset_hard(pre_commit)
            # Add retry context to prompt
            retry_feedback = prepare_retry_context(
                last_error, phase_index, attempt
            )
            context = context + retry_feedback

        report = await spawn_phase_agent(subtasks, context, profile, cwd)

        if report.status == "completed":
            return report

        last_error = report.error_context
        logger.warning(
            "Phase failed",
            phase=phase_index,
            attempt=attempt,
            error=last_error[:200],
        )

    # Both attempts failed
    raise PhaseFailure(
        f"Phase {phase_index} failed after {max_attempts} attempts: {last_error}"
    )
```

### State Tracking

```python
class PhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

@dataclass
class SubtaskState:
    subtask_id: str
    status: PhaseStatus
    attempt: int              # 1 or 2
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None

@dataclass
class PhaseState:
    phase_index: int
    subtasks: list[SubtaskState]
    status: PhaseStatus
    pre_phase_commit: str     # For reset on retry
    review_result: ReviewResult | None
```

### Stream Events

```python
class StreamEventType(str, Enum):
    # ... existing ...
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    PHASE_RETRY = "phase_retry"
    SUBTASK_STARTED = "subtask_started"
    SUBTASK_COMPLETED = "subtask_completed"
    SUBTASK_FAILED = "subtask_failed"
```

Dashboard display:
```
Phase Group 1 (parallel):
  Phase 1 (test): ✓ Write model tests
    ├── ✓ [test] User model tests (completed)
    └── ✓ [test] Post model tests (completed after User)
  Phase 2 (test): ● Running - Write API tests
    ├── ✓ [test] API endpoint tests (completed)
    └── ● [test] CLI command tests (running)

Phase Group 2 (waiting on Group 1):
  Phase 3 (impl): ○ Pending - Implement models
    ├── ○ [impl] User model
    └── ○ [impl] Post model
  Phase 4 (impl): ○ Pending - Implement APIs
    ├── ○ [impl] API endpoints
    └── ○ [impl] CLI commands

Subtasks within each phase: sequential (one after another)
Phases 1 and 2: parallel (independent, no shared dependencies)
Phases 3 and 4: parallel (once Group 1 completes)
```

## Implementation Plan

### Integration with Current Architecture

**Flow:**
```
Architect (agentic) → Plan Validator (extracts subtasks) → Human Approval → Python Orchestrator → Phase Agents → Review per Phase
```

### Files to Modify

| File | Changes |
|------|---------|
| `amelia/agents/architect.py` | Update system prompt to guide TDD-ordered subtask generation in markdown format |
| `amelia/core/state.py` | Add `PhaseState`, `SubtaskState`, `phases`, `current_phase` to ExecutionState (frozen model patterns) |
| `amelia/core/types.py` | Add `SubtaskType` enum, new `StreamEventType` variants for phase/subtask events, `PhaseReport` |
| `amelia/core/orchestrator.py` | Add `phased_execution_node` that runs the Python orchestration loop |
| `amelia/core/plan_validator.py` | Extend to extract `Subtask` list from plan markdown sections |

### New Modules

```
amelia/core/phased_executor.py         # Python orchestration loop
├── execute_phased_plan()              # Main orchestration loop
├── execute_phase_with_retry()         # Single phase with retry logic
├── validate_tdd_ordering()            # Ensure impl subtasks depend on test subtasks
├── spawn_phase_agent()                # Create fresh phase agent session
├── handle_phase_completion()          # Commit and generate summary
├── reset_to_commit()                  # Git reset for retry
├── initialize_execution_dir()         # Create docs/amelia/{execution_dir}/ structure
└── make_execution_dir_name()          # Generate <YYYY-MM-DD>-<TRACKER-ID>-<slug>

amelia/core/context_engineering.py
├── build_phase_agent_prompt()         # Simple signposting prompt for phase agent
├── generate_phase_summary()           # Create summary with git refs for restoration
├── prepare_retry_context()            # Error context with file path references
├── write_execution_state()            # Persist phase/subtask state to JSON
└── read_execution_state()             # Recover state for resumption
```

### State Model Changes (Frozen Pattern)

Since `ExecutionState` is frozen, phase tracking uses the same patterns as existing fields:

```python
# In amelia/core/state.py

class SubtaskState(BaseModel):
    """Tracks execution state for a single subtask."""
    model_config = ConfigDict(frozen=True)

    subtask_id: str
    status: Literal["pending", "running", "completed", "failed", "retrying"]
    attempt: int = 1
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

class PhaseState(BaseModel):
    """Tracks execution state for a phase (group of sequential subtasks)."""
    model_config = ConfigDict(frozen=True)

    phase_index: int
    subtasks: tuple[SubtaskState, ...]  # Immutable sequence
    status: Literal["pending", "running", "completed", "failed", "retrying"]
    pre_phase_commit: str | None = None
    review_result: ReviewResult | None = None

class ExecutionState(BaseModel):
    # ... existing fields ...

    # Phased execution (optional - None means single-session mode)
    subtasks: tuple[Subtask, ...] | None = None
    phases: tuple[tuple[str, ...], ...] | None = None  # Computed from dependencies
    phase_states: tuple[PhaseState, ...] = ()
    current_phase_index: int = 0
```

State updates use `model_copy(update={...})`:
```python
new_state = state.model_copy(update={
    "current_phase_index": state.current_phase_index + 1,
    "phase_states": state.phase_states + (completed_phase,),
})
```

### Evaluator Integration for Phase Review

The existing `Evaluator` agent (added for review-fix workflow) provides structured feedback processing. For phased execution, we integrate it into per-phase review:

```python
async def review_phase_with_evaluator(
    phase: list[Subtask],
    pre_commit: str,
    plan: PhasedPlanOutput,
    profile: Profile,
) -> tuple[ReviewResult, EvaluationResult]:
    """Review phase and evaluate feedback for actionability."""
    # Get raw review
    review = await Reviewer(profile).review(pre_commit)

    if review.approved:
        return review, None

    # Evaluate feedback to partition items
    evaluation = await Evaluator(profile).evaluate(
        review_comments=review.comments,
        context=f"Phase {phase[0].phase_index} review"
    )

    # Items to implement are actionable feedback
    # REJECT items indicate reviewer errors (ignore)
    # DEFER items are out of scope (log but don't retry for)
    actionable = [item for item in evaluation.items if item.disposition == "IMPLEMENT"]

    return review, evaluation
```

This allows the retry mechanism to focus on actionable feedback and filter out noise.

### Backward Compatibility

- If plan validator extracts no subtasks → existing single-session `developer_node`
- If plan validator extracts subtasks → routed to `phased_execution_node`
- Profile flag `enable_phased_execution: bool = True` to opt-out if needed

## Testing Strategy

1. **Unit tests**: Phase dependency resolution, retry logic, state transitions
2. **Context engineering tests**:
   - `build_phase_agent_prompt()` includes correct filesystem paths
   - `build_phase_agent_prompt()` includes subtask list in expected format
   - `build_phase_agent_prompt()` appends retry context when provided
   - `generate_phase_summary()` produces valid markdown with git refs
   - `generate_phase_summary()` includes restoration commands that work
   - `prepare_retry_context()` preserves full error context
   - `prepare_retry_context()` includes path to review-feedback.md
   - `write_execution_state()` / `read_execution_state()` round-trip correctly
3. **Orchestration loop tests**:
   - `execute_phased_plan()` iterates phases in dependency order
   - `execute_phase_with_retry()` retries once on failure, halts on second failure
   - Parallel phases are spawned via `asyncio.gather`
   - State updates use frozen model pattern correctly
4. **Integration tests**: Full phased execution with mock driver
5. **E2E tests**: Real multi-phase task with actual LLM calls

## Implementation Approach

### Phase 1: Foundation (No User-Visible Changes)
1. Add `Subtask`, `SubtaskState`, `PhaseState`, `PhaseReport` types to `amelia/core/types.py`
2. Extend `ExecutionState` with optional phase fields (frozen pattern)
3. Create `amelia/core/context_engineering.py` with:
   - `build_phase_agent_prompt()` - simple signposting prompt
   - `generate_phase_summary()` - summary with git refs
   - `prepare_retry_context()` - error context for retries
   - `write_execution_state()` / `read_execution_state()` - state persistence
4. Add unit tests for context engineering functions

### Phase 2: Subtask Extraction
1. Extend `plan_validator_node` output schema to include optional `subtasks` field
2. Update architect prompt to generate subtask markdown format
3. Parse subtask format from plan markdown in validator
4. Add `validate_tdd_ordering()` check

### Phase 3: Python Orchestration Loop
1. Create `amelia/core/phased_executor.py` with:
   - `execute_phased_plan()` - main orchestration loop
   - `execute_phase_with_retry()` - single phase with retry
   - `spawn_phase_agent()` - create fresh agent session
   - `handle_phase_completion()` - commit and summarize
   - `reset_to_commit()` - git reset for retry
2. Add `phased_execution_node` to orchestrator graph
3. Wire routing: subtasks present → phased execution node, else → existing developer node

### Phase 4: Phase Agent Integration
1. Define phase agent prompt templates
2. Implement phase agent spawning with scoped context
3. Integrate per-phase review with Evaluator
4. Test orchestration → phase agent → review flow

### Phase 5: Polish
1. Dashboard updates for phase visualization
2. Stream event multiplexing for parallel phases
3. E2E tests with real LLM
4. Performance benchmarks for context size reduction

**Current branch (`feat/199-plan-validator-node`)** provides foundation for Phase 2 - the validator infrastructure is in place.
