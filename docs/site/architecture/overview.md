# Architecture & Data Flow

This document provides a technical deep dive into Amelia's architecture, component interactions, and data flow.

## What Amelia Does Today

**Phase 1 (Complete):** Multi-agent orchestration with the **Architect → Developer → Reviewer** loop. Issues flow through planning, execution, and review stages with human approval gates before any code ships. Supports both API-based (OpenRouter) and CLI-based (Claude) LLM drivers, with Jira and GitHub issue tracker integrations.

```
Issue → [Queue] → Architect (plan) → Human Approval → Developer (execute) ↔ Reviewer (review) → Done
           ↓
     (optional)
   pending state
```

**Queue Step (Optional):** With `--queue` flag, workflows enter `pending` state instead of immediate execution. Use `amelia run` to start queued workflows. The `--plan` flag runs the Architect while queued, setting `planned_at` when complete.

**Phase 2 (In Progress):** Observable orchestration through a local web dashboard. FastAPI server with SQLite persistence, REST API for workflow management, React dashboard with real-time WebSocket updates, and agentic execution with streaming tool calls.

## Design Philosophy

Amelia follows the four-layer agent architecture pattern established in industry research:

| Layer | Amelia Implementation |
|-------|----------------------|
| **Model** | Pluggable LLM drivers (API or CLI-wrapped) |
| **Tools** | SafeShell, SafeFile with defense-in-depth security |
| **Orchestration** | LangGraph state machine with human approval gates |
| **Deployment** | Local-first server with SQLite persistence |

