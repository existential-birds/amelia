# Remove Legacy Driver Values Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove backward compatibility for legacy driver values (`cli:claude`, `api:openrouter`) from the driver factory, accepting only canonical forms (`cli`, `api`).

**Architecture:** Modify `amelia/drivers/factory.py` to use strict equality checks instead of tuple membership for driver validation. Update all documentation to use canonical values. Add tests to verify legacy values are rejected with clear error messages.

**Tech Stack:** Python 3.12, pytest, Pydantic validation

---

## Task 1: Add Tests for Legacy Value Rejection

**Files:**
- Modify: `tests/unit/drivers/test_factory.py`

**Step 1: Write failing test for legacy CLI driver rejection**

Add to `tests/unit/drivers/test_factory.py`:

```python
def test_legacy_cli_driver_rejected() -> None:
    """Legacy cli:claude driver form should raise clear error."""
    with pytest.raises(
        ValueError,
        match=r"Unknown driver key: 'cli:claude'.*Legacy forms.*no longer supported",
    ):
        get_driver("cli:claude", model="test-model")
```

**Step 2: Write failing test for legacy API driver rejection**

Add to `tests/unit/drivers/test_factory.py`:

```python
def test_legacy_api_driver_rejected() -> None:
    """Legacy api:openrouter driver form should raise clear error."""
    with pytest.raises(
        ValueError,
        match=r"Unknown driver key: 'api:openrouter'.*Legacy forms.*no longer supported",
    ):
        get_driver("api:openrouter", model="test-model")
```

**Step 3: Write failing test for legacy cleanup rejection**

Add to `tests/unit/drivers/test_factory.py`:

```python
@pytest.mark.asyncio
async def test_legacy_cleanup_driver_rejected() -> None:
    """Legacy driver values should be rejected in cleanup."""
    with pytest.raises(
        ValueError,
        match=r"Unknown driver key: 'cli:claude'",
    ):
        await cleanup_driver_session("cli:claude", "test-session-id")

    with pytest.raises(
        ValueError,
        match=r"Unknown driver key: 'api:openrouter'",
    ):
        await cleanup_driver_session("api:openrouter", "test-session-id")
```

**Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/unit/drivers/test_factory.py::test_legacy_cli_driver_rejected tests/unit/drivers/test_factory.py::test_legacy_api_driver_rejected tests/unit/drivers/test_factory.py::test_legacy_cleanup_driver_rejected -v`

Expected: All 3 tests FAIL (legacy values currently accepted)

**Step 5: Commit failing tests**

```bash
git add tests/unit/drivers/test_factory.py
git commit -m "test: add tests for legacy driver value rejection (TDD red phase)"
```

---

## Task 2: Update get_driver() to Reject Legacy Values

**Files:**
- Modify: `amelia/drivers/factory.py:40-59`

**Step 1: Update container validation (line 40)**

Change:
```python
if driver_key not in ("api:openrouter", "api"):
    raise ValueError(f"Unknown driver key: {driver_key}")
```

To:
```python
if driver_key != "api":
    raise ValueError(f"Unknown driver key: {driver_key}")
```

**Step 2: Update get_driver() main logic (lines 53-59)**

Change:
```python
# Accept legacy values for backward compatibility
if driver_key in ("cli:claude", "cli"):
    return ClaudeCliDriver(model=model, cwd=cwd)
elif driver_key in ("api:openrouter", "api"):
    return ApiDriver(provider="openrouter", model=model)
else:
    raise ValueError(f"Unknown driver key: {driver_key}")
```

To:
```python
if driver_key == "cli":
    return ClaudeCliDriver(model=model, cwd=cwd)
elif driver_key == "api":
    return ApiDriver(provider="openrouter", model=model)
else:
    raise ValueError(
        f"Unknown driver key: {driver_key!r}. "
        f"Valid options: 'cli' or 'api'. "
        f"(Legacy forms 'cli:claude' and 'api:openrouter' are no longer supported.)"
    )
```

**Step 3: Run new tests to verify they pass**

Run: `uv run pytest tests/unit/drivers/test_factory.py::test_legacy_cli_driver_rejected tests/unit/drivers/test_factory.py::test_legacy_api_driver_rejected -v`

Expected: Both tests PASS

**Step 4: Commit get_driver() changes**

```bash
git add amelia/drivers/factory.py
git commit -m "feat(drivers): reject legacy driver values in get_driver()"
```

---

## Task 3: Update cleanup_driver_session() to Reject Legacy Values

**Files:**
- Modify: `amelia/drivers/factory.py:78-85`

**Step 1: Update cleanup_driver_session() logic**

Change:
```python
# Accept legacy values for backward compatibility
if driver_key in ("cli:claude", "cli"):
    return False  # ClaudeCliDriver has no session state to clean
