# Web Dashboard Design

**Date:** 2025-12-01
**Status:** Ready for Review
**Issue:** #4 - Web UI

## Overview

This document describes the design for Amelia's web dashboard - a real-time observability and control interface for the agentic orchestrator. The dashboard achieves feature parity with the CLI, allowing users to start workflows, approve plans, and monitor agent activity from the browser.

## Goals

- Real-time workflow monitoring with live activity log
- Full control: start workflows, approve/reject plans, cancel runs
- Feature parity between CLI and browser interfaces
- **Multi-workflow support**: one concurrent workflow per git worktree
- Foundation for future platform integrations (Telegram, Slack)

## Non-Goals (MVP)

- Time estimates (show "--:--" until historical data available)
- Platform integrations (Telegram/Slack) - deferred to Phase 2.4
- Views beyond "Active Jobs" (show "Coming soon" placeholders)
- Cross-worktree file operations (each workflow isolated to its worktree)

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          User's Machine                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐                            ┌──────────────────┐   │
│  │   Browser    │◄────── WebSocket ────────► │                  │   │
│  │  (Vite/React)│        /ws/events          │  FastAPI Server  │   │
│  └──────────────┘                            │                  │   │
│                                              │  - Orchestrator  │   │
│  ┌──────────────┐                            │  - REST API      │   │
│  │  Amelia CLI  │◄──────── REST ───────────► │  - WebSocket     │   │
│  │ (thin client)│        /api/*              │  - Event Bus     │   │
│  └──────────────┘                            └────────┬─────────┘   │
│                                                       │             │
│                                                       ▼             │
│                                              ┌──────────────────┐   │
│                                              │   amelia.db      │   │
│                                              │    (SQLite)      │   │
│                                              └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Architectural Decision: Server-Centric

The FastAPI server owns the LangGraph orchestrator. Both browser and CLI are clients calling the same REST API. This enables:

- True feature parity between interfaces
- Single source of truth for workflow state
- Foundation for future platform adapters (Telegram, Slack)
- Clean separation of concerns

### Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| **FastAPI Server** | Python, FastAPI, SQLAlchemy | Runs orchestrator, REST API, WebSocket |
| **React Dashboard** | Vite, React, TypeScript, React Flow | Real-time UI for monitoring and control |
| **CLI Client** | Python, Typer, httpx | Thin client calling server APIs |
| **Database** | SQLite | Persists workflows, events, token usage |
| **Event Bus** | Python asyncio | Pub/sub for real-time WebSocket broadcast |
| **SDK Driver** | Claude Agent SDK | LLM execution with native token tracking |

### Concurrency Model

**One workflow per git worktree.** This constraint provides natural isolation:

- Each worktree is an independent working directory (no file conflicts)
- Users can run `amelia start ISSUE-123` in one worktree while `ISSUE-456` runs in another
- The main repository (non-worktree) is treated as the default worktree
- Server tracks active workflows by `worktree_path` to enforce the constraint

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Git Repository                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │   Main Worktree  │  │  Worktree: feat-A │  │  Worktree: feat-B │   │
│  │   ~/project      │  │  ~/project-feat-a │  │  ~/project-feat-b │   │
│  │                  │  │                   │  │                   │   │
│  │  Workflow: #101  │  │  Workflow: #102   │  │  (no workflow)    │   │
│  │  Status: running │  │  Status: blocked  │  │                   │   │
│  └────────┬─────────┘  └────────┬──────────┘  └───────────────────┘   │
│           │                     │                                     │
│           └──────────┬──────────┘                                     │
│                      ▼                                                │
│           ┌─────────────────────┐                                     │
│           │   FastAPI Server    │                                     │
│           │  (manages all)      │                                     │
│           └─────────────────────┘                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Conflict handling:**
- `POST /workflows` with a `worktree_path` that has an active workflow returns `409 Conflict`
- CLI auto-detects worktree from current directory via `git rev-parse --show-toplevel`
- Dashboard shows all active workflows; user selects which to view

**Concurrency limits:**
- Default: 5 concurrent workflows maximum (configurable via `AMELIA_MAX_CONCURRENT`)
- Beyond limit: immediately returns `429 Too Many Requests` with `Retry-After: 30` header
- No queuing - keeps implementation simple; client can retry

### Event Sourcing Lite

Events are the authoritative source of truth for workflow history. While we persist denormalized state for fast queries, the event log enables full workflow replay and debugging.

**Architecture:**

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Orchestrator  │────►│   Event Store   │────►│  State Cache    │
│   (produces)    │     │   (immutable)   │     │  (derived)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │   Event Bus     │────► WebSocket clients
                        │   (broadcast)   │
                        └─────────────────┘
```

**Key principles:**
- Events are immutable and append-only
- State is derived from events via projection
- State cache (`workflows.state_json`) is an optimization, not the source of truth
- Full workflow replay possible from event log

**Event projection:**

```python
class WorkflowProjection:
    """Reconstructs workflow state from events.

    Event Type Coverage:
    - State-affecting events (handled): WORKFLOW_STARTED, WORKFLOW_COMPLETED,
      WORKFLOW_FAILED, WORKFLOW_CANCELLED, STAGE_STARTED, STAGE_COMPLETED,
      APPROVAL_REQUIRED, APPROVAL_GRANTED, APPROVAL_REJECTED
    - Informational events (logged only, no state change): FILE_CREATED,
      FILE_MODIFIED, FILE_DELETED, REVIEW_REQUESTED, REVIEW_COMPLETED,
      REVISION_REQUESTED, SYSTEM_ERROR, SYSTEM_WARNING

    Informational events are stored for audit/debugging but don't affect
    the ExecutionState projection. They appear in the activity log only.
    """

    def project(self, events: list[WorkflowEvent]) -> ExecutionState:
        """Derive current state from event sequence."""
        state = ExecutionState(
            id=events[0].workflow_id,
            workflow_status="pending",
        )

        for event in sorted(events, key=lambda e: e.sequence):
            state = self._apply_event(state, event)

        return state

    def _apply_event(self, state: ExecutionState, event: WorkflowEvent) -> ExecutionState:
        """Apply single event to state."""
        match event.event_type:
            case EventType.WORKFLOW_STARTED:
                return state.model_copy(update={
                    "workflow_status": "in_progress",
                    "started_at": event.timestamp,
                })

            case EventType.STAGE_STARTED:
                return state.model_copy(update={
                    "current_stage": event.data.get("stage"),
                    "stage_timestamps": {
                        **state.stage_timestamps,
                        event.data.get("stage"): event.timestamp,
                    },
                })

            case EventType.STAGE_COMPLETED:
                # Stage completion is informational - current_stage cleared on next STAGE_STARTED
                return state

            case EventType.APPROVAL_REQUIRED:
                return state.model_copy(update={
                    "workflow_status": "blocked",
                })

            case EventType.APPROVAL_GRANTED:
                return state.model_copy(update={
                    "workflow_status": "in_progress",
                })

            case EventType.APPROVAL_REJECTED:
                return state.model_copy(update={
                    "workflow_status": "failed",
                    "completed_at": event.timestamp,
                    "failure_reason": event.message,
                })

            case EventType.WORKFLOW_COMPLETED:
                return state.model_copy(update={
                    "workflow_status": "completed",
                    "completed_at": event.timestamp,
                })

            case EventType.WORKFLOW_FAILED:
                return state.model_copy(update={
                    "workflow_status": "failed",
                    "completed_at": event.timestamp,
                    "failure_reason": event.message,
                })

            case EventType.WORKFLOW_CANCELLED:
                return state.model_copy(update={
                    "workflow_status": "cancelled",
                    "completed_at": event.timestamp,
                })

            case _:
                return state  # Unknown events don't affect state


class WorkflowRepository:
    """Repository with event sourcing support."""

    def __init__(self, db: Database, projection: WorkflowProjection):
        self._db = db
        self._projection = projection

    async def get(self, workflow_id: str) -> ExecutionState | None:
        """Get workflow state (from cache or projection)."""
        # Try cached state first
        cached = await self._db.fetch_one(
            "SELECT state_json FROM workflows WHERE id = ?",
            (workflow_id,)
        )
        if cached:
            return ExecutionState.model_validate_json(cached["state_json"])

        # Fallback to projection from events
        events = await self.get_events(workflow_id)
        if not events:
            return None
        return self._projection.project(events)

    async def rebuild_state(self, workflow_id: str) -> ExecutionState:
        """Force rebuild state from events (for debugging/recovery)."""
        events = await self.get_events(workflow_id)
        if not events:
            raise ValueError(f"No events found for workflow {workflow_id}")

        state = self._projection.project(events)

        # Update cache
        await self._db.execute(
            "UPDATE workflows SET state_json = ? WHERE id = ?",
            (state.model_dump_json(), workflow_id)
        )

        return state
```

**Benefits:**
- **Debugging**: Replay any workflow to understand what happened
- **Recovery**: Rebuild corrupted state from events
- **Auditing**: Full history of all workflow actions
- **Time travel**: View workflow state at any point in history

**Trade-offs:**
- Slightly more complex than pure CRUD
- State cache must be kept in sync (dual write)
- Event schema evolution requires migration strategy

---

## Data Models

### New Models

```python
class EventType(str, Enum):
    """Exhaustive list of workflow event types."""
    # Lifecycle
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"

    # Stages
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"

    # Approval
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"

    # Artifacts
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"

    # Review cycle
    REVIEW_REQUESTED = "review_requested"
    REVIEW_COMPLETED = "review_completed"
    REVISION_REQUESTED = "revision_requested"

    # System
    SYSTEM_ERROR = "system_error"
    SYSTEM_WARNING = "system_warning"


class WorkflowEvent(BaseModel):
    """Event for activity log and real-time updates."""
    id: str                          # UUID
    workflow_id: str                 # Links to ExecutionState
    sequence: int                    # Monotonic counter per workflow (ensures ordering)
    timestamp: datetime              # When event occurred
    agent: str                       # "architect", "developer", "reviewer", "system"
    event_type: EventType            # Typed event category
    message: str                     # Human-readable summary
    data: dict | None = None         # Structured payload (file paths, error details, etc.)
    correlation_id: str | None = None  # Links related events (e.g., approval request → granted)


class TokenUsage(BaseModel):
    """Token consumption tracking per agent.

    Cache token semantics:
    - input_tokens: Total tokens processed (includes cache_read_tokens)
    - cache_read_tokens: Subset of input_tokens served from prompt cache (cheaper)
    - cache_creation_tokens: Tokens written to cache (billed at higher rate)
    - cost_usd: Calculated as input_cost + output_cost - cache_discount
    """
    workflow_id: str
    agent: str
    model: str = "claude-sonnet-4-20250514"  # Model used for cost calculation
    input_tokens: int                # Total input (includes cache reads)
    output_tokens: int
    cache_read_tokens: int = 0       # Subset of input_tokens from cache (discounted)
    cache_creation_tokens: int = 0   # Tokens written to cache (premium rate)
    cost_usd: float | None = None    # Net cost after cache adjustments
    timestamp: datetime


# Pricing per million tokens (as of 2025)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-20250514": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.5,      # 90% discount on cached input
        "cache_write": 18.75,   # 25% premium on cache creation
    },
    "claude-sonnet-4-20250514": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    },
}


def calculate_token_cost(usage: TokenUsage) -> float:
    """Calculate USD cost for token usage with cache adjustments.

    Args:
        usage: Token usage record with model and token counts.

    Returns:
        Total cost in USD.

    Formula:
        cost = (base_input * input_rate) + (cache_read * cache_read_rate)
             + (cache_write * cache_write_rate) + (output * output_rate)

    Where base_input = input_tokens - cache_read_tokens (non-cached input).
    """
    # Default to sonnet pricing if model unknown
    rates = MODEL_PRICING.get(usage.model, MODEL_PRICING["claude-sonnet-4-20250514"])

    # Cache reads are already included in input_tokens, so subtract them
    base_input_tokens = usage.input_tokens - usage.cache_read_tokens

    cost = (
        (base_input_tokens * rates["input"] / 1_000_000) +
        (usage.cache_read_tokens * rates["cache_read"] / 1_000_000) +
        (usage.cache_creation_tokens * rates["cache_write"] / 1_000_000) +
        (usage.output_tokens * rates["output"] / 1_000_000)
    )

    return round(cost, 6)  # Round to micro-dollars
```

### Extended ExecutionState

```python
class ExecutionState(BaseModel):
    # ... existing fields ...
    id: str                                    # NEW: UUID for persistence
    started_at: datetime | None                # NEW: Workflow start time
    completed_at: datetime | None              # NEW: Workflow end time
    stage_timestamps: dict[str, datetime]      # NEW: When each stage started
    workflow_status: WorkflowStatus            # UPDATED: Added "blocked", "cancelled"
    failure_reason: str | None = None          # NEW: Error message when status is "failed"

    # Worktree context
    worktree_path: str                         # NEW: Absolute path to worktree root
    worktree_name: str                         # NEW: Human-readable (branch name or directory)


WorkflowStatus = Literal["pending", "in_progress", "blocked", "completed", "failed", "cancelled"]
# "blocked" = awaiting human approval
# "cancelled" = explicitly cancelled by user (distinct from "failed")


# State machine validation - prevents invalid transitions
VALID_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    "pending": {"in_progress", "cancelled"},
    "in_progress": {"blocked", "completed", "failed", "cancelled"},
    "blocked": {"in_progress", "failed", "cancelled"},
    "completed": set(),   # Terminal state
    "failed": set(),      # Terminal state
    "cancelled": set(),   # Terminal state
}


class InvalidStateTransitionError(ValueError):
    """Raised when attempting an invalid workflow state transition."""
    def __init__(self, current: WorkflowStatus, target: WorkflowStatus):
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition from '{current}' to '{target}'")


def validate_transition(current: WorkflowStatus, target: WorkflowStatus) -> None:
    """Validate that a state transition is allowed.

    Args:
        current: The current workflow status.
        target: The desired new status.

    Raises:
        InvalidStateTransitionError: If the transition is not allowed.
    """
    if target not in VALID_TRANSITIONS[current]:
        raise InvalidStateTransitionError(current, target)


# Usage in repository
class WorkflowRepository:
    async def set_status(
        self,
        workflow_id: str,
        new_status: WorkflowStatus,
        failure_reason: str | None = None,
    ) -> None:
        """Update workflow status with state machine validation."""
        workflow = await self.get(workflow_id)
        if not workflow:
            raise WorkflowNotFoundError(workflow_id)

        validate_transition(workflow.workflow_status, new_status)

        await self._db.execute(
            "UPDATE workflows SET status = ?, failure_reason = ? WHERE id = ?",
            (new_status, failure_reason, workflow_id)
        )
```

### Database Tables

| Table | Purpose |
|-------|---------|
| `workflows` | ExecutionState records (JSON blob + indexed fields) |
| `events` | WorkflowEvent records for activity log |
| `token_usage` | Token counts per agent per workflow |

#### Schema Details

```sql
-- Workflows table with indexed columns for common queries
CREATE TABLE workflows (
    id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    worktree_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    failure_reason TEXT,
    state_json TEXT NOT NULL          -- Full ExecutionState as JSON
);

-- Indexes for efficient querying
CREATE INDEX idx_workflows_issue_id ON workflows(issue_id);
CREATE INDEX idx_workflows_status ON workflows(status);
CREATE INDEX idx_workflows_worktree ON workflows(worktree_path);
CREATE INDEX idx_workflows_started_at ON workflows(started_at DESC);

-- Unique constraint: one active workflow per worktree
CREATE UNIQUE INDEX idx_workflows_active_worktree
    ON workflows(worktree_path)
    WHERE status IN ('pending', 'in_progress', 'blocked');

-- Events table with monotonic sequence for ordering
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id),
    sequence INTEGER NOT NULL,        -- Monotonic counter per workflow
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    agent TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    data_json TEXT                    -- Optional structured payload
);

-- Unique constraint ensures no duplicate sequences per workflow
CREATE UNIQUE INDEX idx_events_workflow_sequence ON events(workflow_id, sequence);
CREATE INDEX idx_events_workflow ON events(workflow_id, timestamp);

-- Token usage table
CREATE TABLE token_usage (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id),
    agent TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cost_usd REAL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tokens_workflow ON token_usage(workflow_id);

-- Health check table (for write capability verification)
CREATE TABLE health_check (
    id TEXT PRIMARY KEY,
    checked_at TIMESTAMP NOT NULL
);
```

**SQLite configuration:**
- WAL mode enabled for concurrent read/write
- Foreign keys enforced
- Journal size limit: 64MB
- Transaction isolation: `IMMEDIATE` to prevent write-write conflicts
- Busy timeout: 5 seconds for lock retry

```python
# Database connection configuration
async def get_connection() -> aiosqlite.Connection:
    """Get database connection with optimized settings."""
    conn = await aiosqlite.connect(
        db_path,
        isolation_level="IMMEDIATE",  # Prevent write-write conflicts
    )
    await conn.execute("PRAGMA busy_timeout = 5000")  # 5s retry on locks
    await conn.execute("PRAGMA journal_mode = WAL")
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute("PRAGMA journal_size_limit = 67108864")  # 64MB
    return conn
```

### Log Retention

Event logs grow unbounded without retention policy. Cleanup runs on server shutdown to ensure database size stays manageable without impacting runtime performance.

**Configuration:**

```python
# amelia/server/config.py
from pydantic_settings import BaseSettings

class ServerConfig(BaseSettings):
    """Server configuration with environment variable support."""

    # Log retention settings
    log_retention_days: int = 30              # Keep events for 30 days
    log_retention_max_events: int = 100_000   # Max events per workflow

    # Timeout settings
    request_timeout_seconds: float = 30.0           # HTTP request timeout
    websocket_idle_timeout_seconds: float = 300.0   # WebSocket idle timeout (5 min)
    workflow_start_timeout_seconds: float = 60.0    # Max time to start a workflow

    # Can be overridden via environment variables
    # AMELIA_LOG_RETENTION_DAYS=90
    # AMELIA_LOG_RETENTION_MAX_EVENTS=50000
    # AMELIA_REQUEST_TIMEOUT_SECONDS=60
    # AMELIA_WEBSOCKET_IDLE_TIMEOUT_SECONDS=600

    class Config:
        env_prefix = "AMELIA_"
```

**Retention service (shutdown-only):**

```python
class LogRetentionService:
    """Manages event log cleanup on server shutdown.

    Cleanup runs only during graceful shutdown to:
    - Avoid runtime performance impact
    - Ensure cleanup completes before server exits
    - Keep implementation simple (no background tasks)
    """

    def __init__(
        self,
        db: Database,
        config: ServerConfig,
    ):
        self._db = db
        self._config = config

    async def cleanup_on_shutdown(self) -> CleanupResult:
        """Execute retention policy cleanup during server shutdown.

        Called by ServerLifecycle.shutdown() before closing connections.

        Returns:
            CleanupResult with counts of deleted events and workflows.
        """
        logger.info(
            "Running log retention cleanup",
            retention_days=self._config.log_retention_days,
            max_events=self._config.log_retention_max_events,
        )

        cutoff_date = datetime.utcnow() - timedelta(
            days=self._config.log_retention_days
        )

        # Delete old events from completed/failed/cancelled workflows
        events_deleted = await self._db.execute(
            """
            DELETE FROM events
            WHERE workflow_id IN (
                SELECT id FROM workflows
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_at < ?
            )
            """,
            (cutoff_date,)
        )

        # Delete old workflow records
        workflows_deleted = await self._db.execute(
            """
            DELETE FROM workflows
            WHERE status IN ('completed', 'failed', 'cancelled')
            AND completed_at < ?
            """,
            (cutoff_date,)
        )

        # Trim events per workflow if exceeding max
        await self._trim_excess_events()

        # Vacuum to reclaim space (always run on shutdown)
        await self._db.execute("VACUUM")

        result = CleanupResult(
            events_deleted=events_deleted,
            workflows_deleted=workflows_deleted,
            cutoff_date=cutoff_date,
        )

        logger.info(
            "Log cleanup completed",
            events_deleted=events_deleted,
            workflows_deleted=workflows_deleted,
        )

        return result

    async def _trim_excess_events(self) -> int:
        """Delete oldest events if workflow exceeds max_events limit."""
        # Find workflows with too many events
        over_limit = await self._db.fetch_all(
            """
            SELECT workflow_id, COUNT(*) as event_count
            FROM events
            GROUP BY workflow_id
            HAVING event_count > ?
            """,
            (self._config.log_retention_max_events,)
        )

        total_deleted = 0
        for row in over_limit:
            workflow_id = row["workflow_id"]
            excess = row["event_count"] - self._config.log_retention_max_events

            # Delete oldest events (lowest sequence numbers)
            deleted = await self._db.execute(
                """
                DELETE FROM events
                WHERE id IN (
                    SELECT id FROM events
                    WHERE workflow_id = ?
                    ORDER BY sequence ASC
                    LIMIT ?
                )
                """,
                (workflow_id, excess)
            )
            total_deleted += deleted

        return total_deleted


@dataclass
class CleanupResult:
    events_deleted: int
    workflows_deleted: int
    cutoff_date: datetime
```

**CLI command for manual cleanup:**

```bash
# Run cleanup manually (useful if server was killed without graceful shutdown)
amelia server cleanup

# Run with custom retention
amelia server cleanup --retention-days 7

# Dry run to see what would be deleted
amelia server cleanup --dry-run
```

### Database Migrations

Simple sequential migration strategy (no Alembic - overkill for local SQLite):

```
amelia/server/database/
├── migrations/
│   ├── 001_initial_schema.sql
│   ├── 002_add_event_sequence.sql
│   └── ...
├── migrate.py
└── schema_version.py
```

**Migration runner:**
```python
class MigrationRunner:
    """Sequential SQL migration runner for SQLite."""

    MIGRATIONS_DIR = Path(__file__).parent / "migrations"
    VERSION_TABLE = "schema_version"

    def __init__(self, db_path: Path):
        self._db_path = db_path

    async def run_migrations(self) -> int:
        """Run pending migrations. Returns number applied."""
        await self._ensure_version_table()
        current = await self._get_current_version()
        migrations = self._get_pending_migrations(current)

        applied = 0
        for version, sql_file in migrations:
            logger.info(f"Applying migration {version}: {sql_file.name}")
            sql = sql_file.read_text()
            await self._execute_migration(version, sql)
            applied += 1

        return applied

    async def _ensure_version_table(self) -> None:
        """Create schema_version table if not exists."""
        await self._execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    async def _get_current_version(self) -> int:
        """Get current schema version (0 if none)."""
        result = await self._fetch_one(
            "SELECT MAX(version) FROM schema_version"
        )
        return result[0] or 0

    def _get_pending_migrations(self, current: int) -> list[tuple[int, Path]]:
        """Get migrations with version > current, sorted by version."""
        migrations = []
        for sql_file in self.MIGRATIONS_DIR.glob("*.sql"):
            # Extract version from filename: 001_initial_schema.sql -> 1
            version = int(sql_file.stem.split("_")[0])
            if version > current:
                migrations.append((version, sql_file))
        return sorted(migrations, key=lambda x: x[0])

    async def _execute_migration(self, version: int, sql: str) -> None:
        """Execute migration in transaction and record version."""
        async with self._transaction():
            await self._execute(sql)
            await self._execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (version,)
            )
```

**Usage on server startup:**
```python
async def startup():
    runner = MigrationRunner(db_path)
    applied = await runner.run_migrations()
    if applied:
        logger.info(f"Applied {applied} database migrations")
```

**Migration file format:**
```sql
-- migrations/002_add_event_sequence.sql
-- Add sequence column to events table

ALTER TABLE events ADD COLUMN sequence INTEGER;

-- Backfill existing events with sequence numbers
UPDATE events SET sequence = (
    SELECT COUNT(*) FROM events e2
    WHERE e2.workflow_id = events.workflow_id
    AND e2.timestamp <= events.timestamp
);

-- Make sequence NOT NULL after backfill
-- (SQLite doesn't support ALTER COLUMN, so we recreate)
CREATE TABLE events_new (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES workflows(id),
    sequence INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    agent TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    data_json TEXT
);

INSERT INTO events_new SELECT * FROM events;
DROP TABLE events;
ALTER TABLE events_new RENAME TO events;

CREATE UNIQUE INDEX idx_events_workflow_sequence ON events(workflow_id, sequence);
CREATE INDEX idx_events_workflow ON events(workflow_id, timestamp);
```

---

## REST API

**Base URL:** `http://localhost:8420/api`

### Workflow Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/workflows` | Start new workflow |
| `GET` | `/workflows` | List all workflows (with filters) |
| `GET` | `/workflows/active` | Get all active workflows (one per worktree) |
| `GET` | `/workflows/{id}` | Get workflow details + plan |
| `POST` | `/workflows/{id}/approve` | Approve plan (unblocks workflow) |
| `POST` | `/workflows/{id}/reject` | Reject plan with feedback |
| `POST` | `/workflows/{id}/cancel` | Cancel running workflow |

### Event Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/workflows/{id}/events` | Get events (activity log) |
| `GET` | `/workflows/{id}/tokens` | Get token usage breakdown |

### Health & Observability Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Server health check with metrics |
| `GET` | `/health/live` | Kubernetes liveness probe (minimal) |
| `GET` | `/health/ready` | Kubernetes readiness probe |

```python
import psutil
from datetime import datetime

start_time = datetime.utcnow()


async def check_database_health(db: Database) -> dict:
    """Verify database read and write capability.

    Performs a lightweight write/read cycle to ensure the database
    is fully operational, not just connected.
    """
    try:
        # Test write capability
        test_id = str(uuid4())
        await db.execute(
            "INSERT INTO health_check (id, checked_at) VALUES (?, ?)",
            (test_id, datetime.utcnow())
        )
        # Cleanup test row
        await db.execute("DELETE FROM health_check WHERE id = ?", (test_id,))
        # Test read capability
        await db.fetch_one("SELECT 1")
        return {"status": "healthy", "mode": "wal"}
    except Exception as e:
        logger.warning("Database health check failed", error=str(e))
        return {"status": "degraded", "error": str(e)}


@router.get("/health")
async def health(
    orchestrator: OrchestratorService = Depends(get_orchestrator),
    connection_manager: ConnectionManager = Depends(get_connection_manager),
    db: Database = Depends(get_database),
) -> dict:
    """Detailed health check with server metrics."""
    process = psutil.Process()
    db_health = await check_database_health(db)

    # Overall status is degraded if database is unhealthy
    overall_status = "healthy" if db_health["status"] == "healthy" else "degraded"

    return {
        "status": overall_status,
        "version": __version__,
        "uptime_seconds": (datetime.utcnow() - start_time).total_seconds(),
        "active_workflows": len(orchestrator.get_active_workflows()),
        "websocket_connections": len(connection_manager.active_connections),
        "memory_mb": process.memory_info().rss / 1024 / 1024,
        "cpu_percent": process.cpu_percent(),
        "database": {
            **db_health,
            "path": str(db_path),
        },
    }


@router.get("/health/live")
async def liveness() -> dict:
    """Minimal liveness check - is the server responding?"""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(
    lifecycle: ServerLifecycle = Depends(get_lifecycle),
) -> Response:
    """Readiness check - is the server ready to accept requests?"""
    if lifecycle.is_shutting_down:
        return JSONResponse(
            status_code=503,
            content={"status": "shutting_down"}
        )
    return JSONResponse(content={"status": "ready"})
```

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `WS /ws/events` | Real-time event stream, broadcasts all WorkflowEvents |
| `WS /ws/events?since={event_id}` | Reconnect with backfill from last seen event |

### Request/Response Schemas

```python
# POST /workflows
class CreateWorkflowRequest(BaseModel):
    issue_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r'^[A-Za-z0-9_-]+$',
        description="Issue identifier (alphanumeric, underscores, hyphens only)"
    )
    worktree_path: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Absolute path to git worktree root"
    )
    worktree_name: str | None = Field(
        default=None,
        max_length=255,
        description="Human-readable worktree name (derived from path if not provided)"
    )
    profile: str | None = Field(
        default=None,
        max_length=64,
        pattern=r'^[a-z0-9_-]+$',
        description="Profile name for configuration"
    )
    driver: str | None = Field(
        default=None,
        pattern=r'^(sdk|api|cli):[a-z0-9_-]+$',
        description="Driver specification (e.g., 'sdk:claude', 'api:openai')"
    )

    @field_validator('issue_id')
    @classmethod
    def validate_issue_id(cls, v: str) -> str:
        """Prevent path traversal and injection in issue_id."""
        dangerous_chars = ['/', '\\', '..', '\0', '\n', '\r', "'", '"', '`', '$', '|', ';', '&']
        for char in dangerous_chars:
            if char in v:
                raise ValueError(f'Invalid character in issue_id: {repr(char)}')
        return v

    @field_validator('worktree_path')
    @classmethod
    def validate_worktree_path(cls, v: str) -> str:
        """Validate worktree path is absolute and safe."""
        path = Path(v)

        # Must be absolute
        if not path.is_absolute():
            raise ValueError('Worktree path must be absolute')

        # Resolve to canonical form (removes .., symlinks)
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError) as e:
            raise ValueError(f'Invalid path: {e}')

        # Check for null bytes (path traversal attack)
        if '\0' in v:
            raise ValueError('Invalid null byte in path')

        return str(resolved)

class CreateWorkflowResponse(BaseModel):
    id: str
    status: WorkflowStatus
    message: str


# GET /workflows?status=...&worktree=...&limit=...&cursor=...
class WorkflowListResponse(BaseModel):
    workflows: list[WorkflowSummary]
    total: int
    cursor: str | None = None       # Opaque cursor for next page (base64 encoded)
    has_more: bool = False          # True if more results available

class WorkflowSummary(BaseModel):
    id: str
    issue_id: str
    worktree_name: str
    status: WorkflowStatus
    started_at: datetime | None
    current_stage: str | None


# Pagination implementation
@router.get("/workflows")
async def list_workflows(
    status: WorkflowStatus | None = None,
    worktree: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    repository: WorkflowRepository = Depends(get_repository),
) -> WorkflowListResponse:
    """List workflows with cursor-based pagination.

    Cursor encodes (started_at, id) for stable pagination even when
    new workflows are created during iteration.
    """
    # Decode cursor if provided
    after_started_at: datetime | None = None
    after_id: str | None = None
    if cursor:
        try:
            decoded = base64.b64decode(cursor).decode()
            after_started_at_str, after_id = decoded.split("|", 1)
            after_started_at = datetime.fromisoformat(after_started_at_str)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, "Invalid cursor format")

    # Fetch one extra to detect has_more
    workflows = await repository.list_workflows(
        status=status,
        worktree_path=worktree,
        limit=limit + 1,
        after_started_at=after_started_at,
        after_id=after_id,
    )

    has_more = len(workflows) > limit
    if has_more:
        workflows = workflows[:limit]

    # Build next cursor from last item
    next_cursor: str | None = None
    if has_more and workflows:
        last = workflows[-1]
        cursor_data = f"{last.started_at.isoformat()}|{last.id}"
        next_cursor = base64.b64encode(cursor_data.encode()).decode()

    total = await repository.count_workflows(status=status, worktree_path=worktree)

    return WorkflowListResponse(
        workflows=[WorkflowSummary.from_orm(w) for w in workflows],
        total=total,
        cursor=next_cursor,
        has_more=has_more,
    )


# GET /workflows/{id}
class WorkflowDetailResponse(BaseModel):
    id: str
    issue_id: str
    worktree_path: str
    worktree_name: str
    status: WorkflowStatus
    started_at: datetime | None
    completed_at: datetime | None
    failure_reason: str | None
    current_stage: str | None
    plan: TaskDAG | None              # Full plan when available (from amelia.core.types)
    token_usage: dict[str, TokenSummary]  # agent -> totals
    recent_events: list[WorkflowEvent]    # Last 50 events

class TokenSummary(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None


# POST /workflows/{id}/reject
class RejectRequest(BaseModel):
    feedback: str                     # Reason for rejection


# Error responses
class ErrorResponse(BaseModel):
    error: str
    code: str                         # Machine-readable: "WORKFLOW_CONFLICT", "NOT_FOUND", etc.
    details: dict | None = None


# Correlation ID for request tracing
# All mutating endpoints accept X-Correlation-ID header for debugging
@router.post("/workflows/{id}/approve")
async def approve_workflow(
    id: str,
    x_correlation_id: str | None = Header(default=None),
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> dict:
    """Approve a blocked workflow's plan.

    The correlation_id flows through to emitted events, enabling
    end-to-end tracing from UI action → API → event → WebSocket.
    """
    correlation_id = x_correlation_id or str(uuid4())
    success = await orchestrator.approve_workflow(id, correlation_id=correlation_id)
    if not success:
        raise HTTPException(422, detail="Workflow not awaiting approval")
    return {"status": "approved", "correlation_id": correlation_id}
```

### WebSocket Protocol

```python
# Client -> Server: Subscribe to specific workflow (optional)
{"type": "subscribe", "workflow_id": "uuid"}

# Client -> Server: Unsubscribe from workflow
{"type": "unsubscribe", "workflow_id": "uuid"}

# Client -> Server: Subscribe to all workflows
{"type": "subscribe_all"}

# Client -> Server: Heartbeat response
{"type": "pong"}

# Server -> Client: Event broadcast
{
    "type": "event",
    "payload": WorkflowEvent
}

# Server -> Client: Heartbeat
{"type": "ping"}

# Server -> Client: Backfill complete (after reconnect with ?since=)
{"type": "backfill_complete", "count": 15}
```

**Connection Manager with Subscription Filtering:**

```python
class ConnectionManager:
    """Manages WebSocket connections with subscription-based filtering."""

    def __init__(self):
        self._connections: dict[WebSocket, set[str]] = {}  # socket -> workflow_ids
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[websocket] = set()  # Empty = subscribed to all

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(websocket, None)

    async def subscribe(self, websocket: WebSocket, workflow_id: str) -> None:
        """Subscribe connection to specific workflow events."""
        async with self._lock:
            if websocket in self._connections:
                self._connections[websocket].add(workflow_id)

    async def unsubscribe(self, websocket: WebSocket, workflow_id: str) -> None:
        """Unsubscribe connection from specific workflow events."""
        async with self._lock:
            if websocket in self._connections:
                self._connections[websocket].discard(workflow_id)

    async def subscribe_all(self, websocket: WebSocket) -> None:
        """Subscribe connection to all workflow events."""
        async with self._lock:
            if websocket in self._connections:
                self._connections[websocket] = set()  # Empty = all

    async def broadcast(self, event: WorkflowEvent) -> None:
        """Broadcast event to subscribed connections only."""
        async with self._lock:
            for ws, subscribed_ids in list(self._connections.items()):
                # Empty set = subscribed to all workflows
                if not subscribed_ids or event.workflow_id in subscribed_ids:
                    try:
                        await ws.send_json({
                            "type": "event",
                            "payload": event.model_dump(mode="json")
                        })
                    except WebSocketDisconnect:
                        self._connections.pop(ws, None)

    async def close_all(self, code: int = 1000, reason: str = "") -> None:
        """Close all connections gracefully."""
        async with self._lock:
            for ws in list(self._connections.keys()):
                try:
                    await ws.close(code=code, reason=reason)
                except Exception:
                    pass
            self._connections.clear()

    @property
    def active_connections(self) -> int:
        return len(self._connections)
```

**Reconnection protocol:**
1. Client connects with `?since={last_event_id}` query param
2. Server validates the event still exists (may be cleaned up by retention)
3. If event missing, server sends `backfill_expired` → client does full refresh
4. Server replays missed events from database in order
5. Server sends `backfill_complete` message
6. Normal real-time streaming resumes
7. Client reconnects with exponential backoff: 1s, 2s, 4s... max 30s

**Backfill expiration handling:**

```python
# Server-side backfill with expiration check
@router.websocket("/ws/events")
async def websocket_endpoint(
    websocket: WebSocket,
    since: str | None = Query(default=None),
):
    await connection_manager.connect(websocket)

    try:
        # Handle backfill if reconnecting
        if since:
            event_exists = await repository.event_exists(since)
            if not event_exists:
                # Event was cleaned up by retention - client needs full refresh
                await websocket.send_json({
                    "type": "backfill_expired",
                    "message": "Requested event no longer exists. Full refresh required.",
                })
                # Client should call GET /workflows/{id} to get current state
            else:
                events = await repository.get_events_after(since)
                for event in events:
                    await websocket.send_json({
                        "type": "event",
                        "payload": event.model_dump(mode="json")
                    })
                await websocket.send_json({
                    "type": "backfill_complete",
                    "count": len(events)
                })

        # Normal event streaming...
    except WebSocketDisconnect:
        await connection_manager.disconnect(websocket)
```

```typescript
// Client-side handling
function handleWebSocketMessage(data: WebSocketMessage) {
  switch (data.type) {
    case 'backfill_expired':
      // Full refresh required - fetch current state via REST
      refreshAllWorkflows();
      break;
    case 'backfill_complete':
      console.log(`Backfill complete: ${data.count} events`);
      break;
    case 'event':
      handleEvent(data.payload);
      break;
  }
}
```

**Client-side sequence gap detection:**

```typescript
// hooks/useWebSocket.ts
const lastSequence = new Map<string, number>();

function handleEvent(event: WorkflowEvent) {
  const lastSeq = lastSequence.get(event.workflow_id) ?? 0;

  if (event.sequence > lastSeq + 1) {
    console.warn(
      `Sequence gap detected for ${event.workflow_id}: ` +
      `expected ${lastSeq + 1}, got ${event.sequence}`
    );
    // Trigger full state refresh from REST API
    refreshWorkflowState(event.workflow_id);
  }

  lastSequence.set(event.workflow_id, event.sequence);
  store.addEvent(event);
}

async function refreshWorkflowState(workflowId: string) {
  const workflow = await api.getWorkflow(workflowId);
  store.updateWorkflow(workflowId, workflow);
}
```

### CLI Mapping

```bash
amelia server              # Start the server
amelia start ISSUE-123     # POST /api/workflows {issue_id, worktree_path: $(pwd)}
amelia approve             # POST /api/workflows/{id}/approve (id from current worktree)
amelia reject "reason"     # POST /api/workflows/{id}/reject
amelia status              # GET /api/workflows/active (filters to current worktree)
amelia status --all        # GET /api/workflows/active (all worktrees)
amelia cancel              # POST /api/workflows/{id}/cancel
```

**Worktree detection:**
```python
def get_worktree_context() -> tuple[str, str]:
    """Returns (worktree_path, worktree_name) for current directory.

    Handles edge cases:
    - Detached HEAD: Uses short commit hash as name
    - Corrupted repo: Raises clear error
    - Submodules: Works correctly (has .git file pointing to parent)

    Raises:
        ValueError: If not in a git repository or in a bare repository.
        RuntimeError: If git commands fail unexpectedly.
    """
    # Check if we're in a git repo at all
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        # Could be bare repo or not a repo at all
        bare_check = subprocess.run(
            ["git", "rev-parse", "--is-bare-repository"],
            capture_output=True, text=True
        )
        if bare_check.stdout.strip() == "true":
            raise ValueError("Cannot run workflows in a bare repository")
        raise ValueError("Not inside a git repository")

    # Get worktree root (works for main repo and worktrees)
    try:
        worktree_path = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True
        ).stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to determine worktree root: {e.stderr}")

    # Get branch name for display
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True
        ).stdout.strip()
    except subprocess.CalledProcessError:
        # Fallback to directory name if branch detection fails
        return worktree_path, Path(worktree_path).name

    # Handle detached HEAD state
    if branch == "HEAD":
        try:
            short_hash = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, check=True
            ).stdout.strip()
            branch = f"detached-{short_hash}"
        except subprocess.CalledProcessError:
            branch = "detached"

    return worktree_path, branch or Path(worktree_path).name
```

---

## Frontend Structure

### Stack Decision: Custom Components + React Flow

**Resolved:** Build custom components based on the [design mock](./amelia-dashboard-dark.html) using React Flow directly. The aviation/cockpit aesthetic requires custom visuals that would fight against AI Elements' generic styling.

### Routing: React Router v7

Using React Router v7 (framework mode disabled) for client-side routing. While the MVP has minimal routes, starting with v7 avoids future migration.

```typescript
// App.tsx - Simple client-side routing (react-router v7)
import { BrowserRouter, Routes, Route, Navigate } from 'react-router';

export function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route index element={<Navigate to="/workflows" replace />} />
          <Route path="/workflows" element={<ActiveJobs />} />
          <Route path="/workflows/:id" element={<ActiveJobs />} />
          <Route path="/history" element={<ComingSoon title="Past Runs" />} />
          <Route path="/logs" element={<ComingSoon title="Logs" />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
```

**Why v7:**
- Current stable version (avoid future migration)
- Better TypeScript support than v6
- Framework features (loaders/actions) available if needed later
- Import from `react-router` not `react-router-dom` (simplified)

| Requirement | Custom Component |
|-------------|-----------------|
| Pipeline visualization | `WorkflowCanvas` - React Flow + navigation grid |
| Stage nodes | `BeaconNode` - Map pin markers with pulse animation |
| Connections | `FlightEdge` - Custom edges with time labels |
| Job queue | `JobQueue` - Aviation-styled queue panel |
| Activity log | `ActivityLog` - Terminal-style with scanlines |
| Real-time updates | WebSocket hook + React state |
| Multi-workflow | `WorkflowSelector` - Click queue item to switch view |

### Project Layout

```
dashboard/
├── src/
│   ├── main.tsx              # Entry point
│   ├── App.tsx               # Router + layout
│   ├── api/
│   │   ├── client.ts         # REST API client
│   │   └── websocket.ts      # WebSocket connection manager
│   ├── components/
│   │   ├── workflow/         # Custom workflow components
│   │   │   ├── WorkflowCanvas.tsx  # React Flow + aviation grid
│   │   │   ├── BeaconNode.tsx      # Map pin with glow animation
│   │   │   ├── FlightEdge.tsx      # Edge with time labels
│   │   │   └── index.ts            # Exports
│   │   ├── Sidebar.tsx       # Navigation with compass rose
│   │   ├── Header.tsx        # Workflow title, ETA, status, worktree name
│   │   ├── JobQueue.tsx      # Queue panel - click to select workflow
│   │   ├── ActivityLog.tsx   # Terminal-style log with cursor
│   │   ├── StatusBadge.tsx   # RUNNING, DONE, QUEUED, BLOCKED, CANCELLED
│   │   └── ComingSoon.tsx    # Placeholder for future views
│   ├── hooks/
│   │   ├── useWorkflows.ts   # Fetch all active workflows
│   │   ├── useWorkflow.ts    # Fetch + subscribe to single workflow
│   │   ├── useWebSocket.ts   # WebSocket connection hook
│   │   └── useWorkflowSelection.ts  # Selected workflow state
│   ├── store/
│   │   └── workflowStore.ts  # Zustand store for workflow state
│   ├── types/
│   │   └── index.ts          # TypeScript types
│   └── styles/
│       ├── theme.ts          # Color tokens
│       └── animations.ts     # Pulse, blink, beacon glow
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

### Multi-Workflow State Management

```typescript
// store/workflowStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface WorkflowState {
  // All active workflows (one per worktree)
  // Using Record instead of Map for JSON serialization compatibility
  workflows: Record<string, WorkflowSummary>;  // workflow_id -> summary

  // Currently selected workflow for detail view
  selectedWorkflowId: string | null;

  // Events grouped by workflow
  eventsByWorkflow: Record<string, WorkflowEvent[]>;

  // Last seen event ID for reconnection backfill
  lastEventId: string | null;

  // Request/connection states
  isLoading: boolean;
  error: string | null;
  isConnected: boolean;           // WebSocket connection status
  lastSyncAt: Date | null;        // Last successful data sync
  pendingActions: string[];       // Action IDs currently in flight (array for JSON serialization)

  // Actions
  setWorkflows: (workflows: WorkflowSummary[]) => void;
  selectWorkflow: (id: string | null) => void;
  addEvent: (event: WorkflowEvent) => void;
  updateWorkflow: (id: string, update: Partial<WorkflowSummary>) => void;
  setLastEventId: (id: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setConnected: (connected: boolean) => void;
  addPendingAction: (actionId: string) => void;
  removePendingAction: (actionId: string) => void;
  clearError: () => void;
}

export const useWorkflowStore = create<WorkflowState>()(
  persist(
    (set, get) => ({
      workflows: {},
      selectedWorkflowId: null,
      eventsByWorkflow: {},
      lastEventId: null,
      isLoading: false,
      error: null,
      isConnected: false,
      lastSyncAt: null,
      pendingActions: [],

      setWorkflows: (workflows) => set({
        workflows: Object.fromEntries(workflows.map(w => [w.id, w])),
        // Auto-select first workflow if none selected
        selectedWorkflowId: get().selectedWorkflowId ?? workflows[0]?.id ?? null,
        lastSyncAt: new Date(),
        isLoading: false,
      }),

      selectWorkflow: (id) => set({ selectedWorkflowId: id }),

      addEvent: (event) => set((state) => {
        const MAX_EVENTS_PER_WORKFLOW = 500;
        const existing = state.eventsByWorkflow[event.workflow_id] ?? [];
        const updated = [...existing, event];

        // Trim oldest events if exceeding limit (keep most recent)
        const trimmed = updated.length > MAX_EVENTS_PER_WORKFLOW
          ? updated.slice(-MAX_EVENTS_PER_WORKFLOW)
          : updated;

        return {
          eventsByWorkflow: {
            ...state.eventsByWorkflow,
            [event.workflow_id]: trimmed,
          },
          lastEventId: event.id,
        };
      }),

      updateWorkflow: (id, update) => set((state) => {
        const workflow = state.workflows[id];
        if (!workflow) return state;
        return {
          workflows: {
            ...state.workflows,
            [id]: { ...workflow, ...update },
          },
        };
      }),

      setLastEventId: (id) => set({ lastEventId: id }),

      setLoading: (loading) => set({ isLoading: loading }),

      setError: (error) => set({ error, isLoading: false }),

      setConnected: (connected) => set({
        isConnected: connected,
        error: connected ? null : 'Connection lost',
      }),

      addPendingAction: (actionId) => set((state) => ({
        pendingActions: state.pendingActions.includes(actionId)
          ? state.pendingActions
          : [...state.pendingActions, actionId],
      })),

      removePendingAction: (actionId) => set((state) => ({
        pendingActions: state.pendingActions.filter(id => id !== actionId),
      })),

      clearError: () => set({ error: null }),
    }),
    {
      name: 'amelia-workflow-state',
      storage: {
        getItem: (name) => {
          const value = sessionStorage.getItem(name);
          return value ? JSON.parse(value) : null;
        },
        setItem: (name, value) => {
          sessionStorage.setItem(name, JSON.stringify(value));
        },
        removeItem: (name) => {
          sessionStorage.removeItem(name);
        },
      },
      // Only persist UI state, not workflow data (re-fetched on reconnect)
      partialize: (state) => ({
        selectedWorkflowId: state.selectedWorkflowId,
        lastEventId: state.lastEventId,
      }),
    }
  )
);
```

### Component Updates for Multi-Workflow

**JobQueue** - Now interactive:
```typescript
// Selected workflow has gold border, others have default styling
<QueueItem
  key={workflow.id}
  workflow={workflow}
  isSelected={workflow.id === selectedWorkflowId}
  onClick={() => selectWorkflow(workflow.id)}
/>
```

**Header** - Shows worktree context:
```typescript
// "ISSUE-123 · feature-auth" format
<h1>{workflow.issue_id} · {workflow.worktree_name}</h1>
```

**ActivityLog** - Filters by selected workflow:
```typescript
const events = selectedWorkflowId
  ? eventsByWorkflow[selectedWorkflowId] ?? []
  : Object.values(eventsByWorkflow).flat();
// Shows selected workflow events, or all events with workflow badges when none selected
```

### Optimistic UI Updates

For responsive user experience, UI updates immediately while API requests are in flight. Rollback on failure.

```typescript
// hooks/useWorkflowActions.ts
import { useWorkflowStore } from '../store/workflowStore';
import { api } from '../api/client';
import { toast } from '../components/Toast';

interface UseWorkflowActionsResult {
  approveWorkflow: (workflowId: string) => Promise<void>;
  rejectWorkflow: (workflowId: string, feedback: string) => Promise<void>;
  cancelWorkflow: (workflowId: string) => Promise<void>;
  isActionPending: (workflowId: string) => boolean;
}

export function useWorkflowActions(): UseWorkflowActionsResult {
  const {
    updateWorkflow,
    addPendingAction,
    removePendingAction,
    pendingActions,
  } = useWorkflowStore();

  const approveWorkflow = async (workflowId: string) => {
    const actionId = `approve-${workflowId}`;

    // Capture previous state for rollback
    const workflow = useWorkflowStore.getState().workflows[workflowId];
    const previousStatus = workflow?.status;

    // Optimistic update
    updateWorkflow(workflowId, { status: 'in_progress' });
    addPendingAction(actionId);

    try {
      await api.approveWorkflow(workflowId);
      toast.success('Plan approved');
    } catch (error) {
      // Rollback on failure
      updateWorkflow(workflowId, { status: previousStatus });
      toast.error(`Approval failed: ${error.message}`);
    } finally {
      removePendingAction(actionId);
    }
  };

  const rejectWorkflow = async (workflowId: string, feedback: string) => {
    const actionId = `reject-${workflowId}`;

    const workflow = useWorkflowStore.getState().workflows[workflowId];
    const previousStatus = workflow?.status;

    // Optimistic update
    updateWorkflow(workflowId, { status: 'failed' });
    addPendingAction(actionId);

    try {
      await api.rejectWorkflow(workflowId, feedback);
      toast.success('Plan rejected');
    } catch (error) {
      updateWorkflow(workflowId, { status: previousStatus });
      toast.error(`Rejection failed: ${error.message}`);
    } finally {
      removePendingAction(actionId);
    }
  };

  const cancelWorkflow = async (workflowId: string) => {
    const actionId = `cancel-${workflowId}`;

    const workflow = useWorkflowStore.getState().workflows[workflowId];
    const previousStatus = workflow?.status;

    // Optimistic update
    updateWorkflow(workflowId, { status: 'cancelled' });
    addPendingAction(actionId);

    try {
      await api.cancelWorkflow(workflowId);
      toast.success('Workflow cancelled');
    } catch (error) {
      updateWorkflow(workflowId, { status: previousStatus });
      toast.error(`Cancellation failed: ${error.message}`);
    } finally {
      removePendingAction(actionId);
    }
  };

  const isActionPending = (workflowId: string) => {
    return pendingActions.some(id => id.endsWith(workflowId));
  };

  return {
    approveWorkflow,
    rejectWorkflow,
    cancelWorkflow,
    isActionPending,
  };
}
```

**Usage in components:**

```typescript
// components/ApprovalButtons.tsx
function ApprovalButtons({ workflowId }: { workflowId: string }) {
  const { approveWorkflow, rejectWorkflow, isActionPending } = useWorkflowActions();
  const [feedback, setFeedback] = useState('');
  const isPending = isActionPending(workflowId);

  return (
    <div className="flex gap-2">
      <button
        onClick={() => approveWorkflow(workflowId)}
        disabled={isPending}
        className="btn-primary"
      >
        {isPending ? <Spinner /> : 'Approve'}
      </button>
      <button
        onClick={() => rejectWorkflow(workflowId, feedback)}
        disabled={isPending || !feedback}
        className="btn-danger"
      >
        Reject
      </button>
    </div>
  );
}
```

**Optimistic update principles:**
- Update UI immediately before API response
- Show loading indicator for in-flight actions
- Rollback to previous state on error
- Show toast notification on success/failure
- Disable buttons while action is pending
- Server-sent WebSocket events confirm final state

### Custom Component Specifications

Based on [amelia-dashboard-dark.html](./amelia-dashboard-dark.html):

#### BeaconNode
Map pin marker representing workflow stages:
- **States**: completed (green), active (gold pulse), pending (gray), blocked (red)
- **Animation**: `beaconGlow` keyframes for active state
- **Labels**: Stage name, subtitle, token count

#### FlightEdge
Connection between stages:
- **Completed**: Solid line, green tint
- **Active**: Dashed line, gold, with glow filter
- **Pending**: Dashed line, low opacity
- **Time label**: Badge showing duration at midpoint

#### WorkflowCanvas
Container with aviation aesthetic:
- Navigation grid pattern (cross-hatching)
- Compass rose watermark
- Starfield background
- Cockpit glass scanlines
- Vignette overlay

### Design Theme

Based on the Amelia Earhart aviation aesthetic from the design mock:

```typescript
const theme = {
  bg: {
    dark: '#0D1A12',      // Sidebar, panels
    main: '#1F332E'       // Main background
  },
  text: {
    primary: '#EFF8E2',   // Headers, main text
    secondary: '#88A896', // Labels, timestamps
    muted: '#88A896'      // Same as secondary for a11y
  },
  accent: {
    gold: '#FFC857',      // Logo, active states
    blue: '#5B9BD5'       // Links, IDs
  },
  status: {
    running: '#FFC857',   // Amber - in progress
    completed: '#5B8A72', // Green - done
    pending: '#4A5C54',   // Gray - queued
    blocked: '#A33D2E',   // Red - awaiting approval
    failed: '#A33D2E'     // Red - error
  }
};

const typography = {
  display: "'Bebas Neue', sans-serif",      // Logo, workflow ID, large numbers
  heading: "'Barlow Condensed', sans-serif", // Nav labels, section titles, badges
  body: "'Source Sans 3', sans-serif",       // Content text, descriptions
  mono: "'IBM Plex Mono', monospace"         // Timestamps, code, IDs
};
```

### Animations

```css
@keyframes pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 8px rgba(255, 200, 87, 0.6); }
  50% { opacity: 0.6; box-shadow: 0 0 12px rgba(255, 200, 87, 0.8); }
}

@keyframes beaconGlow {
  0%, 100% { filter: drop-shadow(0 0 4px rgba(255, 200, 87, 0.6)); }
  50% { filter: drop-shadow(0 0 16px rgba(255, 200, 87, 0.6)); }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
```

### Accessibility Requirements

Despite the aviation theme's dark aesthetic, the dashboard must be accessible:

**Color contrast:**
- Ensure WCAG AA compliance (4.5:1 for normal text, 3:1 for large text)
- `text.primary` (#EFF8E2) on `bg.main` (#1F332E) = 12.1:1 ✓
- `text.secondary` (#88A896) on `bg.main` (#1F332E) = 5.1:1 ✓
- Bright status badges (running, completed) use dark text for contrast

**Keyboard navigation:**
```typescript
// All interactive elements must be keyboard accessible
<button
  onClick={handleApprove}
  onKeyDown={(e) => e.key === 'Enter' && handleApprove()}
  tabIndex={0}
  aria-label="Approve workflow plan"
>
  Approve
</button>

// Focus management for modal dialogs
const dialogRef = useRef<HTMLDivElement>(null);
useEffect(() => {
  if (isOpen) {
    dialogRef.current?.focus();
  }
}, [isOpen]);
```

**ARIA labels:**
```typescript
// Status badges
<span
  role="status"
  aria-label={`Workflow status: ${status}`}
  className={`badge badge-${status}`}
>
  {status.toUpperCase()}
</span>

// Activity log
<div
  role="log"
  aria-live="polite"
  aria-label="Workflow activity log"
>
  {events.map(event => (
    <div key={event.id} role="listitem">
      {event.message}
    </div>
  ))}
</div>

// Pipeline visualization
<div
  role="img"
  aria-label={`Workflow pipeline with ${stages.length} stages. Current stage: ${currentStage}`}
>
  <ReactFlow ... />
</div>
```

**Animation preferences:**
```css
/* Respect user's motion preferences */
@media (prefers-reduced-motion: reduce) {
  .beacon-pulse,
  .flight-edge-animated {
    animation: none;
  }

  * {
    transition-duration: 0.01ms !important;
  }
}
```

**Screen reader considerations:**
- Announce workflow state changes via `aria-live` regions
- Provide text alternatives for all status indicators
- Ensure React Flow nodes have descriptive labels

### Error Boundaries

React error boundaries for graceful degradation:

```typescript
// components/ErrorBoundary.tsx
import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

