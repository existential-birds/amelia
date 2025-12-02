import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from amelia.core.state import AgentMessage
from amelia.drivers.cli.claude import (
    ClaudeCliDriver,
    ClaudeStreamEvent,
    _is_clarification_request,
)
from amelia.tools.safe_file import SafeFileWriter
from amelia.tools.safe_shell import SafeShellExecutor


class _TestModel(BaseModel):
    reasoning: str
    answer: str


class _TestListModel(BaseModel):
    tasks: list[str]


@pytest.fixture
def driver():
    return ClaudeCliDriver()


@pytest.fixture
def messages():
    return [
        AgentMessage(role="user", content="Hello"),
        AgentMessage(role="assistant", content="Hi there"),
        AgentMessage(role="user", content="How are you?")
    ]


class TestClaudeCliDriver:

    def test_convert_messages_to_prompt(self, driver, messages):
        prompt = driver._convert_messages_to_prompt(messages)
        expected = "USER: Hello\n\nASSISTANT: Hi there\n\nUSER: How are you?"
        assert prompt == expected

    @pytest.mark.asyncio
    async def test_generate_text_success(self, driver, messages, mock_subprocess_process_factory):
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[b"I am fine, ", b"thank you.", b""],
            return_code=0
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            response = await driver._generate_impl(messages)

            assert response == "I am fine, thank you."
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert args[0] == "claude"
            assert args[1] == "-p"
            mock_process.stdin.write.assert_called_once()
            mock_process.stdin.drain.assert_called_once()
            mock_process.stdin.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_json_success(self, driver, messages, mock_subprocess_process_factory):
        expected_json = json.dumps({"reasoning": "ok", "answer": "good"})
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[expected_json.encode(), b""],
            return_code=0
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            response = await driver._generate_impl(messages, schema=_TestModel)

            assert isinstance(response, _TestModel)
            assert response.reasoning == "ok"
            assert response.answer == "good"

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "--json-schema" in args
            assert "--output-format" in args
            assert args[args.index("--output-format") + 1] == "json"
            mock_process.stdin.write.assert_called_once()
            mock_process.stdin.drain.assert_called_once()
            mock_process.stdin.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_json_list_auto_wrap(self, driver, messages, mock_subprocess_process_factory):
        """Test that a raw list from CLI is auto-wrapped if schema expects 'tasks'."""
        expected_list_json = json.dumps(["task1", "task2"])
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[expected_list_json.encode(), b""],
            return_code=0
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            response = await driver._generate_impl(messages, schema=_TestListModel)

            assert isinstance(response, _TestListModel)
            assert response.tasks == ["task1", "task2"]
            mock_process.stdin.write.assert_called_once()
            mock_process.stdin.drain.assert_called_once()
            mock_process.stdin.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_json_from_result_envelope_structured_output(self, driver, messages, mock_subprocess_process_factory):
        """Test unwrapping structured_output from Claude CLI result envelope."""
        envelope = json.dumps({
            "type": "result",
            "subtype": "success",
            "structured_output": {"reasoning": "from envelope", "answer": "structured"},
            "session_id": "test-session"
        })
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[envelope.encode(), b""],
            return_code=0
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            response = await driver._generate_impl(messages, schema=_TestModel)

            assert isinstance(response, _TestModel)
            assert response.reasoning == "from envelope"
            assert response.answer == "structured"

    @pytest.mark.asyncio
    async def test_generate_json_from_result_envelope_result_field(self, driver, messages, mock_subprocess_process_factory):
        """Test parsing JSON from result field when structured_output is missing."""
        inner_json = json.dumps({"reasoning": "from result", "answer": "parsed"})
        envelope = json.dumps({
            "type": "result",
            "subtype": "success",
            "result": inner_json,
            "session_id": "test-session"
        })
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[envelope.encode(), b""],
            return_code=0
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            response = await driver._generate_impl(messages, schema=_TestModel)

            assert isinstance(response, _TestModel)
            assert response.reasoning == "from result"
            assert response.answer == "parsed"

    @pytest.mark.asyncio
    async def test_generate_json_from_result_envelope_text_raises_error(self, driver, messages, mock_subprocess_process_factory):
        """Test that plain text in result field raises clear error."""
        envelope = json.dumps({
            "type": "result",
            "subtype": "success",
            "result": "Here is some plain text that is not a clarification request.",
            "session_id": "test-session"
        })
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[envelope.encode(), b""],
            return_code=0
        )

        with (
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process),
            pytest.raises(RuntimeError, match="Claude CLI returned text instead of structured JSON"),
        ):
            await driver._generate_impl(messages, schema=_TestModel)

    @pytest.mark.asyncio
    async def test_generate_json_clarification_request_raises_specific_error(self, driver, messages, mock_subprocess_process_factory):
        """Test that clarification requests raise a specific, helpful error."""
        envelope = json.dumps({
            "type": "result",
            "subtype": "success",
            "result": "I need more information to create a plan. Could you clarify what type of tracker you need?",
            "session_id": "test-session"
        })
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[envelope.encode(), b""],
            return_code=0
        )

        with (
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process),
            pytest.raises(RuntimeError, match="Claude requested clarification"),
        ):
            await driver._generate_impl(messages, schema=_TestModel)

    @pytest.mark.asyncio
    async def test_generate_failure_stderr(self, driver, messages, mock_subprocess_process_factory):
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[b""],
            stderr_output=b"Some CLI error occurred",
            return_code=1
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            with pytest.raises(RuntimeError, match="Claude CLI failed with return code 1"):
                await driver._generate_impl(messages)
            mock_process.stdin.write.assert_called_once()
            mock_process.stdin.drain.assert_called_once()
            mock_process.stdin.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_json_parse_error(self, driver, messages, mock_subprocess_process_factory):
        mock_process = mock_subprocess_process_factory(
            stdout_lines=[b"Not JSON", b""],
            return_code=0
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            with pytest.raises(RuntimeError, match="Failed to parse JSON"):
                await driver._generate_impl(messages, schema=_TestModel)
            mock_process.stdin.write.assert_called_once()
            mock_process.stdin.drain.assert_called_once()
            mock_process.stdin.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_tool_shell(self, driver):
        with patch.object(SafeShellExecutor, "execute", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Output"
            await driver._execute_tool_impl("run_shell_command", command="echo test")
            mock_run.assert_called_once_with("echo test", timeout=driver.timeout)

    @pytest.mark.asyncio
    async def test_execute_tool_write_file(self, driver):
        with patch.object(SafeFileWriter, "write", new_callable=AsyncMock) as mock_write:
            mock_write.return_value = "Success"
            await driver._execute_tool_impl("write_file", file_path="test.txt", content="data")
            mock_write.assert_called_once_with("test.txt", "data")

    @pytest.mark.asyncio
    async def test_execute_tool_unknown(self, driver):
        with pytest.raises(NotImplementedError):
            await driver._execute_tool_impl("unknown_tool")


class TestClaudeCliDriverResumeAndCwd:
    """Tests for --resume and cwd support in ClaudeCliDriver."""

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


class TestClaudeCliDriverPermissions:
    """Tests for permission management in ClaudeCliDriver."""

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


class TestClaudeCliDriverSystemPrompt:
    """Tests for system prompt handling in ClaudeCliDriver."""

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


class TestClaudeCliDriverModelSelection:
    """Tests for model selection in ClaudeCliDriver."""

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


class TestClaudeCliDriverAgentic:
    """Tests for execute_agentic method."""

    @pytest.mark.asyncio
    async def test_execute_agentic_uses_skip_permissions(self, driver, mock_subprocess_process_factory):
        """execute_agentic should use --dangerously-skip-permissions."""
        stream_lines = [
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"Working..."}]}}\n',
            b'{"type":"result","session_id":"sess_001","subtype":"success"}\n',
            b""
        ]
        mock_process = mock_subprocess_process_factory(stdout_lines=stream_lines, return_code=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process) as mock_exec:
            events = []
            async for event in driver.execute_agentic("test prompt", "/tmp"):
                events.append(event)

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "--dangerously-skip-permissions" in args

    @pytest.mark.asyncio
    async def test_execute_agentic_tracks_tool_calls(self, driver, mock_subprocess_process_factory):
        """execute_agentic should track tool calls in tool_call_history."""
        stream_lines = [
            b'{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"path":"test.py"}}]}}\n',
            b'{"type":"result","session_id":"sess_001","subtype":"success"}\n',
            b""
        ]
        mock_process = mock_subprocess_process_factory(stdout_lines=stream_lines, return_code=0)

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_process):
            async for _ in driver.execute_agentic("test prompt", "/tmp"):
                pass

            assert len(driver.tool_call_history) == 1
            assert driver.tool_call_history[0].tool_name == "Read"


