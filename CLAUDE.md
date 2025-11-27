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
