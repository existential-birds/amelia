# Claude CLI Driver Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance Amelia's Claude CLI driver with streaming support, session continuity, working directory control, and tool observability - inspired by remote-agentic-coding-system patterns while also adding model selection, system prompts, and permission management.

**Architecture:** Add streaming JSON output parsing via async generators, session persistence through state, and optional agentic mode driver. All changes are backward compatible with existing `generate()` API. New capabilities exposed via `generate_stream()` method. Driver constructor gains configuration for model, permissions, and timeouts.

**Tech Stack:** Python 3.12+, asyncio, Pydantic, pytest-asyncio, loguru

---

## Phase 1: Foundation - Streaming & Event Models

### Task 1: Add ClaudeStreamEvent Model

**Files:**
- Modify: `amelia/drivers/cli/claude.py:1-15`
- Test: `tests/unit/test_claude_driver.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_claude_driver.py - add at top after existing imports

from amelia.drivers.cli.claude import ClaudeStreamEvent, ClaudeStreamEventType


class TestClaudeStreamEvent:
    """Tests for ClaudeStreamEvent model."""

    def test_assistant_event(self):
        event = ClaudeStreamEvent(type="assistant", content="Hello world")
        assert event.type == "assistant"
        assert event.content == "Hello world"
        assert event.tool_name is None
        assert event.session_id is None

    def test_tool_use_event(self):
        event = ClaudeStreamEvent(
            type="tool_use",
            tool_name="Read",
            tool_input={"file_path": "/test.py"}
        )
        assert event.type == "tool_use"
        assert event.tool_name == "Read"
        assert event.tool_input == {"file_path": "/test.py"}

    def test_result_event_with_session(self):
        event = ClaudeStreamEvent(type="result", session_id="sess_abc123")
        assert event.type == "result"
        assert event.session_id == "sess_abc123"

    def test_error_event(self):
        event = ClaudeStreamEvent(type="error", content="Something went wrong")
        assert event.type == "error"
        assert event.content == "Something went wrong"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeStreamEvent -v`
Expected: FAIL with "cannot import name 'ClaudeStreamEvent'"

**Step 3: Write minimal implementation**

```python
# amelia/drivers/cli/claude.py - add after existing imports, before ClaudeCliDriver class

from typing import Any, Literal

ClaudeStreamEventType = Literal["assistant", "tool_use", "result", "error", "system"]


class ClaudeStreamEvent(BaseModel):
    """Event from Claude CLI stream-json output.

    Attributes:
        type: Event type (assistant, tool_use, result, error, system).
        content: Text content for assistant/error/system events.
        tool_name: Tool name for tool_use events.
        tool_input: Tool input parameters for tool_use events.
        session_id: Session ID from result events for session continuity.
    """
    type: ClaudeStreamEventType
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    session_id: str | None = None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeStreamEvent -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add amelia/drivers/cli/claude.py tests/unit/test_claude_driver.py
git commit -m "feat(drivers): add ClaudeStreamEvent model for stream parsing"
```

---

### Task 2: Add Stream Event Parsing Utility

**Files:**
- Modify: `amelia/drivers/cli/claude.py`
- Test: `tests/unit/test_claude_driver.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_claude_driver.py - add to TestClaudeStreamEvent class

def test_parse_assistant_message(self):
    """Test parsing assistant message from stream-json."""
    raw = '{"type":"assistant","message":{"content":[{"type":"text","text":"Hello"}]}}'
    event = ClaudeStreamEvent.from_stream_json(raw)
    assert event.type == "assistant"
    assert event.content == "Hello"

def test_parse_tool_use(self):
    """Test parsing tool_use from stream-json."""
    raw = '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"/x.py"}}]}}'
    event = ClaudeStreamEvent.from_stream_json(raw)
    assert event.type == "tool_use"
    assert event.tool_name == "Read"
    assert event.tool_input == {"file_path": "/x.py"}

def test_parse_result_with_session(self):
    """Test parsing result event with session_id."""
    raw = '{"type":"result","session_id":"sess_123","subtype":"success"}'
    event = ClaudeStreamEvent.from_stream_json(raw)
    assert event.type == "result"
    assert event.session_id == "sess_123"

def test_parse_malformed_json_returns_error(self):
    """Test that malformed JSON returns error event."""
    raw = 'not valid json'
    event = ClaudeStreamEvent.from_stream_json(raw)
    assert event.type == "error"
    assert "parse" in event.content.lower()

def test_parse_empty_line_returns_none(self):
    """Test that empty lines return None."""
    event = ClaudeStreamEvent.from_stream_json("")
    assert event is None
    event = ClaudeStreamEvent.from_stream_json("   ")
    assert event is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeStreamEvent::test_parse_assistant_message -v`
