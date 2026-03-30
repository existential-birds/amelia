---
phase: 01-review-pipeline-efficiency
plan: "02"
subsystem: agents/evaluator
tags: [evaluator, tool-calling, execute_agentic, submit_evaluation, reliability]
dependency_graph:
  requires: ["01-01"]
  provides: ["tool-based-evaluator"]
  affects: ["amelia/agents/evaluator.py", "tests/unit/agents/test_evaluator.py"]
tech_stack:
  added: []
  patterns: ["execute_agentic with allowed_tools", "first-call-wins tool capture", "model_validate(tool_input)"]
key_files:
  created: []
  modified:
    - amelia/agents/evaluator.py
    - tests/unit/agents/test_evaluator.py
decisions:
  - "Use allowed_tools=['submit_evaluation'] to restrict evaluator to a single structured tool call"
  - "First-call-wins: if submit_evaluation is called more than once, only first result is used and a warning is logged"
  - "RuntimeError raised (not ValueError) when submit_evaluation is never called — mirrors missing submission as a hard failure"
metrics:
  duration_seconds: 186
  completed_date: "2026-03-29"
requirements: [REQ-06, REQ-07, REQ-08, REQ-11]
---

# Phase 01 Plan 02: Switch Evaluator to Tool-Based Submission Summary

**One-liner:** Evaluator switched from unreliable StructuredOutput (`driver.generate(schema=)`) to `driver.execute_agentic()` with `submit_evaluation` tool, enforcing first-call-wins and RuntimeError on missing submission.

## What Was Built

The `Evaluator.evaluate()` method now uses `driver.execute_agentic()` instead of `driver.generate()`. The LLM is restricted to a single custom tool (`submit_evaluation`) via `allowed_tools=["submit_evaluation"]`, which maps directly to the `EvaluationOutput` schema. The tool call's `tool_input` dict is validated via `EvaluationOutput.model_validate()`.

Key behaviors implemented:
- **execute_agentic pattern**: streams `AgenticMessage` objects; captures the first `TOOL_CALL` with `tool_name == "submit_evaluation"`
- **First-call-wins**: if `submit_evaluation` fires more than once (e.g., from model retry), only the first result is used; a `logger.warning` is emitted
- **Hard failure on missing submission**: `RuntimeError("Evaluator did not call submit_evaluation")` raised if the stream ends without any tool call
- **Prompt updated**: final instruction paragraph now directs the LLM to call `submit_evaluation` with the exact field schema, satisfying REQ-11
- **Partition logic unchanged**: `items_to_implement`, `items_rejected`, `items_deferred`, `items_needing_clarification` bucketing is identical — only the data source changed from `response` to `result_data`

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Switch evaluator to execute_agentic with submit_evaluation tool | f86513d2 | amelia/agents/evaluator.py, tests/unit/agents/test_evaluator.py |

## Tests Added

3 new test cases added to `tests/unit/agents/test_evaluator.py`:
- `test_evaluate_submit_evaluation_first_call_wins` — two tool call messages; asserts result uses first call's data
- `test_evaluate_no_submit_evaluation_raises` — stream with only RESULT message; asserts RuntimeError
- `test_evaluate_uses_execute_agentic_with_allowed_tools` — asserts `execute_agentic` called with `allowed_tools=["submit_evaluation"]` and `generate` not called

All 7 existing evaluate() tests updated to use `execute_agentic` / `AsyncIteratorMock` pattern instead of `mock_driver.generate`.

Total: **18 tests passing**.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED
