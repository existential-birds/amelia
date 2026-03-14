# Codebase Structure

**Analysis Date:** 2026-03-13

## Directory Layout

```
amelia/                          # Project root
├── amelia/                      # Python backend package
│   ├── __init__.py              # Package version (__version__)
│   ├── main.py                  # CLI entry point (Typer app)
│   ├── logging.py               # Loguru configuration and server banner
│   ├── agents/                  # AI agent implementations
│   │   ├── architect.py         # Plan generation agent
│   │   ├── developer.py         # Code execution agent
│   │   ├── reviewer.py          # Multi-persona code review agent
│   │   ├── evaluator.py         # Review evaluation agent
│   │   ├── oracle.py            # On-demand consultation agent
│   │   ├── prompts/             # Prompt management
│   │   │   ├── defaults.py      # Default prompt templates
│   │   │   ├── models.py        # Prompt Pydantic models
│   │   │   └── resolver.py      # DB-backed prompt resolution
│   │   └── schemas/             # Structured output schemas
│   │       └── evaluator.py     # EvaluationResult schema
│   ├── cli/                     # CLI config subcommand
│   │   ├── __init__.py
│   │   └── config.py            # `amelia config` commands
│   ├── client/                  # HTTP client for server API
│   │   ├── api.py               # AmeliaClient (HTTP)
│   │   ├── cli.py               # CLI command implementations
│   │   ├── git.py               # Git helpers for client
│   │   ├── models.py            # Client-side models
│   │   └── streaming.py         # WebSocket event streaming
│   ├── core/                    # Shared types and utilities
│   │   ├── types.py             # Profile, Issue, AgentConfig, ReviewResult, etc.
│   │   ├── agentic_state.py     # AgenticState, ToolCall, ToolResult
│   │   ├── constants.py         # ToolName enum, plan path resolution
│   │   ├── exceptions.py        # ModelProviderError, etc.
│   │   ├── retry.py             # Exponential backoff retry
│   │   ├── extraction.py        # Text extraction utilities
│   │   ├── text.py              # Text processing helpers
│   │   └── utils.py             # General utilities
│   ├── drivers/                 # LLM driver implementations
│   │   ├── base.py              # DriverInterface protocol, AgenticMessage
│   │   ├── factory.py           # get_driver() factory function
│   │   ├── api/                 # API-based driver
│   │   │   └── deepagents.py    # OpenRouter/OpenAI via deepagents
│   │   └── cli/                 # CLI-based drivers
│   │       ├── claude.py        # Claude CLI via claude-agent-sdk
│   │       ├── codex.py         # Codex CLI driver
│   │       └── utils.py         # Shared CLI driver utilities
│   ├── knowledge/               # RAG knowledge library
│   │   ├── service.py           # Background ingestion service
│   │   ├── ingestion.py         # Document parsing pipeline
│   │   ├── embeddings.py        # Embedding client
│   │   ├── repository.py        # pgvector storage
│   │   ├── search.py            # Semantic search
│   │   └── models.py            # Knowledge data models
│   ├── pipelines/               # LangGraph workflow state machines
│   │   ├── base.py              # Pipeline protocol, BasePipelineState
│   │   ├── nodes.py             # Shared node functions (developer, reviewer)
│   │   ├── mixins.py            # Pipeline mixins
│   │   ├── registry.py          # Pipeline registry
│   │   ├── routing.py           # Shared routing helpers
│   │   ├── utils.py             # Config extraction utilities
│   │   ├── implementation/      # Implementation pipeline
│   │   │   ├── graph.py         # LangGraph graph construction
│   │   │   ├── state.py         # ImplementationState model
│   │   │   ├── nodes.py         # Architect, approval, task nodes
│   │   │   ├── routing.py       # Routing logic (approval, review, task)
│   │   │   ├── pipeline.py      # ImplementationPipeline class
│   │   │   ├── external_plan.py # External plan import
│   │   │   └── utils.py         # Plan parsing, task extraction
│   │   └── review/              # Review pipeline
│   │       ├── graph.py         # Review-fix graph construction
│   │       ├── nodes.py         # Evaluation node
│   │       ├── pipeline.py      # ReviewPipeline class
│   │       └── routing.py       # Review routing logic
│   ├── sandbox/                 # Sandboxed execution environments
│   │   ├── provider.py          # SandboxProvider protocol
│   │   ├── driver.py            # ContainerDriver (DriverInterface for sandboxes)
│   │   ├── docker.py            # DockerSandboxProvider
│   │   ├── daytona.py           # DaytonaSandboxProvider
│   │   ├── worker.py            # Worker script (runs inside sandbox)
│   │   ├── worktree.py          # Git worktree management
│   │   ├── network.py           # Network isolation (iptables allowlist)
│   │   ├── proxy.py             # LLM API proxy for sandboxes
│   │   ├── teardown.py          # Sandbox cleanup
│   │   ├── Dockerfile           # Local sandbox image
│   │   ├── Dockerfile.daytona   # Daytona sandbox image
│   │   └── scripts/             # Sandbox setup scripts
│   ├── server/                  # FastAPI server
│   │   ├── main.py              # create_app(), lifespan management
│   │   ├── cli.py               # `amelia server` command
│   │   ├── config.py            # ServerConfig (pydantic-settings)
│   │   ├── dependencies.py      # DI providers (set/get/clear singletons)
│   │   ├── dev.py               # `amelia dev` (API + dashboard dev server)
│   │   ├── checkpoint.py        # LangGraph checkpoint config
│   │   ├── exceptions.py        # Server-specific exceptions
│   │   ├── errors.py            # Error response models
│   │   ├── banner.py            # ASCII art startup banner
│   │   ├── database/            # PostgreSQL data access
│   │   │   ├── connection.py    # Database connection pool (asyncpg)
│   │   │   ├── migrator.py      # Schema migration runner
│   │   │   ├── migrations/      # SQL migration files (001-007)
│   │   │   ├── repository.py    # WorkflowRepository
│   │   │   ├── profile_repository.py
│   │   │   ├── settings_repository.py
│   │   │   ├── brainstorm_repository.py
│   │   │   └── prompt_repository.py
│   │   ├── events/              # Event system
│   │   │   ├── bus.py           # EventBus (pub/sub)
│   │   │   ├── connection_manager.py  # WebSocket connection manager
│   │   │   └── log_subscriber.py      # Console log subscriber
│   │   ├── lifecycle/           # Server lifecycle services
│   │   │   ├── server.py        # ServerLifecycle (startup/shutdown)
│   │   │   ├── health_checker.py # Worktree health monitoring
│   │   │   └── retention.py     # Log/data retention service
│   │   ├── models/              # API data models
│   │   │   ├── state.py         # ServerExecutionState, WorkflowStatus, PlanCache
│   │   │   ├── events.py        # WorkflowEvent, EventType, EventLevel
│   │   │   ├── requests.py      # API request models
│   │   │   ├── responses.py     # API response models
│   │   │   ├── tokens.py        # Token usage tracking
│   │   │   ├── usage.py         # Usage/cost models
│   │   │   └── brainstorm.py    # Brainstorm session models
│   │   ├── orchestrator/        # Workflow orchestration
│   │   │   └── service.py       # OrchestratorService
│   │   ├── routes/              # FastAPI route modules
│   │   │   ├── workflows.py     # CRUD + control for workflows
│   │   │   ├── health.py        # Health check endpoint
│   │   │   ├── config.py        # Config/profiles endpoints
│   │   │   ├── files.py         # File access endpoints
│   │   │   ├── github.py        # GitHub integration endpoints
│   │   │   ├── paths.py         # Path resolution endpoints
│   │   │   ├── usage.py         # Usage/cost endpoints
│   │   │   ├── websocket.py     # WebSocket event streaming
│   │   │   ├── brainstorm.py    # Brainstorm session endpoints
│   │   │   ├── oracle.py        # Oracle consultation endpoints
│   │   │   ├── knowledge.py     # Knowledge library endpoints
│   │   │   ├── prompts.py       # Prompt management endpoints
│   │   │   └── settings.py      # Server settings endpoints
│   │   ├── services/            # Business logic services
│   │   │   └── brainstorm.py    # BrainstormService
│   │   └── static/              # Bundled dashboard build
│   ├── skills/                  # Skill markdown files for agents
│   │   └── review/              # Review skills by stack
│   │       ├── general.md
│   │       ├── verification.md
│   │       ├── python/
│   │       ├── react/
│   │       ├── go/
│   │       ├── elixir/
│   │       ├── swift/
│   │       └── security/
│   ├── tools/                   # Shared tool utilities
│   │   ├── shell_executor.py    # Shell command execution
│   │   ├── git_utils.py         # Git operations
│   │   ├── file_bundler.py      # File content bundling
│   │   └── knowledge.py         # Knowledge search tool
│   └── trackers/                # Issue tracker integrations
│       ├── base.py              # BaseTracker protocol
│       ├── factory.py           # Tracker factory
│       ├── github.py            # GitHub Issues tracker
│       ├── jira.py              # Jira tracker
│       └── noop.py              # No-op tracker
├── dashboard/                   # React frontend (Vite + TypeScript)
│   ├── src/
│   │   ├── main.tsx             # React entry point
│   │   ├── App.tsx              # Root component
│   │   ├── router.tsx           # React Router v7 configuration
│   │   ├── api/                 # API client and types
│   │   │   ├── client.ts        # HTTP client (fetch wrapper)
│   │   │   ├── brainstorm.ts    # Brainstorm API
│   │   │   ├── settings.ts      # Settings API
│   │   │   └── errors.ts        # Error handling
│   │   ├── actions/             # React Router actions (approve, reject, cancel)
│   │   ├── components/          # UI components
│   │   │   ├── ui/              # shadcn/ui primitives
│   │   │   ├── activity/        # Activity log components
│   │   │   ├── ai-elements/     # AI-specific UI elements
│   │   │   ├── brainstorm/      # Brainstorm feature components
│   │   │   ├── model-picker/    # Model selection components
│   │   │   ├── prompts/         # Prompt config components
│   │   │   ├── settings/        # Settings page components
│   │   │   └── *.tsx            # Shared components (Layout, Sidebar, etc.)
│   │   ├── hooks/               # Custom React hooks
│   │   │   ├── useWebSocket.ts  # WebSocket event streaming
│   │   │   ├── useWorkflows.ts  # Workflow data hook
│   │   │   ├── useBrainstormSession.ts
│   │   │   └── *.ts             # Other hooks
│   │   ├── lib/                 # Utility libraries
│   │   ├── loaders/             # React Router data loaders
│   │   ├── mocks/               # MSW mock handlers (dev/test)
│   │   ├── pages/               # Page components
│   │   │   ├── WorkflowsPage.tsx
│   │   │   ├── WorkflowDetailPage.tsx
│   │   │   ├── HistoryPage.tsx
│   │   │   ├── LogsPage.tsx
│   │   │   ├── DevelopPage.tsx
│   │   │   ├── SpecBuilderPage.tsx
│   │   │   ├── CostsPage.tsx
│   │   │   ├── KnowledgePage.tsx
│   │   │   ├── PromptConfigPage.tsx
│   │   │   ├── SettingsProfilesPage.tsx
│   │   │   └── SettingsServerPage.tsx
│   │   ├── store/               # Zustand state stores
│   │   │   ├── workflowStore.ts
│   │   │   ├── brainstormStore.ts
│   │   │   └── useModelsStore.ts
│   │   ├── styles/              # CSS/Tailwind styles
│   │   ├── test/                # Test setup
│   │   ├── types/               # TypeScript type definitions
│   │   └── utils/               # Utility functions
│   ├── package.json
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   ├── eslint.config.js
│   └── tsconfig.json
├── tests/                       # Python test suite
│   ├── conftest.py              # Shared fixtures
│   ├── unit/                    # Unit tests (mocked boundaries)
│   └── integration/             # Integration tests (real components)
├── docs/                        # Documentation site
├── scripts/                     # Utility scripts
├── stubs/                       # mypy type stubs
├── logs/                        # Log output directory
├── pyproject.toml               # Python project config (uv, ruff, mypy, pytest)
├── docker-compose.yml           # PostgreSQL for development
├── CLAUDE.md                    # Claude agent instructions
├── AGENTS.md                    # Agent architecture docs
└── CONTRIBUTING.md              # Contribution guide
```