Expected: FAIL with "ClaudeStreamEvent has no attribute 'from_stream_json'"

**Step 3: Write minimal implementation**

```python
# amelia/drivers/cli/claude.py - add class method to ClaudeStreamEvent

class ClaudeStreamEvent(BaseModel):
    """Event from Claude CLI stream-json output.

    Attributes:
        type: Event type (assistant, tool_use, result, error, system).
        content: Text content for assistant/error/system events.
        tool_name: Tool name for tool_use events.
        tool_input: Tool input parameters for tool_use events.
        session_id: Session ID from result events for session continuity.
    """
    type: ClaudeStreamEventType
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    session_id: str | None = None

    @classmethod
    def from_stream_json(cls, line: str) -> "ClaudeStreamEvent | None":
        """Parse a line from Claude CLI stream-json output.

        Args:
            line: Raw JSON line from stream output.

        Returns:
            Parsed event or None for empty lines, error event for malformed JSON.
        """
        stripped = line.strip()
        if not stripped:
            return None

        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as e:
            return cls(type="error", content=f"Failed to parse stream JSON: {e}")

        msg_type = data.get("type", "")

        # Handle result events (contain session_id)
        if msg_type == "result":
            return cls(
                type="result",
                session_id=data.get("session_id")
            )

        # Handle assistant messages (contain content blocks)
        if msg_type == "assistant":
            message = data.get("message", {})
            content_blocks = message.get("content", [])

            for block in content_blocks:
                block_type = block.get("type", "")

                if block_type == "text":
                    return cls(type="assistant", content=block.get("text", ""))

                if block_type == "tool_use":
                    return cls(
                        type="tool_use",
                        tool_name=block.get("name"),
                        tool_input=block.get("input")
                    )

        # Handle system messages
        if msg_type == "system":
            return cls(type="system", content=data.get("message", ""))

        # Unknown type - return as system event
        return cls(type="system", content=f"Unknown event type: {msg_type}")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeStreamEvent -v`
Expected: PASS (9 tests)

**Step 5: Commit**

```bash
git add amelia/drivers/cli/claude.py tests/unit/test_claude_driver.py
git commit -m "feat(drivers): add stream-json parsing to ClaudeStreamEvent"
```

---

### Task 3: Add session_id to ExecutionState

**Files:**
- Modify: `amelia/core/state.py:160-181`
- Test: `tests/unit/test_state_models.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_state_models.py - add new test class

class TestExecutionStateSession:
    """Tests for session_id in ExecutionState."""

    def test_execution_state_has_session_id(self, mock_profile_factory, mock_issue_factory):
        state = ExecutionState(
            profile=mock_profile_factory(),
            issue=mock_issue_factory(),
            claude_session_id="sess_abc123"
        )
        assert state.claude_session_id == "sess_abc123"

    def test_execution_state_session_id_defaults_none(self, mock_profile_factory, mock_issue_factory):
        state = ExecutionState(
            profile=mock_profile_factory(),
            issue=mock_issue_factory()
        )
        assert state.claude_session_id is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_state_models.py::TestExecutionStateSession -v`
Expected: FAIL with "unexpected keyword argument 'claude_session_id'"

**Step 3: Write minimal implementation**

```python
# amelia/core/state.py - add field to ExecutionState class (after code_changes_for_review)

    claude_session_id: str | None = None
```

Update the docstring to include:
```
        claude_session_id: Session ID for Claude CLI session continuity.
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_state_models.py::TestExecutionStateSession -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add amelia/core/state.py tests/unit/test_state_models.py
git commit -m "feat(state): add claude_session_id to ExecutionState for session continuity"
```

---

## Phase 2: Driver Configuration Enhancements

### Task 4: Add Model Selection Support

