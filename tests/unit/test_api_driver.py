"""Tests for DeepAgents-based ApiDriver."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from amelia.drivers.api.deepagents import ApiDriver, LocalSandbox, _create_chat_model
from amelia.drivers.base import AgenticMessage, AgenticMessageType


class ResponseSchema(BaseModel):
    """Test schema for structured output."""

    message: str


@pytest.fixture
def api_driver() -> ApiDriver:
    """Create ApiDriver instance for tests.

    This fixture provides a standard ApiDriver with test configuration.
    Used by TestGenerate and TestExecuteAgenticYieldsAgenticMessage.
    """
    return ApiDriver(model="test/model", cwd="/test/path", provider="openrouter")


class TestApiDriverInit:
    """Test ApiDriver initialization."""

    def test_uses_provided_model(self) -> None:
        """Should use the provided model name."""
        driver = ApiDriver(model="anthropic/claude-sonnet-4-20250514", provider="openrouter")
        assert driver.model == "anthropic/claude-sonnet-4-20250514"

    def test_defaults_to_minimax_m2(self) -> None:
        """Should default to MiniMax M2 when no model provided."""
        driver = ApiDriver()
        assert driver.model == ApiDriver.DEFAULT_MODEL
        assert driver.model == "minimax/minimax-m2"  # No prefix

    def test_stores_cwd(self) -> None:
        """Should store the cwd parameter."""
        driver = ApiDriver(cwd="/some/path")
        assert driver.cwd == "/some/path"

    def test_stores_provider(self) -> None:
        """Should store the provider parameter."""
        driver = ApiDriver(provider="openrouter")
        assert driver.provider == "openrouter"

    def test_provider_defaults_to_openrouter(self) -> None:
        """Should default provider to 'openrouter' when not specified."""
        driver = ApiDriver()
        assert driver.provider == "openrouter"


class TestGenerate:
    """Test generate() method."""

    async def test_rejects_empty_prompt(self, api_driver: ApiDriver) -> None:
        """Should reject empty or whitespace-only prompts."""
        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            await api_driver.generate("")

        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            await api_driver.generate("   \n\t  ")

    async def test_returns_text_without_schema(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should return plain text when no schema provided."""
        mock_deepagents.agent_result["messages"] = [
            HumanMessage(content="test prompt"),
            AIMessage(content="Test response from model"),
        ]

        result, session_id = await api_driver.generate(
            prompt="test prompt",
            system_prompt="You are a helpful assistant",
        )

        assert result == "Test response from model"
        assert session_id is None

        # Verify create_deep_agent was called correctly
        mock_deepagents.create_deep_agent.assert_called_once()
        call_kwargs = mock_deepagents.create_deep_agent.call_args.kwargs
        assert call_kwargs["system_prompt"] == "You are a helpful assistant"

    async def test_parses_schema_when_provided(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should extract structured_response when schema provided."""
        mock_deepagents.agent_result["structured_response"] = ResponseSchema(
            message="parsed response"
        )

        result, session_id = await api_driver.generate(
            prompt="test prompt",
            schema=ResponseSchema,
        )

        assert isinstance(result, ResponseSchema)
        assert result.message == "parsed response"
        assert session_id is None

        # Verify response_format was passed to create_deep_agent with correct schema
        call_kwargs = mock_deepagents.create_deep_agent.call_args.kwargs
        assert "response_format" in call_kwargs
        response_format = call_kwargs["response_format"]
        assert isinstance(response_format, ToolStrategy)
        assert response_format.schema is ResponseSchema

    async def test_raises_on_missing_structured_output(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should raise RuntimeError when schema provided but no structured_response returned."""
        # structured_response is not set in agent_result (defaults to None)
        mock_deepagents.agent_result["messages"] = [
            AIMessage(content="some response"),
        ]

        with pytest.raises(
            RuntimeError, match="Model did not call the ResponseSchema tool"
        ):
            await api_driver.generate(prompt="test", schema=ResponseSchema)

    async def test_handles_list_content_blocks(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should handle AIMessage with list of content blocks."""
        mock_deepagents.agent_result["messages"] = [
            AIMessage(content=[{"text": "Hello "}, {"text": "World"}]),
        ]

        result, _ = await api_driver.generate(prompt="test")

        assert result == "Hello World"

    async def test_raises_on_empty_response(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should raise RuntimeError when no messages returned."""
        mock_deepagents.agent_result["messages"] = []

        with pytest.raises(RuntimeError, match="No response messages"):
            await api_driver.generate(prompt="test")

    async def test_uses_none_system_prompt_as_empty_string(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should use empty string when system_prompt is None."""
        mock_deepagents.agent_result["messages"] = [
            AIMessage(content="response"),
        ]

        await api_driver.generate(prompt="test", system_prompt=None)

        call_kwargs = mock_deepagents.create_deep_agent.call_args.kwargs
        assert call_kwargs["system_prompt"] == ""

    async def test_passes_provider_to_create_chat_model(
        self, mock_deepagents: MagicMock
    ) -> None:
        """Should pass provider to _create_chat_model."""
        driver = ApiDriver(model="test/model", cwd="/test", provider="openrouter")
        mock_deepagents.agent_result["messages"] = [AIMessage(content="response")]

        with patch("amelia.drivers.api.deepagents._create_chat_model") as mock_create:
            mock_create.return_value = MagicMock()
            await driver.generate(prompt="test")

            mock_create.assert_called_once_with("test/model", provider="openrouter")


class TestExecuteAgentic:
    """Test execute_agentic() method."""

    async def test_rejects_empty_prompt(self) -> None:
        """Should reject empty prompts."""
        driver = ApiDriver(model="test", cwd="/some/path")

        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            async for _ in driver.execute_agentic(prompt="", cwd="/some/path"):
                pass

    async def test_passes_provider_to_create_chat_model(
        self, mock_deepagents: MagicMock
    ) -> None:
        """Should pass provider to _create_chat_model in execute_agentic."""
        driver = ApiDriver(model="test/model", cwd="/test", provider="openrouter")
        mock_deepagents.stream_chunks = [
            {"messages": [AIMessage(content="done")]},
        ]

        with patch("amelia.drivers.api.deepagents._create_chat_model") as mock_create:
            mock_create.return_value = MagicMock()
            async for _ in driver.execute_agentic(prompt="test", cwd="/test"):
                pass

            mock_create.assert_called_once_with("test/model", provider="openrouter")

    async def test_yields_agentic_messages_from_stream(
        self, mock_deepagents: MagicMock
    ) -> None:
        """Should yield AgenticMessage objects from the stream."""
        driver = ApiDriver(model="test", cwd="/test/path")

        # Set up streaming messages: list content -> THINKING, plain string -> only RESULT
        # This matches ClaudeCliDriver semantics where TextBlock is intermediate thinking
        # and ResultMessage.result is the final output (distinct sources)
        messages_stream = [
            {"messages": [AIMessage(content=[{"type": "text", "text": "thinking..."}])]},
            {"messages": [AIMessage(content="done")]},  # Plain string -> only RESULT
        ]
        mock_deepagents.stream_chunks = messages_stream

        collected: list[AgenticMessage] = []
        async for msg in driver.execute_agentic(prompt="test", cwd="/test/path"):
            collected.append(msg)

        # List content yields THINKING, plain string only yields RESULT at end
        thinking_msgs = [m for m in collected if m.type == AgenticMessageType.THINKING]
        result_msgs = [m for m in collected if m.type == AgenticMessageType.RESULT]

        assert len(thinking_msgs) == 1
        assert thinking_msgs[0].content == "thinking..."
        assert len(result_msgs) == 1
        assert result_msgs[0].content == "done"
        assert all(isinstance(m, AgenticMessage) for m in collected)


class TestCreateChatModel:
    """Tests for _create_chat_model function."""

    def test_openrouter_prefix_raises_error(self) -> None:
        """Should raise ValueError for deprecated openrouter: prefix."""
        with pytest.raises(ValueError, match="no longer supported"):
            _create_chat_model("openrouter:anthropic/claude-sonnet-4-20250514")

    def test_openrouter_provider_uses_custom_attribution(self) -> None:
        """Should use custom attribution headers from environment."""
        with (
            patch.dict(os.environ, {
                "OPENROUTER_API_KEY": "test-api-key",
                "OPENROUTER_SITE_URL": "https://example.com",
                "OPENROUTER_SITE_NAME": "CustomApp",
            }),
            patch("amelia.drivers.api.deepagents.init_chat_model") as mock_init,
        ):
            mock_init.return_value = MagicMock()

            _create_chat_model("test/model", provider="openrouter")

            call_kwargs = mock_init.call_args.kwargs
            assert call_kwargs["default_headers"]["HTTP-Referer"] == "https://example.com"
            assert call_kwargs["default_headers"]["X-Title"] == "CustomApp"

    def test_openrouter_model_requires_api_key(self) -> None:
        """Should raise ValueError if OPENROUTER_API_KEY is not set."""
        with (
            patch.dict(os.environ, {}, clear=True),
            pytest.raises(ValueError, match="OPENROUTER_API_KEY"),
        ):
            _create_chat_model("test/model", provider="openrouter")

    def test_non_openrouter_model_uses_default(self) -> None:
        """Should use default init_chat_model for non-openrouter models."""
        with patch("amelia.drivers.api.deepagents.init_chat_model") as mock_init:
            mock_init.return_value = MagicMock()

            _create_chat_model("gpt-4")

            mock_init.assert_called_once_with("gpt-4")

    def test_openrouter_provider_without_prefix(self) -> None:
        """Should configure OpenRouter when provider param is 'openrouter'."""
        with (
            patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-api-key"}),
            patch("amelia.drivers.api.deepagents.init_chat_model") as mock_init,
        ):
            mock_init.return_value = MagicMock()

            _create_chat_model("minimax/minimax-m2", provider="openrouter")

            mock_init.assert_called_once_with(
                model="minimax/minimax-m2",
                model_provider="openai",
                base_url="https://openrouter.ai/api/v1",
                api_key="test-api-key",
                default_headers={
                    "HTTP-Referer": "https://github.com/existential-birds/amelia",
                    "X-Title": "Amelia",
                },
            )


class TestLocalSandbox:
    """Tests for LocalSandbox class."""

    @pytest.fixture
    def sandbox(self, tmp_path: Path) -> LocalSandbox:
        """Create LocalSandbox instance for tests."""
        return LocalSandbox(root_dir=str(tmp_path))

    def test_contract_sandbox_backend_protocol(self, sandbox: LocalSandbox) -> None:
        """Should pass isinstance check for SandboxBackendProtocol.

        This is critical because deepagents uses isinstance() to decide
        whether to enable the 'execute' tool. Without explicit inheritance,
        the check fails since SandboxBackendProtocol is not @runtime_checkable.
        """
        from deepagents.backends.protocol import SandboxBackendProtocol

        assert isinstance(sandbox, SandboxBackendProtocol)

    def test_id_includes_cwd(self, sandbox: LocalSandbox) -> None:
        """Should return unique id based on cwd."""
        assert sandbox.id.startswith("local-")
        assert str(sandbox.cwd) in sandbox.id

    def test_execute_returns_stdout(self, sandbox: LocalSandbox) -> None:
        """Should capture stdout from command."""
        result = sandbox.execute("echo hello")
        assert "hello" in result.output
        assert result.exit_code == 0
        assert result.truncated is False

    def test_execute_returns_stderr(self, sandbox: LocalSandbox) -> None:
        """Should capture stderr from command."""
        result = sandbox.execute("echo error >&2")
        assert "error" in result.output

    def test_execute_returns_exit_code(self, sandbox: LocalSandbox) -> None:
        """Should capture non-zero exit codes."""
        result = sandbox.execute("exit 42")
        assert result.exit_code == 42

    def test_execute_runs_in_cwd(self, sandbox: LocalSandbox, tmp_path: Path) -> None:
        """Should execute commands in the sandbox cwd."""
        result = sandbox.execute("pwd")
        assert str(tmp_path) in result.output

    def test_default_timeout_is_configured(self, sandbox: LocalSandbox) -> None:
        """Should have a reasonable default timeout configured."""
        from amelia.drivers.api.deepagents import _DEFAULT_TIMEOUT

        assert _DEFAULT_TIMEOUT == 300

    def test_execute_returns_timeout_error_on_slow_command(
        self, tmp_path: Path
    ) -> None:
        """Should return error response when command times out."""
        from amelia.drivers.api.deepagents import LocalSandbox

        sandbox = LocalSandbox(root_dir=str(tmp_path))

        with patch("amelia.drivers.api.deepagents._DEFAULT_TIMEOUT", 0.01):
            result = sandbox.execute("sleep 1")
            assert result.exit_code == 124
            assert "timed out" in result.output

    async def test_aexecute_returns_same_as_execute(self, sandbox: LocalSandbox) -> None:
        """Async execute should return same result as sync."""
        sync_result = sandbox.execute("echo test")
        async_result = await sandbox.aexecute("echo test")

        assert sync_result.output == async_result.output
        assert sync_result.exit_code == async_result.exit_code

    def test_virtual_mode_resolves_virtual_paths_under_cwd(self, tmp_path: Path) -> None:
        """virtual_mode=True should resolve /path/to/file as {cwd}/path/to/file.

        This is critical for deepagents integration: _validate_path() adds a leading /
        to all paths (e.g., "docs/plans/plan.md" becomes "/docs/plans/plan.md").
        Without virtual_mode, this would be treated as an absolute filesystem path.
        With virtual_mode=True, the leading / is stripped and the path is joined with cwd.
        """
        sandbox = LocalSandbox(root_dir=str(tmp_path), virtual_mode=True)

        # Test that write() puts file under cwd, not at filesystem root
        result = sandbox.write("/docs/plans/test.md", "# Test Plan")
        assert result.error is None
        assert result.path == "/docs/plans/test.md"

        # Verify file exists under cwd, not at filesystem root
        expected_path = tmp_path / "docs" / "plans" / "test.md"
        assert expected_path.exists()
        assert expected_path.read_text() == "# Test Plan"

        # Verify we didn't write to filesystem root
        root_path = Path("/docs/plans/test.md")
        assert not root_path.exists()

    def test_virtual_mode_read_file_under_cwd(self, tmp_path: Path) -> None:
        """virtual_mode=True should read files relative to cwd."""
        sandbox = LocalSandbox(root_dir=str(tmp_path), virtual_mode=True)

        # Create a file under cwd
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file.txt").write_text("content here")

        # Read using virtual path (with leading /)
        content = sandbox.read("/subdir/file.txt")
        assert "content here" in content


class TestExecuteAgenticYieldsAgenticMessage:
    """Test execute_agentic() yields AgenticMessage types."""

    async def test_plain_string_content_yields_only_result(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """AIMessage with plain string content should only yield RESULT, not THINKING.

        This avoids duplicate content where the same text appears as both THINKING
        and RESULT. Plain string content indicates a final response without tool use,
        so it goes directly to RESULT. This matches ClaudeCliDriver semantics where
        TextBlock (from AssistantMessage) is intermediate thinking and ResultMessage.result
        is the final output - two distinct data sources.
        """
        mock_deepagents.stream_chunks = [
            {"messages": [AIMessage(content="Analyzing the code...")]},
        ]

        results = [msg async for msg in api_driver.execute_agentic("test prompt", cwd="/test/path")]

        # Plain string content should NOT yield THINKING - only RESULT
        thinking_msgs = [m for m in results if m.type == AgenticMessageType.THINKING]
        result_msgs = [m for m in results if m.type == AgenticMessageType.RESULT]
        assert len(thinking_msgs) == 0
        assert len(result_msgs) == 1
        assert result_msgs[0].content == "Analyzing the code..."

    async def test_yields_thinking_for_list_content(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """AIMessage with list content blocks should yield THINKING AgenticMessage."""
        mock_deepagents.stream_chunks = [
            {"messages": [AIMessage(content=[{"type": "text", "text": "Thinking hard..."}])]},
        ]

        results = [msg async for msg in api_driver.execute_agentic("test prompt", cwd="/test/path")]

        thinking_msgs = [m for m in results if m.type == AgenticMessageType.THINKING]
        assert len(thinking_msgs) >= 1
        assert any(m.content == "Thinking hard..." for m in thinking_msgs)

    async def test_yields_tool_call_for_tool_calls(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """AIMessage with tool_calls should yield TOOL_CALL AgenticMessage."""
        ai_msg = AIMessage(content="", tool_calls=[
            {"name": "read_file", "args": {"path": "/test.py"}, "id": "call_123"}
        ])
        mock_deepagents.stream_chunks = [{"messages": [ai_msg]}]

        results = [msg async for msg in api_driver.execute_agentic("test prompt", cwd="/test/path")]

        tool_calls = [m for m in results if m.type == AgenticMessageType.TOOL_CALL]
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == "read_file"
        assert tool_calls[0].tool_input == {"path": "/test.py"}
        assert tool_calls[0].tool_call_id == "call_123"

    async def test_yields_tool_result_for_tool_message(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """ToolMessage should yield TOOL_RESULT AgenticMessage."""
        tool_msg = ToolMessage(content="file contents", tool_call_id="call_123", name="read_file")
        mock_deepagents.stream_chunks = [{"messages": [tool_msg]}]

        results = [msg async for msg in api_driver.execute_agentic("test prompt", cwd="/test/path")]

        tool_results = [m for m in results if m.type == AgenticMessageType.TOOL_RESULT]
        assert len(tool_results) == 1
        assert tool_results[0].tool_output == "file contents"
        assert tool_results[0].tool_name == "read_file"
        assert tool_results[0].is_error is False

    async def test_yields_result_at_end(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Final AIMessage should yield RESULT AgenticMessage."""
        mock_deepagents.stream_chunks = [
            {"messages": [AIMessage(content="Task completed successfully")]},
        ]

        results = [msg async for msg in api_driver.execute_agentic("test prompt", cwd="/test/path")]

        result_msgs = [m for m in results if m.type == AgenticMessageType.RESULT]
        assert len(result_msgs) == 1
        assert result_msgs[0].content == "Task completed successfully"
        # API driver has no session support
        assert result_msgs[0].session_id is None

    async def test_yields_result_with_list_content(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Final AIMessage with list content should yield RESULT with combined text."""
        mock_deepagents.stream_chunks = [
            {"messages": [AIMessage(content=[{"type": "text", "text": "Done!"}])]},
        ]

        results = [msg async for msg in api_driver.execute_agentic("test prompt", cwd="/test/path")]

        result_msgs = [m for m in results if m.type == AgenticMessageType.RESULT]
        assert len(result_msgs) == 1
        assert result_msgs[0].content == "Done!"

    async def test_full_agentic_flow(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Full agentic flow should yield proper sequence of AgenticMessage types."""
        mock_deepagents.stream_chunks = [
            # List content yields THINKING (intermediate text during tool use)
            {"messages": [AIMessage(content=[{"type": "text", "text": "Let me check the file..."}])]},
            {"messages": [AIMessage(content="", tool_calls=[
                {"name": "read_file", "args": {"path": "/test.py"}, "id": "call_1"}
            ])]},
            {"messages": [ToolMessage(content="def test(): pass", tool_call_id="call_1", name="read_file")]},
            # Plain string content only yields RESULT (final response)
            {"messages": [AIMessage(content="The file contains a test function.")]},
        ]

        results = [msg async for msg in api_driver.execute_agentic("test prompt", cwd="/test/path")]

        # Should have all types
        types = [m.type for m in results]
        assert AgenticMessageType.THINKING in types
        assert AgenticMessageType.TOOL_CALL in types
        assert AgenticMessageType.TOOL_RESULT in types
        assert AgenticMessageType.RESULT in types

        # All should be AgenticMessage instances
        assert all(isinstance(m, AgenticMessage) for m in results)


class TestIncompleteTaskDetection:
    """Test incomplete task detection for premature agent termination."""

    async def test_logs_warning_for_incomplete_write_todos(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should log warning when write_todos has in_progress tasks at completion."""
        # Simulate agent calling write_todos with in_progress task, then completing
        ai_msg_with_todos = AIMessage(
            content="",
            tool_calls=[{
                "name": "write_todos",
                "args": {
                    "todos": [
                        {"content": "Create implementation plan", "status": "in_progress"}
                    ]
                },
                "id": "call_todos"
            }]
        )
        tool_result = ToolMessage(
            content="Todos updated",
            tool_call_id="call_todos",
            name="write_todos"
        )
        final_msg = AIMessage(content="I've started planning the implementation.")

        mock_deepagents.stream_chunks = [
            {"messages": [ai_msg_with_todos]},
            {"messages": [tool_result]},
            {"messages": [final_msg]},
        ]

        # Patch logger to capture warning calls
        with patch("amelia.drivers.api.deepagents.logger") as mock_logger:
            results = [msg async for msg in api_driver.execute_agentic("test prompt", cwd="/test/path")]

        # Should have yielded the result
        result_msgs = [m for m in results if m.type == AgenticMessageType.RESULT]
        assert len(result_msgs) == 1

        # Should have logged warning about incomplete tasks
        warning_calls = mock_logger.warning.call_args_list
        assert len(warning_calls) >= 1
        # Check that at least one warning mentions premature termination
        # Access the actual message from the call args (first positional argument)
        warning_messages = [call.args[0] if call.args else "" for call in warning_calls]
        assert any("premature termination" in msg for msg in warning_messages)

    async def test_no_warning_when_all_tasks_completed(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should not log warning when all write_todos tasks are completed."""
        # Simulate agent completing all tasks properly
        ai_msg_with_todos = AIMessage(
            content="",
            tool_calls=[{
                "name": "write_todos",
                "args": {
                    "todos": [
                        {"content": "Create implementation plan", "status": "completed"}
                    ]
                },
                "id": "call_todos"
            }]
        )
        final_msg = AIMessage(content="All tasks completed.")

        mock_deepagents.stream_chunks = [
            {"messages": [ai_msg_with_todos]},
            {"messages": [final_msg]},
        ]

        # Patch logger to capture warning calls
        with patch("amelia.drivers.api.deepagents.logger") as mock_logger:
            results = [msg async for msg in api_driver.execute_agentic("test prompt", cwd="/test/path")]

        # Should have yielded the result
        result_msgs = [m for m in results if m.type == AgenticMessageType.RESULT]
        assert len(result_msgs) == 1

        # Should NOT have logged warning about incomplete tasks (no premature termination warning)
        warning_calls = mock_logger.warning.call_args_list
        # Access the actual message from the call args (first positional argument)
        warning_messages = [call.args[0] if call.args else "" for call in warning_calls]
        assert not any("premature termination" in msg for msg in warning_messages)

    async def test_logs_warning_when_no_write_file_called(
        self, api_driver: ApiDriver, mock_deepagents: MagicMock
    ) -> None:
        """Should log warning when agent completes without calling write_file."""
        # Simulate agent doing only exploration (no write_file)
        ai_msg_exploration = AIMessage(
            content="",
            tool_calls=[{
                "name": "read_file",
                "args": {"file_path": "/test.py"},
                "id": "call_read"
            }]
        )
        tool_result = ToolMessage(
            content="file contents",
            tool_call_id="call_read",
            name="read_file"
        )
        final_msg = AIMessage(content="I've analyzed the codebase.")

        mock_deepagents.stream_chunks = [
            {"messages": [ai_msg_exploration]},
            {"messages": [tool_result]},
            {"messages": [final_msg]},
        ]

        # Patch logger to capture warning calls
        with patch("amelia.drivers.api.deepagents.logger") as mock_logger:
            results = [msg async for msg in api_driver.execute_agentic("test prompt", cwd="/test/path")]

        # Should have yielded the result
        result_msgs = [m for m in results if m.type == AgenticMessageType.RESULT]
        assert len(result_msgs) == 1

        # Should have logged warning about no write_file
        warning_calls = mock_logger.warning.call_args_list
        # Access the actual message from the call args (first positional argument)
        warning_messages = [call.args[0] if call.args else "" for call in warning_calls]
        assert any("without calling write_file" in msg for msg in warning_messages)
