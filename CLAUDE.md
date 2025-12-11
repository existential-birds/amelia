# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies (installs runtime + dev dependencies)
uv sync

# Linting
uv run ruff check amelia tests         # Check for issues
uv run ruff check --fix amelia tests   # Auto-fix issues

# Type checking
uv run mypy amelia                     # Type check the package

# Run tests
uv run pytest                           # Full test suite
uv run pytest tests/unit/              # Unit tests only
uv run pytest tests/unit/test_foo.py   # Single file
uv run pytest -k "test_name"           # By name pattern

# CLI commands
uv run amelia start ISSUE-123 --profile work     # Full orchestrator loop
uv run amelia plan-only ISSUE-123                # Generate plan only
uv run amelia review --local                     # Review uncommitted changes
```

**Pre-push hook**: A git pre-push hook runs `ruff check`, `mypy`, and `pytest` before every push. All checks must pass to push to remote.

## Dashboard Frontend

The dashboard is a React + TypeScript frontend in `dashboard/`.

**Running the dashboard:**
- For general usage: `uv run amelia dev` serves the built dashboard at `localhost:8420`
- For frontend development (HMR): Run `pnpm dev` in `dashboard/` for hot reload

**Ports:**
- Backend API + bundled dashboard: `8420`
- Frontend dev server (HMR only): `8421` (proxied to backend)

```bash
cd dashboard

# Frontend development only (requires backend running separately)
pnpm dev          # Start Vite dev server with HMR on localhost:8421

