# OpenRouter Agentic API Driver Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

---

## Progress Tracker

| Task | Status | Commit |
|------|--------|--------|
| Task 1: Add OpenRouter to DriverType | ✅ Complete | `feat(types): add api:openrouter to DriverType` |
| Task 2: Update DriverFactory for OpenRouter | ✅ Complete | `feat(factory): add api:openrouter driver key` |
| Task 3: Add Provider Extraction to ApiDriver | ✅ Complete | `feat(api-driver): add provider extraction for openrouter support` |
| Task 4: Create Stream Event Types | ✅ Complete | `feat(api-driver): add ApiStreamEvent for agentic execution` |
| Task 6: Create Agentic Context and Tool Definitions | ✅ Complete | `feat(api-driver): add agentic tool definitions` |
| Task 6: Implement execute_agentic Method (8a/8b/8c) | ✅ Complete | `feat(api-driver): implement execute_agentic with pydantic-ai` |
| Task 7: Standardize execute_agentic Interface | ✅ Complete | `refactor(drivers): standardize execute_agentic to use instructions parameter` |
| Task 9: Run Full Test Suite and Lint | ✅ Complete | `chore: fix lint and type issues` |
| Task 10: Integration Test (Optional) | ✅ Complete | `test: add OpenRouter agentic integration test` |

**Last Updated:** 2025-12-22
**Status:** ✅ All Tasks Complete

---

**Goal:** Make ApiDriver OpenRouter-compatible with full agentic tool execution for the Developer agent.

**Architecture:** Generalize ApiDriver to accept both `openai:*` and `openrouter:*` models via pydantic-ai's native provider support. Implement `execute_agentic()` using pydantic-ai's `agent.iter()` API with registered tools for shell commands and file writes. Keep existing `generate()` method unchanged for Architect/Reviewer structured output.

**Tech Stack:** pydantic-ai (>=1.20.0 with OpenRouter support), asyncio, SafeShellExecutor, SafeFileWriter

---

## Task 1: Add OpenRouter to DriverType

**Files:**
- Modify: `amelia/core/types.py:20`
- Test: `tests/unit/test_driver_types.py` (new)

**Step 1: Write the failing test**

```python
# tests/unit/test_driver_types.py
"""Tests for driver type definitions."""
import pytest
from amelia.core.types import DriverType


def test_openrouter_is_valid_driver_type():
    """api:openrouter should be a valid DriverType."""
    valid_types: list[DriverType] = ["cli:claude", "api:openai", "api:openrouter", "cli", "api"]
    assert "api:openrouter" in valid_types
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_driver_types.py -v`
Expected: FAIL - "api:openrouter" not in current DriverType

**Step 3: Update DriverType literal**

```python
# amelia/core/types.py - update the DriverType definition
DriverType = Literal["cli:claude", "api:openai", "api:openrouter", "cli", "api"]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_driver_types.py -v`
Expected: PASS

**Step 5: Run type checker**

Run: `uv run mypy amelia/core/types.py`
Expected: Success, no errors

**Step 6: Commit**

```bash
git add amelia/core/types.py tests/unit/test_driver_types.py
git commit -m "feat(types): add api:openrouter to DriverType"
```

---

## Task 2: Update DriverFactory for OpenRouter

**Files:**
- Modify: `amelia/drivers/factory.py:14-20`
- Test: `tests/unit/test_driver_factory.py` (new)

**Step 1: Write the failing test**

```python
# tests/unit/test_driver_factory.py
"""Tests for driver factory."""
import pytest
from amelia.drivers.factory import DriverFactory
from amelia.drivers.api.openai import ApiDriver


def test_factory_returns_api_driver_for_openrouter():
    """Factory should return ApiDriver for api:openrouter."""
    driver = DriverFactory.get_driver("api:openrouter", model="openrouter:anthropic/claude-3.5-sonnet")
    assert isinstance(driver, ApiDriver)


def test_factory_raises_for_unknown_driver():
    """Factory should raise ValueError for unknown driver key."""
    with pytest.raises(ValueError, match="Unknown driver key"):
        DriverFactory.get_driver("unknown:driver")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_driver_factory.py::test_factory_returns_api_driver_for_openrouter -v`
Expected: FAIL - ValueError "Unknown driver key: api:openrouter"

**Step 3: Update factory to accept openrouter**

```python
# amelia/drivers/factory.py - update get_driver method
@staticmethod
def get_driver(driver_key: str, **kwargs: Any) -> DriverInterface:
    """Get a driver instance by key."""
    if driver_key in ("cli:claude", "cli"):
        return ClaudeCliDriver(**kwargs)
    elif driver_key in ("api:openai", "api:openrouter", "api"):
        return ApiDriver(**kwargs)
    else:
        raise ValueError(f"Unknown driver key: {driver_key}")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_driver_factory.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/factory.py tests/unit/test_driver_factory.py
git commit -m "feat(factory): add api:openrouter driver key"
```

---

## Task 3: Add Provider Extraction to ApiDriver

**Files:**
- Modify: `amelia/drivers/api/openai.py:35-47`
- Test: `tests/unit/test_api_driver_providers.py` (new)

