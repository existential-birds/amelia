# Contributing to Amelia

Thank you for your interest in Amelia!

## External Contributions

We welcome bug reports, feature requests, and feedback via [GitHub Issues](https://github.com/anderskev/amelia/issues).

**Code contributions (pull requests) are not accepted from external contributors.** Amelia uses a dual-licensing model that requires all code to be authored by the project maintainers. See [LICENSING.md](LICENSING.md) for details.

If you've found a bug or have an idea for improvement, please open an issue - we appreciate the feedback.

---

## Internal Development Guide

*The following sections are for internal contributors.*

## Table of Contents

- [Development Setup](#development-setup)
- [Build & Development Commands](#build--development-commands)
- [Code Conventions](#code-conventions)
- [Test Structure](#test-structure)
- [GitHub Workflow](#github-workflow)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)

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

## GitHub Workflow

We practice **continuous delivery** to main with **versioned releases** for stability.

### The Basics

1. **Issues** are the starting point for all work - bugs, features, and tasks
2. **Labels** categorize issues: `bug`, `enhancement`, `good first issue`, `area:*`
3. **Milestones** track release versions (e.g., `v1.2.0`)

### Contribution Flow

```
Issue created → Branch from main → Write tests → Implement → PR → Review → Merge
```

- Reference issues in PRs with closing keywords: `Fixes #123`
- PRs merge to main continuously; releases are cut from tags

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

### Scopes

| Scope | Component |
|-------|-----------|
| `server` | Backend FastAPI server |
| `cli` | Command-line interface |
| `dashboard` | React frontend |

### Examples

```bash
feat(cli): add dry-run flag to start command

fix(server): handle timeout when LLM response exceeds limit

# Breaking change (note the !)
feat!(api): change response format for workflow status

BREAKING CHANGE: The `status` field is now an object instead of a string.
```

### Guidelines

- **Use imperative mood**: "add feature" not "added feature"
- **Keep first line under 72 characters**
- **Reference issues** in the footer: `Closes #123` or `Fixes #456`
- **Mark breaking changes** with `!` after type/scope

## Pull Request Process

### Workflow

1. Create a feature branch from `main`
2. Write tests first (TDD), then implement
3. Ensure all checks pass (run `uv run ruff check`, `uv run mypy`, `uv run pytest`)
4. Create a PR with a clear description
5. Reference related issues: `Fixes #123`
6. Address review feedback
7. Squash and merge once approved

### Frontend Changes (Dashboard)

```bash
cd dashboard
pnpm install       # Install dependencies
pnpm lint          # ESLint check
pnpm typecheck     # TypeScript check
pnpm test          # Run Vitest tests
pnpm build         # Verify production build
```

### Manual Test Plans

For PRs with significant changes, create a manual test plan at `docs/testing/pr-test-plan.md`. The `amelia-qa` GitHub Action will post it as a PR comment. Delete the file after merge (it's preserved in the comment).

### Using Claude Code

If you're using [Claude Code](https://claude.ai/code), these commands streamline the PR process:

```bash
/amelia:review           # Self-review before creating PR
/amelia:create-pr        # Create PR with standardized description
/amelia:commit-push      # Commit and push with proper format
/amelia:gen-test-plan    # Generate manual test plan
```
