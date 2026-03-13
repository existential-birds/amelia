---
status: testing
phase: 01-data-models-configuration
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md]
started: 2026-03-13T16:00:00Z
updated: 2026-03-13T16:00:00Z
---

## Current Test

number: 1
name: Cold Start Smoke Test
expected: |
  Kill any running server/service. Start the application from scratch with `uv run amelia dev`. Server boots without errors, migration 008 completes, and the API health check or dashboard loads on :8420/:8421.
awaiting: user response

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running server/service. Start the application from scratch with `uv run amelia dev`. Server boots without errors, migration 008 completes, and the API health check or dashboard loads on :8420/:8421.
result: [pending]

### 2. All Tests Pass
expected: Running `uv run pytest` completes with 0 failures. All 1815+ tests pass including the 29 new PR auto-fix model tests and 13 persistence tests.
result: [pending]

### 3. PR Auto-Fix Config on Profile via API
expected: Create or update a profile via the API (POST/PATCH to profiles endpoint) with a `pr_autofix` field containing `{"aggressiveness": "standard", "max_files": 10}`. Reading the profile back returns the same config with correct field values. Setting `pr_autofix` to null disables the feature.
result: [pending]

### 4. PR Polling Toggle in Server Settings
expected: Update server settings via the API with `pr_polling_enabled: true`. Reading settings back shows `pr_polling_enabled: true`. Default value for new installations is `false`.
result: [pending]

### 5. AggressivenessLevel JSON Round-Trip
expected: A profile with `pr_autofix.aggressiveness` set to "thorough" serializes to JSON with the string name (not integer 3). Deserializing that JSON back produces an identical config. Both string ("thorough") and integer (3) inputs are accepted.
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0

## Gaps

[none yet]