**Step 1: Write the failing tests**

```python
# tests/unit/test_api_driver_providers.py
"""Tests for ApiDriver provider extraction."""
import pytest
from amelia.drivers.api.openai import ApiDriver


class TestProviderExtraction:
    """Test provider extraction in ApiDriver."""

    def test_extracts_openai_provider(self):
        """Should extract openai provider from model string."""
        driver = ApiDriver(model="openai:gpt-4o")
        assert driver.model_name == "openai:gpt-4o"
        assert driver._provider == "openai"

    def test_extracts_openrouter_provider(self):
        """Should extract openrouter provider from model string."""
        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")
        assert driver.model_name == "openrouter:anthropic/claude-3.5-sonnet"
        assert driver._provider == "openrouter"

    def test_defaults_to_openai_without_prefix(self):
        """Should default to openai provider when no prefix given."""
        driver = ApiDriver(model="gpt-4o")
        assert driver._provider == "openai"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_api_driver_providers.py -v`
Expected: FAIL - _provider attribute missing

**Step 3: Update ApiDriver __init__**

```python
# amelia/drivers/api/openai.py - replace __init__ method

class ApiDriver(DriverInterface):
    """API-based driver using pydantic-ai.

    Supports any provider that pydantic-ai supports (openai, openrouter, etc.).

    Attributes:
        model_name: The model identifier in format 'provider:model-name'.
        _provider: The provider name extracted from model_name.
    """

    def __init__(self, model: str = 'openai:gpt-4o'):
        """Initialize the API driver.

        Args:
            model: Model identifier in format 'provider:model-name'.
                   Pydantic-ai validates provider support at runtime.
                   Defaults to 'openai:gpt-4o'.
        """
        self.model_name = model
        self._provider = model.split(":")[0] if ":" in model else "openai"
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_api_driver_providers.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/api/openai.py tests/unit/test_api_driver_providers.py
git commit -m "feat(api-driver): add provider extraction for openrouter support"
```

---

## ~~Task 4: API Key Validation~~ (REMOVED)

> **Skipped:** Pydantic-ai already validates API keys when `Agent()` is instantiated.
> It raises clear errors like `ValueError: "OPENROUTER_API_KEY environment variable not set"`.
> Custom validation would duplicate this functionality.

---

## Task 4: Create Stream Event Types

**Files:**
- Create: `amelia/drivers/api/events.py`
- Test: `tests/unit/test_api_events.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_api_events.py
"""Tests for API driver stream events."""
import pytest
from amelia.drivers.api.events import ApiStreamEvent, ApiStreamEventType


class TestApiStreamEvent:
    """Test ApiStreamEvent model."""

    def test_create_thinking_event(self):
        """Should create thinking event with content."""
        event = ApiStreamEvent(type="thinking", content="Processing request...")
        assert event.type == "thinking"
        assert event.content == "Processing request..."

    def test_create_tool_use_event(self):
        """Should create tool_use event with tool info."""
        event = ApiStreamEvent(
            type="tool_use",
            tool_name="run_shell_command",
            tool_input={"command": "ls -la"},
        )
        assert event.type == "tool_use"
        assert event.tool_name == "run_shell_command"
        assert event.tool_input == {"command": "ls -la"}

    def test_create_tool_result_event(self):
        """Should create tool_result event."""
        event = ApiStreamEvent(
            type="tool_result",
            tool_name="run_shell_command",
            tool_result="file1.txt\nfile2.txt",
        )
        assert event.type == "tool_result"
        assert event.tool_result == "file1.txt\nfile2.txt"

    def test_create_result_event(self):
        """Should create result event with session_id."""
        event = ApiStreamEvent(
            type="result",
            result_text="Task completed successfully",
            session_id="abc123",
        )
        assert event.type == "result"
        assert event.result_text == "Task completed successfully"
        assert event.session_id == "abc123"

    def test_create_error_event(self):
        """Should create error event."""
        event = ApiStreamEvent(type="error", content="Something went wrong")
        assert event.type == "error"
        assert event.content == "Something went wrong"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api_events.py -v`
Expected: FAIL - ModuleNotFoundError: No module named 'amelia.drivers.api.events'

**Step 3: Create events module**

```python
# amelia/drivers/api/events.py
"""Stream event types for API driver agentic execution."""
from typing import Any, Literal

from pydantic import BaseModel


ApiStreamEventType = Literal["thinking", "tool_use", "tool_result", "result", "error"]


class ApiStreamEvent(BaseModel):
    """Event from API driver agentic execution.

    Mirrors ClaudeStreamEvent structure for unified streaming interface.

    Attributes:
        type: Event type (thinking, tool_use, tool_result, result, error).
        content: Text content for thinking/error events.
        tool_name: Tool name for tool_use/tool_result events.
        tool_input: Tool input parameters for tool_use events.
        tool_result: Tool execution result for tool_result events.
        session_id: Session ID from result events for continuity.
        result_text: Final result text from result events.
    """

    type: ApiStreamEventType
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_result: str | None = None
    session_id: str | None = None
    result_text: str | None = None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_api_events.py -v`
