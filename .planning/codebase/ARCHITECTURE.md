# Architecture

**Analysis Date:** 2026-03-13

## Pattern Overview

**Overall:** Client-Server Agentic Orchestrator with LangGraph State Machines

**Key Characteristics:**
- LangGraph-based pipeline state machines coordinate specialized AI agents (Architect, Developer, Reviewer, Evaluator)
- FastAPI server provides REST API + WebSocket events; Typer CLI acts as thin client
- Immutable Pydantic state models with reducer patterns for append-only fields
- Protocol-based abstractions for drivers, sandboxes, and trackers enable pluggable backends
- Event-driven architecture: EventBus broadcasts workflow events to WebSocket clients and log subscribers
- React dashboard (Vite + TypeScript) communicates with the API server

## Layers

**CLI Layer (Thin Client):**
- Purpose: User-facing commands that delegate to the API server
- Location: `amelia/main.py`, `amelia/client/`, `amelia/cli/`
- Contains: Typer commands (`start`, `plan`, `approve`, `reject`, `status`, `cancel`, `resume`, `review`, `run`), HTTP client (`AmeliaClient`), WebSocket streaming
- Depends on: Server API via HTTP/WebSocket
- Used by: End users from terminal

**Server Layer (FastAPI):**
- Purpose: REST API, WebSocket events, lifecycle management, dependency injection
- Location: `amelia/server/`
- Contains: FastAPI app (`amelia/server/main.py`), routes (`amelia/server/routes/`), models (`amelia/server/models/`), database repos (`amelia/server/database/`), event system (`amelia/server/events/`), lifecycle services (`amelia/server/lifecycle/`), DI module (`amelia/server/dependencies.py`)
- Depends on: Orchestrator, Pipelines, Database (PostgreSQL via asyncpg)
- Used by: CLI client, Dashboard frontend

**Orchestrator Layer:**
- Purpose: Manages concurrent workflow execution, state transitions, checkpointing
- Location: `amelia/server/orchestrator/service.py`
- Contains: `OrchestratorService` class - creates/runs/resumes workflows, manages concurrency limits, handles transient error retries
- Depends on: Pipelines, EventBus, WorkflowRepository, ProfileRepository, LangGraph checkpointer
- Used by: Server routes

**Pipeline Layer (LangGraph State Machines):**
- Purpose: Define workflow graphs as composable state machines
- Location: `amelia/pipelines/`
- Contains:
  - Base abstractions: `amelia/pipelines/base.py` (`Pipeline` protocol, `BasePipelineState`)
  - Implementation pipeline: `amelia/pipelines/implementation/` (Architect -> Plan Validation -> Human Approval -> Developer <-> Reviewer loop)
  - Review pipeline: `amelia/pipelines/review/` (Reviewer -> Evaluation -> Developer fix loop)
  - Shared nodes: `amelia/pipelines/nodes.py` (developer and reviewer node functions)
  - Routing logic: `amelia/pipelines/implementation/routing.py`, `amelia/pipelines/review/routing.py`
  - Pipeline registry: `amelia/pipelines/registry.py`
- Depends on: Agents, Drivers, Core types
- Used by: Orchestrator

**Agent Layer:**
- Purpose: Specialized AI agents with domain-specific prompts and logic
- Location: `amelia/agents/`
- Contains:
  - `amelia/agents/architect.py` - Architect: generates implementation plans from issues
  - `amelia/agents/developer.py` - Developer: executes code changes agentically with tool access
  - `amelia/agents/reviewer.py` - Reviewer: performs multi-persona code review
  - `amelia/agents/evaluator.py` - Evaluator: evaluates review results into actionable items
  - `amelia/agents/oracle.py` - Oracle: on-demand consultant for stuck situations
  - Prompt management: `amelia/agents/prompts/` (defaults, models, resolver)
  - Structured output schemas: `amelia/agents/schemas/`
- Depends on: Drivers, Core types
- Used by: Pipeline nodes

**Driver Layer:**
- Purpose: Abstraction over LLM execution backends
- Location: `amelia/drivers/`
- Contains:
  - Protocol: `amelia/drivers/base.py` (`DriverInterface`, `AgenticMessage`, `DriverUsage`)
  - Factory: `amelia/drivers/factory.py` (`get_driver()`)
  - Implementations:
    - `amelia/drivers/cli/claude.py` - Claude CLI via claude-agent-sdk
    - `amelia/drivers/cli/codex.py` - Codex CLI driver
    - `amelia/drivers/api/deepagents.py` - API driver via deepagents/langchain-openai (OpenRouter)
  - Container driver: `amelia/sandbox/driver.py` - delegates to sandbox worker
