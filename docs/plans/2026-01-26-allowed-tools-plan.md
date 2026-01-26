# Allowed Tools Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `allowed_tools` parameter to the driver interface so agents can run with restricted tool access (e.g., read-only for Oracle).

**Architecture:** Extend `ToolName` enum with all 20 CLI tools, add bidirectional name mapping (`TOOL_NAME_ALIASES` → `CANONICAL_TO_CLI`), a `READONLY_TOOLS` preset, and wire `allowed_tools: list[str] | None` through `DriverInterface` → `ClaudeCliDriver` (full impl) → `ApiDriver` (stub).

**Tech Stack:** Python 3.12+, StrEnum, claude-agent-sdk (`ClaudeAgentOptions.allowed_tools`), pytest

---

### Task 1: Expand `ToolName` enum with all 20 canonical tool names

**Files:**
- Modify: `amelia/core/constants.py:7-18` (ToolName class)
- Test: `tests/unit/core/test_constants.py`

**Step 1: Write the failing test**

Add to `tests/unit/core/test_constants.py`:

```python
def test_tool_name_enum_has_all_canonical_names() -> None:
    """ToolName enum defines all 20 canonical tool names."""
    expected = {
        "read_file", "write_file", "edit_file", "notebook_edit",
        "glob", "grep", "run_shell_command", "task", "task_output",
        "task_stop", "enter_plan_mode", "exit_plan_mode",
        "ask_user_question", "skill", "task_create", "task_get",
        "task_update", "task_list", "web_fetch", "web_search",
    }
    actual = {member.value for member in ToolName}
    assert actual == expected
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_constants.py::test_tool_name_enum_has_all_canonical_names -v`
Expected: FAIL — ToolName only has 3 members.

**Step 3: Write minimal implementation**

Replace the `ToolName` class body in `amelia/core/constants.py` with all 20 members:

```python
class ToolName(StrEnum):
    """Standard tool names used across drivers."""

    # File operations
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    EDIT_FILE = "edit_file"
    NOTEBOOK_EDIT = "notebook_edit"
    GLOB = "glob"
    GREP = "grep"
    # Execution
    RUN_SHELL_COMMAND = "run_shell_command"
    # Agent orchestration
    TASK = "task"
    TASK_OUTPUT = "task_output"
    TASK_STOP = "task_stop"
    # Planning
    ENTER_PLAN_MODE = "enter_plan_mode"
    EXIT_PLAN_MODE = "exit_plan_mode"
    # Interaction
    ASK_USER_QUESTION = "ask_user_question"
    SKILL = "skill"
    # Task tracking
    TASK_CREATE = "task_create"
    TASK_GET = "task_get"
    TASK_UPDATE = "task_update"
    TASK_LIST = "task_list"
    # Web
    WEB_FETCH = "web_fetch"
    WEB_SEARCH = "web_search"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_constants.py::test_tool_name_enum_has_all_canonical_names -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/core/constants.py tests/unit/core/test_constants.py
git commit -m "feat(core): expand ToolName enum with all 20 canonical tool names"
```

---

### Task 2: Expand `TOOL_NAME_ALIASES` and add `CANONICAL_TO_CLI` reverse mapping

**Files:**
- Modify: `amelia/core/constants.py:22-28` (TOOL_NAME_ALIASES) and add new constant
- Test: `tests/unit/core/test_constants.py`

**Step 1: Write the failing tests**

Add to `tests/unit/core/test_constants.py`:

```python
from amelia.core.constants import CANONICAL_TO_CLI, TOOL_NAME_ALIASES, ToolName


def test_tool_name_aliases_covers_all_cli_sdk_names() -> None:
    """TOOL_NAME_ALIASES maps every CLI SDK name to its canonical name."""
    expected_cli_names = {
        "Read", "Write", "Edit", "NotebookEdit", "Glob", "Grep", "Bash",
        "Task", "TaskOutput", "TaskStop", "EnterPlanMode", "ExitPlanMode",
        "AskUserQuestion", "Skill", "TaskCreate", "TaskGet", "TaskUpdate",
        "TaskList", "WebFetch", "WebSearch",
    }
    assert set(TOOL_NAME_ALIASES.keys()) == expected_cli_names


def test_canonical_to_cli_is_inverse_of_aliases() -> None:
    """CANONICAL_TO_CLI maps every canonical name back to its CLI SDK name."""
    for cli_name, canonical in TOOL_NAME_ALIASES.items():
        assert CANONICAL_TO_CLI[canonical] == cli_name


def test_canonical_to_cli_covers_all_tool_names() -> None:
    """CANONICAL_TO_CLI has an entry for every ToolName enum member."""
    for member in ToolName:
        assert member.value in CANONICAL_TO_CLI, f"Missing CANONICAL_TO_CLI entry for {member}"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_constants.py -k "aliases_covers or inverse or canonical_to_cli_covers" -v`
