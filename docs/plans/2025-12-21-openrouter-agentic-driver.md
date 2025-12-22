# OpenRouter Agentic API Driver Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make ApiDriver OpenRouter-compatible with full agentic tool execution for the Developer agent.

**Architecture:** Generalize ApiDriver to accept both `openai:*` and `openrouter:*` models via pydantic-ai's native provider support. Implement `execute_agentic()` using pydantic-ai's `agent.iter()` API with registered tools for shell commands and file writes. Keep existing `generate()` method unchanged for Architect/Reviewer structured output.

**Tech Stack:** pydantic-ai (>=1.20.0 with OpenRouter support), asyncio, SafeShellExecutor, SafeFileWriter

---

## Task 1: Add OpenRouter to DriverType

**Files:**
- Modify: `amelia/core/types.py:27`
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

## Task 3: Generalize ApiDriver Provider Validation

**Files:**
- Modify: `amelia/drivers/api/openai.py:35-47`
- Test: `tests/unit/test_api_driver_providers.py` (new)

**Step 1: Write the failing tests**

```python
# tests/unit/test_api_driver_providers.py
"""Tests for ApiDriver provider validation."""
import os
import pytest
from amelia.drivers.api.openai import ApiDriver


class TestProviderValidation:
    """Test provider validation in ApiDriver."""

    def test_accepts_openai_model(self):
        """Should accept openai: prefixed models."""
        driver = ApiDriver(model="openai:gpt-4o")
        assert driver.model_name == "openai:gpt-4o"
        assert driver._provider == "openai"

    def test_accepts_openrouter_model(self):
        """Should accept openrouter: prefixed models."""
        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")
        assert driver.model_name == "openrouter:anthropic/claude-3.5-sonnet"
        assert driver._provider == "openrouter"

    def test_rejects_unsupported_provider(self):
        """Should reject unsupported providers."""
        with pytest.raises(ValueError, match="Unsupported provider"):
            ApiDriver(model="gemini:pro")

    def test_rejects_no_prefix(self):
        """Should reject models without provider prefix."""
        with pytest.raises(ValueError, match="Unsupported provider"):
            ApiDriver(model="gpt-4o")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_api_driver_providers.py -v`
Expected: FAIL - openrouter tests fail, _provider attribute missing

**Step 3: Update ApiDriver __init__**

```python
# amelia/drivers/api/openai.py - replace __init__ method

SUPPORTED_PROVIDERS = ("openai:", "openrouter:")


class ApiDriver(DriverInterface):
    """API-based driver using pydantic-ai.

    Supports OpenAI and OpenRouter providers for LLM generation.

    Attributes:
        model_name: The model identifier in format 'provider:model-name'.
        _provider: The provider name extracted from model_name.
    """

    def __init__(self, model: str = 'openai:gpt-4o'):
        """Initialize the API driver.

        Args:
            model: Model identifier in format 'provider:model-name'.
                   Supported providers: openai, openrouter.
                   Defaults to 'openai:gpt-4o'.

        Raises:
            ValueError: If model does not use a supported provider prefix.
        """
        if not any(model.startswith(prefix) for prefix in SUPPORTED_PROVIDERS):
            raise ValueError(
                f"Unsupported provider in model '{model}'. "
                f"ApiDriver supports: {', '.join(p.rstrip(':') for p in SUPPORTED_PROVIDERS)}"
            )
        self.model_name = model
        self._provider = model.split(":")[0]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_api_driver_providers.py -v`
Expected: PASS

**Step 5: Run type checker**

Run: `uv run mypy amelia/drivers/api/openai.py`
Expected: Success

**Step 6: Commit**

```bash
git add amelia/drivers/api/openai.py tests/unit/test_api_driver_providers.py
git commit -m "feat(api-driver): support openrouter provider"
```

---

## Task 4: Add Provider-Specific API Key Validation

