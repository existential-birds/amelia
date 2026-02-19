import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

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
