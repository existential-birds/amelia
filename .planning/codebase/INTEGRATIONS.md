# External Integrations

**Analysis Date:** 2026-03-13

## APIs & External Services

**LLM Providers:**
- OpenRouter - Primary LLM API provider (chat completions + embeddings)
  - SDK/Client: `langchain-openai` via `init_chat_model()` in `amelia/drivers/api/deepagents.py`
  - Embeddings: `httpx` direct calls to `https://openrouter.ai/api/v1/embeddings` in `amelia/knowledge/embeddings.py`
  - Auth: `OPENROUTER_API_KEY` env var
  - Site headers: `OPENROUTER_SITE_URL`, `OPENROUTER_SITE_NAME`
- OpenAI - Alternative LLM provider
  - SDK/Client: `langchain-openai` via same API driver
  - Auth: `OPENAI_API_KEY` env var
  - Base URL: `https://api.openai.com/v1`
- Anthropic (Claude CLI) - Via `claude-agent-sdk` subprocess
  - SDK/Client: `claude_agent_sdk.ClaudeSDKClient` in `amelia/drivers/cli/claude.py`
  - Auth: Managed by Claude CLI authentication (no env var needed)
- OpenAI Codex CLI - Via subprocess
  - SDK/Client: `amelia/drivers/cli/codex.py`
  - Auth: Managed by Codex CLI authentication

**LLM Driver Architecture:**
- Three driver types defined in `amelia/core/types.py` (`DriverType` enum):
  - `claude` - Claude CLI via claude-agent-sdk (`amelia/drivers/cli/claude.py`)
  - `codex` - OpenAI Codex CLI (`amelia/drivers/cli/codex.py`)
  - `api` - OpenRouter/OpenAI API via DeepAgents (`amelia/drivers/api/deepagents.py`)
- Driver factory: `amelia/drivers/factory.py`
- Common interface: `DriverInterface` protocol in `amelia/drivers/base.py`

**LLM Proxy:**
- Built-in reverse proxy at `/proxy/v1` for sandboxed containers
  - Implementation: `amelia/sandbox/proxy.py`
  - Purpose: Attaches API keys to requests so secrets never enter sandbox environments
  - Profile-aware: resolves provider from `X-Amelia-Profile` header
  - Supports OpenRouter and OpenAI upstreams

**Cloud Sandbox:**
- Daytona - Cloud sandbox for isolated code execution
  - SDK/Client: `daytona-sdk` (`AsyncDaytona`) in `amelia/sandbox/daytona.py`
  - Auth: `DAYTONA_API_KEY` env var
  - API URL: Configurable, default `https://app.daytona.io/api`
  - Features: Sandbox create/delete, git clone, file upload, session-based command execution with WebSocket streaming
  - Image support: Base images, Debian slim, pre-built snapshots

**Issue Trackers:**
- GitHub Issues - Via `gh` CLI subprocess
  - Implementation: `amelia/trackers/github.py`
  - Auth: `gh auth login` (CLI-managed)
  - Also: `amelia/server/routes/github.py` for dashboard issue listing
- Jira - Via REST API
  - Implementation: `amelia/trackers/jira.py`
  - Client: `httpx` direct HTTP calls
  - Auth: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` env vars
  - Endpoint: `{JIRA_BASE_URL}/rest/api/3/issue/{issue_id}`
- Noop - No-op tracker for manual issue entry
  - Implementation: `amelia/trackers/noop.py`
- Tracker factory: `amelia/trackers/factory.py`
- Tracker types: `TrackerType` enum in `amelia/core/types.py` (github, jira, noop)

## Data Storage

**Database:**
- PostgreSQL 16/17 with pgvector extension
  - Connection: `AMELIA_DATABASE_URL` (default: `postgresql://amelia:amelia@localhost:5434/amelia`)
  - Client: `asyncpg` with connection pooling (`amelia/server/database/connection.py`)
  - Vector extension: `pgvector.asyncpg` registered on connection init
  - Pool: Configurable min/max size (default 2-10)
  - Migrations: Sequential SQL files in `amelia/server/database/migrations/` (7 migrations)
  - Docker: `pgvector/pgvector:pg17` image on port 5434 (`docker-compose.yml`)

