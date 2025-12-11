# Amelia Context for Gemini

This document provides context and instructions for working on the Amelia project.
**Strictly adhere to these guidelines.**

## 1. Project Overview

**Amelia** is a local agentic coding system that orchestrates software development tasks through multiple AI agents. It uses a LangGraph-based state machine to coordinate planning, coding, and reviewing.

*   **Orchestrator:** LangGraph state machine (`amelia/core/orchestrator.py`).
*   **Dual Driver:** Supports `api:openai` (pydantic-ai) and `cli:claude` (for compliance).
*   **Privacy:** Designed to run locally.

## 2. Environment & Commands

### Backend (Python + uv)
Dependency management via **uv**.

```bash
uv sync                                # Install dependencies
uv run amelia start <ISSUE> --profile <PROFILE> # Run Orchestrator
uv run pytest                          # Run all tests
uv run ruff check amelia tests         # Lint
uv run mypy amelia                     # Type check
```

**Pre-push Hook:** Enforces `ruff`, `mypy`, and `pytest` passing before push.

### Frontend (React + Vite)
Located in `dashboard/`.

**Running the dashboard:**
- For general usage: `uv run amelia dev` serves the built dashboard at `localhost:8420`
- For frontend development (HMR): Run `pnpm dev` in `dashboard/` for hot reload

```bash
pnpm install
pnpm dev          # HMR dev server (port 8421) - frontend development only
pnpm build        # Production build
pnpm test         # Vitest
pnpm lint         # ESLint
pnpm type-check   # TypeScript check
```

**Stack:** React Router v7, Tailwind CSS v4, shadcn/ui, Zustand, React Flow.

## 3. Critical Code Conventions

### Python
*   **Type Hints:** Mandatory (Python 3.12+).
*   **Async:** Core logic is async. Use `async/await` consistently.
*   **Pydantic:** Use Models for data structures. No raw dicts.
*   **Logging:** Use `loguru` (`logger.info`), NEVER `print`.
*   **Docstrings:** Google-style mandatory for all exported symbols.

### Testing (TDD)
*   **Principle:** Write tests FIRST (Red-Green-Refactor).
*   **Tooling:** `pytest-asyncio` (auto mode).
*   **Structure:**
    *   `tests/unit/`: Isolated logic verification.
    *   `tests/integration/`: Component interaction.
    *   `tests/e2e/`: Full flow.
*   **Mocking:** Mock external LLM/API calls in unit tests.

### Commit Messages
Follow **Conventional Commits**: `type(scope): description`.

| Type | Scope | Example |
| :--- | :--- | :--- |
| `feat` | `server`, `cli`, `dashboard` | `feat(server): add retry logic` |
| `fix` | `agent`, `core` | `fix(core): handle missing key` |
| `docs` | `readme` | `docs: update setup guide` |
| `refactor`| `utils` | `refactor(utils): simplify regex` |
| `test` | `unit` | `test(unit): add coverage for X` |

## 4. Workflows & Protocols

You should encourage and adhere to the project's agentic workflows (defined in `.agent/workflows/`):

*   **PR Creation:** `/amelia:create-pr` (Standardized, self-verifying descriptions).
*   **Code Review:** `/amelia:review` (Rigorous, tool-backed verification).
*   **Documentation:** `/amelia:ensure-doc` (Coverage enforcement).
*   **Testing:** `/amelia:gen-test-plan` (Manual test plans for complex features).

## 5. Architecture Reference

| Layer | Path | Purpose |
| :--- | :--- | :--- |
| **Core** | `amelia/core/` | State definitions, Orchestrator execution loop. |
| **Agents** | `amelia/agents/` | `Architect` (Plan), `Developer` (Edit), `Reviewer` (Critique). |
| **Drivers** | `amelia/drivers/` | LLM Adapters (`api` vs `cli`). |
| **Trackers** | `amelia/trackers/`| Issue source adapters (GitHub/Jira). |

### Data Flow
`Issue` -> **Architect** (TaskDAG) -> **Human** -> **Developer** (Code) <-> **Reviewer** (Critique) -> **Merge**
