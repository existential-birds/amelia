# Repository Guidelines

## Project Structure & Module Organization
- Source lives in `amelia/` (agents, drivers, trackers, CLI entry in `main.py`; shared utils in `core/`).
- Tests mirror modules in `tests/` (`unit/`, `integration/`, `e2e/`, `perf/`).
- Docs and design notes: `docs/` and `specs/`; top-level configs: `data-model.md`, `pyproject.toml`. Runtime config in `~/.amelia/amelia.db`.

## Build, Test, and Development Commands
- Install deps: `uv sync` (uses `pyproject.toml`/`uv.lock`).
- Run CLI locally: `uv run amelia --help` or `uv run amelia start PROJ-123 --profile dev`.
- Lint: `uv run ruff check .`; format (if needed): `uv run ruff format .`.
- Type check: `uv run mypy .` (strict).
- Tests: fast loop `uv run pytest tests/unit`; full suite `uv run pytest`; scope with `-k "pattern"`.

## Coding Style & Naming Conventions
- Python 3.12; prefer full type hints and dataclasses/TypedDicts where appropriate.
- Line length 100; avoid disabling `E501` unless unavoidable.
- Imports follow Ruff isort order: future, stdlib, third-party, first-party (`amelia`), local.
- Naming: modules/functions snake_case; classes PascalCase; constants UPPER_SNAKE.

## Testing Guidelines
- Framework: pytest (`asyncio_mode = auto`); mark async tests with `@pytest.mark.asyncio`.
- Name tests `test_<behavior>_<condition>` and place next to the code path (e.g., `amelia/core/state.py` → `tests/unit/core/test_state.py`).
- Add unit coverage for new logic; include integration/e2e when touching workflows or drivers.

## Commit & Pull Request Guidelines
- Commits: concise imperative subject (e.g., `Add driver timeout handling`).
- Before PR: run `uv run ruff check .`, `uv run mypy .`, and relevant `uv run pytest` scope; note expected failures.
- PRs: state problem, approach, tests executed; link issue/ticket and include screenshots if UX-facing (CLI output acceptable).

## Security & Configuration Tips
- Repository runs locally; keep secrets out of code and logs. Use env vars (e.g., `OPENROUTER_API_KEY`) for secrets.
- Validate driver/tracker inputs at boundaries; avoid writing tokens to logs or files.
- Treat `data-model.md` and config files as source of truth; update docs when interfaces change.
