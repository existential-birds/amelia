# Session Continuity Design

**Date:** 2025-12-13
**Status:** Draft
**Phase:** 3 (per [Roadmap](../roadmap.md))

## Overview

**Session Continuity** enables long-running workflows to survive context window boundaries. When a workflow pauses—whether due to explicit request, context exhaustion, or timeout—the system captures a structured snapshot that allows any future agent session to resume where the previous one left off.

### Core Problem

```
Session N                          Session N+1
┌─────────────────────────────────┐           ┌─────────────────────────────────┐
│ Agent has accumulated context:  │           │ Agent starts fresh:             │
│ • Issue understanding           │           │ • No memory of Session N        │
│ • Plan decisions & rationale    │  ──X──►   │ • Must rediscover everything    │
│ • Files modified + git state    │  (lost)   │ • Repeats mistakes              │
│ • Errors hit + resolutions      │           │ • Loses decision rationale      │
│ • Reviewer feedback history     │           │ • Context exhaustion inevitable │
└─────────────────────────────────┘           └─────────────────────────────────┘
```

### Solution: Structured Handoff Protocol

```
Session N                                      Session N+1
┌─────────────────────────────────┐           ┌─────────────────────────────────┐
│ Agent working on tasks...       │           │ Agent receives:                 │
│                                 │           │ • Compiled resume context       │
│ [Pause triggered]               │           │ • Task status summary           │
│     │                           │           │ • Key decisions made            │
│     ▼                           │           │ • Errors + resolutions          │
│ Create SessionSnapshot          │           │ • What's next                   │
│ Extract decisions (LLM)         │  ─────►   │                                 │
│ Persist to SQLite               │ (restore) │ [Continues from task boundary]  │
│ Emit WORKFLOW_PAUSED            │           │                                 │
└─────────────────────────────────┘           └─────────────────────────────────┘
```

### Key Characteristics

- **Task-boundary pauses**: Workflows pause only at clean task boundaries, not mid-execution
- **Server-side state**: All snapshots stored in SQLite, queryable via API
- **LLM-extracted decisions**: Key choices automatically extracted from agent messages
- **Adaptive resume context**: Summary provided by default, detailed history retrievable on demand
- **TDD-friendly**: Supports pausing mid-TDD cycle with expected failing tests tracked
- **CLI + Dashboard parity**: Both interfaces use identical server endpoints

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Amelia Server                                   │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        OrchestratorService                             │ │
│  │                                                                        │ │
│  │  pause_workflow(workflow_id, reason, trigger)                          │ │
│  │    • Waits for current task to complete (task boundary)                │ │
│  │    • Creates SessionSnapshot with full state                           │ │
│  │    • Extracts decisions via LLM summarization                          │ │
│  │    • Persists snapshot to SQLite                                       │ │
│  │    • Emits WORKFLOW_PAUSED event                                       │ │
│  │                                                                        │ │
│  │  resume_workflow(workflow_id)                                          │ │
│  │    • Loads latest SessionSnapshot                                      │ │
│  │    • Compiles resume context (summary + retrieval API)                 │ │
│  │    • Restarts LangGraph from checkpoint                                │ │
│  │    • Continues from next pending task                                  │ │
│  │    • Emits WORKFLOW_RESUMED event                                      │ │
│  │                                                                        │ │
│  │  _check_capacity(usage_metadata)                                       │ │
│  │    • Monitors context utilization after each agent call                │ │
│  │    • Triggers pause when threshold exceeded (default 85%)              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                       │
│  ┌───────────────────────────────────▼──────────────────────────────────┐   │
│  │                         SQLite Database                               │   │
│  │                                                                       │   │
│  │  workflows                                                            │   │
│  │    + paused_at: datetime | null                                       │   │
│  │    + pause_reason: str | null                                         │   │
│  │    + session_count: int (default 1)                                   │   │
│  │                                                                       │   │
│  │  session_snapshots (NEW)                                              │   │
│  │    workflow_id, session_number, trigger, snapshot_json, created_at    │   │
│  │                                                                       │   │
│  │  workflow_events                                                      │   │
│  │    + WORKFLOW_PAUSED, WORKFLOW_RESUMED event types                    │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      DecisionExtractor                                │   │
│  │                                                                       │   │
│  │  extract_decisions(messages: list[AgentMessage]) -> list[Decision]   │   │
│  │    • LLM-based extraction of key decisions from agent messages        │   │
│  │    • Structured output: decision_type, description, rationale         │   │
│  │                                                                       │   │
│  │  extract_errors(messages: list[AgentMessage]) -> list[ErrorRecord]   │   │
│  │    • Identifies errors encountered and their resolutions              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     ResumeContextCompiler                             │   │
│  │                                                                       │   │
│  │  compile_resume_context(snapshot: SessionSnapshot) -> str            │   │
│  │    • Generates structured summary for new session                     │   │
│  │    • Includes: issue, plan status, decisions, errors, next steps      │   │
│  │    • Schema-driven format (not prose soup)                            │   │
│  │                                                                       │   │
│  │  get_detailed_history(snapshot_id, category) -> str                  │   │
│  │    • On-demand retrieval for agents needing more context              │   │
│  │    • Categories: decisions, errors, reviewer_feedback, git_changes   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
                    │                              │
                    ▼                              ▼
         ┌─────────────────────┐        ┌─────────────────────┐
         │     Dashboard       │        │        CLI          │
         │                     │        │                     │
         │  [Pause] [Resume]   │        │  amelia pause       │
         │  Session timeline   │        │  amelia resume      │
         │  Snapshot viewer    │        │  amelia status      │
         └─────────────────────┘        └─────────────────────┘
