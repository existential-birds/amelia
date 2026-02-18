# Fix: Loguru KeyError on nested dicts in structured logging

**Issue:** #463
**Date:** 2026-02-17
**Status:** Approved

## Problem

`_plain_log_format` in `amelia/logging.py` doesn't escape `{}`  braces in `repr()` output of extra fields. When structured logging includes nested dicts, lists, or enums, loguru's `format_map` interprets dict keys as format placeholders, raising `KeyError`. Affected log messages are silently dropped.

Only affects piped stderr (i.e., `amelia dev` subprocess mode). The TTY handler `_log_format` already escapes braces correctly.

## Approach

Approach A from brainstorming: fix escaping + parallel display functions following the existing `log_claude_result()` pattern.

## Changes

### 1. Fix brace escaping in `_plain_log_format`

**File:** `amelia/logging.py:113`

Add the missing brace escaping after building `extra_str`, matching `_log_format`:

```python
extra_str = extra_str.replace("{", "{{").replace("}", "}}")
```

### 2. Add `log_todos()` rich display function

**File:** `amelia/logging.py`

New function following the `log_claude_result()` pattern:

- Takes `todos: list[dict[str, object]]`
- TTY-only (no-op when `sys.stderr.isatty()` is False)
- Uses `rich.Table` with columns: Status (icon + label), Task (content)
- Status icons: completed (green checkmark), in_progress (yellow circle), pending (dim circle)

### 3. Flatten nested dicts at call sites

**File:** `amelia/pipelines/nodes.py:150-158`

Replace `details={...}` with flattened scalar kwargs:
```python
logger.info("Agent action completed", agent="developer", action="agentic_execution",
            tool_calls_count=len(final_state.tool_calls),
            agentic_status=str(final_state.agentic_status))
```

**File:** `amelia/pipelines/nodes.py:242-252`

Same pattern for reviewer:
```python
logger.info("Agent action completed", agent=agent_name, action="review_completed",
            severity=str(review_result.severity), approved=review_result.approved,
            issue_count=len(review_result.comments), review_iteration=next_iteration)
```

### 4. Replace nested list extra fields with scalar + rich display

**File:** `amelia/drivers/api/deepagents.py:670-673`

Replace nested todos list with scalar count + rich display:
```python
logger.info("Agent called write_todos", todo_count=len(todos))
log_todos(todos)
```

### 5. Pre-format list fields to strings

**File:** `amelia/drivers/api/deepagents.py:794, 804, 812`

Convert list fields to comma-separated strings before passing to loguru:
```python
tool_names=", ".join(all_tool_names[-10:])
```

## Design principle

Loguru extra fields should only contain scalars (str, int, bool, float). Complex objects get either flattened into scalar kwargs or pre-formatted into strings. Rich display for complex data uses separate display functions that write directly to stderr (TTY only).

## Behavior by mode

| Command | Rich table? | Loguru structured log? |
|---------|------------|----------------------|
| `amelia server` | Yes (TTY) | Yes, via `_log_format` (already escapes) |
| `amelia dev` | No (piped) | Yes, via `_plain_log_format` (after fix) |