elif driver_key in ("api:openrouter", "api"):
    async with ApiDriver._sessions_lock_for_loop():
        return ApiDriver._sessions.pop(session_id, None) is not None
else:
    raise ValueError(f"Unknown driver key: {driver_key}")
```

To:
```python
if driver_key == "cli":
    return False  # ClaudeCliDriver has no session state to clean
elif driver_key == "api":
    async with ApiDriver._sessions_lock_for_loop():
        return ApiDriver._sessions.pop(session_id, None) is not None
else:
    raise ValueError(
        f"Unknown driver key: {driver_key!r}. "
        f"Valid options: 'cli' or 'api'. "
        f"(Legacy forms 'cli:claude' and 'api:openrouter' are no longer supported.)"
    )
```

**Step 2: Run cleanup test to verify it passes**

Run: `uv run pytest tests/unit/drivers/test_factory.py::test_legacy_cleanup_driver_rejected -v`

Expected: Test PASS

**Step 3: Commit cleanup changes**

```bash
git add amelia/drivers/factory.py
git commit -m "feat(drivers): reject legacy driver values in cleanup_driver_session()"
```

---

## Task 4: Remove Tests for Legacy Value Support

**Files:**
- Modify: `tests/unit/drivers/test_factory.py:65`
- Modify: `tests/unit/test_driver_factory.py`

**Step 1: Remove legacy CLI driver test from test_factory.py**

In `tests/unit/drivers/test_factory.py` around line 65, remove the test that verifies `get_driver("cli:claude", sandbox_config=...)` raises ValueError for sandbox incompatibility. This test is no longer needed since "cli:claude" is rejected outright.

**Step 2: Review test_driver_factory.py for legacy value tests**

Check `tests/unit/test_driver_factory.py` lines 18, 70, 119:
- If line 18 has `("api", ApiDriver, ...)` testing legacy "api" form as distinct from canonical, remove it
- If lines 70, 119 test "api" as legacy (not canonical), update to use canonical "api" value
- Most likely these already test canonical values, so minimal changes needed

**Step 3: Run full driver factory test suite**

Run: `uv run pytest tests/unit/drivers/test_factory.py tests/unit/test_driver_factory.py -v`

Expected: All tests PASS

**Step 4: Commit test cleanup**

```bash
git add tests/unit/drivers/test_factory.py tests/unit/test_driver_factory.py
git commit -m "test(drivers): remove tests for legacy driver value support"
```

---

## Task 5: Update Documentation - Configuration Guide

**Files:**
- Modify: `docs/site/guide/configuration.md`

**Step 1: Update driver table (lines 49, 79-82)**

Remove rows or references to `cli:claude` and `api:openrouter`. Update table to show only:

```markdown
| Driver | Description | Requirements |
|--------|-------------|--------------|
| `cli` | Claude CLI wrapper | `claude` CLI installed, authenticated |
| `api` | Direct OpenRouter API calls | `OPENROUTER_API_KEY` env var, `model` field |
```

**Step 2: Update examples (lines 40, 141, 250)**

Change all occurrences of:
- `--driver api:openrouter` → `--driver api`
- `--driver cli:claude` → `--driver cli`

**Step 3: Remove "Alias" references**

If the doc mentions "Alias" rows like "cli is an alias for cli:claude", remove them.

**Step 4: Verify documentation renders correctly**

Run: `cd docs/site && pnpm dev` (if available) or just review the markdown

**Step 5: Commit configuration doc updates**

```bash
git add docs/site/guide/configuration.md
git commit -m "docs(guide): update driver values in configuration guide"
```

---

## Task 6: Update Documentation - Usage & Index

**Files:**
- Modify: `docs/site/guide/usage.md`
- Modify: `docs/site/guide/index.md`

**Step 1: Update usage.md examples**

Around line 14-21, change:
- `--driver api:openrouter` → `--driver api`
- `--driver cli:claude` → `--driver cli`

**Step 2: Update index.md examples**

Around line 20, change:
```bash
amelia config profile create dev --driver cli:claude --tracker none --activate
```

To:
```bash
amelia config profile create dev --driver cli --tracker none --activate
```

**Step 3: Commit usage & index updates**

```bash
git add docs/site/guide/usage.md docs/site/guide/index.md
git commit -m "docs(guide): update driver values in usage and index"
```

---

## Task 7: Update Documentation - Troubleshooting

**Files:**
- Modify: `docs/site/guide/troubleshooting.md`

**Step 1: Update examples (lines 385, 407, 570, 572)**

Change all occurrences of:
- `--driver api:openrouter` → `--driver api`
- `--driver cli:claude` → `--driver cli`
- `cli:claude` mentions → `cli`

**Step 2: Commit troubleshooting updates**

```bash
git add docs/site/guide/troubleshooting.md
git commit -m "docs(guide): update driver values in troubleshooting guide"
```

---

## Task 8: Update Documentation - Architecture & Research

**Files:**
- Modify: `docs/site/architecture/inspiration.md`
- Modify: `docs/research/inspirations-research-notes.md` (optional)

**Step 1: Update inspiration.md (line 14)**

Change:
```markdown
Amelia's driver abstraction (`api:openrouter` vs `cli:claude`)
```

To:
```markdown
Amelia's driver abstraction (`api` vs `cli`)
```

**Step 2: Optionally update research notes**

In `docs/research/inspirations-research-notes.md` line 10, update if needed (research notes are lower priority).

**Step 3: Commit architecture doc updates**

```bash
git add docs/site/architecture/inspiration.md docs/research/inspirations-research-notes.md
git commit -m "docs(architecture): update driver values in architecture docs"
```

---

## Task 9: Update README

**Files:**
- Modify: `README.md`

**Step 1: Search for legacy driver references**

Run: `grep -n "api:openrouter\|cli:claude" README.md`

**Step 2: Update any examples found**

Change:
- `--driver api:openrouter` → `--driver api`
- `--driver cli:claude` → `--driver cli`

**Step 3: Commit README updates**

```bash
git add README.md
git commit -m "docs: update driver values in README"
```

---

## Task 10: Update CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add entry at top of Unreleased section**

Add under `## [Unreleased]`:

