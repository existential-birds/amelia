# Amelia Context for Gemini

This document provides context and instructions for working on the Amelia project.

## Project Overview

**Amelia** is a local agentic coding system that orchestrates software development tasks through multiple AI agents (Architect, Developer, Reviewer, Project Manager). It uses a LangGraph-based state machine to coordinate these agents to analyze issues, plan tasks, execute code changes, and review them.

Key features:
- **Agentic Orchestration:** Specialized agents for planning, coding, and reviewing.
- **Dual Driver Mode:** Supports direct API calls (`api:openai`) via `pydantic-ai` and CLI wrapping (`cli:claude`) for enterprise compliance.
- **Pluggable Trackers:** Integrates with Jira and GitHub for issue management.
- **Local & Secure:** Designed to run locally, respecting data privacy.

## Environment & Build

This project uses **[uv](https://docs.astral.sh/uv/)** for dependency management and build workflows.

### Setup

```bash
# Install dependencies
uv sync
```

### Running the Application

The entry point is `amelia/main.py`, exposed as the `amelia` CLI command.

```bash
# Run the full orchestrator
uv run amelia start <ISSUE_ID> --profile <PROFILE_NAME>

# Generate a plan only
uv run amelia plan-only <ISSUE_ID>

# Run a local review on uncommitted changes
uv run amelia review --local
```

### Testing & Quality

Strict adherence to testing and code quality is required.

```bash
# Run all tests
uv run pytest

# Run specific tests
uv run pytest tests/unit/test_agents.py

# Linting (Ruff)
uv run ruff check .

# Type Checking (MyPy) - Strict mode enabled
uv run mypy .
```

**Pre-push Hook:** The project enforces a pre-push hook that runs `ruff`, `mypy`, and `pytest`. Ensure these pass before attempting to commit/push.

## Architecture Highlights

*   **Core (`amelia/core/`):** Contains the `Orchestrator` (LangGraph state machine), `ExecutionState`, and shared types (`TaskDAG`, `Issue`).
*   **Agents (`amelia/agents/`):** specialized classes (`Architect`, `Developer`, `Reviewer`) that implement the logic for each step.
*   **Drivers (`amelia/drivers/`):** Abstraction layer for LLM interaction.
    *   `api`: Direct usage of LLM APIs (currently OpenAI).
    *   `cli`: Wrappers for CLI tools (currently a stub for Claude).
*   **Trackers (`amelia/trackers/`):** Adapters for issue tracking systems (Jira, GitHub).

### Data Flow
`Issue` -> **Architect** (creates `TaskDAG`) -> **Human Approval** -> **Developer** (executes `Task`s) <-> **Reviewer** (evaluates changes) -> **Complete**

## Development Conventions

*   **Type Hinting:** Python 3.12+ type hints are **mandatory** for all functions and methods.
*   **Pydantic:** Use Pydantic models for all data structures and schemas. Avoid raw dictionaries.
*   **Async/Await:** The core logic is asynchronous. Use `async`/`await` consistently.
*   **Logging:** Use `loguru` for logging. Do not use `print` statements in library code.
*   **Testing:**
    *   Write tests for all new functionality.
    *   Use `pytest-asyncio` for async tests.
    *   Mock external interactions (LLM calls, API calls) in unit tests.
*   **Docstrings:** Google-style docstrings for all public modules, classes, and functions.

## Key Files

*   `amelia/main.py`: CLI entry point.
*   `amelia/core/orchestrator.py`: Main state machine logic.
*   `amelia/core/state.py`: State definition (`ExecutionState`).
*   `amelia/agents/*.py`: Agent implementations.
*   `settings.amelia.yaml`: User configuration (profiles).
*   `pyproject.toml`: Project dependencies and tool configuration.
