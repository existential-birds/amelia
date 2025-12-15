# Architecture & Data Flow

This document provides a technical deep dive into Amelia's architecture, component interactions, and data flow.

## System Overview

```mermaid
flowchart TB
    subgraph CLI["CLI Commands"]
        start[start]
        approve[approve]
        reject[reject]
        status[status]
        cancel[cancel]
        server[server]
        plan[plan-only]
        review[review]
    end

    subgraph Client["Client Layer"]
        apiclient[AmeliaClient]
        gitctx[Git Context]
    end

    subgraph Server["Server Layer"]
        fastapi[FastAPI]
        websocket[WebSocket]
        orchsvc[OrchestratorService]
    end

    subgraph Database["Database"]
        sqlite[(SQLite)]
        workflows[workflows]
        events[events]
        tokens[token_usage]
    end

    subgraph Dashboard["Dashboard"]
        react[React UI]
    end

    subgraph Trackers["Trackers"]
        jira[Jira]
        github[GitHub]
        noop[NoOp]
    end

    subgraph Core["Orchestrator"]
        orch[LangGraph]
    end

    subgraph Agents["Agents"]
        arch[Architect]
        dev[Developer]
        rev[Reviewer]
    end

    subgraph Drivers["Drivers"]
        api[OpenAI API]
        claude[Claude CLI]
    end

    subgraph Tools["Tools"]
        shell[SafeShell]
        file[SafeFile]
    end

    CLI --> Client
    Client -->|REST API| Server
    Server --> orchsvc
    orchsvc --> orch
    orchsvc --> Database
    Server -->|Events| websocket
    websocket --> Dashboard
    orch --> Trackers
    orch --> arch & dev & rev
    arch & dev & rev --> Drivers
    Drivers --> Tools

    classDef cliStyle fill:#e3f2fd,stroke:#1976d2
    classDef clientStyle fill:#e1f5fe,stroke:#0288d1
    classDef serverStyle fill:#f3e5f5,stroke:#7b1fa2
    classDef dbStyle fill:#fafafa,stroke:#616161
    classDef dashStyle fill:#fff8e1,stroke:#ffa000
    classDef coreStyle fill:#f3e5f5,stroke:#7b1fa2
    classDef agentStyle fill:#e8f5e9,stroke:#388e3c
    classDef driverStyle fill:#fff3e0,stroke:#f57c00
    classDef trackerStyle fill:#fce4ec,stroke:#c2185b
    classDef toolStyle fill:#eceff1,stroke:#546e7a

    class start,approve,reject,status,cancel,server,plan,review cliStyle
    class apiclient,gitctx clientStyle
    class fastapi,websocket,orchsvc serverStyle
    class sqlite,workflows,events,tokens dbStyle
    class react dashStyle
    class orch coreStyle
    class arch,dev,rev agentStyle
    class api,claude driverStyle
    class jira,github,noop trackerStyle
    class shell,file toolStyle
```

## Component Breakdown

| Layer | Location | Purpose | Key Abstractions |
|-------|----------|---------|------------------|
| **Core** | `amelia/core/` | LangGraph orchestrator, state management, shared types | `ExecutionState`, `TaskDAG`, `Profile`, `Issue` |
| **Agents** | `amelia/agents/` | Specialized AI agents for planning, execution, and review | `Architect`, `Developer`, `Reviewer` |
| **Drivers** | `amelia/drivers/` | LLM abstraction supporting API and CLI backends | `DriverInterface`, `DriverFactory` |
| **Trackers** | `amelia/trackers/` | Issue source abstraction for different platforms | `BaseTracker` (Jira, GitHub, NoOp) |
| **Tools** | `amelia/tools/` | Secure command and file operations with 4-layer security | `SafeShellExecutor`, `SafeFileWriter` |
| **Client** | `amelia/client/` | CLI commands and REST client for server communication | `AmeliaClient`, Typer commands |
| **Server** | `amelia/server/` | FastAPI backend with WebSocket events, SQLite persistence | `OrchestratorService`, `EventBus`, `WorkflowRepository` |

