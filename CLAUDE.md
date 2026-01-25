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
uv run amelia review --local                     # Review uncommitted changes
```

**Pre-push hook**: A git pre-push hook runs `ruff check`, `mypy`, `pytest`, and `pnpm build` (dashboard) before every push. All checks must pass to push to remote.

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

## Browser Automation

Use `agent-browser` for web automation. Run `agent-browser --help` for all commands.

Core workflow:
1. `agent-browser open <url>` - Navigate to page
2. `agent-browser snapshot -i` - Get interactive elements with refs (@e1, @e2)
3. `agent-browser click @e1` / `agent-browser fill @e2 "text"` - Interact using refs
4. Re-snapshot after page changes

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
| **Drivers** | `amelia/drivers/` | LLM abstraction - `api` (pydantic-ai) or `cli` (CLI wrapper) |
| **Trackers** | `amelia/trackers/` | Issue source abstraction - `jira`, `github`, `none` |
| **Tools** | `amelia/tools/` | Shell execution, git utilities |
| **Extensions** | `amelia/ext/` | Protocols for optional integrations (policy hooks, audit exporters, analytics sinks) |

### Driver Abstraction

The driver abstraction allows switching between direct API calls (`api`) and CLI-wrapped tools (`cli`) without code changes. This enables enterprise compliance where direct API calls may be prohibited.

### Configuration

Profile-based configuration via `settings.amelia.yaml`:
- `driver`: Which LLM driver to use
- `tracker`: Issue source
- `strategy`: `single` or `competitive` review

### Server Configuration

Server settings via environment variables (prefix `AMELIA_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `AMELIA_HOST` | `127.0.0.1` | Host to bind the server to |
| `AMELIA_PORT` | `8420` | Port to bind the server to |
| `AMELIA_LOG_RETENTION_DAYS` | `30` | Days to retain event logs |
| `AMELIA_TRACE_RETENTION_DAYS` | `7` | Days to retain trace-level events. `0` = don't persist traces |
| `AMELIA_CHECKPOINT_RETENTION_DAYS` | `0` | Days to retain LangGraph checkpoints. `0` = delete immediately on shutdown, `-1` = never delete (for debugging) |
| `AMELIA_CHECKPOINT_PATH` | `~/.amelia/checkpoints.db` | Path to LangGraph checkpoint database |
| `AMELIA_DATABASE_PATH` | `~/.amelia/amelia.db` | Path to main SQLite database |
| `AMELIA_MAX_CONCURRENT` | `5` | Maximum concurrent workflows |
| `AMELIA_STREAM_TOOL_RESULTS` | `false` | Stream tool result events to dashboard. Enable for debugging. |

**Debugging tip**: Set `AMELIA_CHECKPOINT_RETENTION_DAYS=-1` to preserve checkpoints for debugging workflow issues.

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

**Integration Tests Must Be Real Integration Tests:**

- Integration tests (`tests/integration/`) must test actual component interactions, not mocked components.
- Only mock at the **external boundary** (e.g., HTTP calls to LLM APIs). Never mock internal classes like `Architect`, `Developer`, `Reviewer`, or `DriverFactory`.
- If you find yourself patching internal components, you're writing a unit test - move it to `tests/unit/`.
- The purpose of integration tests is to verify that real components work together correctly. Mocking them defeats this purpose entirely.

**Example - WRONG (this is a unit test pretending to be an integration test):**

```python
with patch("amelia.core.orchestrator.Architect") as mock_architect:
    mock_architect.return_value.plan = AsyncMock(return_value=mock_plan)
    result = await call_architect_node(state, config)  # Testing nothing real
```

**Example - CORRECT (real integration test):**

```python
# Real Architect instance, only mock the LLM HTTP boundary
with patch("httpx.AsyncClient.post") as mock_http:
    mock_http.return_value = Response(200, json={"choices": [...]})
    result = await call_architect_node(state, config)  # Real Architect runs
```

**High-Fidelity Mocks:**

Mock return values must match production types exactly. When mocking external boundaries, return the same type the real code returns—not a serialized or converted form that happens to work.

**Example - WRONG (lower fidelity):**

```python
# pydantic-ai returns Pydantic instances, not dicts
mock_llm_response = MarkdownPlanOutput(goal="X", plan_markdown="...")
mock_result.output = mock_llm_response.model_dump()  # Returns dict, not instance
```

**Example - CORRECT (production fidelity):**

```python
# Match what pydantic-ai actually returns: a Pydantic model instance
mock_llm_response = MarkdownPlanOutput(goal="X", plan_markdown="...")
mock_result.output = mock_llm_response  # Same type as production
```

This matters because downstream code may rely on type-specific behavior. Even if both happen to work today, the lower-fidelity version could mask bugs or break when code evolves.

## Manual Test Plans

For PRs with significant changes, create a manual test plan that the `amelia-qa` GitHub Action will post as a PR comment.

**Convention:**
- Place test plan at `docs/testing/pr-test-plan.md` (preferred) or `docs/testing/manual-test-plan-*.md`
- The file is auto-detected when the PR is opened and posted as a comment
- After the PR is merged, delete the test plan file (it's preserved in the PR comment)

## Release Process

Releases follow semantic versioning and use automated GitHub Release creation.

### Creating a Release

1. **Generate release notes** (from any branch):
   ```bash
   # Run the gen-release-notes command with the previous tag
   /gen-release-notes v0.1.0
   ```
   This updates `CHANGELOG.md` and all version files (see Files Involved below).

2. **Create release branch and PR**:
   ```bash
   git checkout -b chore/release-X.Y.Z
   git add CHANGELOG.md pyproject.toml amelia/__init__.py dashboard/package.json docs/site/package.json
   git commit -m "chore(release): bump version to X.Y.Z"
   git push -u origin chore/release-X.Y.Z
   gh pr create --title "chore(release): X.Y.Z" --body "Release X.Y.Z"
   ```

3. **Merge the PR** (after CI passes and review)

4. **Tag the release** (after PR is merged):
   ```bash
   git checkout main
   git pull
   git tag -a vX.Y.Z -m "Release vX.Y.Z - Brief summary"
   git push origin vX.Y.Z
   ```

5. **GitHub Action creates the release** automatically from the tag, extracting notes from `CHANGELOG.md`.

### Version Numbering

- **MAJOR** (X.0.0): Breaking changes to CLI, API, or configuration
- **MINOR** (x.Y.0): New features, commands, or backward-compatible changes
- **PATCH** (x.y.Z): Bug fixes only

### Files Involved

| File | Purpose |
|------|---------|
| `pyproject.toml` | Python package version (source of truth) |
| `amelia/__init__.py` | Python module `__version__` export |
| `dashboard/package.json` | Dashboard frontend version |
| `docs/site/package.json` | VitePress documentation site version |
| `CHANGELOG.md` | Release notes in Keep a Changelog format |
| `.github/workflows/release.yml` | Automated GitHub Release creation on tag push |
| `.claude/commands/gen-release-notes.md` | Command to generate release notes |

**Important:** All version files must stay in sync. The `/gen-release-notes` command updates all of them.

