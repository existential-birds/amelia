---
phase: 01-review-pipeline-efficiency
plan: 03
subsystem: reviewer-agent
tags: [reviewer, submit_review, tool-capture, tdd]
dependency_graph:
  requires: ["01-01"]
  provides: [submit_review-tool-capture, structured-review-output]
  affects: [amelia/agents/reviewer.py]
tech_stack:
  added: []
  patterns: [tool-call-capture, first-call-wins, fallback-parsing]
key_files:
  created: []
  modified:
    - amelia/agents/reviewer.py
    - tests/unit/agents/test_reviewer.py
decisions:
  - submit_review tool capture uses first-call-wins semantics; duplicates logged and discarded
  - Markdown parsing (_parse_review_result) retained as fallback for transition safety
  - No allowed_tools restriction — reviewer keeps all tools (per D-09)
  - Invalid severity from submit_review tool_input defaults to MINOR with a warning log
metrics:
  duration_seconds: 136
  completed_date: "2026-03-29"
  tasks_completed: 1
  tasks_total: 1
  files_modified: 2
---

# Phase 01 Plan 03: Submit Review Tool Capture Summary

**One-liner:** Reviewer captures `submit_review` tool-call output for structured ReviewResult instead of regex-parsing markdown; markdown parsing retained as fallback.

## Objective

Eliminate brittle regex parsing of the reviewer's markdown output by adding a `submit_review` tool that the reviewer calls with structured data (approved, severity, comments). The tool call is captured in the agentic loop, validated, and converted directly to a `ReviewResult`. Markdown parsing fallback is retained for transition safety.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for submit_review tool capture | 84b43374 | tests/unit/agents/test_reviewer.py |
| 1 (GREEN) | Implement submit_review tool capture | a0b7d1e8 | amelia/agents/reviewer.py |

## What Was Built

**`amelia/agents/reviewer.py`:**
- Updated `AGENTIC_REVIEW_PROMPT` to include step 5: instructs reviewer to call `submit_review` once after completing the review, with `approved`, `severity`, and `comments` fields.
- Added `submit_review_data: dict[str, Any] | None = None` and `submit_already_called = False` before the retry loop.
- Inside the agentic stream loop: captures `TOOL_CALL` messages with `tool_name == "submit_review"`, enforces first-call-wins, logs duplicates.
- After the retry loop: if `submit_review_data` is set, builds `ReviewResult` directly from it (validates `severity` with MINOR fallback); otherwise falls back to `_parse_review_result()`.
- `_parse_review_result()` remains intact as the fallback path.
- No `allowed_tools` passed to `execute_agentic` (all tools available).

**`tests/unit/agents/test_reviewer.py`:**
- `TestSubmitReviewTool` class with 5 new tests:
  - `test_agentic_review_captures_submit_review_tool` — verifies ReviewResult built from tool_input
  - `test_agentic_review_submit_review_first_call_wins` — verifies only first call used
  - `test_agentic_review_fallback_to_markdown_when_no_submit_review` — verifies markdown fallback
  - `test_agentic_review_does_not_restrict_allowed_tools` — verifies no allowed_tools kwarg
  - `test_agentic_review_prompt_contains_submit_review_instruction` — verifies "submit_review" in instructions

## Verification

```
uv run pytest tests/unit/agents/test_reviewer.py -x -v
# 34 passed in 0.07s

uv run ruff check amelia/agents/reviewer.py
# All checks passed!

uv run mypy amelia/agents/reviewer.py
# Success: no issues found in 1 source file
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- [x] `amelia/agents/reviewer.py` contains `msg.tool_name == "submit_review"`
- [x] `amelia/agents/reviewer.py` contains `submit_review_data`
- [x] `amelia/agents/reviewer.py` contains `submit_already_called`
- [x] `amelia/agents/reviewer.py` constructs `ReviewResult(` from submit_review_data
- [x] `amelia/agents/reviewer.py` retains `_parse_review_result(final_result, workflow_id)` as fallback
- [x] `AGENTIC_REVIEW_PROMPT` contains `submit_review`
- [x] No `allowed_tools` passed to `execute_agentic`
- [x] Tests: `test_agentic_review_captures_submit_review_tool` present and passing
- [x] Tests: `test_agentic_review_submit_review_first_call_wins` present and passing
- [x] Tests: `test_agentic_review_fallback_to_markdown` present (as `test_agentic_review_fallback_to_markdown_when_no_submit_review`) and passing
- [x] All 34 reviewer tests pass