Expected: FAIL — missing CLI names in aliases, `CANONICAL_TO_CLI` doesn't exist.

**Step 3: Write minimal implementation**

In `amelia/core/constants.py`, replace `TOOL_NAME_ALIASES` and add `CANONICAL_TO_CLI`:

```python
TOOL_NAME_ALIASES: dict[str, str] = {
    "Read": ToolName.READ_FILE,
    "Write": ToolName.WRITE_FILE,
    "Edit": ToolName.EDIT_FILE,
    "NotebookEdit": ToolName.NOTEBOOK_EDIT,
    "Glob": ToolName.GLOB,
    "Grep": ToolName.GREP,
    "Bash": ToolName.RUN_SHELL_COMMAND,
    "Task": ToolName.TASK,
    "TaskOutput": ToolName.TASK_OUTPUT,
    "TaskStop": ToolName.TASK_STOP,
    "EnterPlanMode": ToolName.ENTER_PLAN_MODE,
    "ExitPlanMode": ToolName.EXIT_PLAN_MODE,
    "AskUserQuestion": ToolName.ASK_USER_QUESTION,
    "Skill": ToolName.SKILL,
    "TaskCreate": ToolName.TASK_CREATE,
    "TaskGet": ToolName.TASK_GET,
    "TaskUpdate": ToolName.TASK_UPDATE,
    "TaskList": ToolName.TASK_LIST,
    "WebFetch": ToolName.WEB_FETCH,
    "WebSearch": ToolName.WEB_SEARCH,
}

CANONICAL_TO_CLI: dict[str, str] = {v: k for k, v in TOOL_NAME_ALIASES.items()}
```

Also remove the old lowercase API driver aliases (`"write"`, `"read"`) — these were for the DeepAgents driver which uses its own tool names that don't map to this CLI-centric table. The `normalize_tool_name` function will pass them through unchanged, which is correct.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_constants.py -k "aliases_covers or inverse or canonical_to_cli_covers" -v`
Expected: PASS

**Step 5: Also run existing tests to confirm no regressions**

Run: `uv run pytest tests/unit/core/test_constants.py -v`
Expected: PASS (update `test_normalize_tool_name_handles_all_driver_variants` if it asserts on the removed lowercase aliases — remove the `"write"` and `"read"` assertions since those DeepAgents aliases are gone).

**Step 6: Commit**

```bash
git add amelia/core/constants.py tests/unit/core/test_constants.py
git commit -m "feat(core): expand TOOL_NAME_ALIASES and add CANONICAL_TO_CLI reverse mapping"
```

---

### Task 3: Add `READONLY_TOOLS` preset

**Files:**
- Modify: `amelia/core/constants.py` (add constant after `CANONICAL_TO_CLI`)
- Test: `tests/unit/core/test_constants.py`

**Step 1: Write the failing test**

Add to `tests/unit/core/test_constants.py`:

```python
from amelia.core.constants import READONLY_TOOLS, ToolName


def test_readonly_tools_contains_expected_tools() -> None:
    """READONLY_TOOLS preset includes only safe read/search tools."""
    expected = [
        ToolName.READ_FILE,
        ToolName.GLOB,
        ToolName.GREP,
        ToolName.TASK,
        ToolName.TASK_OUTPUT,
        ToolName.WEB_FETCH,
        ToolName.WEB_SEARCH,
    ]
    assert READONLY_TOOLS == expected


def test_readonly_tools_excludes_write_and_exec() -> None:
    """READONLY_TOOLS must not include any write or execution tools."""
    dangerous = {
        ToolName.WRITE_FILE, ToolName.EDIT_FILE, ToolName.RUN_SHELL_COMMAND,
        ToolName.NOTEBOOK_EDIT,
    }
    assert not dangerous.intersection(READONLY_TOOLS)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_constants.py -k "readonly" -v`