class TestClarificationDetection:
    """Tests for clarification request detection."""

    def test_detects_could_you_clarify(self):
        text = "Could you clarify what type of database you're using?"
        assert _is_clarification_request(text) is True

    def test_detects_can_you_provide(self):
        text = "Can you provide more details about the requirements?"
        assert _is_clarification_request(text) is True

    def test_detects_i_need_more(self):
        text = "I need more information before I can create a plan."
        assert _is_clarification_request(text) is True

    def test_detects_multiple_questions(self):
        text = "What framework are you using? What is the target platform?"
        assert _is_clarification_request(text) is True

    def test_detects_numbered_questions(self):
        text = """I have a few questions:
        1. What is the tech stack?
        2. Are there any constraints?
        """
        assert _is_clarification_request(text) is True

    def test_does_not_flag_normal_response(self):
        text = "Here is the implementation plan for your feature."
        assert _is_clarification_request(text) is False

    def test_does_not_flag_single_rhetorical_question(self):
        text = "The implementation looks good. What else would you like me to do?"
        # Single question mark, no clarification phrases - should not flag
        assert _is_clarification_request(text) is False

    def test_does_not_flag_code_with_question_marks(self):
        text = "def check(x): return True if x else False"
        assert _is_clarification_request(text) is False

    def test_case_insensitive_detection(self):
        text = "COULD YOU CLARIFY the requirements?"
        assert _is_clarification_request(text) is True

    def test_detects_before_i_can(self):
        text = "Before I can proceed, I need to understand the architecture."
        assert _is_clarification_request(text) is True

    def test_detects_what_type_of(self):
        text = "What type of authentication system do you want?"
        assert _is_clarification_request(text) is True