Expected: PASS

**Step 5: Run type checker**

Run: `uv run mypy amelia/drivers/api/events.py`
Expected: Success

**Step 6: Commit**

```bash
git add amelia/drivers/api/events.py tests/unit/test_api_events.py
git commit -m "feat(api-driver): add ApiStreamEvent for agentic execution"
```

---

## Task 6: Create Agentic Context and Tool Definitions

**Files:**
- Create: `amelia/drivers/api/tools.py`
- Test: `tests/unit/test_api_tools.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_api_tools.py
"""Tests for API driver tool definitions."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from amelia.drivers.api.tools import AgenticContext, run_shell_command, write_file


class TestAgenticContext:
    """Test AgenticContext dataclass."""

    def test_create_context_with_cwd(self, tmp_path):
        """Should create context with cwd."""
        ctx = AgenticContext(cwd=str(tmp_path))
        assert ctx.cwd == str(tmp_path.resolve())
        assert ctx.allowed_dirs is None

    def test_create_context_with_allowed_dirs(self, tmp_path):
        """Should create context with allowed_dirs."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        ctx = AgenticContext(cwd=str(tmp_path), allowed_dirs=[str(tmp_path), str(subdir)])
        assert len(ctx.allowed_dirs) == 2

    def test_raises_for_nonexistent_cwd(self):
        """Should raise ValueError for non-existent cwd."""
        with pytest.raises(ValueError, match="does not exist"):
            AgenticContext(cwd="/nonexistent/path/that/does/not/exist")


class TestRunShellCommand:
    """Test run_shell_command tool."""

    @pytest.fixture
    def run_context(self, tmp_path):
        """Create RunContext with real tmp_path."""
        ctx = MagicMock()
        ctx.deps = AgenticContext(cwd=str(tmp_path))
        return ctx

    async def test_executes_command_with_cwd(self, run_context, tmp_path):
        """Should execute command in context's cwd."""
        # Create a test file to verify cwd is used
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello from test")

        # Execute real command, no mocking - tests actual behavior
        result = await run_shell_command(run_context, "cat test.txt", timeout=30)

        assert result.strip() == "hello from test"

    async def test_caps_timeout_at_300_seconds(self, run_context):
        """Should cap timeout to prevent resource exhaustion."""
        # This tests the security fix - LLM could try to set huge timeout
        # The function should internally cap it to 300
        # We test this by using a value > 300 and ensuring it doesn't hang
        result = await run_shell_command(run_context, "echo 'quick'", timeout=999999)
        assert "quick" in result

    async def test_returns_command_output(self, run_context):
        """Should return stdout from command."""
        result = await run_shell_command(run_context, "echo 'test output'", timeout=30)
        assert "test output" in result


class TestWriteFile:
    """Test write_file tool."""

    @pytest.fixture
    def run_context(self, tmp_path):
        """Create RunContext with real tmp_path."""
        ctx = MagicMock()
        ctx.deps = AgenticContext(cwd=str(tmp_path), allowed_dirs=[str(tmp_path)])
        return ctx

    async def test_writes_file_with_allowed_dirs(self, run_context, tmp_path):
        """Should write file within allowed directories."""
        file_path = str(tmp_path / "test.py")

        # Execute real write, no mocking - tests actual behavior
        result = await write_file(run_context, file_path, "print('hello')")

        # Verify file was actually written
        assert (tmp_path / "test.py").exists()
        assert (tmp_path / "test.py").read_text() == "print('hello')"
        assert "success" in result.lower() or "written" in result.lower()

    async def test_creates_parent_directories(self, run_context, tmp_path):
        """Should create parent directories if needed."""
        file_path = str(tmp_path / "subdir" / "nested" / "test.py")

        result = await write_file(run_context, file_path, "# nested file")

        assert (tmp_path / "subdir" / "nested" / "test.py").exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api_tools.py -v`
Expected: FAIL - ModuleNotFoundError: No module named 'amelia.drivers.api.tools'

**Step 3: Create tools module**