Expected: FAIL — `READONLY_TOOLS` doesn't exist.

**Step 3: Write minimal implementation**

Add to `amelia/core/constants.py` after `CANONICAL_TO_CLI`:

```python
READONLY_TOOLS: list[str] = [
    ToolName.READ_FILE,
    ToolName.GLOB,
    ToolName.GREP,
    ToolName.TASK,
    ToolName.TASK_OUTPUT,
    ToolName.WEB_FETCH,
    ToolName.WEB_SEARCH,
]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_constants.py -k "readonly" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/core/constants.py tests/unit/core/test_constants.py
git commit -m "feat(core): add READONLY_TOOLS preset for read-only agents"
```

---

### Task 4: Add `allowed_tools` to `DriverInterface.execute_agentic()`

**Files:**
- Modify: `amelia/drivers/base.py:167-189` (DriverInterface.execute_agentic)

**Step 1: Update the interface signature**

In `amelia/drivers/base.py`, add `allowed_tools: list[str] | None = None` to `execute_agentic()`:

```python
def execute_agentic(
    self,
    prompt: str,
    cwd: str,
    session_id: str | None = None,
    instructions: str | None = None,
    schema: type[BaseModel] | None = None,
    allowed_tools: list[str] | None = None,
    **kwargs: Any,
) -> AsyncIterator["AgenticMessage"]:
    """Execute prompt with autonomous tool use, yielding messages.

    Args:
        prompt: The prompt to send.
        cwd: Working directory for tool execution.
        session_id: Optional session ID for conversation continuity.
        instructions: Optional system instructions.
        schema: Optional schema for structured output.
        allowed_tools: Optional list of canonical tool names to allow.
            When None, all tools are available. When set, only listed
            tools may be used. Use canonical names from ToolName enum.
        **kwargs: Driver-specific options (e.g., required_tool, max_continuations).

    Yields:
        AgenticMessage for each event during execution.
    """
    ...
```

**Step 2: Run existing tests to verify no regressions**

Run: `uv run pytest tests/unit/test_claude_driver.py -v`
Expected: PASS — adding a defaulted parameter is backwards-compatible.

**Step 3: Commit**

```bash
git add amelia/drivers/base.py
git commit -m "feat(drivers): add allowed_tools parameter to DriverInterface.execute_agentic"
```

---

### Task 5: Implement `allowed_tools` in `ClaudeCliDriver`

**Files:**
- Modify: `amelia/drivers/cli/claude.py:201-252` (_build_options) and `amelia/drivers/cli/claude.py:370-486` (execute_agentic)
- Test: `tests/unit/test_claude_driver.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_claude_driver.py`:

```python
class TestBuildOptionsAllowedTools:
    """Tests for allowed_tools parameter in _build_options."""

    def test_build_options_without_allowed_tools(self, driver: ClaudeCliDriver) -> None:
        """When allowed_tools is None, options should not include allowed_tools."""
        options = driver._build_options(cwd="/test")
        assert not hasattr(options, "allowed_tools") or options.allowed_tools is None

    def test_build_options_with_allowed_tools(self, driver: ClaudeCliDriver) -> None:
        """When allowed_tools is set, canonical names are mapped to CLI SDK names."""
        options = driver._build_options(
            cwd="/test",
            allowed_tools=["read_file", "glob", "grep"],
        )
        assert options.allowed_tools == ["Read", "Glob", "Grep"]

    def test_build_options_skips_unknown_canonical_names(self, driver: ClaudeCliDriver) -> None:
        """Unknown canonical names are skipped (not passed to SDK)."""
        options = driver._build_options(
            cwd="/test",
            allowed_tools=["read_file", "unknown_tool"],
        )
        assert options.allowed_tools == ["Read"]


class TestExecuteAgenticAllowedTools:
    """Tests for allowed_tools parameter in execute_agentic."""

    async def test_execute_agentic_passes_allowed_tools(self, driver: ClaudeCliDriver) -> None:
        """execute_agentic passes allowed_tools through to _build_options."""
        with patch.object(driver, "_build_options", wraps=driver._build_options) as mock_build:
            # Mock the SDK client to avoid real execution
            mock_client = AsyncMock()
            mock_result = MockResultMessage(result="done", session_id="s1")
            mock_client.receive_response = create_mock_sdk_client([mock_result])
            mock_client.query = create_mock_query()

            with patch("amelia.drivers.cli.claude.ClaudeSDKClient") as MockSDK:
                MockSDK.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                MockSDK.return_value.__aexit__ = AsyncMock(return_value=False)

                messages = []
                async for msg in driver.execute_agentic(
                    prompt="test",
                    cwd="/test",
                    allowed_tools=["read_file", "glob"],
                ):
                    messages.append(msg)

                mock_build.assert_called_once()
                call_kwargs = mock_build.call_args
                assert call_kwargs.kwargs.get("allowed_tools") == ["read_file", "glob"]
```

Note: The test uses fixtures (`driver`, `create_mock_query`, `create_mock_sdk_client`, mock message classes) already defined in the test file. Import `patch` from `unittest.mock` if not already imported.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_claude_driver.py -k "AllowedTools" -v`
Expected: FAIL — `_build_options` doesn't accept `allowed_tools`.

**Step 3: Write minimal implementation**

Update `_build_options` in `amelia/drivers/cli/claude.py` to accept and map `allowed_tools`:

```python
def _build_options(
    self,
    cwd: str | None = None,
    session_id: str | None = None,
    system_prompt: str | None = None,
    schema: type[BaseModel] | None = None,
    bypass_permissions: bool = False,
    allowed_tools: list[str] | None = None,
) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions from driver configuration.

    Args:
        cwd: Working directory for Claude CLI context.
        session_id: Optional session ID to resume a previous conversation.
        system_prompt: Optional system prompt to append.
        schema: Optional Pydantic model for structured output.
        bypass_permissions: Whether to bypass permission prompts for this call.
        allowed_tools: Optional list of canonical tool names. Mapped to CLI SDK
            names via CANONICAL_TO_CLI. Unknown names are skipped.

    Returns:
        Configured ClaudeAgentOptions instance.
    """
    # Determine permission mode
    permission_mode: Literal["default", "acceptEdits", "plan", "bypassPermissions"] | None = None
    if bypass_permissions or self.skip_permissions:
        permission_mode = "bypassPermissions"

    # Build output format for schema if provided
    output_format = None
    if schema:
        output_format = {
            "type": "json_schema",
            "schema": schema.model_json_schema(),
        }

    # When resuming a session, don't override the system prompt.
    effective_system_prompt: str | SystemPromptPreset | None = system_prompt
    if session_id is not None:
        effective_system_prompt = SystemPromptPreset(type="preset", preset="claude_code")

    # Map canonical tool names to CLI SDK names
    cli_allowed_tools: list[str] | None = None
    if allowed_tools is not None:
        cli_allowed_tools = []
        for name in allowed_tools:
            cli_name = CANONICAL_TO_CLI.get(name)
            if cli_name:
                cli_allowed_tools.append(cli_name)
            else:
                logger.debug("Skipping unknown canonical tool name", tool_name=name)

    return ClaudeAgentOptions(
        model=self.model,
        cwd=cwd,
        permission_mode=permission_mode,
        system_prompt=effective_system_prompt,
        resume=session_id,
        output_format=output_format,
        allowed_tools=cli_allowed_tools,
    )
```

Add `CANONICAL_TO_CLI` to the import from constants at the top of the file:

```python
from amelia.core.constants import CANONICAL_TO_CLI, normalize_tool_name
```

Update `execute_agentic` to pass `allowed_tools` through:

```python
async def execute_agentic(
    self,
    prompt: str,
    cwd: str,
    session_id: str | None = None,
    instructions: str | None = None,
    schema: type[BaseModel] | None = None,
    allowed_tools: list[str] | None = None,
    **kwargs: Any,
) -> AsyncIterator[AgenticMessage]:
    # ... docstring updated with allowed_tools ...
    options = self._build_options(
        cwd=cwd,
        session_id=session_id,
        system_prompt=instructions,
        schema=schema,
        bypass_permissions=True,
        allowed_tools=allowed_tools,
    )
    # ... rest unchanged ...
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_claude_driver.py -k "AllowedTools" -v`
Expected: PASS

**Step 5: Run all driver tests for regressions**

Run: `uv run pytest tests/unit/test_claude_driver.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/drivers/cli/claude.py tests/unit/test_claude_driver.py
git commit -m "feat(cli-driver): implement allowed_tools mapping in ClaudeCliDriver"
```

---

### Task 6: Add `allowed_tools` stub to `ApiDriver`

**Files:**
- Modify: `amelia/drivers/api/deepagents.py:296-679` (ApiDriver.execute_agentic)
- Test: `tests/unit/test_claude_driver.py` (or a new `tests/unit/test_api_driver.py` — use whichever file already has ApiDriver tests; if none exist, add a minimal test inline)

**Step 1: Write the failing test**

Add a test (in `tests/unit/core/test_constants.py` or a new file `tests/unit/test_api_driver.py`):

```python
import pytest
from amelia.drivers.api.deepagents import ApiDriver


def test_api_driver_allowed_tools_raises_not_implemented() -> None:
    """ApiDriver raises NotImplementedError when allowed_tools is set."""
    driver = ApiDriver(model="test-model")
    with pytest.raises(NotImplementedError, match="allowed_tools"):
        # We need to start the async generator to trigger the check
        gen = driver.execute_agentic(
            prompt="test",
            cwd="/tmp",
            allowed_tools=["read_file"],
        )
        # Async generators are lazy — advance to trigger the guard
        import asyncio
        asyncio.get_event_loop().run_until_complete(gen.__anext__())
```

Actually, since we use `pytest-asyncio` with auto mode, write it as async:

```python
import pytest
from amelia.drivers.api.deepagents import ApiDriver


async def test_api_driver_allowed_tools_raises_not_implemented() -> None:
    """ApiDriver raises NotImplementedError when allowed_tools is set."""
    driver = ApiDriver(model="test-model")
    with pytest.raises(NotImplementedError, match="allowed_tools"):
        async for _ in driver.execute_agentic(
            prompt="test",
            cwd="/tmp",
            allowed_tools=["read_file"],
        ):
            pass
```

Place this in `tests/unit/test_api_driver_allowed_tools.py`.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api_driver_allowed_tools.py -v`
Expected: FAIL — `execute_agentic` doesn't check `allowed_tools`.

**Step 3: Write minimal implementation**

In `amelia/drivers/api/deepagents.py`, update `execute_agentic`:

Add `allowed_tools: list[str] | None = None` to the signature, and add a guard at the top of the method body (after the empty-prompt check):

```python
async def execute_agentic(
    self,
    prompt: str,
    cwd: str,
    session_id: str | None = None,
    instructions: str | None = None,
    schema: type[BaseModel] | None = None,
    allowed_tools: list[str] | None = None,
    **kwargs: Any,
) -> AsyncIterator[AgenticMessage]:
    # ... existing docstring, updated with allowed_tools ...

    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty")

    if allowed_tools is not None:
        raise NotImplementedError(
            "allowed_tools is not supported by ApiDriver. "
            "Use ClaudeCliDriver for tool-restricted execution."
        )

    # ... rest of method unchanged ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_api_driver_allowed_tools.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/api/deepagents.py tests/unit/test_api_driver_allowed_tools.py
git commit -m "feat(api-driver): add allowed_tools stub with NotImplementedError to ApiDriver"
```

---

### Task 7: Export new constants from `amelia/core/__init__.py` and run full checks

**Files:**
- Modify: `amelia/core/__init__.py` (add exports for `CANONICAL_TO_CLI`, `READONLY_TOOLS`)

**Step 1: Update exports**

In `amelia/core/__init__.py`, add the new public constants to exports alongside the existing `ToolName`:

```python
from amelia.core.constants import CANONICAL_TO_CLI as CANONICAL_TO_CLI
from amelia.core.constants import READONLY_TOOLS as READONLY_TOOLS
from amelia.core.constants import ToolName as ToolName
```

**Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

**Step 3: Run linting and type checking**

Run: `uv run ruff check amelia tests && uv run mypy amelia`
Expected: No errors

**Step 4: Commit**

```bash
git add amelia/core/__init__.py
git commit -m "feat(core): export CANONICAL_TO_CLI and READONLY_TOOLS from amelia.core"
```
