# Tool Call UI Improvements Design

## Overview

Improve the terminal UI for tool calls in `review_fix_loop.py` by:
1. Adding dark background panels around tool calls (including emoji and tool name)
2. Formatting Bash tool calls with description-first display
3. Hiding command details in quiet mode

## Current Behavior

- **Skill calls**: Show `▶ ✨ Skill` header outside panel, skill name as pill badge
- **Bash calls**: Show `▶ 🔧 Bash` header outside panel, args as raw `key=value` string in panel

## New Behavior

### Unified Panel Structure

Both Skill and Bash tool calls use a consistent panel with emoji and tool name inside:

```
┌──────────────────────────────────────┐
│ ▶ ✨ Skill                           │
│                                      │
│ ▌ beagle:review-python ▐             │
└──────────────────────────────────────┘
```

```
┌──────────────────────────────────────┐
│ ▶ 🔧 Bash                            │
│                                      │
│ Get list of changed Python files     │
│ $ git diff --name-only ...           │  ← dimmed, hidden in quiet mode
└──────────────────────────────────────┘
```

Panel styling:
- Dark background (`#1e1e2e`)
- Purple border
- Tool header line with emoji inside the panel

### Bash Display Format

- Description text in cyan (normal weight)
- Command with `$` prefix in dimmed style
- Command hidden when `quiet_mode=True`

### Signature Change

```python
def print_tool_call(
    console: Console,
    name: str,
    args: dict,  # changed from str
    quiet_mode: bool = False,  # new parameter
) -> None:
```

## Implementation

### Changes to `review_ui.py`

1. **`print_tool_call` signature**: Change `args: str` → `args: dict`, add `quiet_mode: bool = False`

2. **Skill handling**: Build a panel containing:
   - Header line: `▶ ✨ Skill`
   - Skill name as pink pill badge

3. **Bash handling**: Build a panel containing:
   - Header line: `▶ 🔧 Bash`
   - Description in cyan (from `args.get("description")`)
   - Command with `$` prefix, dimmed (from `args.get("command")`), only if `not quiet_mode`

4. **Other tools**: Header line + formatted key=value pairs (existing `_colorize_tool_args` logic, adapted for dict input)

### Changes to `review_fix_loop.py`

1. **Line 246**: Pass `block.input or {}` and `_quiet_mode` instead of stringified args

```python
# Before
args_str = ", ".join(f"{k}={v!r}" for k, v in block.input.items()) if block.input else ""
print_tool_call(console, block.name, args_str)

# After
print_tool_call(console, block.name, block.input or {}, _quiet_mode)
```