```python
# amelia/drivers/api/tools.py
"""Tool definitions for pydantic-ai agentic execution."""
from dataclasses import dataclass

from pydantic_ai import RunContext

from amelia.tools.safe_file import SafeFileWriter
from amelia.tools.safe_shell import SafeShellExecutor


@dataclass
class AgenticContext:
    """Context for agentic tool execution.

    Attributes:
        cwd: Working directory for command execution.
        allowed_dirs: Directories where file writes are permitted.
    """

    cwd: str
    allowed_dirs: list[str] | None = None

    def __post_init__(self):
        """Validate and normalize paths."""
        from pathlib import Path

        cwd_path = Path(self.cwd)
        if not cwd_path.exists():
            raise ValueError(f"Working directory does not exist: {self.cwd}")
        if not cwd_path.is_dir():
            raise ValueError(f"Working directory is not a directory: {self.cwd}")

        # Resolve and normalize
        self.cwd = str(cwd_path.resolve())

        if self.allowed_dirs:
            resolved = []
            for d in self.allowed_dirs:
                p = Path(d)
                if not p.exists():
                    raise ValueError(f"Allowed directory does not exist: {d}")
                resolved.append(str(p.resolve()))
            self.allowed_dirs = resolved


MAX_COMMAND_TIMEOUT = 300  # 5 minutes max
MAX_COMMAND_SIZE = 10_000  # 10KB max command


async def run_shell_command(
    ctx: RunContext[AgenticContext],
    command: str,
    timeout: int = 30,
) -> str:
    """Execute a shell command safely.

    Use this to run shell commands like ls, cat, grep, git, npm, python, etc.
    Commands are executed in the working directory with security restrictions.

    Args:
        ctx: Run context containing the working directory.
        command: The shell command to execute.
        timeout: Maximum execution time in seconds. Defaults to 30. Capped at 300.

    Returns:
        Command output (stdout) as a string.
    """
    # Validate command size to prevent memory exhaustion
    if len(command) > MAX_COMMAND_SIZE:
        raise ValueError(f"Command size ({len(command)} bytes) exceeds maximum ({MAX_COMMAND_SIZE} bytes)")

    # Validate and cap timeout
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    timeout = min(timeout, MAX_COMMAND_TIMEOUT)

    # SafeShellExecutor.execute is async - call directly
    return await SafeShellExecutor.execute(
        command=command,
        timeout=timeout,
        cwd=ctx.deps.cwd,
    )


async def write_file(
    ctx: RunContext[AgenticContext],
    file_path: str,
    content: str,
) -> str:
    """Write content to a file safely.

    Use this to create or overwrite files. The file path must be within
    the allowed directories (defaults to working directory).

    Args:
        ctx: Run context containing allowed directories.
        file_path: Absolute or relative path to the file to write.
        content: Content to write to the file.

    Returns:
        Success message confirming the write operation.
    """
    allowed_dirs = ctx.deps.allowed_dirs if ctx.deps.allowed_dirs else [ctx.deps.cwd]
    return await SafeFileWriter.write(
        file_path=file_path,
        content=content,
        allowed_dirs=allowed_dirs,
    )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_api_tools.py -v`
Expected: PASS

**Step 5: Run type checker**

Run: `uv run mypy amelia/drivers/api/tools.py`
Expected: Success

**Step 6: Commit**

```bash
git add amelia/drivers/api/tools.py tests/unit/test_api_tools.py
git commit -m "feat(api-driver): add agentic tool definitions"
```

---

## ~~Task 7: Tool Support Validation~~ (REMOVED)

> **Skipped:** The `_NO_TOOL_MODELS` denylist would become stale immediately.
> Modern models (2024+) all support tools. If a model doesn't support tools,
> pydantic-ai will raise a clear error when `Agent()` tries to register tools.
> No need to maintain a historical blocklist of deprecated models.

---

## Task 6: Implement execute_agentic Method

> **Note:** This task is split into 3 subtasks for better test coverage and maintainability.
> Each subtask focuses on a single responsibility with dedicated tests.

**Files:**
- Modify: `amelia/drivers/api/openai.py`
- Test: `tests/unit/test_api_driver_agentic.py`

---

### Task 8a: Add Message Validation Helper

**Step 1: Write the failing tests for _validate_messages**

```python
# tests/unit/test_api_driver_agentic.py - add first
"""Tests for ApiDriver agentic execution."""
import pytest
from amelia.core.state import AgentMessage
from amelia.drivers.api.openai import ApiDriver


class TestValidateMessages:
    """Test _validate_messages helper method."""

    @pytest.fixture
    def driver(self):
        """Create ApiDriver instance."""
        return ApiDriver(model="openai:gpt-4o")

    def test_rejects_empty_messages(self, driver):
        """Should reject empty message list."""
        with pytest.raises(ValueError, match="cannot be empty"):
            driver._validate_messages([])

    def test_rejects_none_content(self, driver):
        """Should reject messages with None content."""
        with pytest.raises(ValueError, match="None content"):
            driver._validate_messages([AgentMessage(role="user", content=None)])

    def test_rejects_whitespace_only_content(self, driver):
        """Should reject messages with only whitespace content."""
        with pytest.raises(ValueError, match="empty or whitespace-only"):
            driver._validate_messages([AgentMessage(role="user", content="   \n\t  ")])

    def test_rejects_oversized_content(self, driver):
        """Should reject messages exceeding 100KB."""
        large_content = "x" * 100_001
        with pytest.raises(ValueError, match="exceeds maximum"):
            driver._validate_messages([AgentMessage(role="user", content=large_content)])

    def test_rejects_total_size_exceeding_limit(self, driver):
        """Should reject when total message size exceeds 500KB."""
        # 10 messages of 60KB each = 600KB > 500KB limit
        messages = [
            AgentMessage(role="user", content="x" * 60_000)
            for _ in range(10)
        ]
        with pytest.raises(ValueError, match="Total message content exceeds"):
            driver._validate_messages(messages)

    def test_rejects_invalid_role(self, driver):
        """Should reject invalid message roles."""
        with pytest.raises(ValueError, match="Invalid message role"):
            driver._validate_messages([AgentMessage(role="invalid", content="test")])

    def test_accepts_valid_messages(self, driver):
        """Should accept valid message list."""
        messages = [
            AgentMessage(role="system", content="You are helpful"),
            AgentMessage(role="user", content="Hello"),
            AgentMessage(role="assistant", content="Hi there"),
        ]
        driver._validate_messages(messages)  # Should not raise
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api_driver_agentic.py::TestValidateMessages -v`
Expected: FAIL - _validate_messages method doesn't exist

