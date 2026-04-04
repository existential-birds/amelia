---
phase: quick
plan: 260404-fxm
subsystem: descriptions
tags: [ai, condense, github, frontend, backend, tdd]
dependency_graph:
  requires: []
  provides: [POST /api/descriptions/condense, DevelopPage condense button]
  affects: [DevelopPage, api client, request models]
tech_stack:
  added: []
  patterns: [FastAPI router, pydantic models, react-hook-form setValue, TDD]
key_files:
  created:
    - amelia/server/routes/descriptions.py
    - tests/unit/server/routes/test_descriptions.py
  modified:
    - amelia/server/models/requests.py
    - amelia/server/routes/__init__.py
    - amelia/server/main.py
    - dashboard/src/types/index.ts
    - dashboard/src/api/client.ts
    - dashboard/src/pages/DevelopPage.tsx
    - dashboard/src/pages/__tests__/DevelopPage.test.tsx
decisions:
  - Use architect agent config for condensation (available on all GitHub profiles)
  - Profile field not required — falls back to active profile when omitted
  - condense endpoint accepts any GitHub profile, rejects non-GitHub trackers
metrics:
  duration_s: ~900
  completed_date: "2026-04-04"
  tasks_completed: 2
  tasks_total: 2
---

# Quick Task 260404-fxm: Implement AI-Powered Description Condensation

**One-liner:** POST /descriptions/condense endpoint + DevelopPage "Condense with AI" button that strips implementation noise from long GitHub issue bodies via LLM.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Backend — models, endpoint, tests (TDD) | e343df06, 1996d554 | descriptions.py, requests.py, __init__.py, main.py, test_descriptions.py |
| 2 | Frontend — API client, Condense button, tests | 66de0a42 | client.ts, types/index.ts, DevelopPage.tsx, DevelopPage.test.tsx |

## What Was Built

### Backend

- `CondenseDescriptionRequest` / `CondenseDescriptionResponse` Pydantic models in `requests.py`
- `POST /api/descriptions/condense` endpoint in `amelia/server/routes/descriptions.py`
  - Resolves explicit profile or falls back to active profile
  - Validates tracker type is GitHub (400 if not)
  - Uses architect agent's driver/model to call `driver.generate()` with a focused system prompt
  - Wraps LLM failures in HTTP 500 with descriptive message
- Router registered in `routes/__init__.py` and `main.py`
- 7 unit tests covering all success/error paths

### Frontend

- `CondenseDescriptionResponse` interface exported from `types/index.ts`
- `api.condenseDescription(description, profile?)` method in `client.ts`
- DevelopPage changes:
  - `isCondensing` state and `descriptionValue` watch
  - `handleCondense` callback: calls API, replaces description via `setValue`, shows success/error toast
  - "Condense with AI" button in Description label area — visible only when `hasSelectedIssue && descriptionLength > 2000`
  - Spinner + "Condensing..." loading state while request is in flight
- 2 new tests in `DevelopPage.test.tsx`

## Verification

- `uv run pytest tests/unit/server/routes/test_descriptions.py` — 7/7 passed
- `uv run pytest` — 2407 passed, 1 skipped
- `uv run mypy amelia` — clean
- `uv run ruff check amelia tests` — clean
- `cd dashboard && pnpm type-check` — clean
- `cd dashboard && pnpm test:run` — 901/901 passed (84 files)
- `cd dashboard && pnpm build` — succeeded

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check

### Files Created/Modified

- [x] `amelia/server/routes/descriptions.py` — created
- [x] `amelia/server/models/requests.py` — CondenseDescriptionRequest/Response added
- [x] `amelia/server/routes/__init__.py` — descriptions_router added
- [x] `amelia/server/main.py` — descriptions_router mounted
- [x] `tests/unit/server/routes/test_descriptions.py` — 7 tests
- [x] `dashboard/src/types/index.ts` — CondenseDescriptionResponse added
- [x] `dashboard/src/api/client.ts` — condenseDescription() method added
- [x] `dashboard/src/pages/DevelopPage.tsx` — condense button implemented
- [x] `dashboard/src/pages/__tests__/DevelopPage.test.tsx` — 2 new tests

### Commits

- e343df06 — test(260404-fxm): add failing tests for condense description endpoint
- 1996d554 — feat(260404-fxm): implement POST /descriptions/condense endpoint
- 66de0a42 — feat(260404-fxm): add Condense with AI button on DevelopPage

## Self-Check: PASSED