The [roadmap](/reference/roadmap) extends this foundation toward enterprise-grade deployment with evaluation-gated releases, distributed tracing, and agent authorization controls. See [Design Principles](/reference/roadmap#design-principles) for the guiding philosophy.

## Research Foundation

Amelia's architecture incorporates findings from industry research on agentic AI systems:

- **Orchestrator-worker pattern**: Specialized agents (Architect, Developer, Reviewer) coordinated through state machine
- **Iterative refinement**: Developer + Reviewer loop implements the generator-critic pattern
- **Defense in depth**: Layered guardrails (metacharacters -> blocklist -> patterns -> allowlist)
- **Trajectory as truth**: Full execution trace persisted for debugging, not just final outputs

See the [roadmap](/reference/roadmap#research-foundation) for complete research synthesis.

## Component Breakdown

| Layer | Location | Purpose | Key Abstractions |
|-------|----------|---------|------------------|
| **Core** | `amelia/core/` | LangGraph orchestrator, state management, shared types | `ExecutionState`, `AgenticState`, `ToolCall`, `ToolResult`, `Profile`, `Issue` |
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
initial_state = ExecutionState(profile_id=profile.name, issue=issue)

# Run with SQLite checkpointing and profile in config
checkpointer = AsyncSqliteSaver(db_path)
app = create_orchestrator_graph().compile(checkpointer=checkpointer)
config = {
    "configurable": {
        "thread_id": workflow_id,
        "profile": profile,  # Profile passed via config, not state
    }
}
final_state = await app.ainvoke(initial_state, config=config)
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

# Generate markdown plan with goal extraction
architect = Architect(driver)
plan_output = await architect.plan(state=state, profile=profile, workflow_id=workflow_id)
# Returns: PlanOutput(markdown_content=str, markdown_path=Path, goal=str, key_files=list)

# Update state with goal for Developer
state = state.model_copy(update={
    "goal": plan_output.goal,
    "plan_markdown": plan_output.markdown_content,
    "plan_path": plan_output.markdown_path,
})
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

#### Node: `developer_node` (agentic execution)

```python
# Execute goal agentically using tool calls
developer = Developer(driver)
async for event in developer.execute_agentic(
    goal=state.goal,
    cwd=worktree_path,
    session_id=state.driver_session_id,
):
    # Handle streaming events: tool_call, tool_result, thinking, result
    if event.type == "tool_call":
        state = state.model_copy(update={
            "tool_calls": state.tool_calls + [event.tool_call]
        })
    elif event.type == "result":
        state = state.model_copy(update={
            "agentic_status": "completed",
            "final_response": event.content,
        })

# Proceed to reviewer when complete
```

#### Node: `reviewer_node`

```python
# Get code changes
code_changes = state.code_changes_for_review or get_git_diff("HEAD")

# Run review (single or competitive strategy)
reviewer = Reviewer(driver)
review_result = await reviewer.review(state, code_changes)
# Competitive: parallel Security/Performance/Usability reviews, aggregated

state.last_review = review_result

# If not approved and iteration < max → back to developer_node for fixes
# If approved or max iterations reached → END
```

## Key Types

### Configuration Types

#### Profile

```python
class Profile(BaseModel):
    name: str
    driver: DriverType                             # "api:openrouter" | "cli:claude" | "cli" | "api"
    model: str | None = None                       # Model identifier for API drivers
    tracker: TrackerType = "none"                  # "jira" | "github" | "none" | "noop"
    strategy: StrategyType = "single"              # "single" | "competitive"
    working_dir: str | None = None
    plan_output_dir: str = "docs/plans"
    retry: RetryConfig = Field(default_factory=RetryConfig)
    max_review_iterations: int = 3                 # Max review-fix loop iterations
    max_task_review_iterations: int = 5        # Per-task review iteration limit
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

### Agentic Types

#### ToolCall

```python
class ToolCall(BaseModel):
    """A tool call made by the LLM during agentic execution."""
    model_config = ConfigDict(frozen=True)

    id: str                          # Unique identifier for this call
    tool_name: str                   # Name of the tool (run_shell_command, write_file)
    tool_input: dict[str, Any]       # Input parameters for the tool
    timestamp: str | None = None     # When the call was made (ISO format)
```

#### ToolResult

```python
class ToolResult(BaseModel):
    """Result from a tool execution."""
    model_config = ConfigDict(frozen=True)

    call_id: str                     # ID of the ToolCall this result is for
    tool_name: str                   # Name of the tool that was called
    output: str                      # Output from the tool (stdout, file content, etc.)
    success: bool                    # Whether the tool executed successfully
    error: str | None = None         # Error message if success is False
    duration_ms: int | None = None   # Execution time in milliseconds
```

#### AgenticStatus

```python
AgenticStatus = Literal["running", "awaiting_approval", "completed", "failed", "cancelled"]
```

### State Types

#### ExecutionState

```python
class ExecutionState(BaseModel):
    """State for the LangGraph orchestrator execution.

    This model is frozen (immutable) to support the stateless reducer pattern.
    """
    model_config = ConfigDict(frozen=True)

    profile_id: str                                # Profile name for replay determinism
    issue: Issue | None = None
    design: Design | None = None                   # Optional design context
    goal: str | None = None                        # High-level goal for agentic execution
    plan_markdown: str | None = None               # Markdown plan content from Architect
    plan_path: Path | None = None                  # Path where markdown plan was saved
    human_approved: bool | None = None
    human_feedback: str | None = None              # Optional feedback from human
    last_review: ReviewResult | None = None        # Most recent review result
    code_changes_for_review: str | None = None
    driver_session_id: str | None = None           # For driver session continuity
    workflow_status: Literal["running", "completed", "failed", "aborted"] = "running"
    agent_history: Annotated[list[str], operator.add] = Field(default_factory=list)

    # Agentic execution tracking
    tool_calls: Annotated[list[ToolCall], operator.add] = Field(default_factory=list)
    tool_results: Annotated[list[ToolResult], operator.add] = Field(default_factory=list)
    agentic_status: AgenticStatus = "running"
    final_response: str | None = None
    error: str | None = None
    review_iteration: int = 0                      # Current iteration in review-fix loop

    # Task execution tracking (for multi-task plans)
    total_tasks: int | None = None             # Parsed from plan (None = legacy single-session)
    current_task_index: int = 0                # 0-indexed, increments after each task passes review
    task_review_iteration: int = 0             # Resets to 0 when moving to next task
```

**Note**: The full `Profile` object is not stored in state for determinism. Instead, it's passed via LangGraph's RunnableConfig:

```python
config = {
    "configurable": {
        "thread_id": workflow_id,
        "profile": profile,  # Runtime config passed here
    }
}
```

This ensures that when replaying from checkpoints, the profile configuration at invocation time is used, preventing bugs from stale profile data in checkpointed state.

**Agentic Execution**: The `tool_calls` and `tool_results` fields use the `operator.add` reducer, allowing parallel-safe appending of tool history during streaming execution.

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
| `architect_node` | Calls `Architect.plan()` to generate goal and markdown plan | `human_approval_node` |
| `plan_validator_node` | Validates plan and extracts task count | `human_approval_node` |
| `human_approval_node` | Prompts user via typer or dashboard | Developer (approved) or END (rejected) |
| `developer_node` | Executes agentically via `execute_agentic()` with streaming tool calls | `reviewer_node` |
| `reviewer_node` | Calls `Reviewer.review()` | `developer_node` (changes requested) or END (approved) |
| `next_task_node` | Advances to next task after commit | `developer_node` or END |
| `commit_task_changes` | Commits changes after task review passes | `next_task_node` |

## Conditional Edges

```python
# From human_approval_node
def route_after_approval(state):
    if state.human_approved:
        return "developer_node"
    return END

# From reviewer_node
def route_after_review(state, config):
    profile = config["configurable"]["profile"]
    if state.last_review and state.last_review.approved:
        return END
    if state.review_iteration >= profile.max_review_iterations:
        return END  # Stop after max iterations
    return "developer_node"  # Fix issues

# From reviewer_node (task-based execution)
def route_after_task_review(state, config):
    profile = config["configurable"]["profile"]
    if state.last_review and state.last_review.approved:
        return "commit_task_changes"  # Commit and move to next task
    if state.task_review_iteration >= profile.max_task_review_iterations:
        return END  # Max iterations for this task
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

## Observability Architecture

Amelia implements the three pillars of observability:

| Pillar | Implementation | Purpose |
|--------|----------------|---------|
| **Logs** | Loguru structured logging with agent context | Discrete events for debugging |
| **Traces** | Event correlation IDs linking related operations | Causal path through workflow |
| **Metrics** | Token usage tracking per agent and workflow | Cost and efficiency monitoring |

**Why trajectory matters:** Final outputs alone don't indicate agent quality. Amelia persists the full execution trace (tool calls, results, agent decisions) enabling post-hoc debugging and process evaluation. This follows the principle that "the trajectory is the truth"—understanding how an agent reached a conclusion is as important as the conclusion itself.

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

### Why Agentic Execution?

The Developer agent uses autonomous tool-calling execution where the LLM decides what actions to take. This approach:
1. **Leverages model capabilities**: Modern LLMs excel at autonomous decision-making
2. **Reduces brittleness**: No rigid step-by-step plans that break on unexpected situations
3. **Enables streaming**: Real-time visibility into agent reasoning and actions
4. **Simplifies orchestration**: Fewer state transitions and edge cases to handle

### Why LangGraph for Orchestration?

1. **Built for cycles**: Supports developer ↔ reviewer loop naturally
2. **State management**: Built-in state tracking with reducers for streaming data
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
│   ├── architect.py          # Markdown plan generation with goal extraction
│   ├── developer.py          # Agentic execution with streaming tool calls
│   └── reviewer.py           # Code review (single/competitive strategies)
├── client/
│   ├── __init__.py
│   ├── api.py                # AmeliaClient REST client
│   ├── cli.py                # CLI commands: start, approve, reject, status, cancel
│   └── git.py                # get_worktree_context() for git detection
├── core/
│   ├── __init__.py
│   ├── agentic_state.py      # ToolCall, ToolResult, AgenticState
│   ├── constants.py          # Security constants: blocked commands, patterns
│   ├── exceptions.py         # AmeliaError hierarchy
│   ├── orchestrator.py       # LangGraph state machine
│   ├── state.py              # ExecutionState with agentic execution tracking
│   └── types.py              # Profile, Issue, Settings, Design, RetryConfig
├── drivers/
│   ├── api/
│   │   ├── __init__.py
│   │   └── openrouter.py     # OpenRouter API driver
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