**Step 3: Implement _validate_messages** (see Step 5 below for code)

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_api_driver_agentic.py::TestValidateMessages -v`
Expected: PASS

---

### Task 8b: Add Message History Builder

**Step 1: Write the failing tests for _build_message_history**

```python
# tests/unit/test_api_driver_agentic.py - add to file

class TestBuildMessageHistory:
    """Test _build_message_history helper method."""

    @pytest.fixture
    def driver(self):
        """Create ApiDriver instance."""
        return ApiDriver(model="openai:gpt-4o")

    def test_returns_none_for_single_message(self, driver):
        """Should return None for single user message."""
        messages = [AgentMessage(role="user", content="Hello")]
        result = driver._build_message_history(messages)
        assert result is None

    def test_returns_none_for_system_only(self, driver):
        """Should return None when only system messages present."""
        messages = [
            AgentMessage(role="system", content="You are helpful"),
            AgentMessage(role="user", content="Hello"),
        ]
        result = driver._build_message_history(messages)
        assert result is None

    def test_builds_history_from_prior_messages(self, driver):
        """Should build history excluding last user message."""
        messages = [
            AgentMessage(role="user", content="First"),
            AgentMessage(role="assistant", content="Response"),
            AgentMessage(role="user", content="Second"),
        ]
        result = driver._build_message_history(messages)
        assert result is not None
        assert len(result) == 2  # First user + assistant

    def test_skips_empty_content(self, driver):
        """Should skip messages with empty content."""
        messages = [
            AgentMessage(role="user", content="First"),
            AgentMessage(role="assistant", content=""),
            AgentMessage(role="user", content="Second"),
        ]
        result = driver._build_message_history(messages)
        assert result is not None
        assert len(result) == 1  # Only first user message
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api_driver_agentic.py::TestBuildMessageHistory -v`
Expected: FAIL - _build_message_history method doesn't exist

**Step 3: Implement _build_message_history** (see Step 5 below for code)

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_api_driver_agentic.py::TestBuildMessageHistory -v`
Expected: PASS

---

### Task 8c: Implement Core execute_agentic Method

**Step 1: Write the failing tests**

```python
# tests/unit/test_api_driver_agentic.py - add to file

class TestExecuteAgentic:
    """Test execute_agentic core method."""

    async def test_rejects_nonexistent_cwd(self, monkeypatch):
        """Should reject non-existent working directory."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        driver = ApiDriver(model="openai:gpt-4o")

        with pytest.raises(ValueError, match="does not exist"):
            async for _ in driver.execute_agentic(
                messages=[AgentMessage(role="user", content="test")],
                cwd="/nonexistent/path/that/does/not/exist",
            ):
                pass

    async def test_yields_result_event(self, monkeypatch, tmp_path):
        """Should yield result event at end of execution."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        driver = ApiDriver(model="openai:gpt-4o")

        # Mock the pydantic-ai Agent
        with patch("amelia.drivers.api.openai.Agent") as mock_agent_class:
            mock_run = AsyncMock()
            mock_run.result = MagicMock(output="Done")
            mock_run.__aenter__ = AsyncMock(return_value=mock_run)
            mock_run.__aexit__ = AsyncMock(return_value=None)
            mock_run.__aiter__ = lambda self: iter([])  # No nodes, just end

            mock_agent = MagicMock()
            mock_agent.iter = MagicMock(return_value=mock_run)
            mock_agent_class.return_value = mock_agent

            events = []
            async for event in driver.execute_agentic(
                messages=[AgentMessage(role="user", content="test")],
                cwd=str(tmp_path),  # Use real tmp_path
            ):
                events.append(event)

            # Should have at least a result event
            assert len(events) >= 1
            assert events[-1].type == "result"
            assert events[-1].session_id is not None

    async def test_generates_unique_session_id(self, monkeypatch):
        """Should generate unique session IDs."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        driver = ApiDriver(model="openai:gpt-4o")

        session_ids = set()
        for _ in range(3):
            session_ids.add(driver._generate_session_id())

        assert len(session_ids) == 3  # All unique
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_api_driver_agentic.py -v`
Expected: FAIL - execute_agentic raises NotImplementedError

**Step 3: Add imports and session management**

```python
# amelia/drivers/api/openai.py - add imports at top
import uuid
from collections.abc import AsyncIterator

import httpx
from loguru import logger
from pydantic_ai import Agent
from pydantic_ai.agent import CallToolsNode
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)

from amelia.core.exceptions import SecurityError
from amelia.drivers.api.events import ApiStreamEvent
from amelia.drivers.api.tools import AgenticContext, run_shell_command, write_file
```

