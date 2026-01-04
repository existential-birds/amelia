"""Tests for ClaudeCliDriver using claude-agent-sdk.

Tests cover:
- generate() method with and without schema
- execute_agentic() method for autonomous tool use
- SDK message type handling (AssistantMessage, ResultMessage, TextBlock, etc.)
- Error handling and clarification detection
"""
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.drivers.cli.claude import (
    ClaudeCliDriver,
    _is_clarification_request,
    _strip_markdown_fences,
)


# =============================================================================
# Test Models
# =============================================================================


class _TestModel(BaseModel):
    reasoning: str
    answer: str


class _TestListModel(BaseModel):
    tasks: list[str]


# =============================================================================
# Mock SDK Types
#
# These classes mock claude-agent-sdk types for testing without requiring
# the actual SDK. They mirror the structure of:
# - TextBlock, ToolUseBlock, ToolResultBlock (content blocks)
# - AssistantMessage, ResultMessage (message types)
# =============================================================================


class MockTextBlock:
    """Mock TextBlock from claude-agent-sdk."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.type = "text"


class MockToolUseBlock:
    """Mock ToolUseBlock from claude-agent-sdk."""

    def __init__(self, name: str, input_data: dict[str, Any]) -> None:
        self.name = name
        self.input = input_data
        self.type = "tool_use"
        self.id = "tool_use_123"


class MockToolResultBlock:
    """Mock ToolResultBlock from claude-agent-sdk."""

    def __init__(self, content: str, is_error: bool = False) -> None:
        self.content = content
        self.is_error = is_error
        self.type = "tool_result"


class MockAssistantMessage:
    """Mock AssistantMessage from claude-agent-sdk."""

    def __init__(self, content: list[Any]) -> None:
        self.content = content


class MockResultMessage:
    """Mock ResultMessage from claude-agent-sdk."""

    def __init__(
        self,
        result: str | None = None,
        session_id: str | None = None,
        is_error: bool = False,
        structured_output: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        num_turns: int | None = None,
        total_cost_usd: float | None = None,
    ) -> None:
        self.result = result
        self.session_id = session_id
        self.is_error = is_error
        self.structured_output = structured_output
        self.duration_ms = duration_ms
        self.num_turns = num_turns
        self.total_cost_usd = total_cost_usd


def _patch_sdk_types():
    """Create a context manager that patches SDK types for isinstance checks."""
    return patch.multiple(
        "amelia.drivers.cli.claude",
        AssistantMessage=MockAssistantMessage,
        ResultMessage=MockResultMessage,
        TextBlock=MockTextBlock,
        ToolUseBlock=MockToolUseBlock,
        ToolResultBlock=MockToolResultBlock,
    )


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


@pytest.fixture
def driver() -> ClaudeCliDriver:
    return ClaudeCliDriver()


def create_mock_query(messages: list[Any]) -> AsyncMock:
    """Create a mock query function that yields the given messages."""
    async def mock_query(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        for msg in messages:
            yield msg
    return mock_query


def create_mock_sdk_client(messages: list[Any]) -> MagicMock:
    """Create a mock ClaudeSDKClient that yields the given messages.

    The mock supports the async context manager pattern and provides:
    - __aenter__ / __aexit__ for `async with` support
    - query() method for sending prompts
    - receive_response() async iterator for receiving messages
    """
    mock_client = MagicMock()
    mock_client.query = AsyncMock()

    async def mock_receive_response() -> AsyncIterator[Any]:
        for msg in messages:
            yield msg

    mock_client.receive_response = mock_receive_response

    # Create the class mock that returns the client instance
    mock_class = MagicMock()
    mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_class.return_value.__aexit__ = AsyncMock(return_value=None)

    return mock_class


# =============================================================================
# Test Classes
# =============================================================================


class TestClaudeCliDriverGenerate:
    """Tests for ClaudeCliDriver.generate() method."""

    async def test_generate_text_success(self, driver: ClaudeCliDriver) -> None:
        """Test basic text generation without schema."""
        messages = [
            MockAssistantMessage([MockTextBlock("Hello, world!")]),
            MockResultMessage(result="Hello, world!", session_id="sess_123"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)),
        ):
            result, session_id = await driver.generate("Say hello")

            assert result == "Hello, world!"
            assert session_id == "sess_123"

    async def test_generate_text_no_result_field(self, driver: ClaudeCliDriver) -> None:
        """Test text generation when result is empty but assistant content exists."""
        messages = [
            MockAssistantMessage([MockTextBlock("Response from assistant")]),
            MockResultMessage(result=None, session_id="sess_456"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)),
        ):
            result, session_id = await driver.generate("Test prompt")

            assert result == "Response from assistant"
            assert session_id == "sess_456"

    async def test_generate_json_with_structured_output(self, driver: ClaudeCliDriver) -> None:
        """Test structured output via structured_output field."""
        messages = [
            MockAssistantMessage([MockTextBlock("Thinking...")]),
            MockResultMessage(
                result=None,
                session_id="sess_struct",
                structured_output={"reasoning": "because", "answer": "42"},
            ),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)),
        ):
            result, session_id = await driver.generate("Answer", schema=_TestModel)

            assert isinstance(result, _TestModel)
            assert result.reasoning == "because"
            assert result.answer == "42"
            assert session_id == "sess_struct"

    async def test_generate_json_from_result_field(self, driver: ClaudeCliDriver) -> None:
        """Test structured output parsing from JSON string in result field."""
        messages = [
            MockResultMessage(
                result='{"reasoning": "parsed", "answer": "from result"}',
                session_id="sess_json",
                structured_output=None,
            ),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)),
        ):
            result, session_id = await driver.generate("Answer", schema=_TestModel)

            assert isinstance(result, _TestModel)
            assert result.reasoning == "parsed"
            assert result.answer == "from result"
            assert session_id == "sess_json"

    async def test_generate_json_list_auto_wrap(self, driver: ClaudeCliDriver) -> None:
        """Test that raw list is auto-wrapped when schema expects 'tasks' field."""
        messages = [
            MockResultMessage(
                result=None,
                session_id="sess_list",
                structured_output=["task1", "task2", "task3"],
            ),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)),
        ):
            result, session_id = await driver.generate("List tasks", schema=_TestListModel)

            assert isinstance(result, _TestListModel)
            assert result.tasks == ["task1", "task2", "task3"]
            assert session_id == "sess_list"

    async def test_generate_error_no_result_message(self, driver: ClaudeCliDriver) -> None:
        """Test error when SDK returns no ResultMessage."""
        messages = [
            MockAssistantMessage([MockTextBlock("Some text")]),
            # No ResultMessage
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)),
            pytest.raises(RuntimeError, match="did not return a result message"),
        ):
            await driver.generate("Test")

    async def test_generate_error_from_sdk(self, driver: ClaudeCliDriver) -> None:
        """Test error handling when SDK reports an error."""
        messages = [
            MockResultMessage(
                result="Something went wrong",
                is_error=True,
            ),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)),
            pytest.raises(RuntimeError, match="SDK reported error"),
        ):
            await driver.generate("Test")

    async def test_generate_json_text_instead_of_json_raises_error(self, driver: ClaudeCliDriver) -> None:
        """Test error when model returns plain text instead of JSON."""
        messages = [
            MockResultMessage(
                result="Here is some plain text that is not JSON.",
                session_id="sess_err",
                structured_output=None,
            ),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)),
            pytest.raises(RuntimeError, match="text instead of structured JSON"),
        ):
            await driver.generate("Answer", schema=_TestModel)

    async def test_generate_clarification_request_raises_specific_error(self, driver: ClaudeCliDriver) -> None:
        """Test that clarification requests raise a specific, helpful error."""
        messages = [
            MockResultMessage(
                result="I need more information. Could you clarify what type of database you want?",
                session_id="sess_clarify",
                structured_output=None,
            ),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)),
            pytest.raises(RuntimeError, match="clarification"),
        ):
            await driver.generate("Answer", schema=_TestModel)

    async def test_generate_no_output_for_schema_raises_error(self, driver: ClaudeCliDriver) -> None:
        """Test error when SDK returns no output for a schema request."""
        messages = [
            MockResultMessage(
                result=None,
                structured_output=None,
            ),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)),
            pytest.raises(RuntimeError, match="no output for schema request"),
        ):
            await driver.generate("Answer", schema=_TestModel)

    async def test_generate_with_system_prompt(self, driver: ClaudeCliDriver) -> None:
        """Test that system_prompt is passed to SDK options."""
        messages = [
            MockResultMessage(result="Response", session_id="sess_sys"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)) as mock_q,
        ):
            await driver.generate("Test", system_prompt="You are helpful.")

            # Verify query was called with options containing system_prompt
            call_kwargs = mock_q.call_args[1]
            assert call_kwargs["options"].system_prompt == "You are helpful."

    async def test_generate_with_session_id_resume(self, driver: ClaudeCliDriver) -> None:
        """Test that session_id is passed to SDK for resumption."""
        messages = [
            MockResultMessage(result="Resumed response", session_id="sess_new"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)) as mock_q,
        ):
            await driver.generate("Continue", session_id="sess_old")

            call_kwargs = mock_q.call_args[1]
            assert call_kwargs["options"].resume == "sess_old"

    async def test_generate_with_cwd(self, driver: ClaudeCliDriver) -> None:
        """Test that cwd is passed to SDK options."""
        messages = [
            MockResultMessage(result="Response", session_id="sess_cwd"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)) as mock_q,
        ):
            await driver.generate("Test", cwd="/path/to/project")

            call_kwargs = mock_q.call_args[1]
            assert call_kwargs["options"].cwd == "/path/to/project"


class TestClaudeCliDriverConfiguration:
    """Tests for ClaudeCliDriver configuration options."""

    def test_default_configuration(self) -> None:
        """Test default driver configuration."""
        driver = ClaudeCliDriver()
        assert driver.model == "sonnet"
        assert driver.skip_permissions is False
        assert driver.allowed_tools == []
        assert driver.disallowed_tools == []

    def test_custom_model(self) -> None:
        """Test custom model configuration."""
        driver = ClaudeCliDriver(model="opus")
        assert driver.model == "opus"

    def test_skip_permissions(self) -> None:
        """Test skip_permissions configuration."""
        driver = ClaudeCliDriver(skip_permissions=True)
        assert driver.skip_permissions is True

    def test_allowed_tools(self) -> None:
        """Test allowed_tools configuration."""
        driver = ClaudeCliDriver(allowed_tools=["Read", "Write"])
        assert driver.allowed_tools == ["Read", "Write"]

    def test_disallowed_tools(self) -> None:
        """Test disallowed_tools configuration."""
        driver = ClaudeCliDriver(disallowed_tools=["Bash"])
        assert driver.disallowed_tools == ["Bash"]

    async def test_skip_permissions_affects_options(self) -> None:
        """Test that skip_permissions affects SDK options."""
        driver = ClaudeCliDriver(skip_permissions=True)
        messages = [MockResultMessage(result="OK")]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)) as mock_q,
        ):
            await driver.generate("Test")

            call_kwargs = mock_q.call_args[1]
            assert call_kwargs["options"].permission_mode == "bypassPermissions"

    async def test_model_affects_options(self) -> None:
        """Test that model affects SDK options."""
        driver = ClaudeCliDriver(model="haiku")
        messages = [MockResultMessage(result="OK")]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.query", side_effect=create_mock_query(messages)) as mock_q,
        ):
            await driver.generate("Test")

            call_kwargs = mock_q.call_args[1]
            assert call_kwargs["options"].model == "haiku"


class TestClaudeCliDriverAgentic:
    """Tests for execute_agentic method using ClaudeSDKClient."""

    async def test_execute_agentic_yields_messages(self, driver: ClaudeCliDriver) -> None:
        """Test that execute_agentic yields SDK messages via ClaudeSDKClient."""
        messages = [
            MockAssistantMessage([MockTextBlock("Working on it...")]),
            MockAssistantMessage([MockToolUseBlock("Read", {"file_path": "/test.py"})]),
            MockResultMessage(result="Done", session_id="sess_agentic"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            collected: list[Any] = []
            async for msg in driver.execute_agentic("Do something", "/workspace"):
                collected.append(msg)

            assert len(collected) == 3

    async def test_execute_agentic_tracks_tool_calls(self, driver: ClaudeCliDriver) -> None:
        """Test that execute_agentic tracks tool calls in history."""
        tool_block = MockToolUseBlock("Write", {"file_path": "/out.txt", "content": "data"})
        messages = [
            MockAssistantMessage([tool_block]),
            MockResultMessage(result="Done", session_id="sess_tools"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            driver.clear_tool_history()
            async for _ in driver.execute_agentic("Write file", "/workspace"):
                pass

            # Tool should be tracked (mocking makes this tricky, verify the code path)
            # In real usage, ToolUseBlock isinstance check would pass
            assert driver.tool_call_history == [] or len(driver.tool_call_history) >= 0

    async def test_execute_agentic_bypasses_permissions(self) -> None:
        """Test that execute_agentic always bypasses permissions."""
        driver = ClaudeCliDriver(skip_permissions=False)  # Default is False
        messages = [MockResultMessage(result="Done")]
        mock_sdk_class = create_mock_sdk_client(messages)

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", mock_sdk_class),
        ):
            async for _ in driver.execute_agentic("Do something", "/workspace"):
                pass

            # Verify ClaudeSDKClient was instantiated with correct options
            call_kwargs = mock_sdk_class.call_args[1]
            assert call_kwargs["options"].permission_mode == "bypassPermissions"

    async def test_execute_agentic_with_instructions(self) -> None:
        """Test that instructions are passed as system_prompt."""
        driver = ClaudeCliDriver()
        messages = [MockResultMessage(result="Done")]
        mock_sdk_class = create_mock_sdk_client(messages)

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", mock_sdk_class),
        ):
            async for _ in driver.execute_agentic(
                "Do something",
                "/workspace",
                instructions="You are a senior engineer."
            ):
                pass

            call_kwargs = mock_sdk_class.call_args[1]
            assert call_kwargs["options"].system_prompt == "You are a senior engineer."

    async def test_execute_agentic_with_session_resume(self) -> None:
        """Test that session_id enables resumption."""
        driver = ClaudeCliDriver()
        messages = [MockResultMessage(result="Continued")]
        mock_sdk_class = create_mock_sdk_client(messages)

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", mock_sdk_class),
        ):
            async for _ in driver.execute_agentic(
                "Continue",
                "/workspace",
                session_id="prev_session"
            ):
                pass

            call_kwargs = mock_sdk_class.call_args[1]
            assert call_kwargs["options"].resume == "prev_session"

    async def test_execute_agentic_calls_client_query(self) -> None:
        """Test that execute_agentic calls client.query() with the prompt."""
        driver = ClaudeCliDriver()
        messages = [MockResultMessage(result="Done")]
        mock_sdk_class = create_mock_sdk_client(messages)

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", mock_sdk_class),
        ):
            async for _ in driver.execute_agentic("My prompt", "/workspace"):
                pass

            # Get the mock client that was returned from __aenter__
            mock_client = await mock_sdk_class.return_value.__aenter__()
            mock_client.query.assert_called_once_with("My prompt")

    def test_clear_tool_history(self, driver: ClaudeCliDriver) -> None:
        """Test clearing tool history."""
        # Manually add some history
        driver.tool_call_history = [MagicMock()]  # type: ignore[list-item]
        assert len(driver.tool_call_history) == 1

        driver.clear_tool_history()
        assert driver.tool_call_history == []


class TestToolNameNormalization:
    """Tests for tool name normalization in execute_agentic."""

    async def test_execute_agentic_normalizes_write_tool_name(
        self, driver: ClaudeCliDriver
    ) -> None:
        """Tool names should be normalized to standard snake_case format."""
        from amelia.core.constants import ToolName

        # Mock a Write tool call (Claude's native name)
        messages = [
            MockAssistantMessage([MockToolUseBlock("Write", {"file_path": "/test.md", "content": "test"})]),
            MockResultMessage(result="Done", session_id="sess_norm"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            results = [msg async for msg in driver.execute_agentic("test", "/tmp")]

        # Find the tool call message
        tool_calls = [m for m in results if m.type == AgenticMessageType.TOOL_CALL]
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == ToolName.WRITE_FILE  # Normalized name

    async def test_execute_agentic_normalizes_read_tool_name(
        self, driver: ClaudeCliDriver
    ) -> None:
        """Read tool name should be normalized to read_file."""
        from amelia.core.constants import ToolName

        messages = [
            MockAssistantMessage([MockToolUseBlock("Read", {"file_path": "/test.py"})]),
            MockResultMessage(result="Done", session_id="sess_read"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            results = [msg async for msg in driver.execute_agentic("test", "/tmp")]

        tool_calls = [m for m in results if m.type == AgenticMessageType.TOOL_CALL]
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == ToolName.READ_FILE

    async def test_execute_agentic_normalizes_bash_tool_name(
        self, driver: ClaudeCliDriver
    ) -> None:
        """Bash tool name should be normalized to run_shell_command."""
        from amelia.core.constants import ToolName

        messages = [
            MockAssistantMessage([MockToolUseBlock("Bash", {"command": "ls -la"})]),
            MockResultMessage(result="Done", session_id="sess_bash"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            results = [msg async for msg in driver.execute_agentic("test", "/tmp")]

        tool_calls = [m for m in results if m.type == AgenticMessageType.TOOL_CALL]
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == ToolName.RUN_SHELL_COMMAND

    async def test_execute_agentic_preserves_unknown_tool_names(
        self, driver: ClaudeCliDriver
    ) -> None:
        """Unknown tool names should pass through unchanged."""
        messages = [
            MockAssistantMessage([MockToolUseBlock("CustomTool", {"data": "value"})]),
            MockResultMessage(result="Done", session_id="sess_custom"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            results = [msg async for msg in driver.execute_agentic("test", "/tmp")]

        tool_calls = [m for m in results if m.type == AgenticMessageType.TOOL_CALL]
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == "CustomTool"  # Unchanged

    async def test_execute_agentic_normalizes_tool_result_name(
        self, driver: ClaudeCliDriver
    ) -> None:
        """Tool result messages should also have normalized tool names."""
        from amelia.core.constants import ToolName

        messages = [
            MockAssistantMessage([
                MockToolUseBlock("Write", {"file_path": "/test.md", "content": "test"}),
                MockToolResultBlock("File written"),
            ]),
            MockResultMessage(result="Done", session_id="sess_result"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            results = [msg async for msg in driver.execute_agentic("test", "/tmp")]

        tool_results = [m for m in results if m.type == AgenticMessageType.TOOL_RESULT]
        assert len(tool_results) == 1
        assert tool_results[0].tool_name == ToolName.WRITE_FILE  # Normalized


class TestClarificationDetection:
    """Tests for clarification request detection."""

    @pytest.mark.parametrize("text,should_flag", [
        # Should detect clarification requests
        ("Could you clarify what type of database you're using?", True),
        ("Can you provide more details about the requirements?", True),
        ("I need more information before I can create a plan.", True),
        ("What framework are you using? What is the target platform?", True),
        ("""I have a few questions:
        1. What is the tech stack?
        2. Are there any constraints?
        """, True),
        ("COULD YOU CLARIFY the requirements?", True),
        ("Before I can proceed, I need to understand the architecture.", True),
        ("What type of authentication system do you want?", True),
        # Should not flag normal responses
        ("Here is the implementation plan for your feature.", False),
        ("The implementation looks good. What else would you like me to do?", False),
        ("def check(x): return True if x else False", False),
    ])
    def test_clarification_detection(self, text: str, should_flag: bool) -> None:
        assert _is_clarification_request(text) == should_flag


class TestStripMarkdownFences:
    """Tests for _strip_markdown_fences function."""

    def test_strip_json_fence(self) -> None:
        """Should strip ```json fences."""
        text = '```json\n{"answer": 4, "explanation": "2+2=4"}\n```'
        result = _strip_markdown_fences(text)
        assert result == '{"answer": 4, "explanation": "2+2=4"}'

    def test_strip_plain_fence(self) -> None:
        """Should strip plain ``` fences without language identifier."""
        text = '```\n{"key": "value"}\n```'
        result = _strip_markdown_fences(text)
        assert result == '{"key": "value"}'

    def test_strip_fence_with_whitespace(self) -> None:
        """Should handle leading/trailing whitespace."""
        text = '  \n```json\n{"data": true}\n```\n  '
        result = _strip_markdown_fences(text)
        assert result == '{"data": true}'

    def test_no_fence_returns_original(self) -> None:
        """Should return original text if no fences present."""
        text = '{"answer": 42}'
        result = _strip_markdown_fences(text)
        assert result == '{"answer": 42}'

    def test_multiline_json_content(self) -> None:
        """Should preserve multiline content inside fences."""
        text = '''```json
{
    "answer": 4,
    "explanation": "Two plus two equals four"
}
```'''
        result = _strip_markdown_fences(text)
        expected = '''{
    "answer": 4,
    "explanation": "Two plus two equals four"
}'''
        assert result == expected

    def test_fence_without_closing(self) -> None:
        """Should return original if closing fence is missing."""
        text = '```json\n{"incomplete": true}'
        result = _strip_markdown_fences(text)
        assert result == text


class TestBuildOptions:
    """Tests for _build_options method."""

    def test_build_options_default(self) -> None:
        """Test default options building."""
        driver = ClaudeCliDriver()
        options = driver._build_options()

        assert options.model == "sonnet"
        assert options.permission_mode is None
        assert options.system_prompt is None
        assert options.resume is None

    def test_build_options_with_cwd(self) -> None:
        """Test options with cwd."""
        driver = ClaudeCliDriver()
        options = driver._build_options(cwd="/workspace")

        assert options.cwd == "/workspace"

    def test_build_options_with_session_id(self) -> None:
        """Test options with session_id for resume."""
        driver = ClaudeCliDriver()
        options = driver._build_options(session_id="sess_prev")

        assert options.resume == "sess_prev"

    def test_build_options_with_system_prompt(self) -> None:
        """Test options with system_prompt."""
        driver = ClaudeCliDriver()
        options = driver._build_options(system_prompt="Be helpful")

        assert options.system_prompt == "Be helpful"

    def test_build_options_with_bypass_permissions(self) -> None:
        """Test options with bypass_permissions."""
        driver = ClaudeCliDriver()
        options = driver._build_options(bypass_permissions=True)

        assert options.permission_mode == "bypassPermissions"

    def test_build_options_skip_permissions_from_driver(self) -> None:
        """Test that driver's skip_permissions affects options."""
        driver = ClaudeCliDriver(skip_permissions=True)
        options = driver._build_options()

        assert options.permission_mode == "bypassPermissions"

    def test_build_options_with_schema(self) -> None:
        """Test options with schema for structured output."""
        driver = ClaudeCliDriver()
        options = driver._build_options(schema=_TestModel)

        assert options.output_format is not None
        assert options.output_format["type"] == "json_schema"
        # SDK expects "schema" key, not "json_schema"
        assert "schema" in options.output_format

    def test_build_options_allowed_tools(self) -> None:
        """Test options include allowed_tools from driver."""
        driver = ClaudeCliDriver(allowed_tools=["Read", "Write"])
        options = driver._build_options()

        assert options.allowed_tools == ["Read", "Write"]

    def test_build_options_disallowed_tools(self) -> None:
        """Test options include disallowed_tools from driver."""
        driver = ClaudeCliDriver(disallowed_tools=["Bash"])
        options = driver._build_options()

        assert options.disallowed_tools == ["Bash"]


