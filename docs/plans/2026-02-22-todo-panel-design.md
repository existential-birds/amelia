# Todo Panel Widget Design

**Issue:** #469 — `in_progress` status wraps in todo log output
**Date:** 2026-02-22
**Branch:** `fix/469-todo-display-elegance`

## Problem

The current `log_todos` renders a plain Rich Table that feels like debug output. The `Status` column is fixed at `width=12`, causing `in_progress` (13 chars with icon) to wrap.

## Solution

Replace the Table with a Rich Panel containing styled Text lines, with a task counter in the panel title.

### Visual spec

```
╭─ Tasks  3/5 ─────────────────────────╮
│  ✓ Add Workout section with Stepper   │
│  ✓ Pass exerciseRestSeconds from A... │
│  ✓ Implement timer pause logic        │
│  ▸ Final verification and commit      │
│  ○ Update documentation               │
╰───────────────────────────────────────╯
```

### Status styling

| Status        | Icon | Icon color  | Text style |
|---------------|------|-------------|------------|
| `completed`   | `✓`  | green       | dim        |
| `in_progress` | `▸`  | yellow bold | normal     |
| `pending`     | `○`  | dim         | dim        |

### Implementation

- `rich.panel.Panel` with `box=rich.box.ROUNDED`
- Title: `"Tasks  {completed}/{total}"` styled bold
- Each todo is a `rich.text.Text` line with per-status styling
- No fixed width — auto-sizes to terminal
- TTY guard and stderr output unchanged

### Files changed

- `amelia/logging.py` — rewrite `log_todos` body
- `tests/unit/test_logging.py` — update tests for Panel