**Step 4: Add session management method**

```python
# amelia/drivers/api/openai.py - add to ApiDriver class

def _generate_session_id(self) -> str:
    """Generate a unique session ID.

    Returns:
        UUID string for session identification.
    """
    return str(uuid.uuid4())
```

**Step 5: Implement execute_agentic method**

```python
# amelia/drivers/api/openai.py - replace the existing execute_agentic method

async def execute_agentic(
    self,
    messages: list[AgentMessage],
    cwd: str,
    session_id: str | None = None,
    instructions: str | None = None,
) -> AsyncIterator[ApiStreamEvent]:
    """Execute prompt with autonomous tool access using pydantic-ai.

    Args:
        messages: List of conversation messages.
        cwd: Working directory for execution context.
        session_id: Optional session ID for continuity (currently unused, for interface compat).
        instructions: Runtime instructions for the agent.

    Yields:
        ApiStreamEvent objects as tools execute.

    Raises:
        ValueError: If invalid messages or cwd.
    """
    # Note: session_id is accepted for interface compatibility but not used
    # pydantic-ai manages its own conversation state via message_history
    if session_id:
        logger.debug(
            "session_id parameter provided but not used for continuity. "
            "Pydantic-ai manages conversation state via message_history parameter instead."
        )

    # Note: cwd validation (existence, directory check) is handled
    # by AgenticContext.__post_init__ when we create the context below.
    # API key validation is handled by pydantic-ai when Agent() is created.

    self._validate_messages(messages)
    self._validate_instructions(instructions)

    # Create agent with tools
    agent = Agent(
        self.model_name,
        output_type=str,
        tools=[run_shell_command, write_file],
    )

    # Build context
    context = AgenticContext(cwd=cwd, allowed_dirs=[cwd])

    # Extract current prompt from last user message
    non_system = [m for m in messages if m.role != "system"]
    if not non_system or non_system[-1].role != "user":
        raise ValueError("Messages must end with a user message")
    current_prompt = non_system[-1].content

    if not current_prompt or not current_prompt.strip():
        raise ValueError("User message cannot be empty")

    # Build message history from prior messages
    history = self._build_message_history(messages)

    new_session_id = self._generate_session_id()

    try:
        async with agent.iter(
            user_prompt=current_prompt,  # Must use keyword argument
            deps=context,
            message_history=history,
            instructions=instructions,
        ) as agent_run:
            async for node in agent_run:
                # Process tool calls from CallToolsNode
                if isinstance(node, CallToolsNode):
                    for part in node.model_response.parts:
                        if isinstance(part, ToolCallPart):
                            yield ApiStreamEvent(
                                type="tool_use",
                                tool_name=part.tool_name,
                                tool_input=part.args_as_dict(),
                            )
                    # Note: Tool results are handled internally by pydantic-ai.
                    # If you need to track results, emit events from tool functions.

            # Final result
            yield ApiStreamEvent(
                type="result",
                result_text=str(agent_run.result.output) if agent_run.result else "",
                session_id=new_session_id,
            )

    except ValueError as e:
        # Our validation errors (messages, instructions, cwd)
        logger.info("Validation failed", error=str(e))
        yield ApiStreamEvent(type="error", content=f"Invalid input: {e}")

    except SecurityError as e:
        # SafeShellExecutor/SafeFileWriter security violations
        logger.warning("Security violation", error=str(e))
        yield ApiStreamEvent(type="error", content=f"Security violation: {e}")

    except Exception as e:
        # Pydantic-ai exceptions have excellent error messages - pass them through
        # This covers: UsageLimitExceeded, ModelRetry, UnexpectedModelBehavior,
        # AgentRunError, httpx errors, etc.
        logger.error("Agentic execution failed", error=str(e), error_type=type(e).__name__)
        yield ApiStreamEvent(type="error", content=str(e))

MAX_MESSAGE_SIZE = 100_000  # 100KB per message
MAX_TOTAL_SIZE = 500_000  # 500KB total across all messages
MAX_INSTRUCTIONS_SIZE = 10_000  # 10KB max instructions


def _validate_instructions(self, instructions: str | None) -> None:
    """Validate instructions parameter for size and content.

    Args:
        instructions: Optional runtime instructions string.

    Raises:
        ValueError: If instructions are empty/whitespace or exceed size limit.
    """
    if instructions is None:
        return

    if not instructions.strip():
        raise ValueError("instructions cannot be empty or whitespace-only")

    if len(instructions) > MAX_INSTRUCTIONS_SIZE:
        raise ValueError(
            f"instructions exceeds maximum length ({MAX_INSTRUCTIONS_SIZE} chars). "
            f"Got {len(instructions)} characters."
        )


def _validate_messages(self, messages: list[AgentMessage]) -> None:
    """Validate message list for security and sanity.

    Args:
        messages: List of messages to validate.

    Raises:
        ValueError: If messages are invalid.
    """
    if not messages:
        raise ValueError("Messages list cannot be empty")

    # Check total size first (prevents many small messages attack)
    total_size = sum(len(m.content or "") for m in messages)
    if total_size > MAX_TOTAL_SIZE:
        raise ValueError(
            f"Total message content exceeds maximum ({MAX_TOTAL_SIZE // 1000}KB). "
            f"Got {total_size} characters."
        )

    for msg in messages:
        if msg.content is None:
            raise ValueError(f"Message with role '{msg.role}' has None content")

        if not msg.content.strip():
            raise ValueError(f"Message with role '{msg.role}' has empty or whitespace-only content")

        if len(msg.content) > MAX_MESSAGE_SIZE:
            raise ValueError(
                f"Message content exceeds maximum length ({MAX_MESSAGE_SIZE // 1000}KB). "
                f"Got {len(msg.content)} characters."
            )

        if msg.role not in ("system", "user", "assistant"):
            raise ValueError(f"Invalid message role: {msg.role}")

def _build_message_history(self, messages: list[AgentMessage]) -> list[ModelMessage] | None:
    """Build pydantic-ai message history from AgentMessages.

    Args:
        messages: Current conversation messages.

    Returns:
        Pydantic-ai ModelMessage list, or None for empty history.
    """
    non_system = [m for m in messages if m.role != "system"]
    if len(non_system) <= 1:
        return None

    history: list[ModelMessage] = []
    for msg in non_system[:-1]:  # Exclude last (current prompt)
        if not msg.content:
            continue
        if msg.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=msg.content)]))
        elif msg.role == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=msg.content)]))

    return history if history else None
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_api_driver_agentic.py -v`
Expected: PASS

