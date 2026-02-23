# Todo Panel Widget — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the plain Rich Table in `log_todos` with a polished Rich Panel widget that fixes the `in_progress` wrapping bug (#469) and feels like an intentional terminal UI component.

**Architecture:** Rewrite `log_todos` to build a `rich.text.Text` block of styled lines and wrap it in a `rich.panel.Panel` with a "Tasks N/M" title. No new files, no API changes — same function signature, same TTY guard.

**Tech Stack:** Rich (Panel, Text, box), pytest, unittest.mock

**Design doc:** `docs/plans/2026-02-22-todo-panel-design.md`

---

### Task 1: Update tests for Panel-based rendering

**Files:**
- Modify: `tests/unit/test_logging.py:61-95` (TestLogTodos class)

**Step 1: Rewrite the test class**

Replace the three existing tests. The key change: `console.print` should receive a `Panel` (not a `Table`), and we add a new test verifying the panel title contains the counter.

```python
class TestLogTodos:
    """log_todos renders a Rich Panel on TTY, no-op on piped stderr."""

    def test_no_output_when_not_tty(self) -> None:
        """log_todos should be a no-op when stderr is not a TTY."""
        from amelia.logging import log_todos

        with patch("sys.stderr") as mock_stderr:
            mock_stderr.isatty.return_value = False
            log_todos([{"content": "Fix bug", "status": "completed"}])
            mock_stderr.write.assert_not_called()

    def test_renders_panel_on_tty(self) -> None:
        """log_todos should print a Rich Panel to stderr when it is a TTY."""
        from rich.panel import Panel

        from amelia.logging import log_todos

        with patch("sys.stderr") as mock_stderr:
            mock_stderr.isatty.return_value = True
            with patch("amelia.logging.Console") as mock_console_cls:
                mock_console = MagicMock()
                mock_console_cls.return_value = mock_console
                log_todos([{"content": "Fix bug", "status": "completed"}])
                mock_console.print.assert_called_once()
                printed_arg = mock_console.print.call_args[0][0]
                assert isinstance(printed_arg, Panel)

    def test_panel_title_contains_counter(self) -> None:
        """Panel title should show completed/total count."""
        from rich.panel import Panel

        from amelia.logging import log_todos

        with patch("sys.stderr") as mock_stderr:
            mock_stderr.isatty.return_value = True
            with patch("amelia.logging.Console") as mock_console_cls:
                mock_console = MagicMock()
                mock_console_cls.return_value = mock_console
                log_todos([
                    {"content": "Done task", "status": "completed"},
                    {"content": "Active task", "status": "in_progress"},
                    {"content": "Todo task", "status": "pending"},
                ])
                printed_arg = mock_console.print.call_args[0][0]
                assert isinstance(printed_arg, Panel)
                title_text = printed_arg.title.plain  # type: ignore[union-attr]
                assert "1/3" in title_text

    def test_handles_empty_list(self) -> None:
        """log_todos should handle empty todo list gracefully."""
        from rich.panel import Panel

        from amelia.logging import log_todos

        with patch("sys.stderr") as mock_stderr:
            mock_stderr.isatty.return_value = True
            with patch("amelia.logging.Console") as mock_console_cls:
                mock_console = MagicMock()
                mock_console_cls.return_value = mock_console
                log_todos([])
                mock_console.print.assert_called_once()
                printed_arg = mock_console.print.call_args[0][0]
                assert isinstance(printed_arg, Panel)
                title_text = printed_arg.title.plain  # type: ignore[union-attr]
                assert "0/0" in title_text
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_logging.py::TestLogTodos -v`
Expected: FAIL — `printed_arg` is a `Table`, not a `Panel`

**Step 3: Commit failing tests**

```bash
git add tests/unit/test_logging.py
git commit -m "test: update log_todos tests for Panel-based rendering (#469)"
```

---

### Task 2: Rewrite log_todos to use Rich Panel

**Files:**
- Modify: `amelia/logging.py:331-361` (log_todos function body)

**Step 1: Replace the function body**

```python
def log_todos(todos: list[dict[str, object]]) -> None:
    """Display agent todos as a styled Rich Panel (TTY only).

    Renders a bordered panel with a task counter title and per-status
    styling to stderr when running in a terminal.

    Args:
        todos: List of todo dicts with 'content' and 'status' keys.
    """
    if not sys.stderr.isatty():
        return

    from rich.panel import Panel  # noqa: PLC0415
    from rich.text import Text  # noqa: PLC0415

    console = Console(stderr=True)

    status_styles: dict[str, tuple[str, str, str]] = {
        "completed": ("\u2713", "green", "dim"),
        "in_progress": ("\u25b8", "yellow bold", ""),
        "pending": ("\u25cb", "dim", "dim"),
    }

    completed = sum(1 for t in todos if t.get("status") == "completed")
    total = len(todos)

    lines = Text()
    for i, todo in enumerate(todos):
        status = str(todo.get("status", ""))
        content = str(todo.get("content", ""))
        icon, icon_style, text_style = status_styles.get(status, ("?", "", ""))
        lines.append(f" {icon} ", style=icon_style)
        lines.append(content, style=text_style)
        if i < len(todos) - 1:
            lines.append("\n")

    title = Text.assemble(("Tasks", "bold"), f"  {completed}/{total}")
    panel = Panel(lines, title=title, title_align="left", box=ROUNDED, padding=(0, 1))
    console.print(panel)
```

Note: `ROUNDED` needs to be imported. Add it to the existing `rich.box` import or add a new one near the top of the file. Check the current imports first.

**Step 2: Add the ROUNDED import**

Near the top of `amelia/logging.py`, find the rich imports and add:

```python
from rich.box import ROUNDED
```

If there's no existing `rich.box` import, add it alongside the other rich imports.

**Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_logging.py::TestLogTodos -v`
Expected: All 4 tests PASS

**Step 4: Run linter and type checker**

Run: `uv run ruff check amelia/logging.py tests/unit/test_logging.py`
Run: `uv run mypy amelia/logging.py`

Fix any issues.

**Step 5: Commit**

```bash
git add amelia/logging.py tests/unit/test_logging.py
git commit -m "fix(logging): replace todo Table with styled Panel widget (#469)"
```

---

### Task 3: Manual verification

**Step 1: Run the full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests pass, no regressions

**Step 2: Visual check (optional)**

Create a quick script to preview the output:

```python
# /tmp/preview_todos.py
import sys; sys.stderr = sys.stdout  # redirect so we see it
from amelia.logging import log_todos
log_todos([
    {"content": "Add Workout section with Stepper", "status": "completed"},
    {"content": "Pass exerciseRestSeconds from API", "status": "completed"},
    {"content": "Implement timer pause logic", "status": "completed"},
    {"content": "Final verification and commit", "status": "in_progress"},
    {"content": "Update documentation", "status": "pending"},
])
```

Run: `uv run python /tmp/preview_todos.py`
Expected: The styled panel with rounded borders, counter title, and proper dim/bold styling.

**Step 3: Commit if any fixes were needed, then done**
