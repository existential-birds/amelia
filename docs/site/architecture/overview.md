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
| **Tools** | LLM-native tools via driver (shell, file, search) |
| **Orchestration** | LangGraph state machine with human approval gates |
| **Deployment** | Local-first server with SQLite persistence |

The [roadmap](/reference/roadmap) extends this foundation with evaluation-gated releases, distributed tracing, and agent authorization controls. See [Design Principles](/reference/roadmap#design-principles) for the guiding philosophy.

## Research Foundation

Amelia's architecture incorporates findings from industry research on agentic AI systems:

- **Orchestrator-worker pattern**: Specialized agents (Architect, Developer, Reviewer) coordinated through state machine
- **Iterative refinement**: Developer + Reviewer loop implements the generator-critic pattern
- **Human-in-the-loop**: Approval gates before code execution and review cycles
- **Trajectory as truth**: Full execution trace persisted for debugging, not just final outputs

See the [roadmap](/reference/roadmap#research-foundation) for complete research synthesis.

## Component Breakdown

| Layer | Location | Purpose | Key Abstractions |
|-------|----------|---------|------------------|
| **Core** | `amelia/core/` | Shared types and agentic state | `AgenticState`, `ToolCall`, `ToolResult`, `Profile`, `Issue` |
| **Pipelines** | `amelia/pipelines/` | LangGraph state machines and workflow logic | `BasePipelineState`, `ImplementationState`, `Pipeline` |
| **Agents** | `amelia/agents/` | Specialized AI agents for planning, execution, and review | `Architect`, `Developer`, `Reviewer` |
| **Drivers** | `amelia/drivers/` | LLM abstraction supporting API and CLI backends | `DriverInterface`, `DriverFactory` |
| **Trackers** | `amelia/trackers/` | Issue source abstraction for different platforms | `BaseTracker` (Jira, GitHub, NoOp) |
| **Tools** | `amelia/tools/` | Git utilities and shell helpers | `git_utils`, `shell_executor` |
| **Client** | `amelia/client/` | CLI commands and REST client for server communication | `AmeliaClient`, Typer commands |
| **Server** | `amelia/server/` | FastAPI backend with WebSocket events, SQLite persistence | `OrchestratorService`, `EventBus`, `WorkflowRepository` |

See [File Structure Reference](#file-structure-reference) for detailed file listings.

## Data Flow: `amelia start PROJ-123`

Amelia uses a server-based execution architecture.

### Server-Based Flow

This is the production architecture where CLI commands communicate with a background server via REST API.

#### 1. CLI to Client

The CLI detects git worktree context and sends requests to the server via the API client.

See [`amelia/client/cli.py`](https://github.com/existential-birds/amelia/blob/main/amelia/client/cli.py) and [`amelia/client/api.py`](https://github.com/existential-birds/amelia/blob/main/amelia/client/api.py) for implementation.

#### 2. Server to OrchestratorService

The server validates the worktree, checks concurrency limits (one active workflow per worktree, max 5 global), creates a workflow record in the database, and starts the workflow in a background task.

See [`OrchestratorService`](https://github.com/existential-birds/amelia/blob/main/amelia/server/orchestrator/service.py) for implementation.

#### 3. Workflow Execution (LangGraph)

The workflow loads settings, creates a tracker for the issue source, initializes state, and runs the LangGraph pipeline with SQLite checkpointing. The profile is passed via LangGraph's RunnableConfig for deterministic replay.

See the implementation pipeline:
- [`ImplementationPipeline`](https://github.com/existential-birds/amelia/blob/main/amelia/pipelines/implementation/pipeline.py) - Pipeline entry point
- [`create_implementation_graph()`](https://github.com/existential-birds/amelia/blob/main/amelia/pipelines/implementation/graph.py) - LangGraph state machine

#### 4. Real-Time Events to Dashboard

Events are emitted at each stage and broadcast to WebSocket clients for real-time dashboard updates.

See the event system:
- [`EventBus`](https://github.com/existential-birds/amelia/blob/main/amelia/server/events/bus.py) - Pub/sub event bus
- [`ConnectionManager`](https://github.com/existential-birds/amelia/blob/main/amelia/server/events/connection_manager.py) - WebSocket client management

#### 5. Human Approval Gate

The workflow blocks at the human approval node (using LangGraph interrupt), emits an `APPROVAL_REQUIRED` event, and waits for user approval via CLI (`amelia approve`) or dashboard.

### Orchestrator Nodes (LangGraph)

See [`amelia/pipelines/implementation/nodes.py`](https://github.com/existential-birds/amelia/blob/main/amelia/pipelines/implementation/nodes.py) for implementation-specific nodes and [`amelia/pipelines/nodes.py`](https://github.com/existential-birds/amelia/blob/main/amelia/pipelines/nodes.py) for shared nodes.

**Node: `call_architect_node`** - Gets driver, calls `Architect.plan()` to generate markdown plan with goal extraction, updates state with plan content.

**Node: `plan_validator_node`** - Validates plan file and extracts structured fields (goal, plan_markdown, key_files) using lightweight LLM extraction.

**Node: `human_approval_node`** - In server mode: emits `APPROVAL_REQUIRED` event and uses LangGraph interrupt to block. In CLI mode: prompts user directly via typer.

**Node: `developer_node`** - Executes goal agentically using streaming tool calls. Handles events (tool_call, tool_result, thinking, result) and updates state with tool history.

**Node: `reviewer_node`** - Gets code changes, runs `Reviewer.review()`, updates state with review result. Routes back to developer if changes requested, or to END if approved.

## Key Types

### Configuration Types

#### Profile

See [`Profile`](https://github.com/existential-birds/amelia/blob/main/amelia/core/types.py#L37-L72) for the full definition. Key fields:

- `driver`: LLM driver type (`api`, `cli`)
- `model`: LLM model identifier
- `tracker`: Issue tracker type (`jira`, `github`, `none`)
- `max_review_iterations`: Maximum review-fix loop iterations
- `max_task_review_iterations`: Per-task review iteration limit

#### RetryConfig

See [`RetryConfig`](https://github.com/existential-birds/amelia/blob/main/amelia/core/types.py#L17-L34) for the full definition.

#### ServerConfig

See [`ServerConfig`](https://github.com/existential-birds/amelia/blob/main/amelia/server/config.py#L8-L113) for the full definition. All settings can be overridden via `AMELIA_*` environment variables.

### Domain Types

See the source files:
- [`Issue`](https://github.com/existential-birds/amelia/blob/main/amelia/core/types.py#L84-L96) - Issue or ticket to be worked on
- [`Design`](https://github.com/existential-birds/amelia/blob/main/amelia/core/types.py#L99-L116) - Design document for implementation

### Agentic Types

See [`amelia/core/agentic_state.py`](https://github.com/existential-birds/amelia/blob/main/amelia/core/agentic_state.py) for the full definitions:

- [`ToolCall`](https://github.com/existential-birds/amelia/blob/main/amelia/core/agentic_state.py#L14-L29) - A tool call made by the LLM during agentic execution
- [`ToolResult`](https://github.com/existential-birds/amelia/blob/main/amelia/core/agentic_state.py#L32-L51) - Result from a tool execution
- [`AgenticStatus`](https://github.com/existential-birds/amelia/blob/main/amelia/core/agentic_state.py#L11) - Execution status literal type

### State Types

Amelia uses a pipeline-based state architecture with a common base class and pipeline-specific extensions.

#### BasePipelineState

See [`BasePipelineState`](https://github.com/existential-birds/amelia/blob/main/amelia/pipelines/base.py#L53-L95) for the common state fields shared by all pipelines (workflow identity, lifecycle, human interaction, agentic execution).

#### ImplementationState

See [`ImplementationState`](https://github.com/existential-birds/amelia/blob/main/amelia/pipelines/implementation/state.py#L25-L75) for the implementation pipeline state, which extends `BasePipelineState` with:
- Domain data (issue, design, plan)
- Human approval workflow
- Code review tracking
- Multi-task execution

**Note**: The full `Profile` object is not stored in state for determinism. Instead, it's passed via LangGraph's RunnableConfig. This ensures that when replaying from checkpoints, the profile configuration at invocation time is used, preventing bugs from stale profile data in checkpointed state.

**Agentic Execution**: The `tool_calls` and `tool_results` fields use the `operator.add` reducer, allowing parallel-safe appending of tool history during streaming execution.

#### ReviewResult

See [`ReviewResult`](https://github.com/existential-birds/amelia/blob/main/amelia/core/types.py#L122-L138) for the full definition.

### Server Types

See [`amelia/server/models/events.py`](https://github.com/existential-birds/amelia/blob/main/amelia/server/models/events.py) for the full definitions:

- [`WorkflowEvent`](https://github.com/existential-birds/amelia/blob/main/amelia/server/models/events.py#L150-L238) - Event for activity log and real-time updates
- [`EventType`](https://github.com/existential-birds/amelia/blob/main/amelia/server/models/events.py#L24-L108) - Exhaustive list of workflow event types (lifecycle, stage, approval, artifact, review, agent message, and system events)
- [`EventLevel`](https://github.com/existential-birds/amelia/blob/main/amelia/server/models/events.py#L10-L22) - Event severity level for filtering and retention (info, debug, trace)

#### TokenUsage

See [`TokenUsage`](https://github.com/existential-birds/amelia/blob/main/amelia/server/models/tokens.py#L47-L96) for the full definition. Includes cache token semantics for cost calculation with prompt caching.

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

See [`Database.ensure_schema()`](https://github.com/existential-birds/amelia/blob/main/amelia/server/database/connection.py#L254-L471) for the complete schema definition. Core tables:

| Table | Purpose |
|-------|---------|
| `workflows` | Workflow state persistence with status tracking |
| `events` | Append-only event log with monotonic ordering |
| `token_usage` | Token consumption tracking per agent |
| `prompts` / `prompt_versions` | Prompt configuration and versioning |
| `brainstorm_sessions` / `brainstorm_messages` | Brainstorming chat sessions |

### Health Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health/live` | Kubernetes liveness probe |
| `GET /api/health/ready` | Kubernetes readiness probe |
| `GET /api/health` | Detailed health with metrics (uptime, memory, CPU, active workflows) |

### Logging

Loguru-based logging with custom Amelia dashboard colors. See [`amelia/logging.py`](https://github.com/existential-birds/amelia/blob/main/amelia/logging.py) for configuration.

| Level | Color | Usage |
|-------|-------|-------|
| `debug` | Sage muted | Low-level details |
| `info` | Blue | General information |
| `success` | Sage green | Operation succeeded |
| `warning` | Gold | Potential issue |
| `error` | Rust red | Error occurred |

### Log Retention

The `LogRetentionService` runs during graceful shutdown:
- Deletes events older than `AMELIA_LOG_RETENTION_DAYS` (default: 30)
- Enforces `AMELIA_LOG_RETENTION_MAX_EVENTS` per workflow (default: 100,000)

## Key Design Decisions

### Why the Driver Abstraction?

Some environments prohibit direct API calls due to data retention policies. The CLI driver wraps existing approved tools (like `claude` CLI) that inherit SSO authentication and comply with policies. Users can switch between API (fast prototyping) and CLI (policy compliance) without code changes.

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
│   ├── architect.py          # Markdown plan generation with goal extraction
│   ├── developer.py          # Agentic execution with streaming tool calls
│   └── reviewer.py           # Code review
├── client/
│   ├── api.py                # AmeliaClient REST client
│   ├── cli.py                # CLI commands: start, approve, reject, status, cancel
│   └── git.py                # get_worktree_context() for git detection
├── core/
│   ├── agentic_state.py      # ToolCall, ToolResult, AgenticState, AgenticStatus
│   ├── constants.py          # Security constants: blocked commands, patterns
│   ├── exceptions.py         # AmeliaError hierarchy
│   ├── extraction.py         # LLM-based structured extraction utilities
│   └── types.py              # Profile, Issue, Settings, Design, RetryConfig, ReviewResult
├── pipelines/
│   ├── base.py               # BasePipelineState, Pipeline protocol
│   ├── nodes.py              # Shared LangGraph node functions
│   ├── registry.py           # Pipeline registry
│   ├── implementation/
│   │   ├── graph.py          # LangGraph state machine for implementation
│   │   ├── nodes.py          # Implementation-specific nodes
│   │   ├── pipeline.py       # ImplementationPipeline class
│   │   ├── routing.py        # Conditional edge routing logic
│   │   └── state.py          # ImplementationState
│   └── review/               # Review-only pipeline
├── drivers/
│   ├── api/
│   │   └── openrouter.py     # OpenRouter API driver
│   ├── cli/
│   │   ├── base.py           # CliDriver base with retry logic
│   │   └── claude.py         # Claude CLI wrapper with agentic mode
│   ├── base.py               # DriverInterface protocol
│   └── factory.py            # DriverFactory
├── server/
│   ├── database/
│   │   ├── connection.py     # Async SQLite wrapper, schema init
│   │   └── repository.py     # WorkflowRepository CRUD operations
│   ├── events/
│   │   ├── bus.py            # EventBus pub/sub
│   │   └── connection_manager.py  # WebSocket client management
│   ├── lifecycle/
│   │   ├── retention.py      # LogRetentionService
│   │   └── server.py         # Server startup/shutdown
│   ├── models/
│   │   ├── events.py         # WorkflowEvent, EventType, EventLevel
│   │   ├── requests.py       # CreateWorkflowRequest, RejectRequest
│   │   ├── responses.py      # WorkflowResponse, ActionResponse
│   │   ├── state.py          # ServerExecutionState, WorkflowStatus
│   │   └── tokens.py         # TokenUsage, TokenSummary
│   ├── orchestrator/
│   │   └── service.py        # OrchestratorService
│   ├── routes/
│   │   ├── health.py         # Health check endpoints
│   │   ├── websocket.py      # /ws/events WebSocket handler
│   │   └── workflows.py      # /api/workflows REST endpoints
│   ├── cli.py                # amelia server command
│   ├── config.py             # ServerConfig with AMELIA_* env vars
│   ├── dev.py                # amelia dev command (server + dashboard)
│   └── main.py               # FastAPI application
├── trackers/
│   ├── base.py               # BaseTracker protocol
│   ├── factory.py            # create_tracker()
│   ├── github.py             # GitHub via gh CLI
│   ├── jira.py               # Jira REST API
│   └── none.py               # Placeholder tracker
├── tools/
│   ├── git_utils.py          # Git operations (diff, commit, worktree)
│   └── shell_executor.py     # Simple shell command execution
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
