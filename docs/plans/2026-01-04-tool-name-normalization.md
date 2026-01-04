# Tool Name Normalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Normalize CLI driver tool names ("Write", "Read", "Bash") to standard snake_case names ("write_file", "read_file", "run_shell_command") so the orchestrator works consistently with both CLI and API drivers.

**Architecture:** Add a normalization step in the CLI driver's `execute_agentic()` method that translates Claude's native tool names to the standard `ToolName` enum values defined in `constants.py`. This keeps the translation at the driver boundary, maintaining clean abstraction.

**Tech Stack:** Python, Pydantic, existing `ToolName` enum from `amelia/core/constants.py`

---

### Task 1: Add Tool Name Mapping to CLI Driver

**Files:**
- Modify: `amelia/drivers/cli/claude.py`
- Test: `tests/unit/drivers/test_claude_driver.py`

**Step 1: Write the failing test**

Add test to `tests/unit/drivers/test_claude_driver.py`:

```python
@pytest.mark.asyncio
async def test_execute_agentic_normalizes_tool_names(
    mock_claude_agent: MagicMock,
) -> None:
    """Tool names should be normalized to standard snake_case format."""
    from amelia.core.constants import ToolName

    # Mock a Write tool call (Claude's native name)
    mock_tool_block = MagicMock(spec=ToolUseBlock)
    mock_tool_block.name = "Write"  # Claude's native name
    mock_tool_block.input = {"file_path": "/test.md", "content": "test"}
    mock_tool_block.id = "tool_123"

    mock_message = MagicMock(spec=AssistantMessage)
    mock_message.content = [mock_tool_block]

    mock_result = MagicMock(spec=ResultMessage)
    mock_result.result = "Done"
    mock_result.session_id = "session_123"
    mock_result.is_error = False

    async def mock_stream():
        yield mock_message
        yield mock_result

    mock_claude_agent.return_value.__aiter__ = mock_stream

    driver = ClaudeCliDriver(model="claude-sonnet-4-20250514")
    messages = [msg async for msg in driver.execute_agentic("test", "/tmp")]

    # Find the tool call message
    tool_calls = [m for m in messages if m.type == AgenticMessageType.TOOL_CALL]
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == ToolName.WRITE_FILE  # Normalized name
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/drivers/test_claude_driver.py::test_execute_agentic_normalizes_tool_names -v`
Expected: FAIL with `AssertionError: assert 'Write' == 'write_file'`

**Step 3: Add tool name mapping constant**

In `amelia/drivers/cli/claude.py`, add after imports:

```python
from amelia.core.constants import ToolName

# Mapping from Claude CLI tool names to standard ToolName values
CLAUDE_TOOL_NAME_MAP: dict[str, str] = {
    "Write": ToolName.WRITE_FILE,
    "Read": ToolName.READ_FILE,
    "Bash": ToolName.RUN_SHELL_COMMAND,
}
```

**Step 4: Normalize tool names in execute_agentic**

In `execute_agentic()`, update the `ToolUseBlock` handling (around line 411-416):

```python
elif isinstance(block, ToolUseBlock):
    # Track tool calls in history
    self.tool_call_history.append(block)
    last_tool_name = block.name
    # Normalize tool name to standard format
    normalized_name = CLAUDE_TOOL_NAME_MAP.get(block.name, block.name)
    yield AgenticMessage(
        type=AgenticMessageType.TOOL_CALL,
        tool_name=normalized_name,
        tool_input=block.input,
        tool_call_id=block.id,
    )
```

**Step 5: Also normalize tool result messages**

Update the `ToolResultBlock` handling (around line 417-424):

```python
elif isinstance(block, ToolResultBlock):
    content = block.content if isinstance(block.content, str) else str(block.content)
    # Normalize tool name to standard format
    normalized_name = CLAUDE_TOOL_NAME_MAP.get(last_tool_name, last_tool_name) if last_tool_name else None
    yield AgenticMessage(
        type=AgenticMessageType.TOOL_RESULT,
        tool_name=normalized_name,
        tool_output=content,
        is_error=block.is_error or False,
    )
```

**Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/drivers/test_claude_driver.py::test_execute_agentic_normalizes_tool_names -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/drivers/cli/claude.py tests/unit/drivers/test_claude_driver.py
git commit -m "feat(drivers): normalize CLI tool names to standard format

Adds CLAUDE_TOOL_NAME_MAP to translate Claude's native tool names
(Write, Read, Bash) to the standard ToolName enum values (write_file,
read_file, run_shell_command).