## Directory Purposes

**`amelia/agents/`:**
- Purpose: AI agent classes that encapsulate domain logic and LLM interaction
- Contains: Agent classes (Architect, Developer, Reviewer, Evaluator, Oracle), prompt templates, structured output schemas
- Key files: `architect.py`, `developer.py`, `reviewer.py`, `evaluator.py`, `oracle.py`

**`amelia/core/`:**
- Purpose: Foundation types and utilities shared across all layers
- Contains: Pydantic models, enums, constants, exceptions, retry logic
- Key files: `types.py` (Profile, Issue, AgentConfig, ReviewResult, SandboxConfig), `agentic_state.py`, `constants.py`

**`amelia/drivers/`:**
- Purpose: LLM execution backend implementations behind DriverInterface protocol
- Contains: Protocol definition, factory, CLI drivers (Claude, Codex), API driver (OpenRouter via deepagents)
- Key files: `base.py` (protocol), `factory.py` (get_driver), `cli/claude.py`, `api/deepagents.py`

**`amelia/pipelines/`:**
- Purpose: LangGraph state machine definitions for workflow types
- Contains: Base abstractions, implementation graph (architect->dev->review), review graph (review->fix loop)
- Key files: `base.py`, `implementation/graph.py`, `implementation/state.py`, `review/graph.py`, `nodes.py`