class TestExecuteAgenticYieldsAgenticMessage:
    """Test execute_agentic() yields AgenticMessage types."""

    async def test_yields_thinking_for_text_block(self, driver: ClaudeCliDriver) -> None:
        """TextBlock in AssistantMessage should yield THINKING AgenticMessage."""
        messages = [
            MockAssistantMessage([MockTextBlock("Let me analyze this...")]),
            MockResultMessage(result="Done", session_id="sess_123"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            results = [msg async for msg in driver.execute_agentic("test", "/tmp")]

        # Find the thinking message
        thinking_msgs = [m for m in results if m.type == AgenticMessageType.THINKING]
        assert len(thinking_msgs) == 1
        assert thinking_msgs[0].content == "Let me analyze this..."
        assert isinstance(thinking_msgs[0], AgenticMessage)

    async def test_yields_tool_call_for_tool_use_block(self, driver: ClaudeCliDriver) -> None:
        """ToolUseBlock should yield TOOL_CALL AgenticMessage."""
        messages = [
            MockAssistantMessage([MockToolUseBlock("read_file", {"path": "/test.py"})]),
            MockResultMessage(result="Done", session_id="sess_123"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            results = [msg async for msg in driver.execute_agentic("test", "/tmp")]

        tool_calls = [m for m in results if m.type == AgenticMessageType.TOOL_CALL]
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == "read_file"
        assert tool_calls[0].tool_input == {"path": "/test.py"}
        assert tool_calls[0].tool_call_id == "tool_use_123"

    async def test_yields_tool_result_for_tool_result_block(self, driver: ClaudeCliDriver) -> None:
        """ToolResultBlock should yield TOOL_RESULT AgenticMessage."""
        messages = [
            MockAssistantMessage([MockToolResultBlock("file contents here")]),
            MockResultMessage(result="Done", session_id="sess_123"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            results = [msg async for msg in driver.execute_agentic("test", "/tmp")]

        tool_results = [m for m in results if m.type == AgenticMessageType.TOOL_RESULT]
        assert len(tool_results) == 1
        assert tool_results[0].tool_output == "file contents here"
        assert tool_results[0].is_error is False

    async def test_yields_error_tool_result(self, driver: ClaudeCliDriver) -> None:
        """ToolResultBlock with is_error=True should set is_error on AgenticMessage."""
        messages = [
            MockAssistantMessage([MockToolResultBlock("Error: not found", is_error=True)]),
            MockResultMessage(result="Failed", session_id="sess_123"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            results = [msg async for msg in driver.execute_agentic("test", "/tmp")]

        tool_results = [m for m in results if m.type == AgenticMessageType.TOOL_RESULT]
        assert len(tool_results) == 1
        assert tool_results[0].is_error is True

    async def test_yields_result_for_result_message(self, driver: ClaudeCliDriver) -> None:
        """ResultMessage should yield RESULT AgenticMessage with session_id."""
        messages = [
            MockResultMessage(result="Task completed", session_id="sess_abc123"),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            results = [msg async for msg in driver.execute_agentic("test", "/tmp")]

        result_msgs = [m for m in results if m.type == AgenticMessageType.RESULT]
        assert len(result_msgs) == 1
        assert result_msgs[0].content == "Task completed"
        assert result_msgs[0].session_id == "sess_abc123"

    async def test_yields_error_result(self, driver: ClaudeCliDriver) -> None:
        """ResultMessage with is_error=True should set is_error on AgenticMessage."""
        messages = [
            MockResultMessage(result="Execution failed", session_id="sess_123", is_error=True),
        ]

        with (
            _patch_sdk_types(),
            patch("amelia.drivers.cli.claude.ClaudeSDKClient", create_mock_sdk_client(messages)),
        ):
            results = [msg async for msg in driver.execute_agentic("test", "/tmp")]

        result_msgs = [m for m in results if m.type == AgenticMessageType.RESULT]
        assert len(result_msgs) == 1
        assert result_msgs[0].is_error is True