// components/ConnectionLost.tsx
interface ConnectionLostProps {
  onRetry: () => void;
  error?: string;
}

export function ConnectionLost({ onRetry, error }: ConnectionLostProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <div className="text-status-failed text-xl">Connection Lost</div>
      {error && <div className="text-text-secondary text-sm">{error}</div>}
      <button
        onClick={onRetry}
        className="px-4 py-2 bg-accent-gold text-bg-dark rounded"
      >
        Reconnect
      </button>
    </div>
  );
}
```

**Usage in App.tsx:**
```typescript
import { ErrorBoundary } from './components/ErrorBoundary';
import { ConnectionLost } from './components/ConnectionLost';

function App() {
  const { reconnect } = useWebSocket();

  return (
    <ErrorBoundary fallback={<ConnectionLost onRetry={reconnect} />}>
      <BrowserRouter>
        {/* ... routes ... */}
      </BrowserRouter>
    </ErrorBoundary>
  );
}
```

**Error handling strategy:**
- WebSocket disconnection: Show `ConnectionLost` with retry button
- API failures: Toast notification with error message
- Malformed events: Log and skip (don't crash the UI)
- Component errors: Isolate to affected component via boundary

### Navigation Structure

| Section | View | MVP Status |
|---------|------|------------|
| **WORKFLOWS** | Active Jobs | Functional |
| | Agents | Coming soon |
| | Outputs | Coming soon |
| **HISTORY** | Past Runs | Coming soon |
| | Milestones | Coming soon |
| | Deployments | Coming soon |
| **MONITORING** | Logs | Coming soon |
| | Notifications | Coming soon |

---

## Server Structure

### Package Layout

```
amelia/
├── server/                    # NEW: FastAPI server package
│   ├── __init__.py
│   ├── main.py               # FastAPI app, mounts routes
│   ├── config.py             # Server configuration (port, limits, etc.)
│   ├── routes/
│   │   ├── workflows.py      # /api/workflows/* endpoints
│   │   └── websocket.py      # /ws/events handler
│   ├── services/
│   │   ├── orchestrator_service.py  # Manages concurrent workflows
│   │   └── event_bus.py      # Pub/sub for WebSocket broadcast
│   └── database/
│       ├── models.py         # SQLAlchemy/SQLModel tables
│       └── repository.py     # CRUD operations
├── core/
│   └── orchestrator.py       # Existing LangGraph (logic unchanged)
├── main.py                   # CLI (refactored to thin client)
```

### FastAPI Application Setup

```python
# amelia/server/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Amelia API",
    description="Agentic coding orchestrator REST API",
    version=__version__,
    docs_url="/api/docs",           # Swagger UI
    redoc_url="/api/redoc",         # ReDoc alternative
    openapi_url="/api/openapi.json", # OpenAPI schema
)