```markdown
### Changed

- **drivers:** Remove support for legacy driver values (`cli:claude`, `api:openrouter`). Use canonical forms `cli` and `api` instead.
```

**Step 2: Keep historical migration notes**

Do NOT modify existing migration notes (lines 80, 169, 292, 304). These document past changes.

**Step 3: Commit CHANGELOG update**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): add entry for legacy driver value removal"
```

---

## Task 11: Run Full Test Suite

**Files:**
- None (verification step)

**Step 1: Run complete test suite**

Run: `uv run pytest`

Expected: All tests PASS

**Step 2: Run type checking**

Run: `uv run mypy amelia`

Expected: No type errors

**Step 3: Run linting**

Run: `uv run ruff check amelia tests`

Expected: No lint errors

**Step 4: If any failures, fix them**

Address any test failures, type errors, or lint issues before proceeding.

---

## Task 12: Final Verification & Commit

**Files:**
- None (verification step)

**Step 1: Verify all changes**

Run: `git status` and `git diff main`

Review all modified files to ensure:
- No legacy value support remains in code
- Documentation consistently uses canonical values
- Tests verify rejection of legacy values

**Step 2: Run full test suite one more time**

Run: `uv run pytest && uv run mypy amelia && uv run ruff check amelia tests`

Expected: All checks PASS

**Step 3: Review commit history**

Run: `git log --oneline -15`

Verify all commits follow conventional commit format and are properly scoped.

**Step 4: Update implementation plan status**

Mark this plan as complete in `docs/plans/2026-02-13-remove-legacy-driver-values.md`:

Add at top:
```markdown
**Status:** ✅ Implemented (2026-02-13)
```

**Step 5: Final commit**

```bash
git add docs/plans/2026-02-13-remove-legacy-driver-values.md
git commit -m "docs: mark legacy driver value removal plan as complete"
```

---

## Success Criteria

- ✅ Factory only accepts `"cli"` and `"api"`
- ✅ Clear error messages guide users to correct values
- ✅ All documentation uses canonical values
- ✅ Tests verify legacy values are rejected
- ✅ All existing tests pass with canonical values
- ✅ No type errors or lint issues
- ✅ Conventional commit messages for all commits

## Related Skills

- @superpowers:test-driven-development for TDD workflow
- @superpowers:verification-before-completion before marking complete