**Repositories:**
- `WorkflowRepository` - Workflow state persistence (`amelia/server/database/repository.py`)
- `ProfileRepository` - Agent profile configuration (`amelia/server/database/profile_repository.py`)
- `SettingsRepository` - Server settings (`amelia/server/database/settings_repository.py`)
- `BrainstormRepository` - Brainstorm session data (`amelia/server/database/brainstorm_repository.py`)
- `PromptRepository` - Custom prompt templates (`amelia/server/database/prompt_repository.py`)
- `KnowledgeRepository` - Document chunks + vector embeddings (`amelia/knowledge/repository.py`)

**Checkpointing:**
- LangGraph checkpoint persistence in PostgreSQL
  - Client: `langgraph-checkpoint-postgres` (`AsyncPostgresSaver`)
  - Uses same database URL as main application
  - Custom serializer with allowed module list (`amelia/server/checkpoint.py`)

**File Storage:**
- Local filesystem only for sandbox Docker containers
- Daytona sandbox uses remote filesystem API (`sandbox.fs.upload_file`)

**Caching:**
- None (no Redis or external cache)

## Authentication & Identity

**Auth Provider:**
- No user authentication system
- API keys managed via environment variables
- JWT library (`pyjwt[crypto]`) present - used for token handling
- GitHub CLI auth for issue tracker (`gh auth login`)

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry or external error tracking)

**Logs:**
- Loguru (`amelia/logging.py`) with structured key-value logging
- Server console logging via event bus subscriber (`amelia/server/events/log_subscriber.py`)
- Log retention service for cleanup (`amelia/server/lifecycle/retention.py`)

## CI/CD & Deployment

**CI Pipeline:**
- GitHub Actions (`.github/workflows/ci.yml`)
  - Runs on: push to main, pull requests to main
  - PostgreSQL 16 service container for tests
  - Steps: ruff check, mypy, pytest (unit + integration)
  - Uses `astral-sh/setup-uv@v4` for Python tooling

**Other Workflows:**
- `.github/workflows/docs.yml` - Documentation deployment
- `.github/workflows/release.yml` - Release automation

**Hosting:**
- Self-hosted / local development (no cloud deployment config)
- Docker Compose for PostgreSQL (`docker-compose.yml`)

**Pre-push Hook:**
- Runs: `ruff check`, `mypy`, `pytest`, `pnpm build` (all must pass)

## Real-Time Communication

**WebSocket:**
- Server endpoint: `/ws/events` (`amelia/server/routes/websocket.py`)
- Protocol: Subscribe/unsubscribe to workflow events, ping/pong keepalive
- Event bus: `amelia/server/events/bus.py` with connection manager
- Client backfill support via `since` query parameter
- Dashboard connects for live workflow streaming

## Environment Configuration

**Required env vars (for full functionality):**
- `OPENROUTER_API_KEY` - LLM API access and embeddings (knowledge service disabled without it)

**Optional env vars:**
- `AMELIA_DATABASE_URL` - PostgreSQL connection (has sensible default)
- `AMELIA_HOST` / `AMELIA_PORT` - Server binding
- `AMELIA_LOG_LEVEL` - Logging verbosity
- `OPENAI_API_KEY` - Alternative LLM provider
- `DAYTONA_API_KEY` - Cloud sandbox support
- `AMELIA_GITHUB_TOKEN` / `GITHUB_TOKEN` - Private repo sandbox access
- `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` - Jira integration
- `AMELIA_KNOWLEDGE_TAG_MODEL` - Knowledge tag extraction model
- `AMELIA_KNOWLEDGE_TAG_DRIVER` - Knowledge tag extraction driver type

**Secrets location:**
- Environment variables (loaded from `.env` via pydantic-settings)
- No `.env` file committed to repository

## Network Allowlist (Sandbox)

**Default allowed hosts for sandboxed execution** (defined in `amelia/core/types.py`):
- `api.anthropic.com`
- `openrouter.ai`
- `api.openai.com`
- `github.com`
- `registry.npmjs.org`
- `pypi.org`
- `files.pythonhosted.org`
- `app.daytona.io`

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

---

*Integration audit: 2026-03-13*