- Depends on: claude-agent-sdk, deepagents, langchain-openai
- Used by: Agents

**Sandbox Layer:**
- Purpose: Isolated execution environments for code changes
- Location: `amelia/sandbox/`
- Contains:
  - Protocol: `amelia/sandbox/provider.py` (`SandboxProvider`)
  - Docker: `amelia/sandbox/docker.py` (`DockerSandboxProvider`)
  - Daytona: `amelia/sandbox/daytona.py` (`DaytonaSandboxProvider`)
  - Container driver: `amelia/sandbox/driver.py` (`ContainerDriver`)
  - Worker: `amelia/sandbox/worker.py` (runs inside sandbox)
  - Worktree management: `amelia/sandbox/worktree.py`
  - Network isolation: `amelia/sandbox/network.py`
  - LLM proxy: `amelia/sandbox/proxy.py`
- Depends on: Docker/Daytona SDKs, Driver interfaces
- Used by: Driver factory, Orchestrator

**Knowledge Layer:**
- Purpose: RAG-based document ingestion, embedding, and search
- Location: `amelia/knowledge/`
- Contains:
  - `amelia/knowledge/service.py` - Background ingestion service
  - `amelia/knowledge/ingestion.py` - Document parsing and chunking pipeline
  - `amelia/knowledge/embeddings.py` - Embedding client (OpenRouter)
  - `amelia/knowledge/repository.py` - pgvector-backed storage
  - `amelia/knowledge/search.py` - Semantic search
  - `amelia/knowledge/models.py` - Knowledge data models
- Depends on: docling, pgvector, asyncpg
- Used by: Server routes, Agents

**Core Layer:**
- Purpose: Shared types, constants, utilities
- Location: `amelia/core/`
- Contains:
  - `amelia/core/types.py` - All shared Pydantic models (Profile, Issue, AgentConfig, ReviewResult, etc.)
  - `amelia/core/agentic_state.py` - AgenticState, ToolCall, ToolResult
  - `amelia/core/constants.py` - Tool names, plan path resolution
  - `amelia/core/exceptions.py` - Custom exception types
  - `amelia/core/retry.py` - Retry with exponential backoff
  - `amelia/core/extraction.py`, `amelia/core/text.py`, `amelia/core/utils.py`
- Depends on: Pydantic, standard library
- Used by: All other layers

**Dashboard (Frontend):**
- Purpose: Web UI for monitoring and managing workflows
- Location: `dashboard/`
- Contains: React + TypeScript SPA with Vite, React Router v7, Zustand stores
- Depends on: Server REST API + WebSocket
- Used by: End users via browser

## Data Flow

**Implementation Workflow (Full):**

1. User runs `amelia start <issue-id>` or creates workflow via dashboard
2. CLI client sends POST to `/api/workflows` on the FastAPI server
3. `OrchestratorService` creates `ServerExecutionState`, persists to PostgreSQL
4. `OrchestratorService` creates LangGraph `ImplementationState`, builds graph from `create_implementation_graph()`
5. Graph execution begins:
   - `architect_node`: Architect agent generates plan via driver (agentic tool-calling loop)
   - `plan_validator_node`: Validates plan structure, may loop back to architect
   - `human_approval_node`: Graph interrupts, workflow status -> BLOCKED, awaits user approval
   - User approves via CLI (`amelia approve`) or dashboard
   - `developer_node`: Developer agent implements each task agentically
   - `reviewer_node`: Reviewer agent reviews changes with multiple personas
   - Routing decides: retry developer, next task, or end
6. Events emitted via EventBus -> WebSocket -> Dashboard in real-time
7. LangGraph checkpoints state to PostgreSQL after each node for resumability

**Review Workflow:**

1. User runs `amelia review --local` or creates review via dashboard
2. Git diff content sent to server
3. Review graph: `reviewer_node` -> `evaluation_node` -> `developer_node` (fix loop)
4. Loops until no issues or max passes reached

**State Management:**
- **Pipeline state**: Immutable Pydantic models with `operator.add` reducers for append-only lists (history, tool_calls). State is checkpointed to PostgreSQL via LangGraph's `AsyncPostgresSaver`.
- **Server state**: `ServerExecutionState` tracks workflow metadata in PostgreSQL via `WorkflowRepository`. Separate from pipeline state.
- **Frontend state**: Zustand stores (`dashboard/src/store/`) + React Router data loaders. WebSocket connection provides real-time event streaming.

## Key Abstractions

