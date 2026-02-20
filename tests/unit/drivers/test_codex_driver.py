import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from amelia.core.exceptions import ModelProviderError
from amelia.drivers.base import AgenticMessageType
from amelia.drivers.cli.codex import CodexCliDriver


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
async def test_execute_agentic_maps_stream_events() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")
    with patch.object(
        driver,
        "_run_codex_stream",
        return_value=iter([
            {"type": "reasoning", "content": "thinking"},
            {"type": "tool_call", "name": "read_file", "input": {"path": "a.py"}, "id": "1"},
            {"type": "tool_result", "name": "read_file", "output": "ok", "id": "1"},
            {"type": "final", "content": "done"},
        ]),
    ):
        msgs = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

    assert [m.type for m in msgs] == [
        AgenticMessageType.THINKING,
        AgenticMessageType.TOOL_CALL,
        AgenticMessageType.TOOL_RESULT,
        AgenticMessageType.RESULT,
    ]


@pytest.mark.asyncio
async def test_cleanup_session_is_false() -> None:
    driver = CodexCliDriver(model="gpt-5-codex")
    assert await driver.cleanup_session("any") is False


def test_run_codex_stream_yields_parsed_ndjson_events() -> None:
    """_run_codex_stream should spawn codex subprocess and yield parsed NDJSON lines."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    ndjson_output = (
        '{"type": "reasoning", "content": "thinking hard"}\n'
        '{"type": "tool_call", "name": "read_file", "input": {"path": "a.py"}, "id": "t1"}\n'
        '{"type": "tool_result", "name": "read_file", "output": "content", "id": "t1"}\n'
        '{"type": "final", "content": "done"}\n'
    )

    mock_process = MagicMock()
    mock_process.stdout = [line + b"\n" for line in ndjson_output.encode().split(b"\n") if line]
    mock_process.returncode = 0
    mock_process.wait.return_value = 0

    with patch("subprocess.Popen", return_value=mock_process):
        events = list(driver._run_codex_stream("do something", cwd="/tmp"))

    assert len(events) == 4
    assert events[0] == {"type": "reasoning", "content": "thinking hard"}
    assert events[1]["type"] == "tool_call"
    assert events[1]["name"] == "read_file"
    assert events[3] == {"type": "final", "content": "done"}


def test_run_codex_stream_skips_malformed_json_lines() -> None:
    """_run_codex_stream should skip lines that are not valid JSON."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    ndjson_output = (
        'not valid json\n'
        '{"type": "final", "content": "ok"}\n'
    )

    mock_process = MagicMock()
    mock_process.stdout = [line + b"\n" for line in ndjson_output.encode().split(b"\n") if line]
    mock_process.returncode = 0
    mock_process.wait.return_value = 0

    with patch("subprocess.Popen", return_value=mock_process):
        events = list(driver._run_codex_stream("do something", cwd="/tmp"))

    assert len(events) == 1
    assert events[0] == {"type": "final", "content": "ok"}


def test_run_codex_stream_raises_on_nonzero_exit() -> None:
    """_run_codex_stream should raise ModelProviderError on non-zero exit code."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    mock_process = MagicMock()
    mock_process.stdout = []
    mock_process.stderr = MagicMock()
    mock_process.stderr.read.return_value = b"codex crashed"
    mock_process.returncode = 1
    mock_process.wait.return_value = 1

    with patch("subprocess.Popen", return_value=mock_process):
        with pytest.raises(ModelProviderError, match="Codex CLI streaming failed"):
            list(driver._run_codex_stream("do something", cwd="/tmp"))
