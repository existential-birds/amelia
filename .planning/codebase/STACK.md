# Technology Stack

**Analysis Date:** 2026-03-13

## Languages

**Primary:**
- Python 3.12+ - Backend server, CLI, agents, pipelines, knowledge system (`amelia/`)
- TypeScript ~5.6 - Dashboard frontend (`dashboard/`)

**Secondary:**
- SQL - Database migrations (`amelia/server/database/migrations/`)
- Shell - Docker entrypoint scripts (`scripts/`)

## Runtime

**Environment:**
- Python 3.12+ (required: `requires-python = ">=3.12"`)
- Node.js (for dashboard build via pnpm)

**Package Manager:**
- uv (Python) - `pyproject.toml` with hatchling build backend
- pnpm (JavaScript) - `dashboard/package.json`
- Lockfile: `uv.lock` present, `pnpm-lock.yaml` in `dashboard/`

## Frameworks

**Core:**
- FastAPI >=0.115.0 - REST API server (`amelia/server/main.py`)
- Uvicorn >=0.40.0 - ASGI server
- LangGraph >=1.0.8 - Agent orchestration graph (`amelia/pipelines/`)
- DeepAgents >=0.4.3 - Agentic execution backend (`amelia/drivers/api/deepagents.py`)
- Pydantic >=2.12.4 - Data models and validation throughout
- Pydantic-Settings >=2.6.0 - Configuration management (`amelia/server/config.py`)
- Typer >=0.15.1 - CLI framework (`amelia/main.py`)

**Frontend:**
- React 18 - UI framework (`dashboard/`)
- React Router DOM >=7.13 - Client-side routing
- Zustand >=5.0.9 - State management
- Tailwind CSS 4 - Styling
- Radix UI - Component primitives (dialog, dropdown, tabs, etc.)
- Recharts 2.15.4 - Charts and data visualization
- Vite 6 - Build tooling and dev server
- Zod >=3.25 - Schema validation

**Testing:**
- pytest >=8.3.4 - Python test runner
- pytest-asyncio >=0.24.0 - Async test support (mode: auto)
- Vitest >=4.0.15 - Dashboard test runner
- Testing Library (React + User Event) - Dashboard component testing

**Build/Dev:**
- Hatchling - Python build backend
- Ruff >=0.8.0 - Python linter and formatter (target: py312, line-length: 100)
- mypy >=1.13.0 - Static type checking (strict mode)
- ESLint 9 - TypeScript linting
- TypeScript ~5.6 - Type checking for dashboard

## Key Dependencies

**Critical:**
- `langgraph` >=1.0.8 - Core orchestration engine for agent pipelines
- `langchain-openai` >=1.1.9 - LLM API integration via LangChain
- `claude-agent-sdk` >=0.1.38 - Claude CLI driver SDK (`amelia/drivers/cli/claude.py`)
- `deepagents` >=0.4.3 - Agentic code execution with filesystem backend
- `asyncpg` >=0.30.0 - PostgreSQL async driver
- `pgvector` >=0.3.7 - Vector similarity search for knowledge library
- `httpx` >=0.28.0 - Async HTTP client (API calls, embeddings, proxy)
- `daytona-sdk` >=0.148.0 - Cloud sandbox management (`amelia/sandbox/daytona.py`)

**Infrastructure:**
- `langgraph-checkpoint-postgres` >=3.0.4 - Persistent workflow checkpoints
- `pyjwt[crypto]` >=2.9.0 - JWT token handling
- `websockets` >=15.0 - WebSocket support for real-time events
- `tiktoken` >=0.7.0 - Token counting for LLM interactions
- `docling` >=2.73.0 - Document parsing (PDF/markdown) for knowledge ingestion
- `psutil` >=6.1.0 - System resource monitoring
- `rich` >=14.1.0 / `rich-click` >=1.9.4 - Terminal formatting
- `loguru` >=0.7.2 - Structured logging
- `pyyaml` >=6.0.2 - YAML configuration parsing

**Frontend Critical:**
- `ai` >=5.0.108 - Vercel AI SDK for streaming
- `react-hook-form` >=7.70 + `@hookform/resolvers` - Form management
- `react-markdown` >=10.1 - Markdown rendering
- `streamdown` >=1.6.11 - Streaming markdown display
- `motion` >=12.23 - Animations
- `sonner` >=1.7 - Toast notifications
- `cmdk` >=1.1 - Command palette

## Configuration

**Environment:**
- `AMELIA_` prefix for server config (loaded from `.env` via pydantic-settings)
- `AMELIA_HOST` - Server bind host (default: 127.0.0.1)
- `AMELIA_PORT` - Server bind port (default: 8420)
- `AMELIA_DATABASE_URL` - PostgreSQL connection URL (default: postgresql://amelia:amelia@localhost:5434/amelia)
- `AMELIA_DB_POOL_MIN_SIZE` / `AMELIA_DB_POOL_MAX_SIZE` - Connection pool sizing
- `AMELIA_LOG_LEVEL` - Log level (default: INFO)
- `OPENROUTER_API_KEY` - Required for knowledge service embeddings and API driver
- `OPENAI_API_KEY` - Alternative LLM provider
- `DAYTONA_API_KEY` - Required for Daytona cloud sandboxes
- `AMELIA_GITHUB_TOKEN` / `GITHUB_TOKEN` - Git access for sandbox operations
- `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` - Jira tracker integration
- `AMELIA_KNOWLEDGE_TAG_MODEL` - LLM model for knowledge tag extraction
- `AMELIA_KNOWLEDGE_TAG_DRIVER` - Driver type for tag extraction

**Build:**
- `pyproject.toml` - Python project config, ruff, mypy, pytest settings
- `dashboard/vite.config.ts` - Vite build config with `@` path alias to `./src`
- `dashboard/tsconfig.json` - TypeScript config
- Dashboard builds to `amelia/server/static/` for bundled serving

## Platform Requirements

**Development:**
- Python 3.12+
- Node.js + pnpm (for dashboard)
- PostgreSQL 16+ with pgvector extension (via Docker: `pgvector/pgvector:pg17`)
- uv package manager
- Docker (optional, for sandbox and database)
- `gh` CLI (optional, for GitHub issue tracker integration)

**Production:**
- PostgreSQL with pgvector extension
- Server runs on port 8420 (API) with embedded dashboard
- Dashboard dev server on port 8421 (proxies API/WS to 8420)

---

*Stack analysis: 2026-03-13*