```

### Component Responsibilities

| Component | Purpose |
|-----------|---------|
| **OrchestratorService** | Coordinates pause/resume lifecycle, monitors capacity, manages snapshots |
| **SessionSnapshot** | Point-in-time capture of all workflow state needed for resume |
| **DecisionExtractor** | LLM-based extraction of key decisions from agent message history |
| **ResumeContextCompiler** | Generates structured summary for new sessions, provides retrieval API |
| **DriverInterface** | Extended to report token usage and remaining capacity |

---

## Data Models

### Core Snapshot Model

```python
class SessionSnapshot(BaseModel):
    """Point-in-time capture of workflow state for resume.

    Contains everything needed to resume a workflow in a new agent session,
    including task progress, decisions made, errors encountered, and git state.
    """
    id: str = Field(description="Unique snapshot identifier")
    workflow_id: str = Field(description="Parent workflow")
    session_number: int = Field(description="1-indexed session count")

    # When and why this snapshot was created
    created_at: datetime
    trigger: Literal["pause", "task_complete", "exhaustion", "timeout", "crash"]
    pause_reason: str | None = Field(
        description="Human-readable explanation of why paused"
    )

    # Task state
    task_dag: TaskDAG = Field(description="Full DAG with current statuses")
    current_task_id: str | None = Field(description="Task that was in progress")
    next_task_id: str | None = Field(description="Next task to execute on resume")
    tasks_completed: int = Field(description="Count of completed tasks")
    tasks_remaining: int = Field(description="Count of pending/blocked tasks")

    # Git state
    git_state: GitState

    # Extracted context for resume
    decisions: list[Decision] = Field(
        default_factory=list,
        description="Key decisions extracted from agent messages"
    )
    errors: list[ErrorRecord] = Field(
        default_factory=list,
        description="Errors encountered and their resolutions"
    )
    reviewer_feedback: list[ReviewerFeedback] | None = Field(
        default=None,
        description="Feedback from review cycles, if any"
    )

    # TDD state
    test_state: TestState | None = Field(
        default=None,
        description="Current TDD cycle state"
    )

    # Resource tracking
    usage: UsageMetrics


class GitState(BaseModel):
    """Git repository state at snapshot time."""
    branch: str
    commit_at_workflow_start: str = Field(description="SHA when workflow began")
    commit_at_snapshot: str = Field(description="SHA at snapshot time")
    files_modified: list[str] = Field(
        description="Paths changed since workflow start"
    )
    files_staged: list[str] = Field(description="Files in staging area")
    has_uncommitted_changes: bool = Field(description="Dirty working tree?")
    uncommitted_summary: str | None = Field(
        description="Brief summary of uncommitted changes"
    )


class Decision(BaseModel):
    """Structured record of a significant choice made during execution.

    Extracted automatically from agent messages via LLM summarization.
    """
    id: str
    timestamp: datetime
    task_id: str | None = Field(description="Related task, if any")
    decision_type: Literal[
        "approach",      # How to implement something
        "library",       # Which library/tool to use
        "architecture",  # Structural choice
        "workaround",    # Temporary fix for blocker
        "skip",          # Decision to defer/skip something
        "clarification", # Interpretation of ambiguous requirement
    ]
    description: str = Field(description="What was decided")
    rationale: str = Field(description="Why this choice was made")
    alternatives_considered: list[str] | None = Field(
        default=None,
        description="Other options that were evaluated"
    )


class ErrorRecord(BaseModel):
    """Record of an error encountered and its resolution."""
    id: str
    timestamp: datetime
    task_id: str | None
    error_type: str = Field(description="Exception type or error category")
    error_message: str = Field(description="Error details")
    context: str | None = Field(description="What was happening when error occurred")
    resolution: Literal["fixed", "workaround", "deferred", "unresolved"]
    resolution_notes: str | None = Field(
        description="How it was resolved or why deferred"
    )


class ReviewerFeedback(BaseModel):
    """Feedback from a review cycle."""
    review_id: str
    reviewer_persona: str
    timestamp: datetime
    approved: bool
    severity: str
    comments: list[str]
    addressed: bool = Field(
        default=False,
        description="Whether this feedback has been addressed"
    )