# Build & test
pnpm build        # Build for production (output to dist/)
pnpm test         # Run Vitest tests
pnpm test:run     # Run tests once (CI mode)
pnpm lint         # ESLint check
pnpm lint:fix     # ESLint auto-fix
pnpm type-check   # TypeScript checking
```

**Tech Stack:** React Router v7, Tailwind CSS v4, shadcn/ui, Zustand, Vitest, XyFlow

## Architecture Overview

Amelia is a local agentic coding orchestrator that coordinates specialized AI agents through a LangGraph state machine.

### Core Flow

```
Issue → Architect (plan) → Human Approval → Developer (execute) ↔ Reviewer (review) → Done
```

The orchestrator loops between Developer and Reviewer until changes are approved.

### Key Layers

| Layer | Location | Purpose |
|-------|----------|---------|
| **Core** | `amelia/core/` | LangGraph orchestrator, state types (`ExecutionState`, `TaskDAG`), shared types (`Profile`, `Issue`) |
| **Agents** | `amelia/agents/` | Architect (planning), Developer (execution), Reviewer (review), Project Manager (issue fetch) |
| **Drivers** | `amelia/drivers/` | LLM abstraction - `api:openai` (pydantic-ai) or `cli:claude` (CLI wrapper) |
| **Trackers** | `amelia/trackers/` | Issue source abstraction - `jira`, `github`, `noop` |
| **Tools** | `amelia/tools/` | Shell execution, git utilities |

### Driver Abstraction

The driver abstraction allows switching between direct API calls (`api:openai`) and CLI-wrapped tools (`cli:claude`) without code changes. This enables enterprise compliance where direct API calls may be prohibited.

### Configuration

Profile-based configuration via `settings.amelia.yaml`:
- `driver`: Which LLM driver to use
- `tracker`: Issue source
- `strategy`: `single` or `competitive` review

## Code Conventions

- **Test-Driven Development (TDD)** - Always write tests first, then implementation. Follow the red-green-refactor cycle.
- **Python 3.12+** with type hints everywhere
- **Pydantic models** for all data structures - use validators/defaults, not ad-hoc dicts
- **Async throughout** - agents/drivers expose async methods, avoid blocking calls in async functions
- **Loguru** for logging (via `logger`), not `print`
- **Typer** for CLI with annotated parameters
- **Google-style docstrings** for all functions
- Raise `ValueError` with clear messages for validation failures
- New drivers/agents must conform to interfaces in `amelia/core/`

## Test Structure

```
tests/
├── conftest.py      # Shared fixtures (mock_driver, mock_issue, mock_profile, etc.)
├── unit/            # Unit tests
├── integration/     # Integration tests
├── e2e/             # End-to-end tests
└── perf/            # Performance tests
```

Tests use `pytest-asyncio` with `asyncio_mode = "auto"`.

**Test Principles:**
- **Don't Repeat Yourself (DRY)** - Extract common setup, assertions, and utilities into fixtures and helper functions. Avoid duplicating test logic across test files.

## Manual Test Plans

For PRs with significant changes, create a manual test plan that the `amelia-qa` GitHub Action will post as a PR comment.

**Convention:**
- Place test plan at `docs/testing/pr-test-plan.md` (preferred) or `docs/testing/manual-test-plan-*.md`
- The file is auto-detected when the PR is opened and posted as a comment
- After the PR is merged, delete the test plan file (it's preserved in the PR comment)

## Slash Commands

Custom slash commands are in `.claude/commands/amelia/`. Key commands:

| Command | Purpose |
|---------|---------|
| `/amelia:create-pr` | Create PR with standardized description template |
| `/amelia:update-pr-desc` | Update existing PR description after changes |
| `/amelia:commit-push` | Commit and push with Conventional Commits format |
| `/amelia:review` | Launch code review agent for production readiness |
| `/amelia:review-frontend` | Comprehensive React Router v7 frontend review |
| `/amelia:review-tests` | Review test code for usefulness and conciseness |
| `/amelia:gen-test-plan` | Generate manual test plan for PR |
| `/amelia:run-test-plan` | Execute test plan in isolated worktree |
| `/amelia:gen-release-notes` | Generate release notes since a tag |
| `/amelia:greptile-review` | Fetch and evaluate greptile-apps bot comments |
| `/amelia:respond-review` | Reply to review comments after fixes |
| `/amelia:eval-feedback` | Evaluate code review feedback |
| `/amelia:ensure-doc` | Verify code documentation (OpenAPI, docstrings) |
| `/amelia:review-plan` | Review implementation plans with parallel agents |
| `/amelia:skill-builder` | Create Claude Code skills with best practices |

## Skills

Custom skills are in `.claude/skills/`. These provide domain-specific knowledge:

**LangGraph:**
| Skill | Purpose |
|-------|---------|
| `langgraph-architecture` | Architectural decisions for LangGraph applications |
| `langgraph-implementation` | Implementing stateful agent graphs, nodes/edges, state schemas |
| `langgraph-code-review` | Review LangGraph code for bugs and anti-patterns |

**PydanticAI:**
| Skill | Purpose |
|-------|---------|
| `pydantic-ai-agent-creation` | Create PydanticAI agents with type-safe dependencies |
| `pydantic-ai-tool-system` | Register and implement PydanticAI tools |
| `pydantic-ai-dependency-injection` | Dependency injection using RunContext |
| `pydantic-ai-model-integration` | Configure LLM providers, fallback models |
| `pydantic-ai-testing` | Test PydanticAI agents using TestModel, FunctionModel |
| `pydantic-ai-common-pitfalls` | Avoid common mistakes in PydanticAI agents |

**React Flow:**
| Skill | Purpose |
|-------|---------|
| `react-flow-architecture` | Architectural guidance for node-based UIs with React Flow |
| `react-flow-implementation` | Implementing React Flow nodes, edges, handles, state |
| `react-flow-advanced` | Advanced patterns: sub-flows, layouts, drag-and-drop |
| `react-flow-code-review` | Review React Flow code for anti-patterns |
| `react-flow` | React Flow workflow visualization, custom nodes/edges |

**Frontend:**
| Skill | Purpose |
|-------|---------|
| `shadcn-ui` | shadcn/ui components, CVA patterns, Radix primitives |
| `tailwind-v4` | Tailwind CSS v4 with CSS-first config, @theme directive |
| `react-router-v7` | React Router v7 patterns and navigation |
| `zustand-state` | Zustand state management patterns |

**AI Integration:**
| Skill | Purpose |
|-------|---------|
| `vercel-ai-sdk` | Chat interfaces with streaming, useChat hook |
| `ai-elements` | Vercel AI Elements for chat interfaces, tool execution, reasoning displays |

**Data Processing:**
| Skill | Purpose |
|-------|---------|
| `docling` | Document parsing for PDF, DOCX, PPTX, HTML, images (15+ formats) |
| `sqlite-vec` | Vector similarity search in SQLite for embeddings and semantic search |

**Testing:**
| Skill | Purpose |
|-------|---------|
| `vitest-testing` | Vitest patterns, mocking, async testing |

**Tooling:**
| Skill | Purpose |
|-------|---------|
| `github-projects` | GitHub Projects v2 via gh CLI