**Files:**
- Modify: `amelia/drivers/cli/claude.py` (constructor and `_generate_impl`)
- Test: `tests/unit/test_claude_driver.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_claude_driver.py - add new test class

class TestClaudeCliDriverModelSelection:

    def test_default_model_is_sonnet(self):
        driver = ClaudeCliDriver()
        assert driver.model == "sonnet"

    def test_custom_model_parameter(self):
        driver = ClaudeCliDriver(model="opus")
        assert driver.model == "opus"

    @pytest.mark.asyncio
    async def test_model_flag_in_command(self, messages, mock_subprocess_process_factory):
        driver = ClaudeCliDriver(model="opus")
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[b"response", b""],
            return_code=0
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            await driver._generate_impl(messages)

            args = mock_exec.call_args[0]
            assert "--model" in args
            model_idx = args.index("--model")
            assert args[model_idx + 1] == "opus"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeCliDriverModelSelection -v`
Expected: FAIL with `AttributeError: 'ClaudeCliDriver' object has no attribute 'model'`

**Step 3: Write minimal implementation**

```python
# amelia/drivers/cli/claude.py - modify constructor

class ClaudeCliDriver(CliDriver):
    """Claude CLI Driver interacts with the Claude model via the local 'claude' CLI tool.

    Attributes:
        model: Claude model to use (sonnet, opus, haiku).
    """

    def __init__(
        self,
        model: str = "sonnet",
        timeout: int = 30,
        max_retries: int = 0,
    ):
        """Initialize the Claude CLI driver.

        Args:
            model: Claude model to use. Defaults to "sonnet".
            timeout: Maximum execution time in seconds. Defaults to 30.
            max_retries: Number of retry attempts. Defaults to 0.
        """
        super().__init__(timeout, max_retries)
        self.model = model
```

In `_generate_impl`, change:
```python
cmd_args = ["claude", "-p"]
```
to:
```python
cmd_args = ["claude", "-p", "--model", self.model]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeCliDriverModelSelection -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/cli/claude.py tests/unit/test_claude_driver.py
git commit -m "feat(cli-driver): add model selection support"
```

---

### Task 5: Add System Prompt Handling

**Files:**
- Modify: `amelia/drivers/cli/claude.py`
- Test: `tests/unit/test_claude_driver.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_claude_driver.py - add new test class

class TestClaudeCliDriverSystemPrompt:

    @pytest.fixture
    def messages_with_system(self):
        return [
            AgentMessage(role="system", content="You are a helpful assistant."),
            AgentMessage(role="user", content="Hello"),
            AgentMessage(role="assistant", content="Hi there"),
            AgentMessage(role="user", content="How are you?")
        ]

    def test_convert_messages_excludes_system(self, driver, messages_with_system):
        """System messages should not appear in the user prompt."""
        prompt = driver._convert_messages_to_prompt(messages_with_system)
        assert "SYSTEM:" not in prompt
        assert "You are a helpful assistant" not in prompt
        assert "USER: Hello" in prompt

    @pytest.mark.asyncio
    async def test_system_prompt_passed_via_flag(self, messages_with_system, mock_subprocess_process_factory):
        driver = ClaudeCliDriver()
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[b"response", b""],
            return_code=0
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            await driver._generate_impl(messages_with_system)

            args = mock_exec.call_args[0]
            assert "--append-system-prompt" in args
            sys_idx = args.index("--append-system-prompt")
            assert args[sys_idx + 1] == "You are a helpful assistant."

    @pytest.mark.asyncio
    async def test_no_system_prompt_flag_when_no_system_messages(self, messages, mock_subprocess_process_factory):
        driver = ClaudeCliDriver()
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[b"response", b""],
            return_code=0
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            await driver._generate_impl(messages)

            args = mock_exec.call_args[0]
            assert "--append-system-prompt" not in args
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeCliDriverSystemPrompt -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Modify `_convert_messages_to_prompt` to filter system messages:
```python
def _convert_messages_to_prompt(self, messages: list[AgentMessage]) -> str:
    """Converts a list of AgentMessages into a single string prompt.

    System messages are excluded as they are handled separately via CLI flags.
    """
    prompt_parts = []
    for msg in messages:
        if msg.role == "system":
            continue  # System messages handled separately
        role_str = msg.role.upper() if msg.role else "USER"
        content = msg.content or ""
        prompt_parts.append(f"{role_str}: {content}")

    return "\n\n".join(prompt_parts)