class TestState(BaseModel):
    """TDD cycle state for clean handoffs mid-cycle.

    Tracks which tests are expected to fail (red phase) vs unexpected failures.
    """
    phase: Literal["red", "green", "refactor", "unknown"]
    failing_tests: list[str] = Field(
        description="Test names currently failing"
    )
    expected_failures: list[str] = Field(
        default_factory=list,
        description="Tests expected to fail in red phase"
    )
    last_test_run_at: datetime | None
    last_test_command: str | None
    last_test_output_summary: str | None = Field(
        description="Truncated test output for context"
    )


class UsageMetrics(BaseModel):
    """Resource usage tracking for the session."""
    tokens_used: int = Field(description="Total tokens consumed this session")
    tokens_remaining_estimate: int | None = Field(
        description="Estimated remaining capacity from driver"
    )
    context_utilization: float | None = Field(
        description="Percentage of context window used (0.0-1.0)"
    )
    llm_calls: int = Field(description="Number of LLM API calls made")
    tool_calls: int = Field(description="Number of tool executions")
    cost_usd: float | None = Field(description="Estimated cost in USD")
    session_duration_seconds: int = Field(description="Wall clock time")
```

### Driver Capacity Reporting

```python
class UsageMetadata(BaseModel):
    """Token usage and capacity info returned by drivers.

    Enables orchestrator to detect approaching context exhaustion
    and trigger proactive pause before failure.
    """
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    # Capacity tracking
    context_window_size: int = Field(
        description="Model's maximum context (e.g., 200000 for Claude)"
    )
    tokens_remaining: int = Field(
        description="Estimated remaining capacity"
    )
    utilization_percent: float = Field(
        description="Current utilization (0.0-1.0)"
    )

    @classmethod
    def from_pydantic_ai_usage(
        cls,
        usage: "pydantic_ai.Usage",
        context_window: int = 200_000,
    ) -> "UsageMetadata":
        """Create from pydantic-ai usage object."""
        total = (usage.request_tokens or 0) + (usage.response_tokens or 0)
        remaining = context_window - total
        return cls(
            prompt_tokens=usage.request_tokens or 0,
            completion_tokens=usage.response_tokens or 0,
            total_tokens=total,
            context_window_size=context_window,
            tokens_remaining=max(0, remaining),
            utilization_percent=min(1.0, total / context_window),
        )
```

### Database Schema Additions

```sql
-- Add pause tracking to workflows table
ALTER TABLE workflows ADD COLUMN paused_at TIMESTAMP;
ALTER TABLE workflows ADD COLUMN pause_reason TEXT;
ALTER TABLE workflows ADD COLUMN session_count INTEGER DEFAULT 1;

-- Session snapshots table
CREATE TABLE session_snapshots (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id),
    session_number INTEGER NOT NULL,
    trigger TEXT NOT NULL,  -- pause, task_complete, exhaustion, timeout, crash
    snapshot_json TEXT NOT NULL,  -- Full SessionSnapshot as JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes for common queries
    UNIQUE(workflow_id, session_number)
);

CREATE INDEX idx_snapshots_workflow ON session_snapshots(workflow_id);
CREATE INDEX idx_snapshots_created ON session_snapshots(created_at DESC);

-- Add new event types to workflow_events
-- WORKFLOW_PAUSED, WORKFLOW_RESUMED
```

### Workflow Status Extension

```python
# Update in amelia/server/models/state.py
WorkflowStatus = Literal[
    "pending",      # Not yet started
    "in_progress",  # Currently executing
    "blocked",      # Awaiting human approval
    "paused",       # NEW: Paused for session handoff
    "completed",    # Successfully finished
    "failed",       # Error occurred
    "cancelled",    # Explicitly cancelled
]

