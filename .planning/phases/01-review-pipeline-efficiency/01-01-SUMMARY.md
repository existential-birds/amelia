---
phase: 01-review-pipeline-efficiency
plan: "01"
subsystem: review-pipeline
tags: [reviewer, driver, diff, performance, tdd]
dependency_graph:
  requires: []
  provides:
    - custom-tool-name-passthrough
    - diff-pre-computation
    - reviewer-diff-path-integration
  affects:
    - amelia/drivers/cli/claude.py
    - amelia/pipelines/nodes.py
    - amelia/agents/reviewer.py
    - amelia/agents/prompts/defaults.py
tech_stack:
  added: []
  patterns:
    - passthrough-for-unknown-tool-names
    - pre-computed-diff-file-shared-across-passes
    - try-finally-cleanup-for-temp-files
key_files:
  created:
    - tests/unit/drivers/test_claude_driver_build_options.py
  modified:
    - amelia/drivers/cli/claude.py
    - amelia/pipelines/nodes.py
    - amelia/agents/reviewer.py
    - amelia/agents/prompts/defaults.py
    - tests/unit/pipelines/test_reviewer_node_config.py
    - tests/unit/agents/test_reviewer.py
    - tests/unit/agents/test_reviewer_prompts.py
decisions:
  - "Custom tool names in _build_options pass through as-is via CANONICAL_TO_CLI.get(name, name)"
  - "Diff written once to /tmp/amelia-review-{workflow_id}/diff.patch before the review loop"
  - "try/finally cleanup ensures diff directory is removed even when agentic_review raises"
  - "AGENTIC_REVIEW_PROMPT now uses {diff_path} placeholder instead of instructing git diff"
  - "diff_path param is optional (str | None = None) for backward compatibility"
metrics:
  duration_seconds: 323
  completed_date: "2026-03-29"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 7
  files_created: 1
requirements_satisfied:
  - REQ-01
  - REQ-02
  - REQ-03
  - REQ-04
  - REQ-05
  - REQ-09
  - REQ-10
---

# Phase 01 Plan 01: Fix driver tool names and diff pre-computation Summary

**One-liner:** Custom tool name passthrough in _build_options (CANONICAL_TO_CLI.get(name, name)) plus pre-computed diff file written once to /tmp/amelia-review-{workflow_id}/diff.patch shared across all review passes.

## What Was Built

### Task 1: Fix _build_options to pass custom tool names through

Changed the tool name mapping loop in `amelia/drivers/cli/claude.py` from raising `ValueError` for unknown canonical tool names to passing them through as-is. The change is `CANONICAL_TO_CLI.get(name)` with conditional raise replaced by `CANONICAL_TO_CLI.get(name, name)`.

This unblocks Plans 02 and 03 which need custom tool names like `submit_evaluation` in `allowed_tools`.

**Key change:**
- `/Users/ka/github/existential-birds/amelia/amelia/drivers/cli/claude.py` line ~332: `CANONICAL_TO_CLI.get(name, name)`
- Created `tests/unit/drivers/test_claude_driver_build_options.py` with 3 test cases

### Task 2: Diff pre-computation in call_reviewer_node and reviewer prompt update

**nodes.py changes:**
- Added `import shutil` and `from pathlib import Path`
- Extended `asyncio.gather` to fetch `git diff --stat` alongside existing `--name-only` and raw diff
- After `changed_files` is built, writes `diff_dir = Path(f"/tmp/amelia-review-{nc.workflow_id}")` and `diff_path = diff_dir / "diff.patch"` with content: stat header + changed file list + raw diff
- Wrapped the review loop in `try/finally` with `shutil.rmtree(diff_dir, ignore_errors=True)` in `finally`
- Passes `diff_path=str(diff_path)` to every `reviewer.agentic_review()` call

**reviewer.py changes:**
- `agentic_review()` signature now accepts `diff_path: str | None = None`
- User prompt branches: when `diff_path` is provided, includes `"The diff is pre-fetched at: {diff_path}\nRead it from that file rather than running git diff."`
- `system_prompt.format()` now includes `diff_path=diff_path or "(not provided — use git diff)"`
- `AGENTIC_REVIEW_PROMPT` Process section replaced: removed steps 1-2 (`git diff --name-only` / `git diff`) with step 1 "Read the Diff: Read the pre-fetched diff from `{diff_path}`"

**defaults.py changes:**
- `PROMPT_DEFAULTS["reviewer.agentic"]` updated to match `AGENTIC_REVIEW_PROMPT` — same `{diff_path}` instruction replacing git diff steps

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test assertions in pre-existing test_reviewer_prompts.py**
- **Found during:** Task 2 GREEN phase
- **Issue:** `test_falls_back_to_class_default_for_agentic` asserted `"git diff" in reviewer.agentic_prompt` and `test_agentic_prompt_property` asserted `"base_commit" in reviewer_default.agentic_prompt` — both fail after AGENTIC_REVIEW_PROMPT was updated to remove git diff instructions
- **Fix:** Updated assertions to check for `"diff_path"` instead, which correctly reflects the new prompt structure
- **Files modified:** `tests/unit/agents/test_reviewer_prompts.py`
- **Commit:** ad559c9d

**2. [Rule 1 - Bug] Fixed test assertions for workflow_id vs thread_id in node tests**
- **Found during:** Task 2 GREEN phase
- **Issue:** Test `test_call_reviewer_node_writes_diff_file` asserted `str(mock_state.workflow_id) in diff_path_str`, but `nc.workflow_id` comes from `thread_id` in config, not from the state's workflow_id
- **Fix:** Tests now use `thread_id = str(uuid4())` as the config thread_id and assert `thread_id in diff_path_str`
- **Files modified:** `tests/unit/pipelines/test_reviewer_node_config.py`
- **Commit:** ad559c9d

## Known Stubs

None — all data is fully wired. The `diff_path=None` default provides backward compatibility but does not stub any UI rendering or data flow.

## Verification

- `uv run pytest tests/unit/drivers/ tests/unit/pipelines/test_reviewer_node_config.py tests/unit/agents/test_reviewer.py tests/unit/agents/test_reviewer_prompts.py -x -v` — 173 passed
- `uv run ruff check amelia/drivers/cli/claude.py amelia/pipelines/nodes.py amelia/agents/reviewer.py amelia/agents/prompts/defaults.py` — All checks passed
- `uv run mypy amelia/drivers/cli/claude.py amelia/pipelines/nodes.py amelia/agents/reviewer.py` — Success: no issues found in 3 source files

## Self-Check: PASSED
