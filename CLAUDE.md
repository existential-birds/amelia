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
uv run amelia plan ISSUE-123                     # Generate plan only
uv run amelia review --local                     # Review uncommitted changes
```

**Pre-push hook**: A git pre-push hook runs `ruff check`, `mypy`, and `pytest` before every push. All checks must pass to push to remote.

## Graphite Stacked PRs

This repo uses [Graphite](https://graphite.dev/) for stacked PRs. **Always use `gt` commands instead of raw `git push`** to keep the stack properly tracked.

```bash
# Before starting work - sync with remote
gt sync

# After making changes
git add -A && git commit -m "message"
gt restack              # If Graphite asks for it
gt submit --stack       # Push all branches in stack

# View stack structure
gt ls

# Switch branches within stack
gt checkout <branch>
```

**Why this matters**: Graphite tracks version history for each PR. Using raw `git push` bypasses this tracking and can cause sync errors like `refs/gt-fetch-head` issues. Always use `gt submit` to push changes.

**If sync breaks**: If you see errors about missing refs (e.g., `graphite-base/XXX`), try:
```bash
gt untrack <branch>
gt track <branch> --parent <parent-branch>
gt sync
```

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
| **Core** | `amelia/core/` | LangGraph orchestrator, state types (`ExecutionState`), shared types (`Profile`, `Issue`) |
| **Agents** | `amelia/agents/` | Architect (planning), Developer (execution), Reviewer (review) |
| **Drivers** | `amelia/drivers/` | LLM abstraction - `api:openrouter` (pydantic-ai) or `cli:claude` (CLI wrapper) |
| **Trackers** | `amelia/trackers/` | Issue source abstraction - `jira`, `github`, `noop` |
| **Tools** | `amelia/tools/` | Shell execution, git utilities |
| **Extensions** | `amelia/ext/` | Protocols for optional integrations (policy hooks, audit exporters, analytics sinks) |

### Driver Abstraction

The driver abstraction allows switching between direct API calls (`api:openrouter`) and CLI-wrapped tools (`cli:claude`) without code changes. This enables enterprise compliance where direct API calls may be prohibited.

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
- **Structured logging** - Use kwargs for structured fields: `logger.info("msg", key=value)`. Don't use `.bind()` for single-log context. Fields appear in `record["extra"]` and are displayed in log output.
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