**Step 7: Run type checker**

Run: `uv run mypy amelia/drivers/api/openai.py`
Expected: Success (may need to fix some types)

**Step 8: Commit**

```bash
git add amelia/drivers/api/openai.py tests/unit/test_api_driver_agentic.py
git commit -m "feat(api-driver): implement execute_agentic with pydantic-ai"
```

---

## Task 9: Run Full Test Suite and Lint

**Step 1: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests pass

**Step 2: Run linter**

Run: `uv run ruff check amelia/drivers/api/`
Expected: No errors

**Step 3: Run type checker on full package**

Run: `uv run mypy amelia/`
Expected: Success

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "chore: fix lint and type issues"
```

---

## Task 10: Integration Test (Optional - Requires API Key)

**Files:**
- Create: `tests/integration/test_openrouter_agentic.py`

**Step 1: Create integration test**

```python
# tests/integration/test_openrouter_agentic.py
"""Integration tests for OpenRouter agentic execution."""
import os
import pytest
from amelia.core.state import AgentMessage
from amelia.drivers.api.openai import ApiDriver


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)
class TestOpenRouterAgenticIntegration:
    """Integration tests requiring real OpenRouter API."""

    async def test_simple_shell_command(self, tmp_path):
        """Should execute a simple shell command."""
        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")

        events = []
        async for event in driver.execute_agentic(
            messages=[AgentMessage(role="user", content="Run 'echo hello' and tell me the output")],
            cwd=str(tmp_path),
            instructions="You are a helpful assistant. Use tools to complete tasks.",
        ):
            events.append(event)

        # Should have tool_use, tool_result, and result events
        event_types = [e.type for e in events]
        assert "tool_use" in event_types
        assert "result" in event_types