**Pipeline Protocol:**
- Purpose: Defines contract for all workflow types
- Examples: `amelia/pipelines/base.py`
- Pattern: Protocol with `metadata`, `create_graph()`, `get_initial_state()`, `get_state_class()`

**DriverInterface Protocol:**
- Purpose: Abstracts LLM execution (single-turn generation + agentic tool-calling)
- Examples: `amelia/drivers/base.py`
- Pattern: Protocol with `generate()`, `execute_agentic()`, `get_usage()`, `cleanup_session()`
- Implementations: `ClaudeCliDriver`, `CodexCliDriver`, `ApiDriver`, `ContainerDriver`

**SandboxProvider Protocol:**
- Purpose: Transport-agnostic sandbox lifecycle and command execution
- Examples: `amelia/sandbox/provider.py`
- Pattern: Runtime-checkable Protocol with `ensure_running()`, `exec_stream()`, `write_file()`, `teardown()`
- Implementations: `DockerSandboxProvider`, `DaytonaSandboxProvider`

**BaseTracker Protocol:**
- Purpose: Issue tracker integration abstraction
- Examples: `amelia/trackers/base.py`
- Pattern: Protocol with `get_issue()`
- Implementations: `amelia/trackers/github.py`, `amelia/trackers/jira.py`, `amelia/trackers/noop.py`

**BasePipelineState:**
- Purpose: Common state fields for all pipelines (workflow_id, status, history, etc.)
- Examples: `amelia/pipelines/base.py`
- Pattern: Frozen Pydantic BaseModel with `Annotated[list[T], operator.add]` reducers for append-only fields

**AgenticMessage:**
- Purpose: Unified message type for streaming driver execution events
- Examples: `amelia/drivers/base.py`
- Pattern: Pydantic model with type enum (THINKING, TOOL_CALL, TOOL_RESULT, RESULT), converts to WorkflowEvent for EventBus emission

## Entry Points

**CLI Entry Point:**
- Location: `amelia/main.py`
- Triggers: `amelia <command>` via Typer
- Responsibilities: Configure logging, dispatch to subcommands (start, plan, approve, reject, status, cancel, resume, review, run, server, dev, config)

**Server Entry Point:**
- Location: `amelia/server/main.py` (`create_app()`)
- Triggers: `amelia server` or `amelia dev` (starts uvicorn)
- Responsibilities: FastAPI app creation, lifespan management (DB, orchestrator, event bus, knowledge service, lifecycle services), route mounting, CORS, SPA serving

**Dashboard Entry Point:**
- Location: `dashboard/src/main.tsx`
- Triggers: Browser navigation to server URL
- Responsibilities: React root rendering, router initialization

## Error Handling

**Strategy:** Layered error handling with domain-specific exceptions, retry for transient failures, event emission for observability

**Patterns:**
- Custom exceptions in `amelia/core/exceptions.py` (ModelProviderError) and `amelia/server/exceptions.py` (WorkflowNotFoundError, ConcurrencyLimitError, WorkflowConflictError, InvalidStateError, InvalidWorktreeError)
- Transient LLM/network errors trigger automatic retry with exponential backoff (`amelia/core/retry.py`, `TRANSIENT_EXCEPTIONS` in orchestrator)
- Workflow state machine validates transitions via `amelia/server/models/state.py` (`validate_transition()`, `VALID_TRANSITIONS` dict)
- FastAPI exception handlers configured in `amelia/server/routes/workflows.py` (`configure_exception_handlers()`)
- Agents raise `ValueError` with clear messages for validation failures
- Failed workflows can be resumed from LangGraph checkpoints

## Cross-Cutting Concerns

**Logging:** Loguru throughout (`from loguru import logger`). Structured kwargs: `logger.info("msg", key=value)`. Configuration in `amelia/logging.py`. Server startup banner in same module.

**Validation:** Pydantic models for all data structures. Frozen models (immutable) for state. Model validators for cross-field validation (e.g., `SandboxConfig._validate_daytona`).

**Authentication:** JWT-based (`pyjwt[crypto]`). No auth middleware visible on API routes (likely optional/development mode).

**Dependency Injection:** Module-level singletons in `amelia/server/dependencies.py` with `set_*/get_*/clear_*` pattern. FastAPI `dependency_overrides` for route-level DI.

**Event System:** `EventBus` (`amelia/server/events/bus.py`) provides synchronous pub/sub. Events broadcast to WebSocket clients via `ConnectionManager` and to console via `log_subscriber`. Events are `WorkflowEvent` Pydantic models with typed `EventType` enum.

---

*Architecture analysis: 2026-03-13*