**`amelia/sandbox/`:**
- Purpose: Isolated execution environments (Docker containers, Daytona cloud)
- Contains: Provider protocol, Docker/Daytona implementations, container driver, worker script, network isolation
- Key files: `provider.py`, `docker.py`, `daytona.py`, `driver.py`, `worker.py`

**`amelia/server/`:**
- Purpose: FastAPI REST API server with WebSocket support
- Contains: Application setup, routes, models, database layer, event system, orchestrator, lifecycle management
- Key files: `main.py`, `orchestrator/service.py`, `dependencies.py`

**`amelia/server/database/`:**
- Purpose: PostgreSQL data access via asyncpg
- Contains: Connection pool, migration runner, repository classes for workflows/profiles/settings/prompts/brainstorms
- Key files: `connection.py`, `repository.py`, `profile_repository.py`, `migrator.py`

**`amelia/server/routes/`:**
- Purpose: FastAPI router modules for each API domain
- Contains: Route handlers for workflows, config, files, GitHub, health, WebSocket, brainstorm, oracle, knowledge, prompts, settings, usage
- Key files: `workflows.py`, `websocket.py`, `brainstorm.py`

**`amelia/knowledge/`:**
- Purpose: RAG-based document ingestion and semantic search
- Contains: Ingestion pipeline, embedding client, pgvector repository, search
- Key files: `service.py`, `ingestion.py`, `repository.py`, `search.py`

