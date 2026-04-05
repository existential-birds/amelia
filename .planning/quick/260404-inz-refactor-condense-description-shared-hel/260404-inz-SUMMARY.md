---
phase: quick
plan: 260404-inz
subsystem: server/frontend
tags: [refactor, service-layer, condense, undo, config]
dependency_graph:
  requires: [260404-fxm]
  provides: [condenser-service, resolve-github-profile-helper, condense-undo-ui]
  affects: [descriptions-route, github-route, config-route, develop-page]
tech_stack:
  added: [amelia/services/condenser.py, amelia/server/routes/_helpers.py]
  patterns: [service-layer, shared-route-helpers, centralized-prompts]
key_files:
  created:
    - amelia/server/routes/_helpers.py
    - amelia/services/condenser.py
    - tests/unit/services/test_condenser.py
  modified:
    - amelia/server/routes/descriptions.py
    - amelia/server/routes/github.py
    - amelia/server/routes/config.py
    - amelia/server/models/requests.py
    - amelia/agents/prompts/defaults.py
    - dashboard/src/types/index.ts
    - dashboard/src/pages/DevelopPage.tsx
    - dashboard/src/pages/__tests__/DevelopPage.test.tsx
    - dashboard/src/pages/__tests__/SpecBuilderPage.test.tsx
decisions:
  - condenser service returns (str, session_id) not (str, DriverUsage) — driver.generate() returns session_id as second element per GenerateResult type alias, not usage
  - resolve_github_profile accepts profile_name as str|None with require_github kwarg to cover both github.py (required name) and descriptions.py (optional name with active-profile fallback)
metrics:
  duration_s: 1080
  completed: "2026-04-04T17:46:09Z"
  tasks_completed: 2
  files_modified: 9
  files_created: 3
---

# Quick Task 260404-inz: Refactor condense-description — shared helper, service layer, centralized prompt, undo UI

**One-liner:** Extracted resolve_github_profile helper and condense_description service, centralized condenser prompt in PROMPT_DEFAULTS, added configurable agent_type and threshold, and implemented undo button in the frontend.

## What Was Built

### Backend

**`amelia/server/routes/_helpers.py`** — New shared helper `resolve_github_profile(profile_name, profile_repo, *, require_github)` used by both `github.py` and `descriptions.py`. Eliminated the duplicated `_resolve_github_profile` local function in `github.py`.

**`amelia/services/condenser.py`** — New service function `condense_description(description, driver, system_prompt=None)`. Loads default prompt from `PROMPT_DEFAULTS["condenser.system"]`, calls `driver.generate()`, logs completion at debug level, returns `(str, session_id)`.

**`amelia/agents/prompts/defaults.py`** — Added `"condenser.system"` entry to `PROMPT_DEFAULTS`. Removed inline `CONDENSE_SYSTEM_PROMPT` constant from `descriptions.py`.

**`amelia/server/routes/descriptions.py`** — Now a thin adapter: resolves profile via helper, gets agent config using `request.agent_type`, gets driver, calls service. Reduced from 88 LOC to 63 LOC.

**`amelia/server/models/requests.py`** — Added `agent_type: str = "architect"` to `CondenseDescriptionRequest`.

**`amelia/server/routes/config.py`** — Added `condense_threshold_chars: int = 2000` to `ConfigResponse`.

### Frontend

**`dashboard/src/types/index.ts`** — Added `condense_threshold_chars: number` to `ConfigResponse` interface.

**`dashboard/src/pages/DevelopPage.tsx`** — Store config in state; use `config?.condense_threshold_chars ?? 2000` instead of hardcoded 2000. Added `originalDescription` state saved before condensing; "Restore original" button appears when `originalDescription !== null && originalDescription !== current`. Cleared on new issue selection.

**`dashboard/src/pages/__tests__/DevelopPage.test.tsx`** — Replaced inline `ApiError` class with `vi.importActual`. Added 3 new tests: restore button appears, restore sets original value, restore disappears after clicking.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] driver.generate() returns session_id not DriverUsage**

- **Found during:** Task 1 implementation
- **Issue:** Plan specified `condense_description` should return `tuple[str, DriverUsage | None]` but `DriverInterface.generate()` returns `GenerateResult = tuple[Any, str | None]` where the second element is a session_id, not usage. mypy caught this.
- **Fix:** Changed service signature to `tuple[str, Any]` matching the driver protocol. Updated test assertions accordingly.
- **Files modified:** `amelia/services/condenser.py`, `tests/unit/services/test_condenser.py`

**2. [Rule 2 - Missing] SpecBuilderPage.test.tsx ConfigResponse mock missing new field**

- **Found during:** Task 2 pnpm build (tsc caught it)
- **Issue:** `SpecBuilderPage.test.tsx` had a typed mock of `ConfigResponse` missing the required `condense_threshold_chars` field.
- **Fix:** Added `condense_threshold_chars: 2000` to the mock object.
- **Files modified:** `dashboard/src/pages/__tests__/SpecBuilderPage.test.tsx`
- **Commit:** 1adbe964

## Test Results

- Backend unit tests: 2375 passed (13 new tests added)
- Frontend tests: 904 passed (4 new tests added)
- mypy: 168 files, no errors
- ruff: all checks passed
- pnpm build: success

## Known Stubs

None — all features fully implemented and wired.

## Self-Check: PASSED

Files exist:
- amelia/server/routes/_helpers.py: FOUND
- amelia/services/condenser.py: FOUND
- amelia/agents/prompts/defaults.py: FOUND (condenser.system key added)
- tests/unit/services/test_condenser.py: FOUND

Commits:
- 632d4007: FOUND (Task 1 — backend refactor)
- 69d2ef19: FOUND (Task 2 — frontend changes)
- 1adbe964: FOUND (Fix — SpecBuilderPage test)