# Update valid transitions
VALID_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    "pending": {"in_progress", "cancelled"},
    "in_progress": {"blocked", "paused", "completed", "failed", "cancelled"},
    "blocked": {"in_progress", "failed", "cancelled"},
    "paused": {"in_progress", "cancelled"},  # NEW: Can resume or cancel
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}
```

---

## Session Lifecycle

### Pause Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Pause Triggers                                 │
├─────────────────────────────────────────────────────────────────────────┤
│  1. Explicit pause     │ User clicks Pause or runs `amelia pause`       │
│  2. Context exhaustion │ Driver reports >85% utilization                │
│  3. Task completion    │ Configurable auto-pause after N tasks          │
│  4. Timeout            │ Workflow exceeds configured duration           │
│  5. Crash recovery     │ Server restart with in_progress workflows      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    1. Wait for Task Boundary                             │
│                                                                          │
│  • If mid-task, set pause_requested flag                                │
│  • Continue until current task completes or fails                       │
│  • Timeout: force pause after 5 minutes with warning                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    2. Gather State                                       │
│                                                                          │
│  • Snapshot TaskDAG with current statuses                               │
│  • Capture git state (branch, commits, modified files)                  │
│  • Collect agent message history for decision extraction                │
│  • Record test state if TDD in progress                                 │
│  • Calculate usage metrics                                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    3. Extract Decisions & Errors                         │
│                                                                          │
│  • Send recent messages to LLM for structured extraction                │
│  • Identify key decisions with rationale                                │
│  • Identify errors and their resolutions                                │
│  • Extract reviewer feedback status                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    4. Create & Persist Snapshot                          │
│                                                                          │
│  • Build SessionSnapshot with all gathered data                         │
│  • Increment session_count on workflow                                  │
│  • Serialize to JSON and store in session_snapshots                     │
│  • Update workflow status to "paused"                                   │
│  • Emit WORKFLOW_PAUSED event                                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    5. Notify                                             │
│                                                                          │
│  • WebSocket event to dashboard                                         │
│  • Log pause reason and snapshot ID                                     │
│  • (Future: Slack/Discord notification)                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### Resume Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Resume Trigger                                   │
│                                                                          │
│  • Dashboard: User clicks [Resume] button                               │
│  • CLI: User runs `amelia resume` in worktree                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    1. Load Latest Snapshot                               │
│                                                                          │
│  • Fetch most recent SessionSnapshot for workflow                       │
│  • Validate workflow status is "paused"                                 │
│  • Check git state matches (warn if diverged)                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    2. Compile Resume Context                             │
│                                                                          │
│  • Generate structured summary from snapshot                            │
│  • Include: issue, plan status, key decisions, recent errors            │
│  • Format as schema-driven context (not prose)                          │
│  • Register retrieval endpoints for detailed history                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    3. Restore Workflow State                             │
│                                                                          │
│  • Update ExecutionState with snapshot.task_dag                         │
│  • Set current_task_id to snapshot.next_task_id                         │
│  • Increment session_count                                              │
│  • Update workflow status to "in_progress"                              │
│  • Emit WORKFLOW_RESUMED event                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    4. Continue Execution                                 │
│                                                                          │
│  • Inject resume context into agent system prompt                       │
│  • Resume LangGraph from checkpoint (or create new run)                 │
│  • Continue from next pending task in DAG                               │
│  • Normal execution flow resumes                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Decision Extraction

### Extraction Prompt

```python
DECISION_EXTRACTION_PROMPT = """Analyze the following agent conversation and extract key decisions that were made.

A "decision" is a significant choice that:
- Affects how the task is implemented
- Chooses between multiple valid approaches
- Works around a limitation or blocker
- Interprets an ambiguous requirement

For each decision, provide:
1. decision_type: One of [approach, library, architecture, workaround, skip, clarification]
2. description: What was decided (1-2 sentences)
3. rationale: Why this choice was made
4. alternatives_considered: Other options that were evaluated (if mentioned)

Also extract any errors encountered and their resolutions.

Return as JSON matching this schema:
{
  "decisions": [
    {
      "decision_type": "approach",
      "description": "...",
      "rationale": "...",
      "alternatives_considered": ["...", "..."]
    }
  ],
  "errors": [
    {
      "error_type": "...",
      "error_message": "...",
      "context": "...",
      "resolution": "fixed|workaround|deferred|unresolved",
      "resolution_notes": "..."
    }
  ]
}

<conversation>
{messages}
</conversation>
"""
```

### Extraction Implementation

```python
class DecisionExtractor:
    """Extract structured decisions from agent message history."""

    def __init__(self, driver: DriverInterface):
        self.driver = driver

    async def extract(
        self,
        messages: list[AgentMessage],
        max_messages: int = 50,
    ) -> tuple[list[Decision], list[ErrorRecord]]:
        """Extract decisions and errors from recent messages.

        Args:
            messages: Agent message history.
            max_messages: Limit to most recent N messages for context.

        Returns:
            Tuple of (decisions, errors) extracted from messages.
        """
        # Take most recent messages
        recent = messages[-max_messages:] if len(messages) > max_messages else messages

        # Format for extraction
        formatted = "\n\n".join(
            f"[{msg.role}]: {msg.content}"
            for msg in recent
            if msg.content
        )

        # Extract via LLM
        result = await self.driver.generate(
            messages=[
                AgentMessage(role="system", content=DECISION_EXTRACTION_PROMPT),
                AgentMessage(role="user", content=formatted),
            ],
            schema=ExtractionResult,
        )

        # Convert to domain models
        decisions = [
            Decision(
                id=str(uuid4()),
                timestamp=datetime.now(UTC),
                task_id=None,  # Could be inferred from context
                **d.model_dump()
            )
            for d in result.decisions
        ]

        errors = [
            ErrorRecord(
                id=str(uuid4()),
                timestamp=datetime.now(UTC),
                task_id=None,
                **e.model_dump()
            )
            for e in result.errors
        ]

        return decisions, errors
