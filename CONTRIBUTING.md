# Contributing to Amelia

Thank you for your interest in contributing to Amelia! This document provides guidelines and information for contributors.

## Table of Contents

- [Development Setup](#development-setup)
- [Build & Development Commands](#build--development-commands)
- [Code Conventions](#code-conventions)
- [Test Structure](#test-structure)
- [GitHub Organization](#github-organization)
- [Commit Messages](#commit-messages)
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

**Using Claude Code:**
```bash
# Generate a test plan automatically based on branch changes
/amelia:gen-test-plan
```

This command analyzes your branch changes and creates a structured test plan at `docs/testing/pr-test-plan.md`.

**Convention:**
- Place test plan at `docs/testing/pr-test-plan.md` (preferred) or `docs/testing/manual-test-plan-*.md`
- The file is auto-detected when the PR is opened and posted as a comment
- After the PR is merged, delete the test plan file (it's preserved in the PR comment)

## GitHub Organization

We practice **continuous delivery** to main while maintaining **versioned releases** for stability. Depend on tagged releases rather than main for production use.

### Issues

Issues are the atomic unit of work. Every bug, feature, or task starts as an issue.

- Use issue templates for consistency
- Link related issues to each other
- All discussion about a piece of work happens on the issue

### Labels

Labels are the primary way to categorize and filter issues.

| Category | Labels | Purpose |
|----------|--------|---------|
| Type | `bug`, `enhancement`, `breaking-change`, `docs` | What kind of work |
| Priority | `critical`, `high`, `low` | Internal triage |
| Status | `needs-triage`, `accepted`, `blocked` | Workflow state |
| Contributor | `good first issue`, `help wanted` | Guide contributors |
| Area | `area:core`, `area:agents`, `area:dashboard`, `area:cli`, `area:server` | Which component |

The `breaking-change` label is particularly important for identifying what requires a major version bump and should be highlighted in release notes.

### Milestones

Milestones represent **release versions** (e.g., `v1.2.0`, `v1.3.0`).

- Assign issues and PRs to a milestone when committed to that release
- Use for tracking progress toward the next release
- Enables easy release notes generation

### Projects

We use a single public **Roadmap** project board to communicate what's planned and in progress.

#### Board Columns

| Column | Description |
|--------|-------------|
| Exploring | Ideas under consideration, not committed |
| Planned | Accepted work, will happen, not yet started |
| In Progress | Actively being worked on |
| Done | Shipped (clear periodically) |

#### Custom Fields

| Field | Values | Purpose |
|-------|--------|---------|
| Target release | `v1.2`, `v1.3`, `Future` | When it's expected to ship |
| Area | `Core`, `Agents`, `Dashboard`, `CLI`, `Server` | Which component |
| Size | `Small`, `Medium`, `Large` | Set expectations on scope |

#### Roadmap Guidelines

- Link **issues** to the project, not PRs
- Only include meaningful user-facing work
- Move items back to Exploring if priorities shift
- Archive Done items periodically to keep the board scannable

### Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Issue created                                               │
│     ↓                                                           │
│  2. Triaged: labeled, possibly added to Roadmap (Exploring)     │
│     ↓                                                           │
│  3. Prioritized: assigned to milestone, moved to Planned        │
│     ↓                                                           │
│  4. Work begins: moved to In Progress                           │
│     ↓                                                           │
│  5. PR opened: references issue with "Fixes #___"               │
│     ↓                                                           │
│  6. PR merged to main (CD deploys)                              │
│     ↓                                                           │
│  7. Milestone complete: tag release, publish release notes      │
└─────────────────────────────────────────────────────────────────┘
```

## Commit Messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/) format:

```
type(scope): description

[optional body]

[optional footer]
```

### Types

| Type | When to Use |
|------|-------------|
| `feat` | New features or capabilities |
| `fix` | Bug fixes |
| `docs` | Documentation only changes |
| `refactor` | Code changes that neither fix bugs nor add features |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks, dependency updates |
| `perf` | Performance improvements |
| `ci` | CI/CD configuration changes |

### Scopes

| Scope | Component |
|-------|-----------|
| `server` | Backend FastAPI server |
| `cli` | Command-line interface |
| `dashboard` | React frontend |
| `skills` | Claude Code skills |
| `commands` | Slash commands |
| `client` | API client |
| `health` | Health check endpoints |

### Examples

```bash
# Feature with scope
feat(cli): add dry-run flag to start command

# Bug fix with scope
fix(server): handle timeout when LLM response exceeds limit

# Breaking change (note the !)
feat!(api): change response format for workflow status

BREAKING CHANGE: The `status` field is now an object instead of a string.

# Simple docs change (no scope needed)
docs: update installation instructions

# Multi-line with body
fix(dashboard): resolve memory leak in workflow view

The useEffect cleanup was not properly canceling pending API requests,
causing state updates on unmounted components.
```

### Guidelines

- **Use imperative mood**: "add feature" not "added feature" or "adds feature"
- **Keep first line under 72 characters**
- **Reference issues** in the footer: `Closes #123` or `Fixes #456`
- **Mark breaking changes** with `!` after type/scope and explain in footer

> **Tip:** If you're using Claude Code, run `/amelia:commit-push` to automatically generate a properly formatted commit message and push your changes.

## Pull Request Process

### General Workflow

1. Create a feature branch from `main`
2. Write tests first (TDD), then implement
3. Ensure all checks pass (see below)
4. Create a PR with a clear description of changes
5. **Reference related issues** using closing keywords (`Fixes #123`, `Closes #456`)
6. **Assign to milestone** when the linked issue has one
7. Address review feedback
8. Squash and merge once approved

PRs are merged to main continuously; releases are cut from tags.

### Backend Changes

```bash
uv run ruff check amelia tests   # Linting
uv run mypy amelia               # Type checking
uv run pytest                    # Run all tests
```

### Frontend Changes (Dashboard)

```bash
cd dashboard

# Install dependencies
pnpm install

# Linting and formatting
pnpm lint          # ESLint check
pnpm format        # Prettier formatting

# Type checking
pnpm typecheck     # TypeScript check

# Testing
pnpm test          # Run Vitest tests
pnpm test:ui       # Run with UI

# Build verification
pnpm build         # Ensure production build succeeds
```

### Using Claude Code Commands

If you're using Claude Code, leverage Amelia's custom commands to streamline the PR process:

```bash
# 1. Ensure documentation is complete
/amelia:ensure-doc

# 2. Review your test code
/amelia:review-tests

# 3. Run a self-review before creating PR
/amelia:review

# 4. Evaluate and address review feedback
/amelia:eval-feedback <paste feedback here>

# 5. Create the PR with standardized description
/amelia:create-pr

# 6. Generate manual test plan (for significant changes)
/amelia:gen-test-plan
```

## Claude Code Commands

When working on this project with [Claude Code](https://claude.ai/code), the following slash commands are available:

| Command | Description |
|---------|-------------|
| `/amelia:commit-push` | Commit and push all local changes to remote |
| `/amelia:create-pr` | Create a PR with standardized description template |
| `/amelia:update-pr-desc` | Update existing PR description after additional changes |
| `/amelia:review` | Launch a code review agent for the current PR |
| `/amelia:review-frontend` | Comprehensive React Router v7 frontend code review |
| `/amelia:review-backend` | Comprehensive Python/FastAPI/LangGraph backend code review |
| `/amelia:review-plan <path>` | Review implementation plan for parallelization, TDD, types, library practices |
| `/amelia:review-tests` | Review test code for quality and conciseness |
| `/amelia:ensure-doc` | Ensure all code is properly documented |
| `/amelia:gen-test-plan` | Generate manual test plan for PR |
| `/amelia:run-test-plan <path>` | Execute a manual test plan in an isolated worktree |
| `/amelia:greptile-review` | Fetch and evaluate greptile-apps review comments |
| `/amelia:coderabbit-review` | Fetch and evaluate CodeRabbit review comments |
| `/amelia:gemini-review` | Fetch and evaluate Gemini Code Assist review comments |
| `/amelia:eval-feedback <feedback>` | Evaluate code review feedback from another session |
| `/amelia:prompt-improver <prompt>` | Optimize a prompt following Claude 4 best practices |
| `/amelia:respond-review` | Respond to greptile review comments after evaluation |
| `/amelia:coderabbit-respond` | Respond to CodeRabbit review comments after evaluation |
| `/amelia:gemini-respond` | Respond to Gemini Code Assist review comments after evaluation |
| `/amelia:skill-builder` | Create Claude Code skills with comprehensive best practices |
| `/amelia:12-factor-analysis <path>` | Analyze codebase against 12-Factor Agents methodology |

## Claude Code Skills

The following skills are available in `.claude/skills/` to help Claude Code understand project-specific patterns and libraries:

### LangGraph Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| **langgraph-architecture** | `StateGraph`, `multi-agent`, `persistence` | Architectural decisions for LangGraph applications |
| **langgraph-implementation** | `add_node`, `add_edge`, `state schema` | Implementing stateful agent graphs, nodes/edges, state schemas |
| **langgraph-code-review** | `StateGraph`, `checkpointing` | Review LangGraph code for bugs and anti-patterns |

### PydanticAI Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| **pydantic-ai-agent-creation** | `pydantic_ai`, `Agent`, `result_type` | Create PydanticAI agents with type-safe dependencies |
| **pydantic-ai-tool-system** | `@agent.tool`, `RunContext` | Register and implement PydanticAI tools |
| **pydantic-ai-dependency-injection** | `deps_type`, `RunContext` | Dependency injection using RunContext |
| **pydantic-ai-model-integration** | `model`, `fallback`, `streaming` | Configure LLM providers, fallback models |
| **pydantic-ai-testing** | `TestModel`, `FunctionModel` | Test PydanticAI agents using TestModel, FunctionModel |
| **pydantic-ai-common-pitfalls** | debugging, errors | Avoid common mistakes in PydanticAI agents |

### React Flow Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| **react-flow-architecture** | `@xyflow/react`, architecture | Architectural guidance for node-based UIs with React Flow |
| **react-flow-implementation** | `ReactFlow`, `Handle`, `NodeProps` | Implementing React Flow nodes, edges, handles, state |
| **react-flow-advanced** | sub-flows, layouts, drag-and-drop | Advanced patterns: sub-flows, layouts, undo/redo |
| **react-flow-code-review** | `@xyflow/react`, review | Review React Flow code for anti-patterns |
| **react-flow** | `ReactFlow`, `useReactFlow`, `fitView` | React Flow workflow visualization, custom nodes/edges |
| **dagre-react-flow** | `dagre`, `auto-layout`, `getLayoutedElements` | Automatic graph layout using dagre with React Flow |

### Frontend Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| **tailwind-v4** | `@theme`, `oklch`, `--color-` | Tailwind CSS v4 with CSS-first configuration, OKLCH colors, dark mode |
| **shadcn-ui** | `shadcn`, `cva`, `cn()`, `data-slot` | shadcn/ui component patterns, CVA variants, Radix primitives |
| **react-router-v7** | `loader`, `action`, `NavLink` | React Router v7 data loading, actions, navigation patterns |
| **zustand-state** | `zustand`, `create`, `persist` | Zustand state management, middleware, TypeScript patterns |

### AI Integration Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| **vercel-ai-sdk** | `useChat`, `streamText`, `UIMessage` | Vercel AI SDK for streaming chat, tool calls, message handling |
| **ai-elements** | `Queue`, `Tool`, `Confirmation` | Vercel AI Elements for chat UI, tool execution, workflows |

### Data Processing Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| **docling** | `DocumentConverter`, `HierarchicalChunker` | Document parsing (PDF, DOCX), chunking for RAG pipelines |
| **sqlite-vec** | `vec0`, `MATCH`, `vec_distance` | Vector similarity search in SQLite, KNN queries, embeddings |

### Testing Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| **vitest-testing** | `vitest`, `vi.mock`, `describe` | Vitest patterns, mocking, configuration, test utilities |

### Tooling Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| **github-projects** | `gh project`, `project board`, `kanban` | GitHub Projects (v2) via gh CLI, project items, fields, workflows |

### Architecture Analysis Skills

| Skill | Triggers | Description |
|-------|----------|-------------|
| **agent-architecture-analysis** | `12-Factor`, `compliance`, `agent architecture` | Evaluate agentic codebases against 12-Factor Agents methodology |
