# Loguru KeyError Fix - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix silent log message loss caused by unescaped braces in `_plain_log_format`, and improve structured logging for complex data types.

**Architecture:** Two-part fix: (1) add missing brace escaping in the plain log formatter, (2) move complex data out of loguru extra fields -- flatten nested dicts to scalars, pre-format lists to strings, and add a `log_todos()` rich display function following the existing `log_claude_result()` pattern.

**Tech Stack:** Python, loguru, rich (already in deps)

---

### Task 1: Fix brace escaping in `_plain_log_format` (tests)

**Files:**
- Create: `tests/unit/test_logging.py`

**Step 1: Write failing tests for brace escaping**

```python
"""Tests for amelia/logging.py format functions."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from amelia.logging import _plain_log_format


def _make_record(**extra: Any) -> MagicMock:
    """Create a minimal loguru Record-like dict for testing format functions."""
    record = MagicMock()
    record.__getitem__ = lambda self, key: {
        "extra": extra,
        "level": MagicMock(name="INFO"),
        "exception": None,
    }[key]
    return record


class TestPlainLogFormatBraceEscaping:
    """_plain_log_format must escape braces in extra field repr output."""

    def test_nested_dict_braces_are_escaped(self) -> None:
        """Nested dict in extra should not cause KeyError in format_map."""
        record = _make_record(details={"key": "value"})
        fmt = _plain_log_format(record)
        # Braces from repr should be doubled for loguru format_map safety
        assert "{{" in fmt
        assert "}}" in fmt

    def test_list_of_dicts_braces_are_escaped(self) -> None:
        """List of dicts in extra should not cause KeyError in format_map."""
        record = _make_record(todos=[{"content": "Fix X", "status": "pending"}])
        fmt = _plain_log_format(record)
        assert "{{" in fmt

    def test_scalar_extra_unchanged(self) -> None:
        """Scalar extra fields without braces should pass through normally."""
        record = _make_record(count=42, name="test")
        fmt = _plain_log_format(record)
        assert "count=42" in fmt
        assert "name='test'" in fmt

    def test_empty_extra_no_separator(self) -> None:
        """No extra separator when extra dict is empty."""
        record = _make_record()
        fmt = _plain_log_format(record)
        assert "│" in fmt  # timestamp/level separators exist
        # Should not have a trailing separator for empty extra
        assert fmt.count("│") == 2  # time │ level │ name:message
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_logging.py -v`
Expected: `test_nested_dict_braces_are_escaped` and `test_list_of_dicts_braces_are_escaped` FAIL (no `{{` in output)

**Step 3: Commit failing tests**

```bash
git add tests/unit/test_logging.py
git commit -m "test: add failing tests for _plain_log_format brace escaping (#463)"
```

---

### Task 2: Fix brace escaping in `_plain_log_format` (implementation)

**Files:**
- Modify: `amelia/logging.py:112-113` (inside `_plain_log_format`)

**Step 1: Add brace escaping**

In `_plain_log_format`, after `extra_str = " ".join(...)` (line 113), add:

```python
        extra_str = extra_str.replace("{", "{{").replace("}", "}}")
```

This matches the escaping already present in `_log_format` at line 84.

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_logging.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add amelia/logging.py
git commit -m "fix(logging): escape braces in _plain_log_format to prevent KeyError (#463)"
```

---

### Task 3: Add `log_todos()` display function (tests)

**Files:**
- Modify: `tests/unit/test_logging.py`

**Step 1: Write failing tests for `log_todos`**

Append to `tests/unit/test_logging.py`:

```python
from unittest.mock import patch
from amelia.logging import log_todos


class TestLogTodos:
    """log_todos renders rich table on TTY, no-op on piped stderr."""

    def test_no_output_when_not_tty(self, capsys: pytest.CaptureFixture[str]) -> None:
        """log_todos should be a no-op when stderr is not a TTY."""
        with patch("sys.stderr") as mock_stderr:
            mock_stderr.isatty.return_value = False
            log_todos([{"content": "Fix bug", "status": "completed"}])
            mock_stderr.write.assert_not_called()

    def test_renders_on_tty(self) -> None:
        """log_todos should write to stderr when it is a TTY."""
        with patch("sys.stderr") as mock_stderr:
            mock_stderr.isatty.return_value = True
            # Rich Console needs a real file-like, so patch at Console level
            with patch("amelia.logging.Console") as mock_console_cls:
                mock_console = MagicMock()
                mock_console_cls.return_value = mock_console
                log_todos([{"content": "Fix bug", "status": "completed"}])
                mock_console.print.assert_called_once()

    def test_handles_empty_list(self) -> None:
        """log_todos should handle empty todo list gracefully."""
        with patch("sys.stderr") as mock_stderr:
            mock_stderr.isatty.return_value = True
            with patch("amelia.logging.Console") as mock_console_cls:
                mock_console = MagicMock()
                mock_console_cls.return_value = mock_console
                log_todos([])
                mock_console.print.assert_called_once()  # Still prints table (empty)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_logging.py::TestLogTodos -v`
Expected: FAIL with `ImportError: cannot import name 'log_todos'`

**Step 3: Commit failing tests**

```bash
git add tests/unit/test_logging.py
git commit -m "test: add failing tests for log_todos display function (#463)"
```

---

### Task 4: Implement `log_todos()` display function

**Files:**
- Modify: `amelia/logging.py` (add function after `log_claude_result`)

**Step 1: Add `log_todos` function**