```

Modify `_generate_impl` to extract and pass system prompts:
```python
async def _generate_impl(self, messages: list[AgentMessage], schema: type[BaseModel] | None = None) -> Any:
    # Extract system messages
    system_messages = [m for m in messages if m.role == "system"]

    full_prompt = self._convert_messages_to_prompt(messages)

    cmd_args = ["claude", "-p", "--model", self.model]

    # Add system prompt if present
    if system_messages:
        system_prompt = "\n\n".join(m.content for m in system_messages)
        cmd_args.extend(["--append-system-prompt", system_prompt])

    # ... rest unchanged
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeCliDriverSystemPrompt -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/cli/claude.py tests/unit/test_claude_driver.py
git commit -m "feat(cli-driver): add system prompt handling via --append-system-prompt"
```

---

### Task 6: Add Permission Management

**Files:**
- Modify: `amelia/drivers/cli/claude.py`
- Test: `tests/unit/test_claude_driver.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_claude_driver.py - add new test class

class TestClaudeCliDriverPermissions:

    def test_skip_permissions_default_false(self):
        driver = ClaudeCliDriver()
        assert driver.skip_permissions is False

    def test_skip_permissions_configurable(self):
        driver = ClaudeCliDriver(skip_permissions=True)
        assert driver.skip_permissions is True

    def test_allowed_tools_default_none(self):
        driver = ClaudeCliDriver()
        assert driver.allowed_tools is None

    @pytest.mark.asyncio
    async def test_skip_permissions_flag_added(self, messages, mock_subprocess_process_factory):
        driver = ClaudeCliDriver(skip_permissions=True)
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[b"response", b""],
            return_code=0
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            await driver._generate_impl(messages)

            args = mock_exec.call_args[0]
            assert "--dangerously-skip-permissions" in args

    @pytest.mark.asyncio
    async def test_allowed_tools_flag_added(self, messages, mock_subprocess_process_factory):
        driver = ClaudeCliDriver(allowed_tools=["Read", "Write", "Bash"])
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[b"response", b""],
            return_code=0
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            await driver._generate_impl(messages)

            args = mock_exec.call_args[0]
            assert "--allowedTools" in args
            idx = args.index("--allowedTools")
            assert args[idx + 1] == "Read,Write,Bash"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeCliDriverPermissions -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Update constructor:
```python
def __init__(
    self,
    model: str = "sonnet",
    timeout: int = 30,
    max_retries: int = 0,
    skip_permissions: bool = False,
    allowed_tools: list[str] | None = None,
    disallowed_tools: list[str] | None = None,
):
    super().__init__(timeout, max_retries)
    self.model = model
    self.skip_permissions = skip_permissions
    self.allowed_tools = allowed_tools
    self.disallowed_tools = disallowed_tools
```

Add permission flags in `_generate_impl`:
```python
cmd_args = ["claude", "-p", "--model", self.model]

# Add permission flags
if self.skip_permissions:
    cmd_args.append("--dangerously-skip-permissions")
if self.allowed_tools:
    cmd_args.extend(["--allowedTools", ",".join(self.allowed_tools)])
if self.disallowed_tools:
    cmd_args.extend(["--disallowedTools", ",".join(self.disallowed_tools)])
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeCliDriverPermissions -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/cli/claude.py tests/unit/test_claude_driver.py
git commit -m "feat(cli-driver): add permission management (skip_permissions, allowed/disallowed tools)"
```

---

## Phase 3: Streaming & Session Continuity

### Task 7: Add generate_stream() Method

