# Repository Guidelines

## Project Structure & Modules
- Source: `amelia/` (agents, drivers, trackers, CLI entry in `main.py`, shared core utilities in `core/`).
- Tests: `tests/` split into `unit/`, `integration/`, `e2e/`, and `perf/`; pytest config lives in `pyproject.toml`.
- Docs & specs: `docs/` (architecture, configuration) and `specs/` for design notes; top-level configs include `settings.amelia.yaml` and `data-model.md`.

## Build, Test, and Development Commands
- Create env & install: `uv sync` (uses `pyproject.toml` and `uv.lock`).
- Run CLI: `uv run amelia --help` or `uv run amelia start PROJ-123 --profile dev`.
- Lint/format: `uv run ruff check .` (lint) and `uv run ruff format .` if formatting is enabled; keep `line-length = 100`.
- Type check: `uv run mypy .` (strict mode, ignores missing imports).
- Tests: `uv run pytest tests/unit` for fast feedback; `uv run pytest` for full suite; add `-k "<pattern>"` to scope.

## Coding Style & Naming
- Python 3.12; prefer type hints everywhere (mypy strict).
- Imports follow Ruff isort settings: `future`, `standard-library`, `third-party`, `first-party (amelia)`, `local-folder`; single-line imports enforced.
- Keep modules/functions/classes snake_case; classes PascalCase; constants UPPER_SNAKE.
- Target line length 100; avoid disabling `E501` unless unavoidable.

## Testing Guidelines
- Place tests mirroring module paths (e.g., `amelia/core/state.py` → `tests/unit/core/test_state.py`).
- Use pytest with `asyncio_mode = auto`; prefer `pytest.mark.asyncio` for async tests.
- Name tests descriptively: `test_<behavior>_<condition>`.
- For new features, add unit coverage and, when touching workflows, an integration or e2e path under `tests/integration` or `tests/e2e`.

## Commit & Pull Request Guidelines
- Commits: concise imperative subject (e.g., `Add driver timeout handling`); group related changes.
- Before PR: run `uv run ruff check .`, `uv run mypy .`, and `uv run pytest`; note any expected failures.
- PR description: problem statement, approach, testing commands executed, and any follow-up TODOs; include issue link if applicable and screenshots for UX changes.

## Security & Configuration Tips
- Keep secrets out of repo; prefer environment variables referenced by `settings.amelia.yaml`.
- When adding drivers/trackers, validate inputs at boundaries and avoid writing tokens to logs.
