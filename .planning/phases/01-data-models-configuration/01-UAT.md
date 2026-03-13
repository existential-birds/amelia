---
status: complete
phase: 01-data-models-configuration
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md]
started: 2026-03-13T16:00:00Z
updated: 2026-03-13T16:10:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running server/service. Start the application from scratch with `uv run amelia dev`. Server boots without errors, migration 008 completes, and the API health check or dashboard loads on :8420/:8421.
result: pass

### 2. All Tests Pass
expected: Running `uv run pytest` completes with 0 failures. All 1815+ tests pass including the 29 new PR auto-fix model tests and 13 persistence tests.
result: pass

### 3. PR Auto-Fix Config on Profile via API
expected: Create or update a profile via the API (POST/PATCH to profiles endpoint) with a `pr_autofix` field containing `{"aggressiveness": "standard", "max_files": 10}`. Reading the profile back returns the same config with correct field values. Setting `pr_autofix` to null disables the feature.
result: issue
reported: "Setting pr_autofix to null via PUT did not clear it — the response still shows the previous config. The null update is being ignored rather than applied. The issue is likely in the ProfileUpdate handling: since all fields default to None, the update logic can't distinguish between 'field not provided' (should keep existing value) and 'field explicitly set to null' (should clear it). Both arrive as None on the Pydantic model, so the update code skips it in both cases. This is a classic optional-nullable ambiguity problem. The fix would need to use a sentinel value (like UNSET) or check model_fields_set to distinguish 'explicitly sent null' from 'not included in the request.'"
severity: major

### 4. PR Polling Toggle in Server Settings
expected: Update server settings via the API with `pr_polling_enabled: true`. Reading settings back shows `pr_polling_enabled: true`. Default value for new installations is `false`.
result: pass

### 5. AggressivenessLevel JSON Round-Trip
expected: A profile with `pr_autofix.aggressiveness` set to "thorough" serializes to JSON with the string name (not integer 3). Deserializing that JSON back produces an identical config. Both string ("thorough") and integer (3) inputs are accepted.
result: pass

## Summary

total: 5
passed: 4
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "Setting pr_autofix to null disables the feature"
  status: failed
  reason: "User reported: Setting pr_autofix to null via PUT did not clear it — the response still shows the previous config. The null update is being ignored rather than applied. Classic optional-nullable ambiguity: ProfileUpdate can't distinguish 'field not provided' from 'field explicitly set to null' since both arrive as None."
  severity: major
  test: 3
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