**Files:**
- Modify: `amelia/drivers/cli/claude.py`
- Test: `tests/unit/test_claude_driver.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_claude_driver.py - add new test class

class TestClaudeCliDriverStreaming:
    """Tests for streaming generate method."""

    @pytest.fixture
    def stream_lines(self):
        """Fixture providing mock stream-json output lines."""
        return [
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"Hello"}]}}\n',
            b'{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"/x.py"}}]}}\n',
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"Done!"}]}}\n',
            b'{"type":"result","session_id":"sess_xyz789","subtype":"success"}\n',
            b''  # EOF
        ]

    @pytest.mark.asyncio
    async def test_generate_stream_yields_events(self, driver, messages, stream_lines):
        """Test that generate_stream yields ClaudeStreamEvent objects."""
        mock_process = AsyncMock()
        mock_process.stdin = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=stream_lines)
        mock_process.stderr.read = AsyncMock(return_value=b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            events = []
            async for event in driver.generate_stream(messages):
                events.append(event)

            assert len(events) == 4
            assert events[0].type == "assistant"
            assert events[0].content == "Hello"
            assert events[1].type == "tool_use"
            assert events[1].tool_name == "Read"
            assert events[2].type == "assistant"
            assert events[2].content == "Done!"
            assert events[3].type == "result"
            assert events[3].session_id == "sess_xyz789"

    @pytest.mark.asyncio
    async def test_generate_stream_captures_session_id(self, driver, messages, stream_lines):
        """Test that generate_stream captures session_id from result event."""
        mock_process = AsyncMock()
        mock_process.stdin = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=stream_lines)
        mock_process.stderr.read = AsyncMock(return_value=b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            session_id = None
            async for event in driver.generate_stream(messages):
                if event.type == "result" and event.session_id:
                    session_id = event.session_id

            assert session_id == "sess_xyz789"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeCliDriverStreaming -v`
Expected: FAIL with "'ClaudeCliDriver' object has no attribute 'generate_stream'"

**Step 3: Write minimal implementation**

```python
# amelia/drivers/cli/claude.py - add imports and method

from collections.abc import AsyncIterator

class ClaudeCliDriver(CliDriver):
    # ... existing code ...

    async def generate_stream(
        self,
        messages: list[AgentMessage],
        session_id: str | None = None,
        cwd: str | None = None
    ) -> AsyncIterator[ClaudeStreamEvent]:
        """Generate a streaming response from Claude CLI.

        Args:
            messages: History of conversation messages.
            session_id: Optional session ID to resume a previous conversation.
            cwd: Optional working directory for Claude CLI context.

        Yields:
            ClaudeStreamEvent objects as they are parsed from the stream.
        """
        # Extract system messages
        system_messages = [m for m in messages if m.role == "system"]
        full_prompt = self._convert_messages_to_prompt(messages)

        cmd_args = ["claude", "-p", "--model", self.model, "--output-format", "stream-json"]

        # Add permission flags
        if self.skip_permissions:
            cmd_args.append("--dangerously-skip-permissions")
        if self.allowed_tools:
            cmd_args.extend(["--allowedTools", ",".join(self.allowed_tools)])
        if self.disallowed_tools:
            cmd_args.extend(["--disallowedTools", ",".join(self.disallowed_tools)])

        # Add system prompt if present
        if system_messages:
            system_prompt = "\n\n".join(m.content for m in system_messages)
            cmd_args.extend(["--append-system-prompt", system_prompt])

        if session_id:
            cmd_args.extend(["--resume", session_id])
            logger.info(f"Resuming Claude session: {session_id}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )

            if process.stdin:
                process.stdin.write(full_prompt.encode())
                await process.stdin.drain()
                process.stdin.close()

            # Stream stdout line by line
            if process.stdout:
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break

                    event = ClaudeStreamEvent.from_stream_json(line.decode())
                    if event:
                        yield event

            await process.wait()

            if process.returncode != 0:
                stderr_data = await process.stderr.read() if process.stderr else b""
                logger.error(f"Claude CLI failed: {stderr_data.decode()}")

        except Exception as e:
            logger.error(f"Error in Claude CLI streaming: {e}")
            yield ClaudeStreamEvent(type="error", content=str(e))
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeCliDriverStreaming -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add amelia/drivers/cli/claude.py tests/unit/test_claude_driver.py
git commit -m "feat(drivers): add generate_stream() method for streaming Claude responses"
```

---

### Task 8: Add --resume and cwd Support to generate()