**Files:**
- Modify: `amelia/drivers/api/openai.py`
- Test: `tests/unit/test_api_driver_providers.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_api_driver_providers.py - add to existing file

class TestApiKeyValidation:
    """Test API key validation per provider."""

    def test_openai_requires_openai_api_key(self, monkeypatch):
        """OpenAI provider should require OPENAI_API_KEY."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        driver = ApiDriver(model="openai:gpt-4o")

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            driver._validate_api_key()

    def test_openrouter_requires_openrouter_api_key(self, monkeypatch):
        """OpenRouter provider should require OPENROUTER_API_KEY."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")

        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            driver._validate_api_key()

    def test_openai_passes_with_key_set(self, monkeypatch):
        """OpenAI validation should pass when key is set."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        driver = ApiDriver(model="openai:gpt-4o")
        driver._validate_api_key()  # Should not raise

    def test_openrouter_passes_with_key_set(self, monkeypatch):
        """OpenRouter validation should pass when key is set."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")
        driver._validate_api_key()  # Should not raise
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_api_driver_providers.py::TestApiKeyValidation -v`
Expected: FAIL - _validate_api_key method doesn't exist

**Step 3: Add _validate_api_key method**

```python
# amelia/drivers/api/openai.py - add method after __init__

def _validate_api_key(self) -> None:
    """Validate that the appropriate API key is set for the provider.

    Raises:
        ValueError: If the required API key environment variable is not set.
    """
    if self._provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError(
                "OPENAI_API_KEY environment variable is not set. "
                "Please configure it to use OpenAI models."
            )
    elif self._provider == "openrouter":
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise ValueError(
                "OPENROUTER_API_KEY environment variable is not set. "
                "Please configure it to use OpenRouter models."
            )
```

**Step 4: Update generate() to use new validation**

```python
# amelia/drivers/api/openai.py - update generate method start
# Replace the old OPENAI_API_KEY check with:

async def generate(self, messages: list[AgentMessage], schema: type[BaseModel] | None = None, **kwargs: Any) -> tuple[Any, str | None]:
    """Generate a response from the model."""
    self._validate_api_key()
    # ... rest of method unchanged
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_api_driver_providers.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/drivers/api/openai.py tests/unit/test_api_driver_providers.py
git commit -m "feat(api-driver): provider-specific API key validation"
```

---

## Task 5: Create Stream Event Types

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

    def test_create_context_with_cwd(self):
        """Should create context with cwd."""
        ctx = AgenticContext(cwd="/tmp/work")
        assert ctx.cwd == "/tmp/work"
        assert ctx.allowed_dirs is None

    def test_create_context_with_allowed_dirs(self):
        """Should create context with allowed_dirs."""
        ctx = AgenticContext(cwd="/tmp/work", allowed_dirs=["/tmp/work", "/tmp/out"])
        assert ctx.allowed_dirs == ["/tmp/work", "/tmp/out"]


class TestRunShellCommand:
    """Test run_shell_command tool."""

    @pytest.fixture
    def mock_run_context(self):
        """Create mock RunContext."""
        ctx = MagicMock()
        ctx.deps = AgenticContext(cwd="/tmp/work")
        return ctx

    async def test_executes_command_with_cwd(self, mock_run_context, mocker):
        """Should execute command in context's cwd."""
        mock_executor = mocker.patch(
            "amelia.drivers.api.tools.SafeShellExecutor.execute",
            new_callable=AsyncMock,
            return_value="output",
        )

        result = await run_shell_command(mock_run_context, "ls -la", timeout=30)

        assert result == "output"
        mock_executor.assert_called_once_with(
            command="ls -la",
            timeout=30,
            cwd="/tmp/work",
        )