# Mount API routes
app.include_router(workflow_router, prefix="/api")
app.include_router(health_router, prefix="/api")

# Mount WebSocket
app.include_router(websocket_router)

# Serve dashboard static files (production)
app.mount("/", StaticFiles(directory="dashboard/dist", html=True), name="dashboard")
```

**API documentation access:**
- Swagger UI: `http://localhost:8420/api/docs`
- ReDoc: `http://localhost:8420/api/redoc`
- OpenAPI JSON: `http://localhost:8420/api/openapi.json`

### Orchestrator Service (Concurrency Manager)

The `OrchestratorService` manages multiple concurrent workflow executions:

```python
class OrchestratorService:
    """Manages concurrent workflow executions across worktrees."""

    def __init__(
        self,
        event_bus: EventBus,
        repository: WorkflowRepository,
        max_concurrent: int = 5,
    ):
        self._event_bus = event_bus
        self._repository = repository
        self._max_concurrent = max_concurrent
        self._active_tasks: dict[str, asyncio.Task] = {}  # worktree_path -> task
        self._approval_events: dict[str, asyncio.Event] = {}  # workflow_id -> event
        self._approval_lock = asyncio.Lock()  # Prevents race conditions on concurrent approvals
        self._sequence_counters: dict[str, int] = {}  # workflow_id -> next sequence number
        self._sequence_locks: dict[str, asyncio.Lock] = {}  # workflow_id -> lock for sequence counter

    async def start_workflow(
        self,
        issue_id: str,
        worktree_path: str,
        worktree_name: str,
        profile: str | None = None,
    ) -> str:
        """Start a new workflow. Returns workflow ID."""
        # Check worktree conflict
        if worktree_path in self._active_tasks:
            raise WorkflowConflictError(
                f"Workflow already active in {worktree_path}"
            )

        # Check concurrency limit
        if len(self._active_tasks) >= self._max_concurrent:
            raise ConcurrencyLimitError(
                f"Maximum {self._max_concurrent} concurrent workflows"
            )

        # Create workflow record
        workflow_id = str(uuid4())
        state = ExecutionState(
            id=workflow_id,
            issue_id=issue_id,
            worktree_path=worktree_path,
            worktree_name=worktree_name,
            workflow_status="pending",
            started_at=datetime.utcnow(),
        )
        await self._repository.create(state)

        # Start async task
        task = asyncio.create_task(
            self._run_workflow(workflow_id, state, profile)
        )
        self._active_tasks[worktree_path] = task
        task.add_done_callback(
            lambda _: self._active_tasks.pop(worktree_path, None)
        )

        return workflow_id

    async def _run_workflow(
        self,
        workflow_id: str,
        initial_state: ExecutionState,
        profile: str | None,
    ) -> None:
        """Execute workflow with event emission."""
        try:
            self._emit(workflow_id, EventType.WORKFLOW_STARTED, "Workflow started")

            async for state in langgraph_app.astream(initial_state):
                await self._repository.update(state)
                self._emit_stage_events(workflow_id, state)

                # Handle approval gate
                if state.workflow_status == "blocked":
                    await self._wait_for_approval(workflow_id)

            self._emit(workflow_id, EventType.WORKFLOW_COMPLETED, "Workflow completed")

        except asyncio.CancelledError:
            self._emit(workflow_id, EventType.WORKFLOW_CANCELLED, "Workflow cancelled")
            await self._repository.set_status(workflow_id, "cancelled")
            raise

        except Exception as e:
            self._emit(workflow_id, EventType.WORKFLOW_FAILED, str(e))
            await self._repository.set_status(workflow_id, "failed", failure_reason=str(e))

    async def approve_workflow(self, workflow_id: str, correlation_id: str | None = None) -> bool:
        """Approve a blocked workflow.

        Args:
            workflow_id: The workflow to approve.
            correlation_id: Optional ID for tracing this action through the system.

        Returns:
            True if approval was processed, False if already approved or not blocked.

        Thread-safe: Uses atomic pop to prevent race conditions when multiple
        clients (browser + CLI) approve simultaneously.
        """
        async with self._approval_lock:
            # Atomic check-and-remove prevents duplicate approvals
            event = self._approval_events.pop(workflow_id, None)
            if not event:
                # Already approved, rejected, or not blocked
                return False

            await self._repository.set_status(workflow_id, "in_progress")
            await self._emit(
                workflow_id,
                EventType.APPROVAL_GRANTED,
                "Plan approved",
                correlation_id=correlation_id,
            )
            event.set()
            return True

    async def reject_workflow(self, workflow_id: str, feedback: str) -> bool:
        """Reject a blocked workflow.

        Returns:
            True if rejection was processed, False if already handled or not blocked.

        Thread-safe: Uses atomic pop to prevent race conditions.
        """
        async with self._approval_lock:
            # Atomic check-and-remove prevents duplicate rejections
            event = self._approval_events.pop(workflow_id, None)
            if not event:
                # Already approved, rejected, or not blocked
                return False

            await self._repository.set_status(workflow_id, "failed", failure_reason=feedback)
            await self._emit(workflow_id, EventType.APPROVAL_REJECTED, f"Plan rejected: {feedback}")

            # Cancel the waiting task
            workflow = await self._repository.get(workflow_id)
            if workflow and workflow.worktree_path in self._active_tasks:
                self._active_tasks[workflow.worktree_path].cancel()

            return True

    async def cancel_workflow(self, workflow_id: str) -> None:
        """Cancel a running workflow."""
        workflow = await self._repository.get(workflow_id)
        if workflow and workflow.worktree_path in self._active_tasks:
            self._active_tasks[workflow.worktree_path].cancel()

    async def _wait_for_approval(self, workflow_id: str) -> None:
        """Block until workflow is approved or rejected."""
        event = asyncio.Event()
        self._approval_events[workflow_id] = event
        self._emit(workflow_id, EventType.APPROVAL_REQUIRED, "Awaiting plan approval")
        try:
            await event.wait()
        finally:
            del self._approval_events[workflow_id]

    async def _emit(
        self,
        workflow_id: str,
        event_type: EventType,
        message: str,
        data: dict | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Emit a workflow event with write-ahead persistence.

        Events are persisted to database BEFORE being broadcast to WebSocket clients.
        This ensures no events are lost if server crashes between emit and broadcast.

        Thread-safe: Uses per-workflow lock to prevent sequence number collisions
        when multiple events are emitted concurrently for the same workflow.

        Args:
            workflow_id: The workflow this event belongs to.
            event_type: Type of event being emitted.
            message: Human-readable description.
            data: Optional structured payload.
            correlation_id: Optional ID for tracing related events.
        """
        # Get or create lock for this workflow's sequence counter
        if workflow_id not in self._sequence_locks:
            self._sequence_locks[workflow_id] = asyncio.Lock()

        async with self._sequence_locks[workflow_id]:
            # Get next sequence number for this workflow
            if workflow_id not in self._sequence_counters:
                # On first event, query DB for max sequence
                max_seq = await self._repository.get_max_event_sequence(workflow_id)
                self._sequence_counters[workflow_id] = max_seq or 0

            self._sequence_counters[workflow_id] += 1
            sequence = self._sequence_counters[workflow_id]

            event = WorkflowEvent(
                id=str(uuid4()),
                workflow_id=workflow_id,
                sequence=sequence,
                timestamp=datetime.utcnow(),
                agent="system",
                event_type=event_type,
                message=message,
                data=data,
                correlation_id=correlation_id,
            )

            # Write-ahead: persist to DB first
            await self._repository.save_event(event)

        # Broadcast outside the lock to avoid holding it during I/O
        self._event_bus.emit(event)

    def get_active_workflows(self) -> list[str]:
        """Return list of active worktree paths."""
        return list(self._active_tasks.keys())
```