**Files:**
- Modify: `amelia/drivers/cli/claude.py`
- Test: `tests/unit/test_claude_driver.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_claude_driver.py - add to TestClaudeCliDriver class

@pytest.mark.asyncio
async def test_generate_with_session_resume(self, driver, messages, mock_subprocess_process_factory):
    """Test that generate passes --resume when session_id provided."""
    mock_process = mock_subprocess_process_factory(
        stdout_lines=[b"Resumed response", b""],
        return_code=0
    )

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
        response = await driver._generate_impl(messages, session_id="sess_resume123")

        assert response == "Resumed response"
        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert "--resume" in args
        assert "sess_resume123" in args

@pytest.mark.asyncio
async def test_generate_with_working_directory(self, driver, messages, mock_subprocess_process_factory):
    """Test that generate passes cwd to subprocess."""
    mock_process = mock_subprocess_process_factory(
        stdout_lines=[b"Response from cwd", b""],
        return_code=0
    )

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
        response = await driver._generate_impl(messages, cwd="/workspace/project")

        assert response == "Response from cwd"
        kwargs = mock_exec.call_args[1]
        assert kwargs.get("cwd") == "/workspace/project"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeCliDriver::test_generate_with_session_resume -v`
Expected: FAIL with "got an unexpected keyword argument 'session_id'"

**Step 3: Write minimal implementation**

Update `_generate_impl` signature and add --resume/cwd handling:

```python
async def _generate_impl(
    self,
    messages: list[AgentMessage],
    schema: type[BaseModel] | None = None,
    session_id: str | None = None,
    cwd: str | None = None
) -> Any:
    """Generates a response using the 'claude' CLI.

    Args:
        messages: Conversation history.
        schema: Optional Pydantic model for structured output.
        session_id: Optional session ID to resume a previous conversation.
        cwd: Optional working directory for Claude CLI context.

    Returns:
        Either a string (if no schema) or an instance of the schema.
    """
    # ... existing setup code ...

    # Add resume support
    if session_id:
        cmd_args.extend(["--resume", session_id])
        logger.info(f"Resuming Claude session: {session_id}")

    # ... rest of method, update subprocess call:
    process = await asyncio.create_subprocess_exec(
        *cmd_args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd  # Add cwd parameter
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_claude_driver.py::TestClaudeCliDriver::test_generate_with_session_resume tests/unit/test_claude_driver.py::TestClaudeCliDriver::test_generate_with_working_directory -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/drivers/cli/claude.py tests/unit/test_claude_driver.py
git commit -m "feat(drivers): add --resume and cwd support to Claude CLI driver"
```

---

## Phase 4: Agentic Driver Mode

### Task 9: Create ClaudeAgenticCliDriver Class

**Files:**
- Create: `amelia/drivers/cli/agentic.py`
- Test: `tests/unit/test_claude_agentic_driver.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_claude_agentic_driver.py - create new file

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from amelia.drivers.cli.agentic import ClaudeAgenticCliDriver
from amelia.drivers.cli.claude import ClaudeStreamEvent


class TestClaudeAgenticCliDriver:
    """Tests for ClaudeAgenticCliDriver."""

    @pytest.fixture
    def agentic_driver(self):
        return ClaudeAgenticCliDriver()

    @pytest.fixture
    def agentic_stream_lines(self):
        """Stream output including tool execution."""
        return [
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"Let me read the file"}]}}\n',
            b'{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"/test.py"}}]}}\n',
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"The file contains..."}]}}\n',
            b'{"type":"result","session_id":"agentic_sess_001","subtype":"success"}\n',
            b''
        ]

    @pytest.mark.asyncio
    async def test_execute_agentic_uses_skip_permissions(self, agentic_driver, agentic_stream_lines):
        """Test that execute_agentic uses --dangerously-skip-permissions."""
        mock_process = AsyncMock()
        mock_process.stdin = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=agentic_stream_lines)
        mock_process.stderr.read = AsyncMock(return_value=b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            events = []
            async for event in agentic_driver.execute_agentic(
                prompt="Read the test file",
                cwd="/workspace"
            ):
                events.append(event)

            args = mock_exec.call_args[0]
            assert "--dangerously-skip-permissions" in args

    @pytest.mark.asyncio
    async def test_execute_agentic_tracks_tool_calls(self, agentic_driver, agentic_stream_lines):
        """Test that tool calls are tracked in history."""
        mock_process = AsyncMock()
        mock_process.stdin = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=agentic_stream_lines)
        mock_process.stderr.read = AsyncMock(return_value=b"")
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            async for _ in agentic_driver.execute_agentic(
                prompt="Read the test file",
                cwd="/workspace"
            ):
                pass

            assert len(agentic_driver.tool_call_history) == 1
            assert agentic_driver.tool_call_history[0].tool_name == "Read"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_claude_agentic_driver.py -v`