**`amelia/skills/`:**
- Purpose: Markdown skill files loaded by agents for domain-specific review knowledge
- Contains: Review skills organized by tech stack (python, react, go, elixir, swift, security)
- Key files: `review/general.md`, `review/verification.md`, stack-specific subdirectories

**`dashboard/src/`:**
- Purpose: React + TypeScript frontend for workflow management
- Contains: Pages, components, hooks, stores, API client, router, loaders, actions
- Key files: `router.tsx`, `main.tsx`, `api/client.ts`, `store/workflowStore.ts`

## Key File Locations

**Entry Points:**
- `amelia/main.py`: CLI entry point (Typer app, registered as `amelia` console script)
- `amelia/server/main.py`: FastAPI app factory (`create_app()`) and `app` instance
- `dashboard/src/main.tsx`: React app entry point

**Configuration:**
- `pyproject.toml`: Python project config (dependencies, ruff, mypy, pytest, hatch build)
- `amelia/server/config.py`: Server runtime config (`ServerConfig` via pydantic-settings)
- `amelia/core/types.py`: Profile, AgentConfig, SandboxConfig definitions
- `dashboard/vite.config.ts`: Vite build configuration
- `dashboard/tsconfig.json`: TypeScript configuration
- `docker-compose.yml`: PostgreSQL service for development

**Core Logic:**
- `amelia/server/orchestrator/service.py`: Workflow lifecycle management
- `amelia/pipelines/implementation/graph.py`: Implementation state machine
- `amelia/pipelines/review/graph.py`: Review state machine
- `amelia/pipelines/nodes.py`: Shared developer/reviewer node functions
- `amelia/drivers/factory.py`: Driver instantiation factory

**Testing:**
- `tests/conftest.py`: Shared test fixtures
- `tests/unit/`: Unit tests with mocked external boundaries
- `tests/integration/`: Integration tests with real components

## Naming Conventions

**Files:**
- Python: `snake_case.py` (e.g., `shell_executor.py`, `profile_repository.py`)
- TypeScript: `camelCase.ts` for utilities, `PascalCase.tsx` for React components (e.g., `WorkflowsPage.tsx`, `useWebSocket.ts`)
- SQL migrations: `NNN_description.sql` (e.g., `001_initial_schema.sql`)
- Skills: `language/topic.md` (e.g., `review/python/`, `review/general.md`)