### Event Emission

Orchestrator nodes wrapped to emit events on state transitions:

```python
async def call_architect_node(state: ExecutionState) -> ExecutionState:
    event_bus.emit(WorkflowEvent(
        agent="architect",
        event_type=EventType.STAGE_STARTED,
        message="Parsing issue and creating task DAG"
    ))
    result = await original_architect_logic(state)
    event_bus.emit(WorkflowEvent(
        agent="architect",
        event_type=EventType.STAGE_COMPLETED,
        message=f"Plan created with {len(result.plan.tasks)} tasks"
    ))
    return result
```

### Human Approval Flow

Refactored from CLI input blocking to REST-based:

1. Orchestrator reaches approval gate
2. Sets `workflow_status = "blocked"`
3. Persists state to SQLite
4. Emits `WorkflowEvent(event_type=EventType.APPROVAL_REQUIRED)`
5. `OrchestratorService._wait_for_approval()` blocks on `asyncio.Event`
6. `POST /api/workflows/{id}/approve` calls `approve_workflow()` which sets the event
7. Workflow resumes with `workflow_status = "in_progress"`

### Server Lifecycle

Graceful startup and shutdown handling:

```python
class ServerLifecycle:
    """Manages server startup and shutdown."""

    def __init__(
        self,
        orchestrator: OrchestratorService,
        log_retention: LogRetentionService,
    ):
        self._orchestrator = orchestrator
        self._log_retention = log_retention
        self._shutting_down = False
        self._shutdown_timeout = 30  # seconds

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    async def startup(self) -> None:
        """Called on server startup."""
        # Recover any workflows that were running when server crashed
        await self._orchestrator.recover_interrupted_workflows()

    async def shutdown(self) -> None:
        """Graceful shutdown sequence."""
        self._shutting_down = True
        logger.info("Server shutting down...")

        # 1. Stop accepting new workflows (middleware checks is_shutting_down)
        # 2. Wait for blocked workflows with timeout
        active = self._orchestrator.get_active_workflows()
        if active:
            logger.info(f"Waiting for {len(active)} active workflows...")
            try:
                await asyncio.wait_for(
                    self._wait_for_workflows_to_finish(),
                    timeout=self._shutdown_timeout
                )
            except asyncio.TimeoutError:
                logger.warning("Shutdown timeout - cancelling remaining workflows")

        # 3. Cancel any still-running workflows
        for worktree_path in self._orchestrator.get_active_workflows():
            task = self._orchestrator._active_tasks.get(worktree_path)
            if task:
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=5)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

        # 4. Persist final state (already done via repository on each update)
        logger.info("Final state persisted to database")

        # 5. Run log retention cleanup
        await self._log_retention.cleanup_on_shutdown()

        # 6. Close WebSocket connections
        await connection_manager.close_all(code=1001, reason="Server shutting down")

        logger.info("Server shutdown complete")

    async def _wait_for_workflows_to_finish(self) -> None:
        """Wait for all active workflows to complete."""
        while self._orchestrator.get_active_workflows():
            await asyncio.sleep(1)


# Middleware to reject requests during shutdown
@app.middleware("http")
async def shutdown_middleware(request: Request, call_next):
    if lifecycle.is_shutting_down and request.url.path.startswith("/api/workflows"):
        if request.method == "POST":
            return JSONResponse(
                status_code=503,
                content={"error": "Server shutting down", "code": "SHUTTING_DOWN"}
            )
    return await call_next(request)
```