Expected: FAIL with "No module named 'amelia.drivers.cli.agentic'"

**Step 3: Write minimal implementation**

```python
# amelia/drivers/cli/agentic.py - create new file

"""Claude Agentic CLI Driver for autonomous code execution."""

import asyncio
from collections.abc import AsyncIterator

from loguru import logger

from amelia.drivers.cli.base import CliDriver
from amelia.drivers.cli.claude import ClaudeStreamEvent


class ClaudeAgenticCliDriver(CliDriver):
    """Claude CLI Driver for fully autonomous agentic execution.

    Uses --dangerously-skip-permissions for YOLO mode where Claude
    executes tools autonomously. Tracks tool calls for observability.

    Attributes:
        tool_call_history: List of tool call events for audit logging.
        model: Claude model to use.
    """

    def __init__(
        self,
        model: str = "sonnet",
        timeout: int = 300,
        max_retries: int = 0
    ):
        """Initialize the agentic driver.

        Args:
            model: Claude model to use. Defaults to "sonnet".
            timeout: Maximum execution time in seconds. Defaults to 300 (5 min).
            max_retries: Number of retry attempts. Defaults to 0.
        """
        super().__init__(timeout=timeout, max_retries=max_retries)
        self.model = model
        self.tool_call_history: list[ClaudeStreamEvent] = []

    async def execute_agentic(
        self,
        prompt: str,
        cwd: str,
        session_id: str | None = None
    ) -> AsyncIterator[ClaudeStreamEvent]:
        """Execute a prompt with full Claude Code tool access.

        Args:
            prompt: The task or instruction for Claude.
            cwd: Working directory for Claude Code context.
            session_id: Optional session ID to resume.

        Yields:
            ClaudeStreamEvent objects including tool executions.
        """
        cmd_args = [
            "claude", "-p",
            "--model", self.model,
            "--output-format", "stream-json",
            "--dangerously-skip-permissions"  # YOLO mode
        ]

        if session_id:
            cmd_args.extend(["--resume", session_id])
            logger.info(f"Resuming agentic session: {session_id}")

        logger.info(f"Starting agentic execution in {cwd}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )

            if process.stdin:
                process.stdin.write(prompt.encode())
                await process.stdin.drain()
                process.stdin.close()

            if process.stdout:
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break

                    event = ClaudeStreamEvent.from_stream_json(line.decode())
                    if event:
                        # Track tool calls for observability
                        if event.type == "tool_use":
                            self.tool_call_history.append(event)
                            logger.info(f"Tool call: {event.tool_name}")

                        yield event

            await process.wait()

            if process.returncode != 0:
                stderr_data = await process.stderr.read() if process.stderr else b""
                logger.error(f"Agentic execution failed: {stderr_data.decode()}")

        except Exception as e:
            logger.error(f"Error in agentic execution: {e}")
            yield ClaudeStreamEvent(type="error", content=str(e))

    def clear_tool_history(self) -> None:
        """Clear the tool call history."""
        self.tool_call_history = []
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_claude_agentic_driver.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add amelia/drivers/cli/agentic.py tests/unit/test_claude_agentic_driver.py
git commit -m "feat(drivers): add ClaudeAgenticCliDriver for autonomous execution"
```

---

### Task 10: Register Agentic Driver in Factory

**Files:**
- Modify: `amelia/core/types.py`
- Modify: `amelia/drivers/factory.py`
- Test: `tests/unit/test_driver_factory.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_driver_factory.py - create or add to file

import pytest
from amelia.drivers.factory import DriverFactory
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.drivers.cli.agentic import ClaudeAgenticCliDriver
from amelia.drivers.api.openai import ApiDriver


class TestDriverFactory:
    """Tests for DriverFactory."""

    def test_get_cli_claude_driver(self):
        driver = DriverFactory.get_driver("cli:claude")
        assert isinstance(driver, ClaudeCliDriver)

    def test_get_cli_claude_agentic_driver(self):
        driver = DriverFactory.get_driver("cli:claude:agentic")
        assert isinstance(driver, ClaudeAgenticCliDriver)

    def test_get_api_openai_driver(self):
        driver = DriverFactory.get_driver("api:openai")
        assert isinstance(driver, ApiDriver)

    def test_unknown_driver_raises(self):
        with pytest.raises(ValueError, match="Unknown driver key"):
            DriverFactory.get_driver("invalid:driver")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_driver_factory.py::TestDriverFactory::test_get_cli_claude_agentic_driver -v`