```

---

## Resume Context Compilation

### Resume Context Format

The resume context is injected into the agent's system prompt when resuming. It uses a schema-driven format that preserves structure while being token-efficient.

```python
RESUME_CONTEXT_TEMPLATE = """
## Session Resume Context

You are resuming workflow {workflow_id} (session {session_number} of {total_sessions}).

### Original Issue
{issue_summary}

### Plan Status
- Total tasks: {total_tasks}
- Completed: {completed_tasks}
- Remaining: {remaining_tasks}
- Current task: {current_task}

<completed_tasks>
{completed_task_list}
</completed_tasks>

<pending_tasks>
{pending_task_list}
</pending_tasks>

### Key Decisions Made
{decisions_summary}

### Errors Encountered
{errors_summary}

### Git State
- Branch: {branch}
- Files modified: {files_modified_count}
- Uncommitted changes: {has_uncommitted}

{test_state_section}

### What to Do Next
Continue from task "{next_task_description}". The previous session ended because: {pause_reason}.

{reviewer_feedback_section}

---
NOTE: Use the retrieval API to get more detail on any section if needed:
- GET /workflows/{workflow_id}/snapshots/{snapshot_id}/decisions
- GET /workflows/{workflow_id}/snapshots/{snapshot_id}/errors
- GET /workflows/{workflow_id}/snapshots/{snapshot_id}/git-changes
"""
```

### Context Compiler Implementation

```python
class ResumeContextCompiler:
    """Compile structured resume context from session snapshots."""

    def compile(self, snapshot: SessionSnapshot, issue: Issue) -> str:
        """Generate resume context for a new agent session.

        Args:
            snapshot: The session snapshot to resume from.
            issue: The original issue being worked on.

        Returns:
            Formatted context string for agent system prompt.
        """
        # Format completed tasks
        completed = [t for t in snapshot.task_dag.tasks if t.status == "completed"]
        completed_list = "\n".join(
            f"  ✓ [{t.id}] {t.description}"
            for t in completed
        )

        # Format pending tasks
        pending = [t for t in snapshot.task_dag.tasks if t.status in ("pending", "blocked")]
        pending_list = "\n".join(
            f"  ○ [{t.id}] {t.description}"
            for t in pending
        )

        # Format decisions (summary)
        decisions_summary = self._format_decisions(snapshot.decisions)

        # Format errors (summary)
        errors_summary = self._format_errors(snapshot.errors)

        # Test state section (if applicable)
        test_section = self._format_test_state(snapshot.test_state)

        # Reviewer feedback section (if applicable)
        feedback_section = self._format_reviewer_feedback(snapshot.reviewer_feedback)

        # Find next task
        next_task = next(
            (t for t in snapshot.task_dag.tasks if t.id == snapshot.next_task_id),
            None
        )

        return RESUME_CONTEXT_TEMPLATE.format(
            workflow_id=snapshot.workflow_id,
            session_number=snapshot.session_number,
            total_sessions=snapshot.session_number,  # Will be incremented
            issue_summary=f"{issue.id}: {issue.title}\n{issue.description[:500]}...",
            total_tasks=len(snapshot.task_dag.tasks),
            completed_tasks=snapshot.tasks_completed,
            remaining_tasks=snapshot.tasks_remaining,
            current_task=snapshot.current_task_id or "None",
            completed_task_list=completed_list or "  (none yet)",
            pending_task_list=pending_list or "  (all complete)",
            decisions_summary=decisions_summary,
            errors_summary=errors_summary,
            branch=snapshot.git_state.branch,
            files_modified_count=len(snapshot.git_state.files_modified),
            has_uncommitted=snapshot.git_state.has_uncommitted_changes,
            test_state_section=test_section,
            next_task_description=next_task.description if next_task else "Unknown",
            pause_reason=snapshot.pause_reason or "Unknown",
            reviewer_feedback_section=feedback_section,
            snapshot_id=snapshot.id,
        )

    def _format_decisions(self, decisions: list[Decision]) -> str:
        if not decisions:
            return "  (no significant decisions recorded)"

        # Show most recent 5 decisions
        recent = decisions[-5:]
        lines = []
        for d in recent:
            lines.append(f"  • [{d.decision_type}] {d.description}")
            lines.append(f"    Rationale: {d.rationale}")

        if len(decisions) > 5:
            lines.append(f"  ... and {len(decisions) - 5} more (use retrieval API)")

        return "\n".join(lines)

    def _format_errors(self, errors: list[ErrorRecord]) -> str:
        if not errors:
            return "  (no errors encountered)"

        # Show unresolved errors first, then recent resolved
        unresolved = [e for e in errors if e.resolution == "unresolved"]
        resolved = [e for e in errors if e.resolution != "unresolved"][-3:]

        lines = []
        for e in unresolved:
            lines.append(f"  ⚠ UNRESOLVED: {e.error_type}: {e.error_message}")
        for e in resolved:
            lines.append(f"  ✓ {e.error_type}: {e.error_message} [{e.resolution}]")

        return "\n".join(lines) or "  (no errors encountered)"

    def _format_test_state(self, test_state: TestState | None) -> str:
        if not test_state:
            return ""

        return f"""### TDD State
- Phase: {test_state.phase}
- Failing tests: {', '.join(test_state.failing_tests) or 'none'}
- Expected failures (red phase): {', '.join(test_state.expected_failures) or 'none'}
"""

    def _format_reviewer_feedback(
        self,
        feedback: list[ReviewerFeedback] | None,
    ) -> str:
        if not feedback:
            return ""

        unaddressed = [f for f in feedback if not f.addressed]
        if not unaddressed:
            return ""

        lines = ["### Unaddressed Reviewer Feedback"]
        for f in unaddressed:
            lines.append(f"  From {f.reviewer_persona} ({f.severity}):")
            for c in f.comments[:3]:  # Limit to 3 comments
                lines.append(f"    - {c}")
            if len(f.comments) > 3:
                lines.append(f"    ... and {len(f.comments) - 3} more")

        return "\n".join(lines)