class TestWriteFile:
    """Test write_file tool."""

    @pytest.fixture
    def mock_run_context(self):
        """Create mock RunContext."""
        ctx = MagicMock()
        ctx.deps = AgenticContext(cwd="/tmp/work", allowed_dirs=["/tmp/work"])
        return ctx

    async def test_writes_file_with_allowed_dirs(self, mock_run_context, mocker):
        """Should write file using allowed_dirs from context."""
        mock_writer = mocker.patch(
            "amelia.drivers.api.tools.SafeFileWriter.write",
            new_callable=AsyncMock,
            return_value="File written successfully",
        )

        result = await write_file(mock_run_context, "/tmp/work/test.py", "print('hello')")

        assert result == "File written successfully"
        mock_writer.assert_called_once_with(
            file_path="/tmp/work/test.py",
            content="print('hello')",
            allowed_dirs=["/tmp/work"],
        )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api_tools.py -v`
Expected: FAIL - ModuleNotFoundError: No module named 'amelia.drivers.api.tools'

**Step 3: Create tools module**

```python
# amelia/drivers/api/tools.py
"""Tool definitions for pydantic-ai agentic execution."""
from dataclasses import dataclass
from typing import Any

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
        timeout: Maximum execution time in seconds. Defaults to 30.

    Returns:
        Command output (stdout) as a string.
    """
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
    allowed_dirs = ctx.deps.allowed_dirs or [ctx.deps.cwd]
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

## Task 7: Add Tool Support Validation

**Files:**
- Modify: `amelia/drivers/api/openai.py`
- Test: `tests/unit/test_api_driver_providers.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_api_driver_providers.py - add to existing file

class TestToolSupportValidation:
    """Test tool support validation."""

    def test_gpt4o_supports_tools(self):
        """GPT-4o should support tools."""
        driver = ApiDriver(model="openai:gpt-4o")
        assert driver._supports_tools() is True

    def test_claude_sonnet_supports_tools(self):
        """Claude 3.5 Sonnet via OpenRouter should support tools."""
        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")
        assert driver._supports_tools() is True

    def test_instruct_model_does_not_support_tools(self):
        """Instruct models should not support tools."""
        driver = ApiDriver(model="openai:gpt-3.5-turbo-instruct")
        assert driver._supports_tools() is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_api_driver_providers.py::TestToolSupportValidation -v`
Expected: FAIL - _supports_tools method doesn't exist

**Step 3: Add _supports_tools method**

```python
# amelia/drivers/api/openai.py - add after SUPPORTED_PROVIDERS constant

# Models known NOT to support tool calling
_NO_TOOL_MODELS = frozenset({
    "gpt-3.5-turbo-instruct",
    "text-davinci-003",
    "text-davinci-002",
    "davinci",
    "curie",
    "babbage",
    "ada",
})


# In ApiDriver class, add method:

def _supports_tools(self) -> bool:
    """Check if the current model supports tool calling.

    Returns:
        True if model supports tools, False otherwise.
    """
    # Extract model name without provider prefix
    model_suffix = self.model_name.split(":", 1)[1] if ":" in self.model_name else self.model_name

    # Most modern models support tools; reject known non-tool models
    return model_suffix not in _NO_TOOL_MODELS
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_api_driver_providers.py::TestToolSupportValidation -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/api/openai.py tests/unit/test_api_driver_providers.py
git commit -m "feat(api-driver): add tool support validation"
```

---

## Task 8: Implement execute_agentic Method

**Files:**
- Modify: `amelia/drivers/api/openai.py`
- Test: `tests/unit/test_api_driver_agentic.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_api_driver_agentic.py
"""Tests for ApiDriver agentic execution."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from amelia.core.state import AgentMessage
from amelia.drivers.api.openai import ApiDriver
from amelia.drivers.api.events import ApiStreamEvent


