import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pydantic import BaseModel
from typing import List

from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.core.state import AgentMessage

# Dummy Pydantic model for testing schema validation
class _TestModel(BaseModel):
    reasoning: str
    answer: str

class _TestListModel(BaseModel):
    tasks: List[str]

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
    async def test_generate_text_success(self, driver, messages):
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            # Setup mock process
            mock_process = AsyncMock()
            mock_process.stdin = MagicMock()  # Mock stdin as MagicMock (synchronous methods)
            mock_process.stdin.drain = AsyncMock() # drain is awaitable
            mock_process.stdout.readline.side_effect = [b"I am fine, ", b"thank you.", b""]
            mock_process.stderr.read.return_value = b""
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            response = await driver._generate_impl(messages)

            assert response == "I am fine, thank you."
            
            # Verify subprocess call
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert args[0] == "claude"
            assert args[1] == "-p"
            assert "stdin" in mock_exec.call_args[1]
            mock_process.stdin.write.assert_called_once()
            mock_process.stdin.drain.assert_called_once()
            mock_process.stdin.close.assert_called_once()


    @pytest.mark.asyncio
    async def test_generate_json_success(self, driver, messages):
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            # Setup mock process
            mock_process = AsyncMock()
            mock_process.stdin = MagicMock()  # Mock stdin as MagicMock
            mock_process.stdin.drain = AsyncMock()
            expected_json = json.dumps({"reasoning": "ok", "answer": "good"})
            mock_process.stdout.readline.side_effect = [expected_json.encode(), b""]
            mock_process.stderr.read.return_value = b""
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            response = await driver._generate_impl(messages, schema=_TestModel)

            assert isinstance(response, _TestModel)
            assert response.reasoning == "ok"
            assert response.answer == "good"

            # Verify subprocess call includes json schema
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "--json-schema" in args
            assert "--output-format" in args
            assert args[args.index("--output-format") + 1] == "json"
            mock_process.stdin.write.assert_called_once()
            mock_process.stdin.drain.assert_called_once()
            mock_process.stdin.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_json_list_auto_wrap(self, driver, messages):
        """Test that a raw list from CLI is auto-wrapped if schema expects 'tasks'."""
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            # Setup mock process returning a raw list
            mock_process = AsyncMock()
            mock_process.stdin = MagicMock()  # Mock stdin as MagicMock
            mock_process.stdin.drain = AsyncMock()
            expected_list_json = json.dumps(["task1", "task2"])
            mock_process.stdout.readline.side_effect = [expected_list_json.encode(), b""]
            mock_process.stderr.read.return_value = b""
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            # Use a schema that expects {"tasks": [...]}
            response = await driver._generate_impl(messages, schema=_TestListModel)

            assert isinstance(response, _TestListModel)
            assert response.tasks == ["task1", "task2"]
            mock_process.stdin.write.assert_called_once()
            mock_process.stdin.drain.assert_called_once()
            mock_process.stdin.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_failure_stderr(self, driver, messages):
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            # Setup mock process
            mock_process = AsyncMock()
            mock_process.stdin = MagicMock()  # Mock stdin as MagicMock
            mock_process.stdin.drain = AsyncMock()
            mock_process.stdout.readline.side_effect = [b""]
            mock_process.stderr.read.return_value = b"Some CLI error occurred"
            mock_process.returncode = 1
            mock_exec.return_value = mock_process

            with pytest.raises(RuntimeError, match="Claude CLI failed with return code 1"):
                await driver._generate_impl(messages)
            mock_process.stdin.write.assert_called_once()
            mock_process.stdin.drain.assert_called_once()
            mock_process.stdin.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_json_parse_error(self, driver, messages):
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            # Setup mock process
            mock_process = AsyncMock()
            mock_process.stdin = MagicMock()  # Mock stdin as MagicMock
            mock_process.stdin.drain = AsyncMock()
            mock_process.stdout.readline.side_effect = [b"Not JSON", b""]
            mock_process.stderr.read.return_value = b""
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            with pytest.raises(RuntimeError, match="Failed to parse JSON"):
                await driver._generate_impl(messages, schema=_TestModel)
            mock_process.stdin.write.assert_called_once()
            mock_process.stdin.drain.assert_called_once()
            mock_process.stdin.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_tool_shell(self, driver):
        with patch("amelia.drivers.cli.claude.run_shell_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "Output"
            result = await driver._execute_tool_impl("run_shell_command", command="echo test")
            assert result == "Output"
            mock_run.assert_called_once_with("echo test", timeout=driver.timeout)

    @pytest.mark.asyncio
    async def test_execute_tool_write_file(self, driver):
        with patch("amelia.drivers.cli.claude.write_file", new_callable=AsyncMock) as mock_write:
            mock_write.return_value = "Success"
            result = await driver._execute_tool_impl("write_file", file_path="test.txt", content="data")
            assert result == "Success"
            mock_write.assert_called_once_with("test.txt", "data")

    @pytest.mark.asyncio
    async def test_execute_tool_unknown(self, driver):
        with pytest.raises(NotImplementedError):
            await driver._execute_tool_impl("unknown_tool")