```

---

## API Endpoints

### REST API

```python
# Pause a running workflow
@router.post("/{workflow_id}/pause", response_model=ActionResponse)
async def pause_workflow(
    workflow_id: str,
    request: PauseRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> ActionResponse:
    """Pause a running workflow at the next task boundary.

    Args:
        workflow_id: Workflow to pause.
        request: Pause request with optional reason.

    Returns:
        ActionResponse with status and snapshot_id.
    """
    snapshot_id = await orchestrator.pause_workflow(
        workflow_id,
        reason=request.reason,
        trigger="pause",
    )
    return ActionResponse(
        status="paused",
        workflow_id=workflow_id,
        snapshot_id=snapshot_id,
    )


# Resume a paused workflow
@router.post("/{workflow_id}/resume", response_model=ActionResponse)
async def resume_workflow(
    workflow_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> ActionResponse:
    """Resume a paused workflow from its last snapshot.

    Args:
        workflow_id: Workflow to resume.

    Returns:
        ActionResponse with status.
    """
    await orchestrator.resume_workflow(workflow_id)
    return ActionResponse(
        status="resumed",
        workflow_id=workflow_id,
    )


# List snapshots for a workflow
@router.get("/{workflow_id}/snapshots", response_model=SnapshotListResponse)
async def list_snapshots(
    workflow_id: str,
    repository: WorkflowRepository = Depends(get_repository),
) -> SnapshotListResponse:
    """List all session snapshots for a workflow."""
    snapshots = await repository.list_snapshots(workflow_id)
    return SnapshotListResponse(
        workflow_id=workflow_id,
        snapshots=[
            SnapshotSummary(
                id=s.id,
                session_number=s.session_number,
                trigger=s.trigger,
                created_at=s.created_at,
                tasks_completed=s.tasks_completed,
                tasks_remaining=s.tasks_remaining,
            )
            for s in snapshots
        ],
    )


# Get detailed snapshot
@router.get("/{workflow_id}/snapshots/{snapshot_id}", response_model=SessionSnapshot)
async def get_snapshot(
    workflow_id: str,
    snapshot_id: str,
    repository: WorkflowRepository = Depends(get_repository),
) -> SessionSnapshot:
    """Get full session snapshot details."""
    snapshot = await repository.get_snapshot(snapshot_id)
    if not snapshot or snapshot.workflow_id != workflow_id:
        raise WorkflowNotFoundError(workflow_id)
    return snapshot


# Retrieval endpoints for detailed history
@router.get("/{workflow_id}/snapshots/{snapshot_id}/decisions")
async def get_decisions(
    workflow_id: str,
    snapshot_id: str,
    repository: WorkflowRepository = Depends(get_repository),
) -> list[Decision]:
    """Get all decisions from a snapshot."""
    snapshot = await repository.get_snapshot(snapshot_id)
    return snapshot.decisions if snapshot else []


@router.get("/{workflow_id}/snapshots/{snapshot_id}/errors")
async def get_errors(
    workflow_id: str,
    snapshot_id: str,
    repository: WorkflowRepository = Depends(get_repository),
) -> list[ErrorRecord]:
    """Get all errors from a snapshot."""
    snapshot = await repository.get_snapshot(snapshot_id)
    return snapshot.errors if snapshot else []
```

### Request/Response Models

```python
class PauseRequest(BaseModel):
    """Request to pause a workflow."""
    reason: str | None = Field(
        default=None,
        description="Human-readable reason for pausing"
    )


class ActionResponse(BaseModel):
    """Response for workflow actions."""
    status: str
    workflow_id: str
    snapshot_id: str | None = None


class SnapshotSummary(BaseModel):
    """Summary of a session snapshot."""
    id: str
    session_number: int
    trigger: str
    created_at: datetime
    tasks_completed: int
    tasks_remaining: int


class SnapshotListResponse(BaseModel):
    """Response for listing snapshots."""
    workflow_id: str
    snapshots: list[SnapshotSummary]
```

---

## CLI Commands

### Pause Command

```python
@app.command(name="pause")
def pause_command(
    workflow_id: str | None = typer.Option(
        None,
        "--workflow-id",
        "-w",
        help="Workflow ID to pause. If not provided, pauses workflow in current worktree.",
    ),
    reason: str | None = typer.Option(
        None,
        "--reason",
        "-r",
        help="Reason for pausing.",
    ),
) -> None:
    """Pause a running workflow at the next task boundary.

    The workflow will complete its current task before pausing.
    A snapshot is created for resuming later.
    """
    async def _run() -> None:
        client = AmeliaClient()

        # Resolve workflow ID from worktree if not provided
        if not workflow_id:
            worktree = Path.cwd()
            active = await client.get_active_workflow(str(worktree))
            if not active:
                typer.echo("No active workflow in current directory.", err=True)
                raise typer.Exit(1)
            wf_id = active.id
        else:
            wf_id = workflow_id

        typer.echo(f"Pausing workflow {wf_id}...")
        result = await client.pause_workflow(wf_id, reason=reason)

        typer.echo(f"✓ Workflow paused (snapshot: {result.snapshot_id})")
        typer.echo(f"  Resume with: amelia resume --workflow-id {wf_id}")

    asyncio.run(_run())
```

### Resume Command

```python
@app.command(name="resume")
def resume_command(
    workflow_id: str | None = typer.Option(
        None,
        "--workflow-id",
        "-w",
        help="Workflow ID to resume. If not provided, resumes workflow in current worktree.",
    ),
) -> None:
    """Resume a paused workflow from its last snapshot.

    The workflow continues from where it left off, with full context
    of what was accomplished in previous sessions.
    """
    async def _run() -> None:
        client = AmeliaClient()

        # Resolve workflow ID from worktree if not provided
        if not workflow_id:
            worktree = Path.cwd()
            paused = await client.get_paused_workflow(str(worktree))
            if not paused:
                typer.echo("No paused workflow in current directory.", err=True)
                raise typer.Exit(1)
            wf_id = paused.id
        else:
            wf_id = workflow_id

        # Show snapshot summary before resuming
        snapshots = await client.list_snapshots(wf_id)
        if snapshots:
            latest = snapshots[-1]
            typer.echo(f"Resuming from session {latest.session_number}:")
            typer.echo(f"  Paused: {latest.created_at}")
            typer.echo(f"  Tasks: {latest.tasks_completed} done, {latest.tasks_remaining} remaining")

        typer.echo(f"\nResuming workflow {wf_id}...")
        await client.resume_workflow(wf_id)

        typer.echo("✓ Workflow resumed")

    asyncio.run(_run())
```

---

## Dashboard Integration

### New Components

```
dashboard/src/components/workflow/
├── PauseButton.tsx          # Pause action button
├── ResumeButton.tsx         # Resume action button
├── SessionTimeline.tsx      # Visual timeline of sessions
├── SnapshotDetail.tsx       # Detailed snapshot view
└── PauseReasonDialog.tsx    # Dialog for entering pause reason
```

### PauseButton Component

```tsx
export function PauseButton({ workflowId, status }: PauseButtonProps) {
  const [isPausing, setIsPausing] = useState(false);
  const [showDialog, setShowDialog] = useState(false);

  const handlePause = async (reason?: string) => {
    setIsPausing(true);
    try {
      await api.post(`/workflows/${workflowId}/pause`, { reason });
      toast.success("Workflow paused");
    } catch (error) {
      toast.error("Failed to pause workflow");
    } finally {
      setIsPausing(false);
      setShowDialog(false);
    }
  };

  if (status !== "in_progress") return null;

  return (
    <>
      <Button
        variant="outline"
        onClick={() => setShowDialog(true)}
        disabled={isPausing}
      >
        {isPausing ? <Loader className="animate-spin" /> : <Pause />}
        Pause
      </Button>

      <PauseReasonDialog
        open={showDialog}
        onClose={() => setShowDialog(false)}
        onConfirm={handlePause}
      />
    </>
  );
}
```

### SessionTimeline Component

```tsx
export function SessionTimeline({ workflowId }: SessionTimelineProps) {
  const { data: snapshots } = useSnapshots(workflowId);

  return (
    <div className="space-y-2">
      <h3 className="font-medium">Session History</h3>
      <div className="relative border-l-2 border-muted pl-4 space-y-4">
        {snapshots?.map((snapshot, index) => (
          <div key={snapshot.id} className="relative">
            {/* Timeline dot */}
            <div className="absolute -left-[1.3rem] w-3 h-3 rounded-full bg-primary" />

            {/* Session card */}
            <Card className="p-3">
              <div className="flex justify-between items-start">
                <div>
                  <span className="font-medium">Session {snapshot.session_number}</span>
                  <p className="text-sm text-muted-foreground">
                    {formatDistanceToNow(snapshot.created_at)} ago
                  </p>
                </div>
                <Badge variant={snapshot.trigger === "pause" ? "secondary" : "outline"}>
                  {snapshot.trigger}
                </Badge>
              </div>
              <div className="mt-2 text-sm">
                <span className="text-green-600">✓ {snapshot.tasks_completed}</span>
                {" / "}
                <span>{snapshot.tasks_completed + snapshot.tasks_remaining} tasks</span>
              </div>
            </Card>
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

## Implementation Phases

### Phase 1: Core Infrastructure (Foundation)

- Add `paused` status to WorkflowStatus enum and transitions
- Create `session_snapshots` database table
- Add SessionSnapshot Pydantic model
- Implement SnapshotRepository with CRUD operations
- Add pause_workflow() skeleton to OrchestratorService

**Deliverables:**
- Database migration
- Core models
- Repository layer

### Phase 2: Pause Flow

- Implement task-boundary pause waiting logic
- Create SessionSnapshot from current workflow state
- Implement git state capture (branch, commits, modified files)
- Add DecisionExtractor with LLM extraction prompt
- Implement error extraction
- Wire up pause_workflow() in OrchestratorService
- Emit WORKFLOW_PAUSED events

**Deliverables:**
- Complete pause flow
- Decision/error extraction
- Snapshot creation

### Phase 3: Resume Flow

- Implement ResumeContextCompiler
- Create resume context template
- Add resume_workflow() to OrchestratorService
- Implement snapshot loading and state restoration
- Wire up LangGraph continuation from checkpoint
- Emit WORKFLOW_RESUMED events

**Deliverables:**
- Complete resume flow
- Context compilation
- Workflow continuation

### Phase 4: Driver Capacity Reporting

- Add UsageMetadata model
- Extend DriverInterface with capacity reporting
- Update ApiDriver to return usage metadata
- Update ClaudeCliDriver with estimation
- Implement capacity monitoring in OrchestratorService
- Add auto-pause on exhaustion threshold

**Deliverables:**
- Driver interface extension
- Capacity monitoring
- Auto-pause on exhaustion

### Phase 5: API & CLI

- Add REST endpoints (pause, resume, snapshots)
- Implement `amelia pause` command
- Implement `amelia resume` command
- Add snapshot listing to `amelia status`

**Deliverables:**
- REST API endpoints
- CLI commands

### Phase 6: Dashboard UI

- PauseButton component
- ResumeButton component
- PauseReasonDialog component
- SessionTimeline component
- SnapshotDetail view
- Integration with workflow detail page

**Deliverables:**
- Dashboard components
- Session history visualization

### Dependency Graph

```
Phase 1 ──────► Phase 2 ──────► Phase 3
(Infrastructure) (Pause)        (Resume)
                    │               │
                    └───────┬───────┘
                            ▼
                       Phase 4
                    (Capacity)
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
        Phase 5         Phase 6          Tests
        (API/CLI)      (Dashboard)     (E2E)
```

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/session_continuity/test_decision_extractor.py
- test_extract_decisions_from_messages
- test_extract_errors_from_messages
- test_handles_empty_messages
- test_handles_no_decisions

# tests/unit/session_continuity/test_resume_context_compiler.py
- test_compile_minimal_context
- test_compile_with_decisions
- test_compile_with_errors
- test_compile_with_test_state
- test_compile_with_reviewer_feedback

# tests/unit/session_continuity/test_snapshot.py
- test_create_snapshot_from_state
- test_serialize_snapshot_to_json
- test_deserialize_snapshot_from_json
```

### Integration Tests

```python
# tests/integration/session_continuity/test_pause_resume.py
- test_pause_workflow_creates_snapshot
- test_pause_waits_for_task_boundary
- test_resume_workflow_restores_state
- test_resume_continues_from_next_task
- test_multiple_pause_resume_cycles

# tests/integration/session_continuity/test_capacity_monitoring.py
- test_auto_pause_on_exhaustion
- test_capacity_warning_event
```

### E2E Tests

```python
# tests/e2e/session_continuity/test_full_flow.py
- test_dashboard_pause_resume_flow
- test_cli_pause_resume_flow
- test_resume_context_includes_decisions
- test_tdd_state_preserved_across_sessions
```

---

## Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Session boundary | Workflow execution | Aligns with existing workflow model |
| State storage | SQLite (server-side) | Consistent with existing architecture |
| Pause granularity | Task boundaries only | Simpler state, cleaner handoffs |
| Decision capture | LLM extraction | Automatic, no manual annotation needed |
| Resume context | Summary + retrieval | Balance between context size and completeness |
| Capacity detection | Driver metadata | Non-invasive, aligns with API patterns |
| CLI/Dashboard parity | Identical endpoints | Consistent UX, simpler maintenance |
| Mergeable guarantee | Flexible with warning | Supports TDD red phase, pragmatic |
| Snapshot storage | JSON blob in SQLite | Self-contained, easy to query |
| Test state tracking | Explicit TDD model | Enables intelligent resume mid-cycle |

---

## Future Enhancements

### Not in Initial Scope

1. **Cross-workflow learning** - Extract patterns from completed workflows
2. **Predictive pausing** - ML-based prediction of exhaustion
3. **Partial resume** - Resume from specific snapshot, not just latest
4. **Snapshot comparison** - Diff between sessions
5. **Notification integrations** - Slack/Discord on pause/resume

### Depends on Other Phases

1. **Chat integration (Phase 9)** - Resume from Slack/Discord
2. **Continuous improvement (Phase 10)** - Learn from session patterns
3. **Cloud deployment (Phase 15)** - Distributed session management

---

## References

- [Roadmap - Phase 3](../roadmap.md#phase-3-session-continuity-planned)
- [Context Engineering Gaps](../analysis/context-engineering-gaps.md)
- [12-Factor Agents Compliance](../analysis/12-factor-agents-compliance.md)
- [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