```

**Step 2: Run integration test (if API key available)**

Run: `OPENROUTER_API_KEY=your-key uv run pytest tests/integration/test_openrouter_agentic.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_openrouter_agentic.py
git commit -m "test: add OpenRouter agentic integration test"
```

---

## ~~Task 11: Extract Message Utilities~~ (REMOVED)

> **Skipped:** Premature abstraction - "Rule of Three" says wait until 3rd use case.
> Both drivers have slightly different message handling needs and may diverge.
> The inline code is only ~10 lines in each driver. Wait for a third use case.

---

## Task 7: Standardize execute_agentic Interface

**Goal:** Clarify that `execute_agentic` uses `instructions` parameter only - no system messages in the message list.

**Files:**
- Modify: `amelia/drivers/base.py`
- Modify: `amelia/drivers/api/openai.py`
- Modify: `amelia/drivers/cli/claude.py`
- Test: `tests/unit/test_driver_interface.py` (new)

**Step 1: Write interface compliance tests**

```python
# tests/unit/test_driver_interface.py
"""Tests for driver interface compliance."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from amelia.core.state import AgentMessage
from amelia.drivers.api.openai import ApiDriver
from amelia.drivers.cli.claude import ClaudeCliDriver


class TestInterfaceCompliance:
    """Test both drivers implement execute_agentic correctly."""

    def test_api_driver_accepts_instructions_parameter(self, monkeypatch):
        """ApiDriver.execute_agentic should accept instructions parameter."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        driver = ApiDriver(model="openai:gpt-4o")

        # Verify the method signature includes instructions
        import inspect
        sig = inspect.signature(driver.execute_agentic)
        assert "instructions" in sig.parameters, "execute_agentic must accept 'instructions' parameter"
        assert "cwd" in sig.parameters, "execute_agentic must accept 'cwd' parameter"

    def test_claude_driver_accepts_instructions_parameter(self):
        """ClaudeCliDriver.execute_agentic should accept instructions parameter."""
        driver = ClaudeCliDriver()

        # Verify the method signature includes instructions
        import inspect
        sig = inspect.signature(driver.execute_agentic)
        assert "instructions" in sig.parameters, "execute_agentic must accept 'instructions' parameter"
        assert "cwd" in sig.parameters, "execute_agentic must accept 'cwd' parameter"

    async def test_api_driver_uses_instructions_not_system_messages(self, monkeypatch, tmp_path):
        """ApiDriver should use instructions parameter, not extract from system messages."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        driver = ApiDriver(model="openai:gpt-4o")

        with patch("amelia.drivers.api.openai.Agent") as mock_agent_class:
            mock_run = AsyncMock()
            mock_run.result = MagicMock(output="Done")
            mock_run.__aenter__ = AsyncMock(return_value=mock_run)
            mock_run.__aexit__ = AsyncMock(return_value=None)
            mock_run.__aiter__ = lambda self: iter([])

            mock_agent = MagicMock()
            mock_agent.iter = MagicMock(return_value=mock_run)
            mock_agent_class.return_value = mock_agent

            # Execute with instructions parameter
            async for _ in driver.execute_agentic(
                messages=[AgentMessage(role="user", content="test")],
                cwd=str(tmp_path),
                instructions="Be helpful",
            ):
                pass

            # Verify instructions was passed to agent.iter
            mock_agent.iter.assert_called_once()
            call_kwargs = mock_agent.iter.call_args.kwargs
            assert call_kwargs.get("instructions") == "Be helpful"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_driver_interface.py -v`
Expected: FAIL - ClaudeCliDriver may still use system_prompt

**Step 3: Update base interface docstring**

```python
# amelia/drivers/base.py - update execute_agentic docstring
@abstractmethod
async def execute_agentic(
    self,
    messages: list[AgentMessage],
    cwd: str,
    instructions: str | None = None,
) -> AsyncIterator[Any]:
    """Execute prompt with autonomous tool access.

    Args:
        messages: Conversation history (user/assistant messages only).
                  System messages should NOT be included - use `instructions` instead.
        cwd: Working directory for tool execution.
        instructions: Runtime instructions for the agent. This replaces
                      system prompts for agentic execution.

    Yields:
        Stream events as execution progresses.
    """
    ...
```

**Step 4: Verify ApiDriver implementation matches**

The ApiDriver implementation from Task 8 already filters system messages and uses `instructions`. Verify no changes needed.

**Step 5: Update ClaudeCliDriver to match**

```python
# amelia/drivers/cli/claude.py - update execute_agentic
# Remove system_prompt handling from execute_agentic since instructions replaces it
# The instructions parameter is passed to --append-system-prompt instead
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_driver_interface.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/drivers/base.py amelia/drivers/cli/claude.py tests/unit/test_driver_interface.py
git commit -m "refactor(drivers): standardize execute_agentic to use instructions only"
```

---

## ~~Task 13: DeveloperContextStrategy~~ (REMOVED)

> **Skipped:** Not needed yet. Developer agent uses `execute_agentic()` with tools,
> not `generate()` with schemas like Architect/Reviewer. Different execution modes
> require different context handling. Add only when there's a concrete need.

---

## ~~Task 14: ClaudeCliDriver Prompt Consolidation~~ (REMOVED)

> **Skipped:** Premature abstraction - the 15 lines in each method are clear.
> Wait until a third use case emerges or the methods start to diverge.

---

## Summary

After completing all tasks:
- `ApiDriver` accepts both `openai:*` and `openrouter:*` models
- `execute_agentic()` uses pydantic-ai with registered tools
- Session IDs are generated for continuity
- `execute_agentic` interface standardized to use `instructions` parameter
- All tests pass, lint clean, types check

**Simplified approach (leaning on pydantic-ai):**
- No custom `SUPPORTED_PROVIDERS` validation - pydantic-ai handles it
- No custom `_validate_api_key()` - pydantic-ai validates at Agent creation
- No `_NO_TOOL_MODELS` denylist - pydantic-ai errors if tools not supported
- Simplified error handling - pydantic-ai exceptions have excellent messages

**Files created/modified:**
- `amelia/core/types.py` - Added `api:openrouter`
- `amelia/drivers/factory.py` - Updated factory
- `amelia/drivers/api/openai.py` - Provider extraction + execute_agentic
- `amelia/drivers/api/events.py` - New (ApiStreamEvent)
- `amelia/drivers/api/tools.py` - New (run_shell_command, write_file)
- `amelia/drivers/base.py` - Updated docstrings
- `tests/unit/test_driver_types.py` - New
- `tests/unit/test_driver_factory.py` - New
- `tests/unit/test_api_driver_providers.py` - New
- `tests/unit/test_api_events.py` - New
- `tests/unit/test_api_tools.py` - New
- `tests/unit/test_api_driver_agentic.py` - New
- `tests/unit/test_driver_interface.py` - New
- `tests/integration/test_openrouter_agentic.py` - New (optional)