Insert after `log_claude_result` in `amelia/logging.py`:

```python
def log_todos(todos: list[dict[str, object]]) -> None:
    """Display agent todos with rich Table formatting (TTY only).

    Renders a formatted table of todo items to stderr when running in a
    terminal. No-op when stderr is piped (e.g., under `amelia dev`).

    Args:
        todos: List of todo dicts with 'content' and 'status' keys.
    """
    if not sys.stderr.isatty():
        return

    from rich.console import Console
    from rich.table import Table

    console = Console(stderr=True)
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Status", style="dim", width=12)
    table.add_column("Task")

    status_styles = {
        "completed": ("\u2713", "green"),
        "in_progress": ("\u25cc", "yellow"),
        "pending": ("\u25cb", "dim"),
    }
    for todo in todos:
        status = str(todo.get("status", ""))
        content = str(todo.get("content", ""))
        icon, style = status_styles.get(status, ("?", ""))
        table.add_row(f"[{style}]{icon} {status}[/{style}]", content)

    console.print(table)
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_logging.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add amelia/logging.py
git commit -m "feat(logging): add log_todos() rich display function (#463)"
```

---

### Task 5: Flatten nested dicts at call sites in `nodes.py`

**Files:**
- Modify: `amelia/pipelines/nodes.py:150-158` (developer log)
- Modify: `amelia/pipelines/nodes.py:242-252` (reviewer log)

**Step 1: Flatten developer action log (line 150-158)**

Replace:
```python
    logger.info(
        "Agent action completed",
        agent="developer",
        action="agentic_execution",
        details={
            "tool_calls_count": len(final_state.tool_calls),
            "agentic_status": final_state.agentic_status,
        },
    )
```

With:
```python
    logger.info(
        "Agent action completed",
        agent="developer",
        action="agentic_execution",
        tool_calls_count=len(final_state.tool_calls),
        agentic_status=str(final_state.agentic_status),
    )
```

**Step 2: Flatten reviewer action log (line 242-252)**

Replace:
```python
    logger.info(
        "Agent action completed",
        agent=agent_name,
        action="review_completed",
        details={
            "severity": review_result.severity,
            "approved": review_result.approved,
            "issue_count": len(review_result.comments),
            "review_iteration": next_iteration,
        },
    )
```

With:
```python
    logger.info(
        "Agent action completed",
        agent=agent_name,
        action="review_completed",
        severity=str(review_result.severity),
        approved=review_result.approved,
        issue_count=len(review_result.comments),
        review_iteration=next_iteration,
    )
```

**Step 3: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: All PASS

**Step 4: Commit**

```bash
git add amelia/pipelines/nodes.py
git commit -m "fix(logging): flatten nested details dicts to scalar kwargs in nodes (#463)"
```

---

### Task 6: Fix call sites in `deepagents.py`

**Files:**
- Modify: `amelia/drivers/api/deepagents.py:670-673` (write_todos log)
- Modify: `amelia/drivers/api/deepagents.py:790-797` (summary log)
- Modify: `amelia/drivers/api/deepagents.py:800-806` (incomplete tasks warning)
- Modify: `amelia/drivers/api/deepagents.py:809-814` (no write_file warning)

**Step 1: Add import for `log_todos`**

At the top of `deepagents.py`, add to the existing import from `amelia.logging`:

```python
from amelia.logging import log_todos
```

If no existing import from `amelia.logging` exists, add this import near other amelia imports.

**Step 2: Fix write_todos log (line 670-673)**

Replace:
```python
                                logger.info(
                                    "Agent called write_todos",
                                    todos=tool_args.get("todos", []),
                                )
```

With:
```python
                                todos = tool_args.get("todos", [])
                                logger.info(
                                    "Agent called write_todos",
                                    todo_count=len(todos),
                                )
                                log_todos(todos)
```

Note: `todos` variable is already used later (line 784), so assign it here. Check that `tool_args.get("todos", [])` is not already assigned to a different variable nearby.

**Step 3: Pre-format list fields in summary log (line 790-797)**

Replace:
```python
                all_tool_names=all_tool_names,
```

With:
```python
                tool_names=", ".join(all_tool_names[-10:]),
```

**Step 4: Pre-format list fields in incomplete tasks warning (line 800-806)**

Replace:
```python
                    tool_sequence=all_tool_names[-10:] if len(all_tool_names) > 10 else all_tool_names,
```

With:
```python
                    tool_sequence=", ".join(all_tool_names[-10:]),
```

**Step 5: Pre-format list fields in no-write_file warning (line 809-814)**

Replace:
```python
                    tool_sequence=all_tool_names,
```

With:
```python
                    tool_sequence=", ".join(all_tool_names),
```

**Step 6: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: All PASS

**Step 7: Commit**

```bash
git add amelia/drivers/api/deepagents.py
git commit -m "fix(logging): use scalar fields and log_todos() in deepagents (#463)"
```

---

### Task 7: Run linting and type checks

**Step 1: Run ruff**

Run: `uv run ruff check amelia tests`
Expected: No errors. Fix any issues if found.

**Step 2: Run mypy**

Run: `uv run mypy amelia`
Expected: No new errors. Fix any type issues if found.

**Step 3: Run full test suite one final time**

Run: `uv run pytest tests/ -v`
Expected: All PASS

**Step 4: Commit any lint/type fixes if needed**

```bash
git add -A
git commit -m "chore: fix lint and type issues from logging fix (#463)"
```
