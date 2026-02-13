# Remove Legacy Driver Values

**Date:** 2026-02-13
**Status:** Approved
**Approach:** Strict removal of backward compatibility

## Context

PR #333 simplified DriverType values from `"cli:claude"`/`"api:openrouter"` to canonical forms `"cli"`/`"api"`. However, the driver factory retained backward compatibility by accepting both old and new forms. This design removes that backward compatibility entirely.

## Current State

- DriverType enum (`amelia/core/types.py`) defines only `"cli"` and `"api"`
- Driver factory (`amelia/drivers/factory.py`) accepts both old and new forms
- Most code uses canonical values, but documentation still references legacy forms
- Tests explicitly verify legacy value support

## Decision

**Approach 1: Strict Removal** - Remove all backward compatibility code immediately. Only accept `"cli"` and `"api"`.

**Rationale:**
- DriverType enum already defines only canonical values
- No production data concerns (no database migration needed)
- Clean, simple codebase with no confusion about which values to use
- Forces correct usage immediately

## Architecture & Scope

### Files to Modify

**Core Driver Factory** (`amelia/drivers/factory.py`)
- Remove legacy value checks from `get_driver()` (lines 54, 56)
- Remove legacy value checks from `cleanup_driver_session()` (lines 79, 81)
- Remove legacy value checks from container validation (line 40)
- Simplify to strict equality checks: `driver_key == "cli"` or `driver_key == "api"`
- Update error messages to mention only canonical values

**Documentation** (8 files)
- `README.md` - Update examples
- `docs/site/guide/configuration.md` - Remove legacy value references from tables and examples
- `docs/site/guide/troubleshooting.md` - Update examples
- `docs/site/guide/usage.md` - Update examples
- `docs/site/guide/index.md` - Update examples
- `docs/site/architecture/inspiration.md` - Update driver abstraction examples
- `CHANGELOG.md` - Add entry for this change

**Tests** (3 files)
- `tests/unit/drivers/test_factory.py` - Remove test for `"cli:claude"` support
- `tests/unit/test_driver_factory.py` - Update/remove `"api:openrouter"` tests
- Add tests that verify legacy values are **rejected** with clear errors

### No Changes Needed

- `amelia/core/types.py` - DriverType enum already correct
- Dashboard TypeScript - Already uses canonical "api"
- Most test files - Already use canonical values

## Factory Logic Changes

### Before (lines 53-59)

```python
# Accept legacy values for backward compatibility
if driver_key in ("cli:claude", "cli"):
    return ClaudeCliDriver(model=model, cwd=cwd)
elif driver_key in ("api:openrouter", "api"):
    return ApiDriver(provider="openrouter", model=model)
else:
    raise ValueError(f"Unknown driver key: {driver_key}")
```

### After

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

### Similar Changes

1. **Container validation** (line 40): Change to `if driver_key != "api":`
2. **cleanup_driver_session()** (lines 79-85): Same pattern - strict equality checks
3. Remove all "Accept legacy values for backward compatibility" comments

### Key Improvements

- Simple equality checks instead of tuple membership
- Clear error message guides users to correct values
- Mentions legacy forms are no longer supported
- Uses `{driver_key!r}` to show quotes in error message

## Validation & Error Handling

### Validation Points

The factory's `ValueError` is the primary validation since all driver instantiation flows through `get_driver()`. Additional validation exists but doesn't need changes:

1. **Pydantic Validation** (already strict)
   - `amelia/core/types.py` - `DriverType` enum only allows "cli" or "api"
   - Database models use this enum, so invalid values can't be stored
   - API request models inherit this validation

2. **CLI Validation** (`amelia/cli/config.py`)
   - Currently prompts: `"Driver (cli or api)"`
   - No change needed - already uses correct values
   - Typer validation would catch invalid inputs

3. **Error Message Strategy**
   - Factory errors are caught and surfaced in CLI/API responses
   - Users see: `"Unknown driver key: 'cli:claude'. Valid options: 'cli' or 'api'. (Legacy forms 'cli:claude' and 'api:openrouter' are no longer supported.)"`
   - Clear, actionable, mentions what changed

### No Additional Validation Needed

- DriverType enum already enforces correctness at type level
- Factory is the single source of truth for driver instantiation
- Pydantic prevents invalid values from being stored/transmitted

## Test Updates

### Tests to Remove

1. **`tests/unit/drivers/test_factory.py:65`**
   - Currently tests: `get_driver("cli:claude", sandbox_config=...) raises ValueError`
   - Remove this test entirely (legacy value no longer accepted anywhere)

2. **`tests/unit/test_driver_factory.py`**
   - Line 18: Remove `("api", ApiDriver, ...)` from parameterized tests if it tests legacy
   - Lines 70, 119: Update to use canonical "api" if needed, or remove if redundant

### Tests to Add

1. **Test legacy value rejection** in `test_factory.py`:
   ```python
   def test_legacy_driver_values_rejected():
       """Legacy driver forms should raise clear errors."""
       with pytest.raises(ValueError, match="Legacy forms.*no longer supported"):
           get_driver("cli:claude", model="test")

       with pytest.raises(ValueError, match="Legacy forms.*no longer supported"):
           get_driver("api:openrouter", model="test")
   ```

2. **Test cleanup with legacy values** (if not covered):
   ```python
   async def test_cleanup_legacy_values_rejected():
       """Legacy driver values should be rejected in cleanup."""
       with pytest.raises(ValueError, match="Unknown driver key"):
           await cleanup_driver_session("cli:claude", "session-id")
   ```

### Tests Unchanged

- Most test files already use canonical "cli" and "api" values
- No changes needed to tests that use correct values
- Integration tests continue as-is

## Documentation Updates

### Files to Update

1. **README.md**
   - Update any examples showing `--driver api:openrouter` to `--driver api`
   - Update any examples showing `--driver cli:claude` to `--driver cli`

2. **docs/site/guide/configuration.md**
   - Remove references to `cli:claude` and `api:openrouter` from driver tables (lines 49, 79-82)
   - Update to show only `cli` and `api` as valid options
   - Remove "Alias" rows if present
   - Update examples (lines 40, 141, 250)

3. **docs/site/guide/troubleshooting.md**
   - Lines 385, 407, 570, 572: Update examples to use canonical values

4. **docs/site/guide/usage.md & index.md**
   - Update command examples to use `--driver cli` and `--driver api`

5. **docs/site/architecture/inspiration.md**
   - Line 14: Change driver abstraction example from `api:openrouter` vs `cli:claude` to `api` vs `cli`

6. **CHANGELOG.md**
   - Add entry for this change:
     ```markdown
     - **drivers:** Remove support for legacy driver values (`cli:claude`, `api:openrouter`). Use canonical forms `cli` and `api` instead.
     ```
   - Keep historical migration notes as-is (they document past changes)

### Documentation Principles

- Use only `"cli"` and `"api"` in all examples going forward
- Historical CHANGELOG entries stay (they document when simplification happened)
- Focus on user-facing docs (guide/), not internal research notes

## Migration Path

**For users with old configurations:**
- Error message clearly states: `"Legacy forms 'cli:claude' and 'api:openrouter' are no longer supported."`
- Users update their configs to use `"cli"` or `"api"`
- No database migration needed (no production data concerns)

## Success Criteria

- ✅ Factory only accepts `"cli"` and `"api"`
- ✅ Clear error messages guide users to correct values
- ✅ All documentation uses canonical values
- ✅ Tests verify legacy values are rejected
- ✅ All existing tests pass with canonical values