**Directories:**
- Python: `snake_case` (e.g., `amelia/server/database/`, `amelia/pipelines/implementation/`)
- TypeScript: `lowercase` (e.g., `dashboard/src/components/`, `dashboard/src/hooks/`)

**Classes:**
- Python: `PascalCase` (e.g., `OrchestratorService`, `DockerSandboxProvider`, `ImplementationState`)
- TypeScript: `PascalCase` for components, types, interfaces

**Functions:**
- Python: `snake_case` (e.g., `create_implementation_graph`, `get_driver`)
- TypeScript: `camelCase` (e.g., `workflowsLoader`, `useWebSocket`)

## Where to Add New Code

**New Agent:**
- Implementation: `amelia/agents/<agent_name>.py`
- Structured output schema (if needed): `amelia/agents/schemas/<agent_name>.py`
- Default prompts: Add to `amelia/agents/prompts/defaults.py`
- Register agent name in `amelia/core/types.py` `REQUIRED_AGENTS` if mandatory
- Tests: `tests/unit/test_<agent_name>.py`

**New Pipeline:**
- Create directory: `amelia/pipelines/<pipeline_name>/`
- Required files: `graph.py` (LangGraph construction), `state.py` (state model extending `BasePipelineState`), `nodes.py` (node functions), `routing.py` (conditional routing), `pipeline.py` (Pipeline protocol implementation)
- Register in `amelia/pipelines/registry.py`
- Tests: `tests/unit/test_<pipeline_name>_*.py`, `tests/integration/test_<pipeline_name>_*.py`

**New API Route:**
- Route module: `amelia/server/routes/<domain>.py`
- Request/response models: `amelia/server/models/requests.py` and `amelia/server/models/responses.py`
- Mount router in `amelia/server/main.py` (`create_app()`)
- Tests: `tests/unit/test_routes_<domain>.py`

**New Driver:**
- Implementation: `amelia/drivers/<type>/<name>.py`
- Must implement `DriverInterface` protocol from `amelia/drivers/base.py`
- Register in `amelia/drivers/factory.py` (`get_driver()`)
- Add driver key to `amelia/core/types.py` `DriverType` enum
- Tests: `tests/unit/test_driver_<name>.py`

**New Sandbox Provider:**
- Implementation: `amelia/sandbox/<name>.py`
- Must implement `SandboxProvider` protocol from `amelia/sandbox/provider.py`
- Wire up in `amelia/drivers/factory.py` sandbox config handling
- Tests: `tests/unit/test_sandbox_<name>.py`

**New Dashboard Page:**
- Page component: `dashboard/src/pages/<PageName>.tsx`
- Add route in `dashboard/src/router.tsx`
- Data loader (if needed): `dashboard/src/loaders/<name>.ts`
- Tests: `dashboard/src/pages/<PageName>.test.tsx`

**New Dashboard Component:**
- Component: `dashboard/src/components/<ComponentName>.tsx`
- Feature-specific: `dashboard/src/components/<feature>/<ComponentName>.tsx`
- Tests: `dashboard/src/components/<ComponentName>.test.tsx` or `dashboard/src/components/__tests__/`

**New Database Migration:**
- SQL file: `amelia/server/database/migrations/NNN_description.sql` (increment from last migration number)
- Migrations are auto-run by `Migrator` on server startup

**Utilities:**
- Python shared helpers: `amelia/core/` (types, constants) or `amelia/tools/` (git, shell, file operations)
- TypeScript shared helpers: `dashboard/src/lib/` or `dashboard/src/utils/`

## Special Directories

**`amelia/server/static/`:**
- Purpose: Bundled dashboard build output (included in wheel package)
- Generated: Yes (from `dashboard/` build)
- Committed: No (built artifact)

**`amelia/server/database/migrations/`:**
- Purpose: SQL schema migration files run sequentially by Migrator
- Generated: No (manually authored)
- Committed: Yes

**`amelia/skills/`:**
- Purpose: Markdown skill files loaded at runtime by reviewer agent for stack-specific review guidance
- Generated: No (manually authored)
- Committed: Yes (included in wheel via hatch build artifacts)

**`stubs/`:**
- Purpose: Custom mypy type stubs for untyped dependencies
- Generated: No
- Committed: Yes

**`logs/`:**
- Purpose: Runtime log files
- Generated: Yes
- Committed: No (gitignored)

**`.worktrees/`:**
- Purpose: Git worktrees for parallel workflow execution
- Generated: Yes (by sandbox/worktree management)
- Committed: No

---

*Structure analysis: 2026-03-13*