**Startup sequence:**
1. Initialize database connection
2. Start event bus
3. Recover interrupted workflows (mark as failed with reason)
4. Start HTTP server
5. Accept connections

**Interrupted workflow recovery:**
```python
async def recover_interrupted_workflows(self) -> None:
    """Mark any workflows left in active state as failed on startup."""
    active_statuses = ["pending", "in_progress", "blocked"]
    interrupted = await self._repository.find_by_status(active_statuses)
    for workflow in interrupted:
        await self._repository.set_status(
            workflow.id,
            "failed",
            failure_reason="Server restarted unexpectedly"
        )
        logger.warning(f"Marked interrupted workflow {workflow.id} as failed")
```

### Worktree Health Checks

Periodic validation that worktrees still exist:

```python
class WorktreeHealthChecker:
    """Periodically validates worktree health for active workflows."""

    def __init__(
        self,
        orchestrator: OrchestratorService,
        check_interval: float = 30.0,  # seconds
    ):
        self._orchestrator = orchestrator
        self._check_interval = check_interval
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the health check loop."""
        self._task = asyncio.create_task(self._check_loop())

    async def stop(self) -> None:
        """Stop the health check loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _check_loop(self) -> None:
        """Periodically check all active worktrees."""
        while True:
            await asyncio.sleep(self._check_interval)
            await self._check_all_worktrees()

    async def _check_all_worktrees(self) -> None:
        """Check health of all active workflow worktrees."""
        for worktree_path in self._orchestrator.get_active_workflows():
            if not await self._is_worktree_healthy(worktree_path):
                workflow = await self._orchestrator.get_workflow_by_worktree(worktree_path)
                if workflow:
                    logger.warning(f"Worktree deleted: {worktree_path}")
                    await self._orchestrator.cancel_workflow(
                        workflow.id,
                        reason="Worktree directory no longer exists"
                    )

    async def _is_worktree_healthy(self, worktree_path: str) -> bool:
        """Check if worktree directory still exists and is valid."""
        path = Path(worktree_path)
        if not path.exists():
            return False
        if not path.is_dir():
            return False
        # Check .git exists (file for worktrees, dir for main repo)
        git_path = path / ".git"
        return git_path.exists()
```