See [File Structure Reference](#file-structure-reference) for detailed file listings.

## Data Flow: `amelia start PROJ-123`

Amelia uses a server-based execution architecture.

### Server-Based Flow

This is the production architecture where CLI commands communicate with a background server via REST API.

#### 1. CLI → Client (`client/cli.py`)

```python
# Detect git worktree context
worktree_path, worktree_name = get_worktree_context()

# Create API client
client = AmeliaClient(base_url="http://localhost:8420")

# Send create workflow request
response = await client.create_workflow(
    issue_id="PROJ-123",
    worktree_path=worktree_path,
    profile="work"
)
# Returns: CreateWorkflowResponse(id="uuid", status="pending")
```

#### 2. Server → OrchestratorService (`server/orchestrator/service.py`)

```python
# Validate worktree (exists, is directory, has .git)
validate_worktree(worktree_path)

# Check concurrency limits (one per worktree, max 5 global)
if worktree_path in active_workflows:
    raise WorkflowConflictError(active_workflow_id)

# Create workflow record in database
workflow = await repository.create_workflow(...)

# Start workflow in background task
asyncio.create_task(run_workflow_with_retry(workflow_id))
```

#### 3. Workflow Execution (LangGraph)

```python
# Load settings and create tracker
settings = load_settings()
profile = settings.profiles[profile_name]
tracker = create_tracker(profile)
issue = tracker.get_issue("PROJ-123")

# Initialize state
initial_state = ExecutionState(profile=profile, issue=issue)

# Run with SQLite checkpointing
checkpointer = AsyncSqliteSaver(db_path)
app = create_orchestrator_graph().compile(checkpointer=checkpointer)
final_state = await app.ainvoke(initial_state, config={"thread_id": workflow_id})
```

#### 4. Real-Time Events → WebSocket → Dashboard

```python
# Emit events at each stage
await event_bus.publish(WorkflowEvent(
    workflow_id=workflow_id,
    event_type=EventType.STAGE_STARTED,
    agent="architect",
    message="Generating implementation plan"
))

# WebSocket broadcasts to subscribed clients
await connection_manager.broadcast(event, workflow_id)

# Dashboard receives and displays updates
```

#### 5. Human Approval Gate

```python
# Workflow blocks at human_approval_node
await event_bus.publish(WorkflowEvent(
    event_type=EventType.APPROVAL_REQUIRED,
    message="Plan ready for review"
))

# User runs: amelia approve
await client.approve_workflow(workflow_id)

# Server resumes workflow
await orchestrator_service.approve_workflow(workflow_id)
```

### Orchestrator Nodes (LangGraph)

#### Node: `architect_node`

```python
# Get driver for LLM communication
driver = DriverFactory.get_driver(profile.driver)

# Generate plan with structured output (TDD-focused)
architect = Architect(driver)
plan_output = await architect.plan(issue, design=optional_design)
# Returns: PlanOutput(task_dag=TaskDAG, markdown_path=Path)

# Update state
state.plan = plan_output.task_dag
```

#### Node: `human_approval_node`

```python
# In server mode: emit event and block (LangGraph interrupt)
if server_mode:
    emit_event(EventType.APPROVAL_REQUIRED)
    return interrupt(state)  # Blocks until approve/reject

# In CLI mode: prompt user directly
approved = typer.confirm("Approve this plan?")
state.human_approved = approved
```

#### Node: `developer_node` (may loop)

```python
# Find tasks with met dependencies
ready_tasks = state.plan.get_ready_tasks()

# Execute tasks (structured or agentic mode)
developer = Developer(driver, execution_mode=profile.execution_mode)
for task in ready_tasks:
    result = await developer.execute_task(task, cwd=worktree_path)
    task.status = "completed" if result["status"] == "completed" else "failed"

# Loop back if pending tasks remain, else proceed to reviewer
```

#### Node: `reviewer_node`

```python
# Get code changes
code_changes = state.code_changes_for_review or get_git_diff("HEAD")

# Run review (single or competitive strategy)
reviewer = Reviewer(driver)
review_result = await reviewer.review(state, code_changes)
# Competitive: parallel Security/Performance/Usability reviews, aggregated

state.review_results.append(review_result)
# If not approved → back to developer_node for fixes
# If approved → END
```

## Sequence Diagram

### Server-Based Architecture

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Client as AmeliaClient
    participant Server as FastAPI Server
    participant Service as OrchestratorService
    participant DB as SQLite
    participant WS as WebSocket
    participant Dashboard
    participant Orchestrator as LangGraph
    participant Agents as Architect/Developer/Reviewer
    participant Driver
    participant LLM

    User->>CLI: amelia start PROJ-123
    CLI->>Client: create_workflow(issue_id, worktree)
    Client->>Server: POST /api/workflows
    Server->>Service: start_workflow()
    Service->>DB: INSERT workflow
    Service-->>Server: workflow_id
    Server-->>Client: CreateWorkflowResponse
    Client-->>CLI: Success
    CLI-->>User: Workflow started

    Note over Service,Orchestrator: Background execution begins

    Service->>Orchestrator: ainvoke(initial_state)
    Orchestrator->>Agents: Architect.plan(issue)
    Agents->>Driver: generate(messages, schema)
    Driver->>LLM: API call
    LLM-->>Driver: TaskDAG JSON
    Driver-->>Agents: parsed TaskDAG
    Agents-->>Orchestrator: TaskDAG

    Orchestrator->>Service: emit(APPROVAL_REQUIRED)
    Service->>DB: INSERT event
    Service->>WS: broadcast(event)
    WS->>Dashboard: event update

    Note over User,Dashboard: Plan displayed in dashboard

    User->>CLI: amelia approve
    CLI->>Client: approve_workflow(id)
    Client->>Server: POST /api/workflows/{id}/approve
    Server->>Service: approve_workflow()
    Service->>Orchestrator: resume with approval

    loop Until all tasks complete
        Orchestrator->>Agents: Developer.execute_task(task)
        Agents->>Driver: execute_tool() or execute_agentic()
        Driver-->>Agents: result
        Agents-->>Orchestrator: task completed
        Orchestrator->>Service: emit(STAGE_COMPLETED)
        Service->>WS: broadcast(event)
    end

    Orchestrator->>Agents: Reviewer.review(state, changes)
    Agents->>Driver: generate(messages, schema)
    Driver->>LLM: API call
    LLM-->>Driver: ReviewResponse JSON
    Driver-->>Agents: ReviewResult
    Agents-->>Orchestrator: ReviewResult

    alt Not Approved
        Orchestrator->>Agents: Developer (loop back for fixes)
    else Approved
        Orchestrator->>Service: emit(WORKFLOW_COMPLETED)
        Service->>DB: UPDATE workflow status
        Service->>WS: broadcast(event)
        WS->>Dashboard: Complete
    end
```

## Key Types

### Configuration Types

#### Profile

```python
class Profile(BaseModel):
    name: str
    driver: DriverType                             # "api:openai" | "cli:claude" | "cli" | "api"
    tracker: TrackerType = "none"                  # "jira" | "github" | "none" | "noop"
    strategy: StrategyType = "single"              # "single" | "competitive"
    execution_mode: ExecutionMode = "structured"   # "structured" | "agentic"
    plan_output_dir: str = "docs/plans"
    working_dir: str | None = None
    retry: RetryConfig = Field(default_factory=RetryConfig)
```

#### RetryConfig

```python
class RetryConfig(BaseModel):
    max_retries: int = Field(default=3, ge=0, le=10)
    base_delay: float = Field(default=1.0, ge=0.1, le=30.0)
    max_delay: float = Field(default=60.0, ge=1.0, le=300.0)
```

#### ServerConfig

```python
class ServerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AMELIA_")

    host: str = "127.0.0.1"
    port: int = Field(default=8420, ge=1, le=65535)
    database_path: Path = Path("~/.amelia/amelia.db")
    log_retention_days: int = 30
    log_retention_max_events: int = 100_000
    websocket_idle_timeout_seconds: float = 300.0
    workflow_start_timeout_seconds: float = 60.0
    max_concurrent: int = 5
```

### Domain Types

#### Issue

```python
class Issue(BaseModel):
    id: str
    title: str
    description: str
    status: str = "open"
```

#### Design

```python
class Design(BaseModel):
    title: str
    goal: str
    architecture: str
    tech_stack: list[str]
    components: list[str]
    data_flow: str | None = None
    error_handling: str | None = None
    testing_strategy: str | None = None
    relevant_files: list[str] = Field(default_factory=list)
    conventions: str | None = None
    raw_content: str
```

### Task Types

#### TaskStep

```python
class TaskStep(BaseModel):
    description: str
    code: str | None = None          # Code to write
    command: str | None = None       # Shell command to run
    expected_output: str | None = None
```

#### FileOperation

```python
class FileOperation(BaseModel):
    operation: Literal["create", "modify", "test"]
    path: str
    line_range: str | None = None
```

#### Task

```python
class Task(BaseModel):
    id: str
    description: str
    status: TaskStatus = "pending"   # "pending" | "in_progress" | "completed" | "failed"
    dependencies: list[str] = Field(default_factory=list)
    files: list[FileOperation] = Field(default_factory=list)
    steps: list[TaskStep] = Field(default_factory=list)
    commit_message: str | None = None
```

#### TaskDAG

```python
class TaskDAG(BaseModel):
    tasks: list[Task]
    original_issue: str

    @field_validator("tasks")
    def validate_task_graph(cls, tasks):
        # Validates dependencies exist and detects cycles

    def get_ready_tasks(self) -> list[Task]:
        # Returns pending tasks with all dependencies completed
```

### State Types

#### ExecutionState

```python
class ExecutionState(BaseModel):
    profile: Profile
    issue: Issue | None = None
    plan: TaskDAG | None = None
    current_task_id: str | None = None
    human_approved: bool | None = None
    review_results: list[ReviewResult] = Field(default_factory=list)
    messages: list[AgentMessage] = Field(default_factory=list)
    code_changes_for_review: str | None = None
    claude_session_id: str | None = None           # For CLI driver session resumption
    workflow_status: Literal["running", "completed", "failed"] = "running"
```

#### ReviewResult

```python
class ReviewResult(BaseModel):
    reviewer_persona: str          # "General", "Security", "Performance", "Usability"
    approved: bool
    comments: list[str]
    severity: Severity             # "low" | "medium" | "high" | "critical"
```

#### AgentMessage

```python
class AgentMessage(BaseModel):
    role: str                      # "system" | "assistant" | "user"
    content: str
    tool_calls: list[Any] | None = None
```

### Server Types

#### WorkflowEvent

```python
class WorkflowEvent(BaseModel):
    id: str                        # UUID
    workflow_id: str
    sequence: int                  # Monotonic counter for ordering
    timestamp: datetime
    agent: str                     # "architect" | "developer" | "reviewer" | "system"
    event_type: EventType          # See EventType enum below
    message: str
    data: dict[str, Any] | None = None
    correlation_id: str | None = None
```

#### EventType (Enum)

```python
class EventType(str, Enum):
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"
    REVIEW_REQUESTED = "review_requested"
    REVIEW_COMPLETED = "review_completed"
    REVISION_REQUESTED = "revision_requested"
    SYSTEM_ERROR = "system_error"
    SYSTEM_WARNING = "system_warning"
```

#### TokenUsage

```python
class TokenUsage(BaseModel):
    id: str
    workflow_id: str
    agent: str
    model: str = "claude-sonnet-4-20250514"
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float | None = None
    timestamp: datetime
```

## Orchestrator Nodes

The LangGraph state machine consists of these nodes:

| Node | Function | Next |
|------|----------|------|
| `architect_node` | Calls `Architect.plan()` | `human_approval_node` |
| `human_approval_node` | Prompts user via typer | Developer (approved) or END (rejected) |
| `developer_node` | Calls `Developer.execute_task()` for ready tasks | Loop (pending tasks) or `reviewer_node` (all complete) |
| `reviewer_node` | Calls `Reviewer.review()` | `developer_node` (not approved) or END (approved) |

## Conditional Edges

```python
# From human_approval_node
def route_after_approval(state):
    if state.human_approved:
        return "developer_node"
    return END

# From developer_node
def route_after_developer(state):
    if has_pending_tasks(state.plan):
        return "developer_node"  # Loop
    return "reviewer_node"

# From reviewer_node
def route_after_review(state):
    if state.review_results[-1].approved:
        return END
    return "developer_node"  # Fix issues
```

## Security Architecture

### Command Execution Security

The `SafeShellExecutor` (`amelia/tools/safe_shell.py`) implements a 4-layer security model:

| Layer | Check | Purpose |
|-------|-------|---------|
| 1. Metacharacters | Blocks `\|`, `;`, `&`, `$`, backticks, `>`, `<` | Prevents shell injection |
| 2. Blocklist | Blocks `sudo`, `su`, `mkfs`, `dd`, `reboot`, etc. | Prevents privilege escalation |
| 3. Dangerous Patterns | Regex detection of `rm -rf /`, `curl \| sh`, etc. | Prevents destructive commands |
| 4. Strict Allowlist | Optional whitelist of ~50 safe commands | High-security mode |

```python
# Example: Command blocked at layer 1
await executor.execute("cat file.txt | grep error")  # ShellInjectionError

# Example: Command blocked at layer 2
await executor.execute("sudo apt install foo")  # BlockedCommandError

# Example: Strict mode
executor = SafeShellExecutor(strict_mode=True)
await executor.execute("git status")  # OK (in allowlist)
await executor.execute("curl https://...")  # CommandNotAllowedError
```

### File Write Security

The `SafeFileWriter` (`amelia/tools/safe_file.py`) protects against path traversal:

- **Path Resolution**: All paths resolved to absolute before validation
- **Directory Restriction**: Writes only allowed within specified directories (default: cwd)
- **Symlink Detection**: Detects and blocks symlink escape attacks at every path component
- **Parent Creation**: Auto-creates parent directories within allowed bounds

```python
# Example: Path traversal blocked
await writer.write("../../../etc/passwd", content)  # PathTraversalError

# Example: Symlink escape blocked
# If /tmp/escape -> /etc, then:
await writer.write("/allowed/tmp/escape/passwd", content)  # PathTraversalError
```

### Exception Hierarchy

```
AmeliaError (base)
├── ConfigurationError          # Missing/invalid configuration
├── SecurityError               # Base for security violations
│   ├── DangerousCommandError   # Dangerous pattern detected
│   ├── BlockedCommandError     # Command in blocklist
│   ├── ShellInjectionError     # Shell metacharacters detected
│   ├── PathTraversalError      # Path escape attempt
│   └── CommandNotAllowedError  # Not in strict allowlist
└── AgenticExecutionError       # Agentic mode failures
```

## Observability

### Event System

Amelia uses an event-driven architecture for real-time observability:

```
Orchestrator → EventBus → WebSocket → Dashboard
                  ↓
              Database (events table)
```

**Event Types**: 17 distinct event types covering workflow lifecycle, file operations, and review cycles.

### Database Schema

```sql
-- Workflow state persistence
CREATE TABLE workflows (
    id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending/running/completed/failed/cancelled
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    failure_reason TEXT,
    state_json TEXT NOT NULL
);

-- Append-only event log
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    workflow_id TEXT REFERENCES workflows(id),
    sequence INTEGER NOT NULL,      -- Monotonic ordering
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    agent TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    data_json TEXT,
    correlation_id TEXT             -- Links related events
);

