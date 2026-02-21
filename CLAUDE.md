# CLAUDE.md

## Build & Development Commands

This project uses [uv](https://docs.astral.sh/uv/) for Python and [pnpm](https://pnpm.io/) for the dashboard frontend (`dashboard/`).

```bash
# Backend
uv run ruff check --fix amelia tests   # Lint (auto-fix)
uv run mypy amelia                     # Type check
uv run pytest                          # Full test suite
uv run pytest tests/unit/              # Unit tests only

# Dashboard (run from dashboard/)
pnpm build        # Production build
pnpm test:run     # Tests (CI mode)
pnpm lint:fix     # ESLint auto-fix
pnpm type-check   # TypeScript checking

# Full stack
uv run amelia dev                      # API on :8420, dashboard on :8421
```

**Pre-push hook** runs `ruff check`, `mypy`, `pytest`, and `pnpm build` — all must pass.

## Code Conventions

- **Test-Driven Development (TDD)** — write tests first, then implementation
- **Python 3.12+** with type hints everywhere
- **Pydantic models** for all data structures — not ad-hoc dicts
- **Async throughout** — avoid blocking calls in async functions
- **Loguru** for logging (`logger`), not `print`. Use kwargs for structured fields: `logger.info("msg", key=value)`
- **Typer** for CLI with annotated parameters
- Raise `ValueError` with clear messages for validation failures
- New drivers/agents must conform to interfaces in `amelia/core/`

## Test Conventions

Tests use `pytest-asyncio` with `asyncio_mode = "auto"`.

- **DRY** — extract common setup into fixtures in `tests/conftest.py`
- **Integration tests** (`tests/integration/`) must use real components — only mock at the external boundary (e.g., HTTP calls to LLM APIs). Never mock internal classes like `Architect`, `Developer`, or `Reviewer`. If you're patching internals, it's a unit test — put it in `tests/unit/`.
- **High-fidelity mocks** — return the same types production code returns (e.g., Pydantic model instances, not `.model_dump()` dicts)

## Browser Automation

Use `agent-browser` for web automation: `agent-browser open <url>`, then `agent-browser snapshot -i` for interactive element refs, then `agent-browser click @e1` / `agent-browser fill @e2 "text"`.

## Release Process

Use `/gen-release-notes <previous-tag>` to generate notes and bump versions in `pyproject.toml`, `amelia/__init__.py`, `dashboard/package.json`, `docs/site/package.json`, and `CHANGELOG.md`. All version files must stay in sync. Then create a release branch/PR, merge, tag with `vX.Y.Z`, and the GitHub Action creates the release.