### Metrics and Observability

Structured logging and Prometheus-compatible metrics for monitoring:

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()


# Prometheus metrics
WORKFLOW_STARTED = Counter(
    'amelia_workflows_started_total',
    'Total workflows started',
    ['worktree_name']
)

WORKFLOW_COMPLETED = Counter(
    'amelia_workflows_completed_total',
    'Total workflows completed',
    ['worktree_name', 'status']  # status: completed, failed, cancelled
)

WORKFLOW_DURATION = Histogram(
    'amelia_workflow_duration_seconds',
    'Workflow duration in seconds',
    ['worktree_name'],
    buckets=[60, 300, 600, 1800, 3600, 7200]  # 1m, 5m, 10m, 30m, 1h, 2h
)

ACTIVE_WORKFLOWS = Gauge(
    'amelia_active_workflows',
    'Number of currently active workflows'
)

WEBSOCKET_CONNECTIONS = Gauge(
    'amelia_websocket_connections',
    'Number of active WebSocket connections'
)

API_REQUEST_DURATION = Histogram(
    'amelia_api_request_duration_seconds',
    'API request latency',
    ['method', 'endpoint', 'status_code'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

TOKEN_USAGE = Counter(
    'amelia_tokens_total',
    'Total tokens consumed',
    ['agent', 'token_type']  # token_type: input, output, cache_read, cache_write
)

EVENTS_EMITTED = Counter(
    'amelia_events_emitted_total',
    'Total workflow events emitted',
    ['event_type', 'agent']
)


# Metrics endpoint
@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type="text/plain; charset=utf-8"
    )


# Request timing middleware
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    # Extract endpoint pattern (e.g., /api/workflows/{id} -> /api/workflows/:id)
    endpoint = request.url.path
    for route in app.routes:
        if hasattr(route, 'path') and route.matches(request.scope):
            endpoint = route.path
            break

    API_REQUEST_DURATION.labels(
        method=request.method,
        endpoint=endpoint,
        status_code=response.status_code
    ).observe(duration)

    return response


# Structured logging in orchestrator
async def _emit(self, workflow_id: str, event_type: EventType, message: str, data: dict | None = None) -> None:
    # ... existing event creation logic ...

    # Structured logging with context
    logger.info(
        "workflow_event",
        workflow_id=workflow_id,
        event_type=event_type.value,
        agent=event.agent,
        message=message,
    )

    # Update Prometheus metrics
    EVENTS_EMITTED.labels(
        event_type=event_type.value,
        agent=event.agent
    ).inc()
```

**Log format (JSON):**
```json
{
  "timestamp": "2025-12-01T14:30:00.000Z",
  "level": "info",
  "event": "workflow_event",
  "workflow_id": "abc-123",
  "event_type": "stage_completed",
  "agent": "architect",
  "message": "Plan created with 5 tasks"
}
```

**Key metrics:**
| Metric | Type | Description |
|--------|------|-------------|
| `amelia_workflows_started_total` | Counter | Workflows started by worktree |
| `amelia_workflows_completed_total` | Counter | Workflows completed by status |
| `amelia_workflow_duration_seconds` | Histogram | Time to complete workflows |
| `amelia_active_workflows` | Gauge | Currently running workflows |
| `amelia_api_request_duration_seconds` | Histogram | API latency by endpoint |
| `amelia_tokens_total` | Counter | Token consumption by type |
| `amelia_events_emitted_total` | Counter | Events by type and agent |

---

## Token Tracking

### Driver-Level Implementation

Modify `BaseDriver` to capture and return token counts:

```python
class DriverResponse(BaseModel):
    content: str
    token_usage: TokenUsage | None = None

class BaseDriver(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> DriverResponse:
        """Generate response with token tracking."""
```

### Decision: Use Claude Agent SDK

**Resolved:** The Claude CLI does not expose token usage. The Claude Agent SDK provides full token tracking via `ResultMessage`:

| Field | Description |
|-------|-------------|
| `input_tokens` | Tokens processed |
| `output_tokens` | Tokens generated |
| `cache_creation_input_tokens` | Prompt cache creation |
| `cache_read_input_tokens` | Prompt cache reads |
| `total_cost_usd` | USD cost for the request |

### New Driver: `sdk:claude`

Add a third driver option that uses the Agent SDK for programmatic execution with built-in metrics:

```python
class ClaudeSDKDriver(BaseDriver):
    """Claude Agent SDK driver with native token tracking."""

    async def generate(self, prompt: str) -> DriverResponse:
        result = await claude_agent.run(prompt)
        return DriverResponse(
            content=result.result,
            token_usage=TokenUsage(
                input_tokens=result.usage["input_tokens"],
                output_tokens=result.usage["output_tokens"],
            )
        )
```

### Driver Comparison

| Driver | Use Case | Token Tracking |
|--------|----------|----------------|
| `api:openai` | Direct API (OpenAI, Anthropic API) | ✅ Native |
| `cli:claude` | Enterprise compliance, interactive | ❌ Estimate only |
| `sdk:claude` | **Server default** - Programmatic Claude Code | ✅ Native |

The server will use `sdk:claude` as the default driver for full observability.

---

## Error Handling

### HTTP Error Codes

| Code | Condition | Response |
|------|-----------|----------|
| `400` | Invalid request body | `{"error": "...", "code": "INVALID_REQUEST"}` |
| `404` | Workflow not found | `{"error": "Workflow not found", "code": "NOT_FOUND"}` |
| `409` | Workflow conflict (worktree busy) | `{"error": "Workflow already active in /path", "code": "WORKFLOW_CONFLICT", "details": {"worktree_path": "...", "workflow_id": "..."}}` |
| `422` | Invalid state transition | `{"error": "Cannot approve: workflow not blocked", "code": "INVALID_STATE"}` |
| `429` | Concurrency limit reached | `{"error": "Maximum 5 concurrent workflows", "code": "CONCURRENCY_LIMIT"}` + `Retry-After: 30` header |
| `500` | Internal server error | `{"error": "Internal error", "code": "INTERNAL_ERROR"}` |
| `503` | Server shutting down | `{"error": "Server shutting down", "code": "SHUTTING_DOWN"}` |

### Exception Classes

```python
class AmeliaServerError(Exception):
    """Base exception for server errors."""
    code: str
    status_code: int

class WorkflowConflictError(AmeliaServerError):
    """Raised when starting workflow in busy worktree."""
    code = "WORKFLOW_CONFLICT"
    status_code = 409

class ConcurrencyLimitError(AmeliaServerError):
    """Raised when max concurrent workflows reached."""
    code = "CONCURRENCY_LIMIT"
    status_code = 429

class InvalidStateError(AmeliaServerError):
    """Raised on invalid state transitions."""
    code = "INVALID_STATE"
    status_code = 422

class WorkflowNotFoundError(AmeliaServerError):
    """Raised when workflow ID doesn't exist."""
    code = "NOT_FOUND"
    status_code = 404
```

### CLI Error Display

```bash
$ amelia start ISSUE-123
Error: Workflow already active in /Users/ka/project

  Active workflow: abc123 (ISSUE-99)
  Status: in_progress

  To start a new workflow:
    - Cancel the existing one: amelia cancel
    - Or use a different worktree: git worktree add ../project-issue-123

$ amelia approve
Error: No workflow awaiting approval

  Current workflow: abc123 (ISSUE-99)
  Status: in_progress (not blocked)
```

---

## Security

### Binding and Access

**Default (local-only):**
- Server binds to `127.0.0.1:8420` by default
- Refuses to bind to `0.0.0.0` without explicit `--bind-all` flag
- No authentication required (single-user, local machine)
- CORS disabled (same-origin only)

```bash
# Local only (default)
amelia server

# Explicitly allow network access (warns about security)
amelia server --bind-all
# ⚠️  Warning: Server accessible to all network clients. No authentication enabled.
```

### Rate Limiting

Even on localhost, protect against misbehaving scripts or runaway clients:

```python
from collections import defaultdict
from time import time

class RateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 10,
    ):
        self._rate = requests_per_minute / 60.0  # tokens per second
        self._burst = burst_size
        self._tokens: dict[str, float] = defaultdict(lambda: float(burst_size))
        self._last_update: dict[str, float] = defaultdict(time)

    def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed. Consumes a token if yes."""
        now = time()
        # Refill tokens based on time elapsed
        elapsed = now - self._last_update[client_id]
        self._tokens[client_id] = min(
            self._burst,
            self._tokens[client_id] + elapsed * self._rate
        )
        self._last_update[client_id] = now

        if self._tokens[client_id] >= 1:
            self._tokens[client_id] -= 1
            return True
        return False


# Middleware
rate_limiter = RateLimiter(requests_per_minute=60, burst_size=10)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Use client IP as identifier (localhost = 127.0.0.1)
    client_id = request.client.host if request.client else "unknown"

    if not rate_limiter.is_allowed(client_id):
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests", "code": "RATE_LIMITED"},
            headers={"Retry-After": "1"},
        )

    return await call_next(request)
```

**Configuration:**
- Default: 60 requests/minute with burst of 10
- Configurable via `AMELIA_RATE_LIMIT` environment variable
- WebSocket connections exempt (rate limit on initial connect only)

### Future Considerations (Not MVP)

| Feature | Purpose | When |
|---------|---------|------|
| API key auth | Non-browser clients | If `--bind-all` used |
| Audit log | Track all actions | Compliance requirements |
| HTTPS | Encrypted transport | Network deployment |

### Path Traversal Prevention

Worktree paths validated:
```python
def validate_worktree_path(path: str) -> str:
    """Ensure path is a valid git worktree root."""
    resolved = Path(path).resolve()

    # Must be absolute
    if not resolved.is_absolute():
        raise ValueError("Worktree path must be absolute")

    # Must exist and be a directory
    if not resolved.is_dir():
        raise ValueError("Worktree path must be a directory")

    # Must be a git worktree (has .git file or directory)
    git_path = resolved / ".git"
    if not git_path.exists():
        raise ValueError("Not a git repository")

    return str(resolved)
```

---

## Implementation Phases

### Phase 2.1: Foundation (Server + Database)

- FastAPI server skeleton with health endpoint
- SQLite setup with SQLAlchemy/SQLModel
- `WorkflowEvent` and `TokenUsage` models
- Basic REST endpoints (CRUD for workflows)
- `amelia server` command to start it
- Unit tests for API endpoints

### Phase 2.2: Orchestrator Migration

- Move orchestrator execution into server
- Event bus for broadcasting state changes
- Human approval via REST (replace CLI input)
- WebSocket endpoint for real-time events
- Refactor CLI to thin client
- Token tracking in drivers
- Integration tests for orchestrator

### Phase 2.3: Dashboard UI

- Vite + React + TypeScript project setup
- WebSocket connection hook
- Port mock components to proper React
- Active Jobs view (fully functional)
- Placeholder views for other nav items
- Serve dashboard from FastAPI (static files)
- E2E tests with Playwright

### Phase 2.4: Platform Adapters (Future)

Enable Telegram, Slack, and other messaging platform integrations using adapter pattern:

```python
class PlatformAdapter(Protocol):
    """Common interface for messaging platforms."""
    async def send_message(self, conversation_id: str, message: str) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

class TelegramAdapter(PlatformAdapter):
    """Telegraf-based, polling transport."""

class SlackAdapter(PlatformAdapter):
    """Socket Mode or Events API webhooks."""
```

Architecture supports this via event bus subscription:

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Telegram   │  │    Slack    │  │   Browser   │
│   Adapter   │  │   Adapter   │  │  WebSocket  │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       └────────────────┼────────────────┘
                        ▼
              ┌─────────────────┐
              │    Event Bus    │
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │   Orchestrator  │
              └─────────────────┘
```

Platform adapters subscribe to same events as WebSocket, format messages for their platform. Human approval could come from any connected platform.

---

## Testing Strategy

Following TDD - tests first, then implementation.

### Test Structure

```
tests/
├── unit/
│   ├── server/
│   │   ├── test_routes_workflows.py
│   │   ├── test_routes_websocket.py
│   │   ├── test_services_orchestrator.py
│   │   ├── test_services_orchestrator_concurrency.py  # NEW
│   │   ├── test_services_event_bus.py
│   │   └── test_database_repository.py
│   └── drivers/
│       └── test_token_tracking.py
├── integration/
│   ├── test_server_orchestrator.py
│   ├── test_multi_workflow.py       # NEW: Concurrent workflow tests
│   └── test_cli_thin_client.py
└── e2e/
    └── test_dashboard.py

dashboard/
├── src/__tests__/                   # Frontend tests
│   ├── components/
│   │   ├── JobQueue.test.tsx
│   │   ├── ActivityLog.test.tsx
│   │   └── WorkflowCanvas.test.tsx
│   ├── hooks/
│   │   ├── useWebSocket.test.ts
│   │   └── useWorkflows.test.ts
│   └── store/
│       └── workflowStore.test.ts
└── e2e/
    └── multi-workflow.spec.ts       # Playwright E2E
```

### TDD Approach Per Phase

| Phase | Write tests for... | Then implement... |
|-------|-------------------|-------------------|
| 2.1 | API routes, DB persistence, worktree validation | FastAPI routes, SQLite repository |
| 2.2 | Event emission, approval flow, **concurrency** | Event bus, orchestrator service |
| 2.3 | Component rendering, WebSocket updates, **multi-select** | React components, hooks, store |

### Concurrency Test Scenarios

```python
# test_services_orchestrator_concurrency.py

async def test_start_workflow_in_different_worktrees():
    """Can run workflows in separate worktrees concurrently."""
    svc = OrchestratorService(...)

    id1 = await svc.start_workflow("ISSUE-1", "/repo/main", "main")
    id2 = await svc.start_workflow("ISSUE-2", "/repo/feat-a", "feat-a")

    assert len(svc.get_active_workflows()) == 2
    assert id1 != id2


async def test_start_workflow_same_worktree_conflict():
    """Cannot run two workflows in same worktree."""
    svc = OrchestratorService(...)

    await svc.start_workflow("ISSUE-1", "/repo/main", "main")

    with pytest.raises(WorkflowConflictError) as exc:
        await svc.start_workflow("ISSUE-2", "/repo/main", "main")

    assert "already active" in str(exc.value)


async def test_concurrency_limit_reached():
    """Respects max concurrent workflows limit."""
    svc = OrchestratorService(max_concurrent=2, ...)

    await svc.start_workflow("ISSUE-1", "/repo/wt1", "wt1")
    await svc.start_workflow("ISSUE-2", "/repo/wt2", "wt2")

    with pytest.raises(ConcurrencyLimitError):
        await svc.start_workflow("ISSUE-3", "/repo/wt3", "wt3")


async def test_worktree_freed_after_completion():
    """Worktree becomes available after workflow completes."""
    svc = OrchestratorService(...)

    id1 = await svc.start_workflow("ISSUE-1", "/repo/main", "main")
    await wait_for_completion(id1)

    # Same worktree now available
    id2 = await svc.start_workflow("ISSUE-2", "/repo/main", "main")
    assert id2 != id1


async def test_cancel_frees_worktree():
    """Cancelled workflow frees its worktree."""
    svc = OrchestratorService(...)

    id1 = await svc.start_workflow("ISSUE-1", "/repo/main", "main")
    await svc.cancel_workflow(id1)

    # Worktree immediately available
    id2 = await svc.start_workflow("ISSUE-2", "/repo/main", "main")
    assert id2 != id1
```

### Frontend Test Scenarios

```typescript
// JobQueue.test.tsx
describe('JobQueue', () => {
  it('displays all active workflows', () => {
    const workflows = [
      { id: '1', issue_id: 'ISSUE-1', worktree_name: 'main', status: 'running' },
      { id: '2', issue_id: 'ISSUE-2', worktree_name: 'feat-a', status: 'blocked' },
    ];
    render(<JobQueue workflows={workflows} />);

    expect(screen.getByText('ISSUE-1')).toBeInTheDocument();
    expect(screen.getByText('ISSUE-2')).toBeInTheDocument();
  });

  it('highlights selected workflow', () => {
    // ...
  });

  it('calls onSelect when workflow clicked', () => {
    // ...
  });
});

// workflowStore.test.ts
describe('workflowStore', () => {
  it('auto-selects first workflow when none selected', () => {
    const store = useWorkflowStore.getState();
    store.setWorkflows([{ id: '1' }, { id: '2' }]);

    expect(store.selectedWorkflowId).toBe('1');
  });

  it('preserves selection when workflows update', () => {
    const store = useWorkflowStore.getState();
    store.setWorkflows([{ id: '1' }, { id: '2' }]);
    store.selectWorkflow('2');
    store.setWorkflows([{ id: '1' }, { id: '2' }, { id: '3' }]);

    expect(store.selectedWorkflowId).toBe('2');
  });

  it('groups events by workflow_id', () => {
    const store = useWorkflowStore.getState();
    store.addEvent({ workflow_id: '1', message: 'A' });
    store.addEvent({ workflow_id: '2', message: 'B' });
    store.addEvent({ workflow_id: '1', message: 'C' });

    expect(store.eventsByWorkflow.get('1')).toHaveLength(2);
    expect(store.eventsByWorkflow.get('2')).toHaveLength(1);
  });
});
```

### Key Fixtures

```python
@pytest.fixture
def test_client():
    """FastAPI TestClient for API tests."""

@pytest.fixture
def mock_event_bus():
    """Captures emitted events for assertion."""

@pytest.fixture
def sample_workflow_events():
    """Realistic event sequence for UI tests."""

@pytest.fixture
def mock_worktrees(tmp_path):
    """Creates temporary git worktrees for testing."""
    main = tmp_path / "main"
    main.mkdir()
    (main / ".git").mkdir()

    feat_a = tmp_path / "feat-a"
    feat_a.mkdir()
    (feat_a / ".git").write_text("gitdir: ../main/.git/worktrees/feat-a")

    return {"main": str(main), "feat_a": str(feat_a)}

@pytest.fixture
def orchestrator_service(mock_event_bus, mock_worktrees):
    """OrchestratorService with test dependencies."""
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=InMemoryRepository(),
        max_concurrent=5,
    )
```

---

## Open Questions

### Research Required

| Topic | Question | Status |
|-------|----------|--------|
| ~~Claude CLI tokens~~ | ~~Does CLI output token usage?~~ | ✅ Resolved - Use Agent SDK (see Token Tracking) |
| ~~AI Elements library~~ | ~~README mentions it - ready to use?~~ | ✅ Resolved - Not using; custom components match design better |

### Deferred Decisions

| Topic | Current Approach | Revisit When |
|-------|-----------------|--------------|
| Time estimates | Show "--:--" | Have historical data |
| ~~Multi-workflow queue~~ | ~~Single workflow~~ | ✅ Resolved - One per worktree (see Concurrency Model) |
| Notifications | "Coming soon" | Core dashboard stable |
| Authentication | None (localhost only) | Network deployment needed |

### Assumptions

1. SQLite sufficient for single-user local use (WAL mode for concurrent access)
2. Server port 8420 available (configurable via `--port`)
3. Dashboard served from same origin (no CORS needed)
4. Token tracking addable without breaking driver interface
5. Git worktrees work consistently across macOS/Linux (Windows TBD)
6. Maximum 5 concurrent workflows sufficient for typical use
7. `psutil` acceptable as dependency for health endpoint metrics
8. Sequential migrations sufficient (no need for Alembic complexity)
9. **Chrome-only browser support** (no cross-browser testing required)

### Browser Compatibility

**Supported:** Google Chrome (latest stable version)

The dashboard is developed and tested exclusively for Chrome. This simplifies development by:
- No need for cross-browser CSS prefixes
- Can use latest Web APIs without polyfills
- Simplified WebSocket handling (Chrome's implementation is reference)
- Reduced testing matrix

**Unsupported browsers show warning:**

```typescript
// components/BrowserCheck.tsx
function BrowserCheck({ children }: { children: React.ReactNode }) {
  const isChrome = /Chrome/.test(navigator.userAgent) &&
                   !/Edg|OPR/.test(navigator.userAgent);

  if (!isChrome) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-bg-dark text-text-primary">
        <h1 className="text-2xl mb-4">Unsupported Browser</h1>
        <p className="text-text-secondary mb-4">
          Amelia Dashboard is optimized for Google Chrome.
        </p>
        <a
          href="https://www.google.com/chrome/"
          className="text-accent-blue hover:underline"
        >
          Download Chrome
        </a>
      </div>
    );
  }

  return <>{children}</>;
}

// Usage in App.tsx
function App() {
  return (
    <BrowserCheck>
      <BrowserRouter>
        {/* ... */}
      </BrowserRouter>
    </BrowserCheck>
  );
}
```

**Chrome-specific features used:**
- CSS `container-type: inline-size` for responsive components
- `structuredClone()` for deep state copying
- WebSocket with native `ping/pong` handling
- CSS `color-mix()` for dynamic theming

---

## Implementation Notes for Claude Code

This section provides guidance for implementing the dashboard. Follow TDD - write tests first.

### Implementation Order

**Phase 2.1 (Server Foundation):**
1. Create `amelia/server/` package structure
2. Add `ServerConfig` with pydantic-settings
3. Implement SQLite database with migrations
4. Add `WorkflowEvent`, `TokenUsage`, `ExecutionState` models
5. Implement `WorkflowRepository` with state machine validation
6. Create FastAPI app with health endpoints
7. Add `amelia server` CLI command

**Phase 2.2 (Orchestrator Migration):**
1. Implement `EventBus` for pub/sub
2. Create `OrchestratorService` with concurrency control
3. Add `_emit()` with sequence locking
4. Implement approval flow (REST-based)
5. Add WebSocket endpoint with backfill
6. Refactor CLI to thin client using httpx
7. Add `LogRetentionService` (shutdown cleanup)

**Phase 2.3 (Dashboard UI):**
1. Scaffold Vite + React + TypeScript project
2. Add Zustand store with bounded events
3. Implement WebSocket hook with reconnection
4. Build custom components from design mock
5. Add React Flow canvas with BeaconNode/FlightEdge
6. Implement optimistic updates for actions
7. Add accessibility (ARIA labels, keyboard nav)

### Key Files to Create

```
amelia/server/
├── __init__.py
├── main.py                    # FastAPI app setup
├── config.py                  # ServerConfig
├── routes/
│   ├── __init__.py
│   ├── workflows.py           # CRUD + approve/reject/cancel
│   ├── health.py              # /health, /health/live, /health/ready
│   └── websocket.py           # /ws/events
├── services/
│   ├── __init__.py
│   ├── orchestrator_service.py
│   ├── event_bus.py
│   └── log_retention.py
├── database/
│   ├── __init__.py
│   ├── connection.py          # get_connection()
│   ├── repository.py          # WorkflowRepository
│   ├── migrate.py             # MigrationRunner
│   └── migrations/
│       └── 001_initial_schema.sql
└── models/
    ├── __init__.py
    ├── events.py              # EventType, WorkflowEvent
    ├── state.py               # ExecutionState, WorkflowStatus
    └── tokens.py              # TokenUsage
```

### Critical Patterns

**State transitions must use validation:**
```python
# Always validate before updating status
validate_transition(current_status, new_status)
await repository.set_status(workflow_id, new_status)
```

**Events must use sequence locking:**
```python
async with self._sequence_locks[workflow_id]:
    sequence = self._get_next_sequence(workflow_id)
    # ... create and save event
```

**Frontend events must be bounded:**
```typescript
const trimmed = events.slice(-MAX_EVENTS_PER_WORKFLOW);
```

**Correlation IDs for debugging:**
```python
await self._emit(..., correlation_id=correlation_id)
```

### Testing Priorities

1. State machine transitions (all valid/invalid paths)
2. Concurrency limits and worktree conflicts
3. WebSocket backfill with missing events
4. Optimistic updates with rollback
5. Sequence counter race conditions

---

## References

- [Design Mock (HTML)](./amelia-dashboard-dark.html)
- [Design Mock (Image)](./design_mock.jpg)
- [README Phase 2 Description](../../README.md#phase-2-web-ui)
- [remote-agentic-coding-system](https://github.com/ka/remote-agentic-coding-system) - Platform adapter pattern reference