-- Token usage tracking
CREATE TABLE token_usage (
    id TEXT PRIMARY KEY,
    workflow_id TEXT REFERENCES workflows(id),
    agent TEXT NOT NULL,
    model TEXT DEFAULT 'claude-sonnet-4-20250514',
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cost_usd REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Health Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health/live` | Kubernetes liveness probe |
| `GET /api/health/ready` | Kubernetes readiness probe |
| `GET /api/health` | Detailed health with metrics (uptime, memory, CPU, active workflows) |

### Logging

Loguru-based logging with custom Amelia dashboard colors:

```python
from loguru import logger

logger.debug("Low-level details")    # Sage muted
logger.info("General information")   # Blue
logger.success("Operation succeeded") # Sage green
logger.warning("Potential issue")    # Gold
logger.error("Error occurred")       # Rust red
```

### Log Retention

The `LogRetentionService` runs during graceful shutdown:
- Deletes events older than `AMELIA_LOG_RETENTION_DAYS` (default: 30)
- Enforces `AMELIA_LOG_RETENTION_MAX_EVENTS` per workflow (default: 100,000)

## Key Design Decisions

### Why the Driver Abstraction?

Enterprise environments often prohibit direct API calls due to data retention policies. The CLI driver wraps existing approved tools (like `claude` CLI) that inherit SSO authentication and comply with policies. Users can switch between API (fast prototyping) and CLI (enterprise compliance) without code changes.

### Why Separate Agents Instead of One Big Prompt?

1. **Specialization**: Each agent has focused system prompts, leading to better outputs
2. **Token efficiency**: Only relevant context is passed to each agent
3. **Modularity**: Easy to swap implementations (e.g., different review strategies)
4. **Debuggability**: Clear separation makes it easier to trace issues

### Why pydantic-ai for the API Driver?

1. **Structured outputs**: Forces LLM to return valid JSON matching Pydantic schemas
2. **Type safety**: Catches schema mismatches at runtime
3. **Cleaner code**: No manual JSON parsing or validation

### Why LangGraph for Orchestration?

1. **Built for cycles**: Supports developer ↔ reviewer loop naturally
2. **State management**: Built-in state tracking
3. **Checkpointing**: Resumable workflows with SQLite persistence
4. **Conditional edges**: Clean decision logic
5. **Interrupts**: Supports human-in-the-loop approval gates

### Why a Server Architecture?

1. **Decoupled execution**: CLI returns immediately; workflow runs in background
2. **Dashboard integration**: WebSocket enables real-time UI updates
3. **Workflow management**: Approve, reject, cancel from any terminal or browser
4. **Concurrency control**: Prevents multiple workflows on same worktree
5. **Persistence**: SQLite stores workflow state, events, and token usage
6. **Observability**: Event stream enables monitoring and debugging

## File Structure Reference

```
amelia/
├── agents/
│   ├── __init__.py
│   ├── architect.py          # TaskDAG generation with TDD focus
│   ├── developer.py          # Task execution (structured/agentic modes)
│   └── reviewer.py           # Code review (single/competitive strategies)
├── client/
│   ├── __init__.py
│   ├── api.py                # AmeliaClient REST client
│   ├── cli.py                # CLI commands: start, approve, reject, status, cancel
│   └── git.py                # get_worktree_context() for git detection
├── core/
│   ├── __init__.py
│   ├── constants.py          # Security constants: blocked commands, patterns
│   ├── exceptions.py         # AmeliaError hierarchy
│   ├── orchestrator.py       # LangGraph state machine
│   ├── state.py              # ExecutionState, TaskDAG, Task, etc.
│   └── types.py              # Profile, Issue, Settings, Design, RetryConfig
├── drivers/
│   ├── api/
│   │   ├── __init__.py
│   │   └── openai.py         # OpenAI via pydantic-ai
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── base.py           # CliDriver base with retry logic
│   │   └── claude.py         # Claude CLI wrapper with agentic mode
│   ├── __init__.py
│   ├── base.py               # DriverInterface protocol
│   └── factory.py            # DriverFactory
├── server/
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py     # Async SQLite wrapper, schema init
│   │   └── repository.py     # WorkflowRepository CRUD operations
│   ├── events/
│   │   ├── __init__.py
│   │   ├── bus.py            # EventBus pub/sub
│   │   └── connection_manager.py  # WebSocket client management
│   ├── lifecycle/
│   │   ├── __init__.py
│   │   ├── retention.py      # LogRetentionService
│   │   └── server.py         # Server startup/shutdown
│   ├── models/
│   │   ├── __init__.py
│   │   ├── events.py         # WorkflowEvent, EventType
│   │   ├── requests.py       # CreateWorkflowRequest, RejectRequest
│   │   ├── responses.py      # WorkflowResponse, ActionResponse
│   │   └── tokens.py         # TokenUsage
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   └── service.py        # OrchestratorService
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py         # Health check endpoints
│   │   ├── websocket.py      # /ws/events WebSocket handler
│   │   └── workflows.py      # /api/workflows REST endpoints
│   ├── __init__.py
│   ├── cli.py                # amelia server command
│   ├── config.py             # ServerConfig with AMELIA_* env vars
│   ├── dev.py                # amelia dev command (server + dashboard)
│   └── main.py               # FastAPI application
├── trackers/
│   ├── __init__.py
│   ├── base.py               # BaseTracker protocol
│   ├── factory.py            # create_tracker()
│   ├── github.py             # GitHub via gh CLI
│   ├── jira.py               # Jira REST API
│   └── noop.py               # Placeholder tracker
├── tools/
│   ├── __init__.py
│   ├── safe_file.py          # SafeFileWriter with path traversal protection
│   ├── safe_shell.py         # SafeShellExecutor with 4-layer security
│   └── shell_executor.py     # Backward-compat wrappers
├── utils/
│   ├── __init__.py
│   └── design_parser.py      # LLM-powered Design document parser
├── __init__.py
├── config.py                 # load_settings(), validate_profile()
├── logging.py                # Loguru configuration
└── main.py                   # Typer CLI entry point

dashboard/                    # React + TypeScript frontend
├── src/
│   ├── api/
│   │   └── client.ts         # TypeScript API client
│   ├── components/           # React components
│   ├── hooks/                # Custom React hooks
│   ├── pages/                # Route pages
│   └── stores/               # Zustand state stores
├── package.json
└── vite.config.ts
```