Part of #215"
```

---

### Task 2: Update Orchestrator to Use Standard Tool Names

**Files:**
- Modify: `amelia/core/orchestrator.py`
- Test: `tests/unit/core/test_architect_node.py`

**Step 1: Write the failing test**

Add test to `tests/unit/core/test_architect_node.py`:

```python
@pytest.mark.asyncio
async def test_call_architect_node_extracts_goal_from_write_file_tool(
    mock_profile: Profile,
    mock_issue: Issue,
) -> None:
    """Goal should be extracted when tool_name is 'write_file' (API driver format)."""
    from amelia.core.constants import ToolName

    plan_content = """# Implementation Plan

**Goal:** Implement user authentication feature

## Task 1: Setup
..."""

    state = ExecutionState(
        issue=mock_issue,
        raw_architect_output="Plan generated",
        tool_calls=[
            ToolCall(
                tool_name=ToolName.WRITE_FILE,  # API/normalized format
                tool_input={"file_path": "/tmp/plan.md", "content": plan_content},
            )
        ],
    )

    result = await call_architect_node(state, mock_profile)

    assert result["goal"] == "Implement user authentication feature"
    assert "**Goal:**" in result["plan_markdown"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_architect_node.py::test_call_architect_node_extracts_goal_from_write_file_tool -v`
Expected: FAIL - goal is None because orchestrator looks for "Write" not "write_file"

**Step 3: Update orchestrator to use ToolName constant**

In `amelia/core/orchestrator.py`, add import:

```python
from amelia.core.constants import ToolName
```

Update line 207 to use the standard constant:

```python
if tool_call.tool_name == ToolName.WRITE_FILE and isinstance(tool_call.tool_input, dict):
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_architect_node.py::test_call_architect_node_extracts_goal_from_write_file_tool -v`
Expected: PASS

**Step 5: Run existing tests to ensure no regression**

Run: `uv run pytest tests/unit/core/test_architect_node.py -v`
Expected: All tests PASS (existing tests should still work since CLI driver now normalizes)

**Step 6: Commit**

```bash
git add amelia/core/orchestrator.py tests/unit/core/test_architect_node.py
git commit -m "fix(orchestrator): use ToolName constant for plan extraction

Updates call_architect_node to check for ToolName.WRITE_FILE instead
of hardcoded 'Write'. Combined with CLI driver normalization, this
ensures plan extraction works for both CLI and API drivers.

Fixes #215"
```

---

### Task 3: Add Integration Test for Both Drivers

**Files:**
- Test: `tests/integration/test_tool_name_normalization.py` (new)

**Step 1: Create integration test file**

```python
"""Integration tests for tool name normalization across drivers."""

import pytest

from amelia.core.agentic_state import ToolCall
from amelia.core.constants import ToolName
from amelia.core.orchestrator import call_architect_node
from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile


@pytest.mark.asyncio
async def test_goal_extraction_with_normalized_tool_name(
    mock_profile: Profile,
    mock_issue: Issue,
) -> None:
    """Goal extraction works with normalized tool names from any driver."""
    plan_content = """# Feature Plan

**Goal:** Add dark mode support

## Tasks
..."""

    # Simulate state from CLI driver (now normalized to write_file)
    state = ExecutionState(
        issue=mock_issue,
        raw_architect_output="Done",
        tool_calls=[
            ToolCall(
                tool_name=ToolName.WRITE_FILE,
                tool_input={"file_path": "/tmp/plan.md", "content": plan_content},
            )
        ],
    )

    result = await call_architect_node(state, mock_profile)
    assert result["goal"] == "Add dark mode support"


@pytest.mark.asyncio
async def test_goal_extraction_with_api_driver_tool_name(
    mock_profile: Profile,
    mock_issue: Issue,
) -> None:
    """Goal extraction works with API driver tool names (already snake_case)."""
    plan_content = """# API Feature

**Goal:** Implement REST endpoints

## Tasks
..."""

    # Simulate state from API driver (already uses write_file)
    state = ExecutionState(
        issue=mock_issue,
        raw_architect_output="Done",
        tool_calls=[
            ToolCall(
                tool_name="write_file",  # Direct string, API driver format
                tool_input={"file_path": "/tmp/plan.md", "content": plan_content},
            )
        ],
    )

    result = await call_architect_node(state, mock_profile)
    assert result["goal"] == "Implement REST endpoints"
```

**Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_tool_name_normalization.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_tool_name_normalization.py
git commit -m "test(integration): add tool name normalization tests

Verifies goal extraction works with both normalized CLI driver tool
names and API driver tool names.

Part of #215"
```

---

### Task 4: Run Full Test Suite and Create PR

**Step 1: Run linting**

Run: `uv run ruff check amelia tests`
Expected: No errors

**Step 2: Run type checking**

Run: `uv run mypy amelia`
Expected: No errors

**Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All tests PASS

**Step 4: Create PR**

```bash
git push -u origin fix/issue-215-goal-extraction-tool-name
gh pr create --title "fix(core): normalize tool names across drivers" --body "$(cat <<'EOF'
## Summary

- Adds `CLAUDE_TOOL_NAME_MAP` to CLI driver to normalize Claude's native tool names (Write, Read, Bash) to standard ToolName enum values (write_file, read_file, run_shell_command)
- Updates orchestrator to check for `ToolName.WRITE_FILE` instead of hardcoded "Write"
- Adds integration tests to verify goal extraction works with both driver types

## Root Cause

The orchestrator's plan extraction logic (line 207) checked for `tool_name == "Write"`, but API drivers use `write_file`. This caused goal extraction to fail silently when using API drivers like `api:openrouter`.

## Solution

Normalize at the driver boundary: CLI driver now translates tool names to the standard format defined in `ToolName` enum, and orchestrator uses this standard constant.

Fixes #215

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
