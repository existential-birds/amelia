import json
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from amelia.core.state import AgentMessage
from amelia.drivers.cli.claude import ClaudeCliDriver
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