class TestExecuteAgentic:
    """Test execute_agentic method."""

    async def test_rejects_model_without_tool_support(self, monkeypatch):
        """Should raise ValueError for models without tool support."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        driver = ApiDriver(model="openai:gpt-3.5-turbo-instruct")

        with pytest.raises(ValueError, match="does not support tool calling"):
            async for _ in driver.execute_agentic(
                messages=[AgentMessage(role="user", content="test")],
                cwd="/tmp",
            ):
                pass

    async def test_yields_result_event(self, monkeypatch):
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
                cwd="/tmp",
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

from amelia.drivers.api.events import ApiStreamEvent
from amelia.drivers.api.tools import AgenticContext, run_shell_command, write_file
```

**Step 4: Add session management methods**

```python
# amelia/drivers/api/openai.py - add to ApiDriver class

# Class-level session storage
_session_histories: dict[str, list[Any]] = {}

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
    system_prompt: str | None = None,
) -> AsyncIterator[ApiStreamEvent]:
    """Execute prompt with autonomous tool access using pydantic-ai.

    Args:
        messages: List of conversation messages.
        cwd: Working directory for execution context.
        session_id: Optional session ID for continuity.
        system_prompt: System prompt for the agent.

    Yields:
        ApiStreamEvent objects as tools execute.

    Raises:
        ValueError: If API key not set or model doesn't support tools.
    """
    self._validate_api_key()

    if not self._supports_tools():
        raise ValueError(
            f"Model '{self.model_name}' does not support tool calling. "
            "Use a model with tool support for agentic execution."
        )

    # Create agent with tools
    agent = Agent(
        self.model_name,
        output_type=str,
        system_prompt=system_prompt or "",
        tools=[run_shell_command, write_file],
    )

    # Build context
    context = AgenticContext(cwd=cwd, allowed_dirs=[cwd])

    # Extract current prompt from last user message
    non_system = [m for m in messages if m.role != "system"]
    if not non_system or non_system[-1].role != "user":
        raise ValueError("Messages must end with a user message")
    current_prompt = non_system[-1].content

    # Build message history from prior messages
    history = self._build_message_history(messages)

    new_session_id = self._generate_session_id()

    try:
        async with agent.iter(
            current_prompt,
            deps=context,
            message_history=history,
        ) as agent_run:
            async for node in agent_run:
                # Check node type and yield appropriate events
                if hasattr(node, "tool_calls"):
                    # Tool call node
                    for tool_call in node.tool_calls:
                        yield ApiStreamEvent(
                            type="tool_use",
                            tool_name=tool_call.tool_name,
                            tool_input=dict(tool_call.args) if hasattr(tool_call.args, "items") else {"args": tool_call.args},
                        )

                if hasattr(node, "results"):
                    # Tool result node
                    for tool_result in node.results:
                        yield ApiStreamEvent(
                            type="tool_result",
                            tool_name=getattr(tool_result, "tool_name", "unknown"),
                            tool_result=str(tool_result.content) if hasattr(tool_result, "content") else str(tool_result),
                        )

            # Final result
            yield ApiStreamEvent(
                type="result",
                result_text=str(agent_run.result.output) if agent_run.result else "",
                session_id=new_session_id,
            )

    except Exception as e:
        logger.error(f"Agentic execution failed: {e}")
        yield ApiStreamEvent(type="error", content=str(e))

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
            system_prompt="You are a helpful assistant. Use tools to complete tasks.",
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

## Summary

After completing all tasks:
- `ApiDriver` accepts both `openai:*` and `openrouter:*` models
- `execute_agentic()` uses pydantic-ai with registered tools
- Tool support is validated before execution
- Session IDs are generated for continuity
- All tests pass, lint clean, types check

**Files created/modified:**
- `amelia/core/types.py` - Added `api:openrouter`
- `amelia/drivers/factory.py` - Updated factory
- `amelia/drivers/api/openai.py` - Major updates
- `amelia/drivers/api/events.py` - New
- `amelia/drivers/api/tools.py` - New
- `tests/unit/test_driver_types.py` - New
- `tests/unit/test_driver_factory.py` - New
- `tests/unit/test_api_driver_providers.py` - New
- `tests/unit/test_api_events.py` - New
- `tests/unit/test_api_tools.py` - New
- `tests/unit/test_api_driver_agentic.py` - New
- `tests/integration/test_openrouter_agentic.py` - New
