import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from amelia.core.exceptions import ModelProviderError
from amelia.drivers.base import AgenticMessageType
from amelia.drivers.cli.codex import CodexCliDriver, CodexStreamEvent


class _Schema(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_generate_returns_text() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")
    with patch.object(driver, "_run_codex", new=AsyncMock(return_value='{"result":"ok"}')):
        text, session_id = await driver.generate("ping")
    assert text == "ok"
    assert session_id is None


@pytest.mark.asyncio
async def test_generate_parses_schema() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")
    payload = json.dumps({"answer": "42"})
    with patch.object(driver, "_run_codex", new=AsyncMock(return_value=payload)):
        result, _ = await driver.generate("question", schema=_Schema)
    assert isinstance(result, _Schema)
    assert result.answer == "42"


@pytest.mark.asyncio
async def test_generate_parses_jsonl_output() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")
    payload = '\n'.join(
        [
            '{"type":"reasoning","content":"thinking"}',
            '{"type":"final","content":"ok"}',
        ]
    )
    with patch.object(driver, "_run_codex", new=AsyncMock(return_value=payload)):
        text, session_id = await driver.generate("ping")
    assert text == "ok"
    assert session_id is None


@pytest.mark.asyncio
async def test_execute_agentic_maps_stream_events() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    async def mock_run_codex_stream(
        prompt: str, **kwargs: Any
    ) -> AsyncIterator[CodexStreamEvent]:
        events: list[CodexStreamEvent] = [
            CodexStreamEvent(type="reasoning", content="thinking"),
            CodexStreamEvent(type="tool_call", name="read_file", input={"path": "a.py"}, id="1"),
            CodexStreamEvent(type="tool_result", name="read_file", output="ok", id="1"),
            CodexStreamEvent(type="final", content="done"),
        ]
        for event in events:
            yield event

    with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
        msgs = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

    assert [m.type for m in msgs] == [
        AgenticMessageType.THINKING,
        AgenticMessageType.TOOL_CALL,
        AgenticMessageType.TOOL_RESULT,
        AgenticMessageType.RESULT,
    ]
    assert msgs[2].tool_output == "ok"


@pytest.mark.asyncio
async def test_cleanup_session_is_false() -> None:
    driver = CodexCliDriver(model="gpt-5-codex")
    assert await driver.cleanup_session("any") is False


def _create_mock_process(
    stdout_lines: list[bytes], returncode: int = 0, stderr_bytes: bytes = b""
) -> MagicMock:
    """Create a mock async subprocess with given stdout lines."""
    mock_process = MagicMock()
    mock_process.returncode = returncode

    # Create an async readline that returns lines one by one, then empty
    line_index = 0

    async def mock_readline() -> bytes:
        nonlocal line_index
        if line_index < len(stdout_lines):
            line = stdout_lines[line_index]
            line_index += 1
            return line
        return b""

    mock_stdout = MagicMock()
    mock_stdout.readline = mock_readline
    mock_process.stdout = mock_stdout

    async def mock_read() -> bytes:
        return stderr_bytes

    mock_stderr = MagicMock()
    mock_stderr.read = mock_read
    mock_process.stderr = mock_stderr

    async def mock_wait() -> int:
        return returncode

    mock_process.wait = mock_wait

    return mock_process


@pytest.mark.asyncio
async def test_run_codex_stream_yields_parsed_ndjson_events() -> None:
    """_run_codex_stream should spawn async subprocess and yield parsed NDJSON lines."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    stdout_lines = [
        b'{"type": "reasoning", "content": "thinking hard"}\n',
        b'{"type": "tool_call", "name": "read_file", "input": {"path": "a.py"}, "id": "t1"}\n',
        b'{"type": "tool_result", "name": "read_file", "output": "content", "id": "t1"}\n',
        b'{"type": "final", "content": "done"}\n',
    ]

    mock_process = _create_mock_process(stdout_lines)

    async def mock_create_subprocess(*args: Any, **kwargs: Any) -> MagicMock:
        return mock_process

    with patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess):
        events = [e async for e in driver._run_codex_stream("do something", cwd="/tmp")]

    assert len(events) == 4
    assert events[0].type == "reasoning"
    assert events[0].content == "thinking hard"
    assert events[1].type == "tool_call"
    assert events[1].name == "read_file"
    assert events[3].type == "final"
    assert events[3].content == "done"


@pytest.mark.asyncio
async def test_run_codex_stream_skips_malformed_json_lines() -> None:
    """_run_codex_stream should skip lines that are not valid JSON."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    stdout_lines = [
        b"not valid json\n",
        b'{"type": "final", "content": "ok"}\n',
    ]

    mock_process = _create_mock_process(stdout_lines)

    async def mock_create_subprocess(*args: Any, **kwargs: Any) -> MagicMock:
        return mock_process

    with patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess):
        events = [e async for e in driver._run_codex_stream("do something", cwd="/tmp")]

    assert len(events) == 1
    assert events[0].type == "final"
    assert events[0].content == "ok"


@pytest.mark.asyncio
async def test_run_codex_stream_raises_on_nonzero_exit() -> None:
    """_run_codex_stream should raise ModelProviderError on non-zero exit code."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    mock_process = _create_mock_process([], returncode=1, stderr_bytes=b"codex crashed")

    async def mock_create_subprocess(*args: Any, **kwargs: Any) -> MagicMock:
        return mock_process

    with (
        patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess),
        pytest.raises(ModelProviderError, match="Codex CLI streaming failed"),
    ):
        _ = [e async for e in driver._run_codex_stream("do something", cwd="/tmp")]
