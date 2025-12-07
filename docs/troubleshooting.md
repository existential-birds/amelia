# Troubleshooting

Common issues and their solutions when using Amelia.

## "No module named 'amelia'"

Run `uv sync` to install dependencies.

## "Invalid API key"

Set `OPENAI_API_KEY` environment variable or use `cli:claude` driver.

## "Issue not found"

Check your tracker configuration. Use `tracker: noop` for testing without a real issue tracker.

## Pre-push hook failing

Run checks manually to see detailed errors:

```bash
uv run ruff check amelia tests
uv run mypy amelia
uv run pytest
```

## "Missing required dependencies: langgraph-checkpoint-sqlite" when running `amelia server`

This error indicates a dependency conflict from multiple installations.

**Causes:**

1. Multiple amelia installations (e.g., old `pip install` in pyenv AND new `uv tool install`)
2. Outdated `uv tool` installation that didn't pick up new dependencies

**Solutions:**

Check for multiple installations:

```bash
which amelia
type amelia
```

If pyenv shim is being used (`/Users/.../.pyenv/shims/amelia`), uninstall the old version:

```bash
pip uninstall amelia
pyenv rehash
```

Reinstall with uv:

```bash
uv tool install --reinstall git+https://github.com/anderskev/amelia.git
```

Verify correct version is used:

```bash
which amelia  # Should show ~/.local/bin/amelia
```
