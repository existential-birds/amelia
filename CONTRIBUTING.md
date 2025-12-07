# Contributing to Amelia

Thank you for your interest in contributing to Amelia! This document provides guidelines and information for contributors.

## Table of Contents

- [Development Setup](#development-setup)
- [Build & Development Commands](#build--development-commands)
- [Code Conventions](#code-conventions)
- [Test Structure](#test-structure)
- [Pull Request Process](#pull-request-process)
- [Claude Code Commands](#claude-code-commands)
- [Claude Code Skills](#claude-code-skills)

## Development Setup

### Prerequisites

- **Python 3.12+** - Required for type hints and async features
- **uv** - Fast Python package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Git** - For version control operations

### Installation

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/anderskev/amelia.git
cd amelia

# Sync dependencies (installs runtime + dev dependencies)
uv sync
```

## Build & Development Commands

```bash
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

### Manual Test Plans

For PRs with significant changes, create a manual test plan that the `amelia-qa` GitHub Action will post as a PR comment.

**Convention:**
- Place test plan at `docs/testing/pr-test-plan.md` (preferred) or `docs/testing/manual-test-plan-*.md`
- The file is auto-detected when the PR is opened and posted as a comment
- After the PR is merged, delete the test plan file (it's preserved in the PR comment)

## Pull Request Process

1. Create a feature branch from `main`
2. Write tests first (TDD), then implement
3. Ensure all checks pass: `uv run ruff check`, `uv run mypy`, `uv run pytest`
4. Create a PR with a clear description of changes
5. Address review feedback
6. Squash and merge once approved

## Claude Code Commands

When working on this project with [Claude Code](https://claude.ai/code), the following slash commands are available:

| Command | Description |
|---------|-------------|
| `/amelia:commit-push` | Commit and push all local changes to remote |
| `/amelia:create-pr` | Create a PR with standardized description template |
| `/amelia:update-pr-desc` | Update existing PR description after additional changes |
| `/amelia:review` | Launch a code review agent for the current PR |
| `/amelia:review-tests` | Review test code for quality and conciseness |
| `/amelia:ensure-doc` | Ensure all code is properly documented |
| `/amelia:gen-test-plan` | Generate manual test plan for PR |
| `/amelia:run-test-plan <path>` | Execute a manual test plan in an isolated worktree |
| `/amelia:greptile-review` | Fetch and evaluate greptile-apps review comments |
| `/amelia:eval-feedback <feedback>` | Evaluate code review feedback from another session |
| `/amelia:respond-review` | Respond to greptile review comments after evaluation |

## Claude Code Skills

The following skills are available in `.claude/skills/amelia/` to help Claude Code understand project-specific patterns and libraries:

### Frontend Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| **tailwind-v4** | `@theme`, `oklch`, `--color-` | Tailwind CSS v4 with CSS-first configuration, OKLCH colors, dark mode |
| **shadcn-ui** | `shadcn`, `cva`, `cn()`, `data-slot` | shadcn/ui component patterns, CVA variants, Radix primitives |
| **react-router-v7** | `loader`, `action`, `NavLink` | React Router v7 data loading, actions, navigation patterns |
| **zustand-state** | `zustand`, `create`, `persist` | Zustand state management, middleware, TypeScript patterns |
| **react-flow** | `ReactFlow`, `Handle`, `NodeProps` | React Flow workflow visualization, custom nodes/edges |
| **ai-elements** | `Queue`, `Tool`, `Confirmation` | Vercel AI Elements for chat UI, tool execution, workflows |

### Backend Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| **vercel-ai-sdk** | `useChat`, `streamText`, `UIMessage` | Vercel AI SDK for streaming chat, tool calls, message handling |
| **docling** | `DocumentConverter`, `HierarchicalChunker` | Document parsing (PDF, DOCX), chunking for RAG pipelines |
| **langgraph-graphs** | `StateGraph`, `add_node`, `add_edge` | LangGraph state machine patterns, nodes, edges, conditional routing |
| **langgraph-persistence** | `AsyncSqliteSaver`, `interrupt_before`, `GraphInterrupt` | LangGraph checkpointing, human-in-loop, interrupts, streaming |
| **pydantic-ai-agents** | `pydantic_ai`, `Agent`, `RunContext`, `@agent.tool` | Pydantic AI agent patterns, tools, dependencies, structured outputs |
| **sqlite-vec** | `vec0`, `MATCH`, `vec_distance` | Vector similarity search in SQLite, KNN queries, embeddings |

### Testing Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| **vitest-testing** | `vitest`, `vi.mock`, `describe` | Vitest patterns, mocking, configuration, test utilities |