Expected: FAIL with "Unknown driver key: cli:claude:agentic"

**Step 3: Write minimal implementation**

Update `amelia/core/types.py`:
```python
DriverType = Literal["cli:claude", "cli:claude:agentic", "api:openai", "cli", "api"]
```

Update `amelia/drivers/factory.py`:
```python
from typing import Any

from amelia.drivers.api.openai import ApiDriver
from amelia.drivers.base import DriverInterface
from amelia.drivers.cli.agentic import ClaudeAgenticCliDriver
from amelia.drivers.cli.claude import ClaudeCliDriver


class DriverFactory:
    """Factory class for creating driver instances based on configuration keys."""

    @staticmethod
    def get_driver(driver_key: str, **kwargs: Any) -> DriverInterface:
        """Factory method to get a concrete driver implementation.

        Args:
            driver_key: Driver identifier (e.g., "cli:claude", "api:openai").
            **kwargs: Driver-specific configuration passed to constructor.

        Returns:
            Configured driver instance.

        Raises:
            ValueError: If driver_key is not recognized.
        """
        if driver_key == "cli:claude" or driver_key == "cli":
            return ClaudeCliDriver(**kwargs)
        elif driver_key == "cli:claude:agentic":
            return ClaudeAgenticCliDriver(**kwargs)
        elif driver_key == "api:openai" or driver_key == "api":
            return ApiDriver(**kwargs)
        else:
            raise ValueError(f"Unknown driver key: {driver_key}")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_driver_factory.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add amelia/core/types.py amelia/drivers/factory.py tests/unit/test_driver_factory.py
git commit -m "feat(drivers): register cli:claude:agentic driver in factory"
```

---

## Phase 5: Final Verification

### Task 11: Run Full Verification and Lint

**Files:** None (verification only)

**Step 1: Run type checker**

Run: `uv run mypy amelia/drivers/ amelia/core/state.py amelia/core/types.py`
Expected: No errors

**Step 2: Run linter**

Run: `uv run ruff check amelia tests/unit/test_claude_driver.py tests/unit/test_claude_agentic_driver.py tests/unit/test_driver_factory.py tests/unit/test_state_models.py`
Expected: No errors (or fix any)

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests PASS

**Step 4: Final commit if fixes needed**

```bash
git add -A
git commit -m "chore: fix lint/type issues from claude driver improvements"
```

---

## Summary

| Phase | Task | Description | Key Changes |
|-------|------|-------------|-------------|
| 1 | 1 | ClaudeStreamEvent model | New model for stream parsing |
| 1 | 2 | Stream parsing utility | `from_stream_json()` class method |
| 1 | 3 | session_id in state | `claude_session_id` field in ExecutionState |
| 2 | 4 | Model selection | `model` param, `--model` flag |
| 2 | 5 | System prompt handling | `--append-system-prompt` flag |
| 2 | 6 | Permission management | `skip_permissions`, `allowed_tools`, `disallowed_tools` |
| 3 | 7 | generate_stream() | Async generator for streaming |
| 3 | 8 | --resume and cwd | Session continuity and working directory |
| 4 | 9 | ClaudeAgenticCliDriver | YOLO mode autonomous execution |
| 4 | 10 | Factory registration | `cli:claude:agentic` driver key |
| 5 | 11 | Verification | mypy, ruff, pytest |

**Total tasks:** 11 (each with 5 steps following TDD)

**Dependencies:**
- Tasks 1-2 are foundation for Tasks 7-9
- Task 3 supports session continuity in Tasks 7-8
- Tasks 4-6 enhance driver configuration
- Task 9 depends on Tasks 1-2
- Task 10 depends on Task 9
- Task 11 is always last
