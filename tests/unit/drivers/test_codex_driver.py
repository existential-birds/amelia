import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from amelia.core.exceptions import ModelProviderError, SchemaValidationError
from amelia.drivers.base import AgenticMessageType
from amelia.drivers.cli.codex import CodexApprovalMode, CodexCliDriver, CodexStreamEvent


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


@pytest.mark.asyncio
async def test_execute_agentic_skips_lifecycle_events() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    async def mock_run_codex_stream(
        prompt: str, **kwargs: Any
    ) -> AsyncIterator[CodexStreamEvent]:
        events: list[CodexStreamEvent] = [
            CodexStreamEvent(type="thread.started"),
            CodexStreamEvent(type="turn.started"),
            CodexStreamEvent(type="item.started"),
            CodexStreamEvent(type="turn.completed"),
        ]
        for event in events:
            yield event

    with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
        msgs = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

    assert msgs == []


@pytest.mark.asyncio
async def test_execute_agentic_extracts_message_from_item_completed() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    async def mock_run_codex_stream(
        prompt: str, **kwargs: Any
    ) -> AsyncIterator[CodexStreamEvent]:
        events: list[CodexStreamEvent] = [
            CodexStreamEvent(
                type="item.completed",
                item={
                    "type": "agent_message",
                    "id": "msg_1",
                    "text": "Hello world",
                },
            ),
        ]
        for event in events:
            yield event

    with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
        msgs = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

    assert len(msgs) == 1
    assert msgs[0].type == AgenticMessageType.RESULT
    assert msgs[0].content == "Hello world"


@pytest.mark.asyncio
async def test_execute_agentic_extracts_tool_call_from_item_completed() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    async def mock_run_codex_stream(
        prompt: str, **kwargs: Any
    ) -> AsyncIterator[CodexStreamEvent]:
        events: list[CodexStreamEvent] = [
            CodexStreamEvent(
                type="item.completed",
                item={
                    "type": "command_execution",
                    "id": "cmd_1",
                    "command": "cat a.py",
                    "aggregated_output": "",
                    "exit_code": None,
                    "status": "in_progress",
                },
            ),
        ]
        for event in events:
            yield event

    with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
        msgs = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

    assert len(msgs) == 1
    assert msgs[0].type == AgenticMessageType.TOOL_CALL
    assert msgs[0].tool_name == "command_execution"
    assert msgs[0].tool_input == {"command": "cat a.py"}
    assert msgs[0].tool_call_id == "cmd_1"


@pytest.mark.asyncio
async def test_execute_agentic_extracts_tool_result_from_item_completed() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    async def mock_run_codex_stream(
        prompt: str, **kwargs: Any
    ) -> AsyncIterator[CodexStreamEvent]:
        events: list[CodexStreamEvent] = [
            CodexStreamEvent(
                type="item.completed",
                item={
                    "type": "command_execution",
                    "id": "cmd_1",
                    "command": "cat a.py",
                    "aggregated_output": "file contents here",
                    "exit_code": 0,
                    "status": "completed",
                },
            ),
        ]
        for event in events:
            yield event

    with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
        msgs = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

    assert len(msgs) == 1
    assert msgs[0].type == AgenticMessageType.TOOL_RESULT
    assert msgs[0].tool_output == "file contents here"
    assert msgs[0].tool_name == "command_execution"
    assert msgs[0].tool_call_id == "cmd_1"


@pytest.mark.asyncio
async def test_run_codex_stream_uses_resume_when_session_id_provided() -> None:
    """_run_codex_stream should use 'codex exec resume <id>' when session_id is given."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    stdout_lines = [
        b'{"type": "final", "content": "resumed"}\n',
    ]
    mock_process = _create_mock_process(stdout_lines)

    captured_cmd: list[str] = []

    async def mock_create_subprocess(*args: Any, **kwargs: Any) -> MagicMock:
        captured_cmd.extend(args)
        return mock_process

    with patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess):
        events = [
            e
            async for e in driver._run_codex_stream(
                "continue", cwd="/tmp", session_id="sess_abc123"
            )
        ]

    assert len(events) == 1
    # Verify the resume subcommand was used
    assert captured_cmd[:4] == ["codex", "exec", "resume", "sess_abc123"]
    assert "--json" in captured_cmd
    assert "--" in captured_cmd
    assert "continue" in captured_cmd


@pytest.mark.asyncio
async def test_run_codex_stream_no_resume_without_session_id() -> None:
    """_run_codex_stream should use 'codex exec --json' without session_id."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    stdout_lines = [
        b'{"type": "final", "content": "new"}\n',
    ]
    mock_process = _create_mock_process(stdout_lines)

    captured_cmd: list[str] = []

    async def mock_create_subprocess(*args: Any, **kwargs: Any) -> MagicMock:
        captured_cmd.extend(args)
        return mock_process

    with patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess):
        events = [e async for e in driver._run_codex_stream("do it", cwd="/tmp")]

    assert len(events) == 1
    # Verify no resume subcommand
    assert "resume" not in captured_cmd
    assert captured_cmd[:3] == ["codex", "exec", "--json"]


@pytest.mark.asyncio
async def test_execute_agentic_captures_thread_id_in_result() -> None:
    """execute_agentic should capture thread_id from thread.started and include in RESULT."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    async def mock_run_codex_stream(
        prompt: str, **kwargs: Any
    ) -> AsyncIterator[CodexStreamEvent]:
        events: list[CodexStreamEvent] = [
            CodexStreamEvent(type="thread.started", thread_id="thread_xyz789"),
            CodexStreamEvent(type="final", content="all done"),
        ]
        for event in events:
            yield event

    with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
        msgs = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

    assert len(msgs) == 1
    assert msgs[0].type == AgenticMessageType.RESULT
    assert msgs[0].content == "all done"
    assert msgs[0].session_id == "thread_xyz789"


@pytest.mark.asyncio
async def test_execute_agentic_passes_session_id_to_stream() -> None:
    """execute_agentic should forward session_id to _run_codex_stream."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    captured_kwargs: dict[str, Any] = {}

    async def mock_run_codex_stream(
        prompt: str, **kwargs: Any
    ) -> AsyncIterator[CodexStreamEvent]:
        captured_kwargs.update(kwargs)
        events: list[CodexStreamEvent] = [
            CodexStreamEvent(type="final", content="ok"),
        ]
        for event in events:
            yield event

    with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
        msgs = [
            m
            async for m in driver.execute_agentic(
                "task", cwd="/tmp", session_id="sess_existing"
            )
        ]

    assert len(msgs) == 1
    assert captured_kwargs["session_id"] == "sess_existing"


@pytest.mark.asyncio
async def test_execute_agentic_extracts_reasoning_from_item_completed() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    async def mock_run_codex_stream(
        prompt: str, **kwargs: Any
    ) -> AsyncIterator[CodexStreamEvent]:
        events: list[CodexStreamEvent] = [
            CodexStreamEvent(
                type="item.completed",
                item={
                    "type": "reasoning",
                    "id": "r_1",
                    "text": "Let me think about this",
                },
            ),
        ]
        for event in events:
            yield event

    with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
        msgs = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

    assert len(msgs) == 1
    assert msgs[0].type == AgenticMessageType.THINKING
    assert msgs[0].content == "Let me think about this"


# ---------------------------------------------------------------------------
# CodexApprovalMode tests
# ---------------------------------------------------------------------------


def test_init_default_approval_mode_is_full_auto() -> None:
    driver = CodexCliDriver()
    assert driver.approval_mode == CodexApprovalMode.FULL_AUTO


def test_init_accepts_approval_mode_string() -> None:
    driver = CodexCliDriver(approval_mode="suggest")
    assert driver.approval_mode == CodexApprovalMode.SUGGEST


def test_init_rejects_invalid_approval_mode() -> None:
    with pytest.raises(ValueError):
        CodexCliDriver(approval_mode="yolo")


@pytest.mark.asyncio
async def test_run_codex_stream_includes_full_auto_flag() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp", approval_mode="full-auto")

    stdout_lines = [b'{"type": "final", "content": "ok"}\n']
    mock_process = _create_mock_process(stdout_lines)

    captured_cmd: list[str] = []

    async def mock_create_subprocess(*args: Any, **kwargs: Any) -> MagicMock:
        captured_cmd.extend(args)
        return mock_process

    with patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess):
        _ = [
            e
            async for e in driver._run_codex_stream(
                "test", cwd="/tmp", approval_mode=CodexApprovalMode.FULL_AUTO
            )
        ]

    assert "--full-auto" in captured_cmd
    dash_dash_idx = captured_cmd.index("--")
    assert captured_cmd.index("--full-auto") < dash_dash_idx


@pytest.mark.asyncio
async def test_run_codex_stream_includes_auto_edit_flag() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    stdout_lines = [b'{"type": "final", "content": "ok"}\n']
    mock_process = _create_mock_process(stdout_lines)

    captured_cmd: list[str] = []

    async def mock_create_subprocess(*args: Any, **kwargs: Any) -> MagicMock:
        captured_cmd.extend(args)
        return mock_process

    with patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess):
        _ = [
            e
            async for e in driver._run_codex_stream(
                "test", cwd="/tmp", approval_mode=CodexApprovalMode.AUTO_EDIT
            )
        ]

    assert "--auto-edit" in captured_cmd
    dash_dash_idx = captured_cmd.index("--")
    assert captured_cmd.index("--auto-edit") < dash_dash_idx


@pytest.mark.asyncio
async def test_run_codex_stream_suggest_mode_has_no_flag() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    stdout_lines = [b'{"type": "final", "content": "ok"}\n']
    mock_process = _create_mock_process(stdout_lines)

    captured_cmd: list[str] = []

    async def mock_create_subprocess(*args: Any, **kwargs: Any) -> MagicMock:
        captured_cmd.extend(args)
        return mock_process

    with patch.object(asyncio, "create_subprocess_exec", mock_create_subprocess):
        _ = [
            e
            async for e in driver._run_codex_stream(
                "test", cwd="/tmp", approval_mode=CodexApprovalMode.SUGGEST
            )
        ]

    assert "--full-auto" not in captured_cmd
    assert "--auto-edit" not in captured_cmd


def test_resolve_approval_mode_none_uses_constructor_default() -> None:
    driver = CodexCliDriver(approval_mode="suggest")
    assert driver._resolve_approval_mode(None) == CodexApprovalMode.SUGGEST


def test_resolve_approval_mode_readonly_tools_returns_suggest() -> None:
    driver = CodexCliDriver()
    assert driver._resolve_approval_mode(["read_file", "glob"]) == CodexApprovalMode.SUGGEST


def test_resolve_approval_mode_write_tools_returns_full_auto() -> None:
    driver = CodexCliDriver()
    result = driver._resolve_approval_mode(["read_file", "write_file", "run_shell_command"])
    assert result == CodexApprovalMode.FULL_AUTO


def test_resolve_approval_mode_write_no_shell_returns_auto_edit() -> None:
    driver = CodexCliDriver()
    assert driver._resolve_approval_mode(["read_file", "write_file"]) == CodexApprovalMode.AUTO_EDIT


@pytest.mark.asyncio
async def test_execute_agentic_passes_resolved_mode_to_stream() -> None:
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

    captured_kwargs: dict[str, Any] = {}

    async def mock_run_codex_stream(
        prompt: str, **kwargs: Any
    ) -> AsyncIterator[CodexStreamEvent]:
        captured_kwargs.update(kwargs)
        events: list[CodexStreamEvent] = [
            CodexStreamEvent(type="final", content="ok"),
        ]
        for event in events:
            yield event

    with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
        _ = [
            m
            async for m in driver.execute_agentic(
                "task", cwd="/tmp", allowed_tools=["read_file"]
            )
        ]

    assert captured_kwargs["approval_mode"] == CodexApprovalMode.SUGGEST


@pytest.mark.asyncio
async def test_generate_schema_validation_raises_schema_error() -> None:
    """Schema validation failure should raise SchemaValidationError, not ModelProviderError."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")
    # Return invalid JSON that won't match _Schema
    payload = json.dumps({"wrong_field": "value"})
    with (
        patch.object(driver, "_run_codex", new=AsyncMock(return_value=payload)),
        pytest.raises(SchemaValidationError, match="Schema validation failed"),
    ):
        await driver.generate("question", schema=_Schema)


@pytest.mark.asyncio
async def test_validate_schema_raises_schema_error() -> None:
    """_validate_schema should raise SchemaValidationError for invalid data."""
    driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")
    with pytest.raises(SchemaValidationError, match="Schema validation failed"):
        driver._validate_schema({"wrong": "data"}, _Schema, "source")


# ---------------------------------------------------------------------------
# Usage tracking tests
# ---------------------------------------------------------------------------


def _make_turn_completed_event(
    input_tokens: int, output_tokens: int, cached_input_tokens: int = 0
) -> CodexStreamEvent:
    """Build a turn.completed CodexStreamEvent with a usage dict."""
    return CodexStreamEvent(
        type="turn.completed",
        usage={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_input_tokens": cached_input_tokens,
        },
    )


class TestCodexDriverGetUsage:
    """Tests for CodexCliDriver.get_usage() before any execution."""

    def test_get_usage_returns_none_before_execution(self) -> None:
        driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")
        assert driver.get_usage() is None


class TestCodexDriverUsageAccumulation:
    """Tests for usage accumulation during execute_agentic."""

    @pytest.mark.asyncio
    async def test_accumulates_usage_across_turns(self) -> None:
        driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

        async def mock_run_codex_stream(
            prompt: str, **kwargs: Any
        ) -> AsyncIterator[CodexStreamEvent]:
            events: list[CodexStreamEvent] = [
                _make_turn_completed_event(100, 50, 10),
                _make_turn_completed_event(200, 80, 20),
                CodexStreamEvent(type="final", content="done"),
            ]
            for event in events:
                yield event

        with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
            _ = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

        usage = driver.get_usage()
        assert usage is not None
        assert usage.input_tokens == 300
        assert usage.output_tokens == 130
        assert usage.cache_read_tokens == 30
        assert usage.num_turns == 2
        assert usage.model == "gpt-5-codex"
        assert usage.duration_ms is not None
        assert usage.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_returns_none_when_no_usage_events(self) -> None:
        driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

        async def mock_run_codex_stream(
            prompt: str, **kwargs: Any
        ) -> AsyncIterator[CodexStreamEvent]:
            events: list[CodexStreamEvent] = [
                CodexStreamEvent(type="final", content="done"),
            ]
            for event in events:
                yield event

        with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
            _ = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

        assert driver.get_usage() is None

    @pytest.mark.asyncio
    async def test_tracks_duration_ms(self) -> None:
        driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

        async def mock_run_codex_stream(
            prompt: str, **kwargs: Any
        ) -> AsyncIterator[CodexStreamEvent]:
            await asyncio.sleep(0.05)
            events: list[CodexStreamEvent] = [
                _make_turn_completed_event(10, 5),
                CodexStreamEvent(type="final", content="done"),
            ]
            for event in events:
                yield event

        with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
            _ = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

        usage = driver.get_usage()
        assert usage is not None
        assert usage.duration_ms is not None
        assert usage.duration_ms >= 50

    @pytest.mark.asyncio
    async def test_resets_usage_on_new_execution(self) -> None:
        driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

        async def mock_stream_with_usage(
            prompt: str, **kwargs: Any
        ) -> AsyncIterator[CodexStreamEvent]:
            events: list[CodexStreamEvent] = [
                _make_turn_completed_event(100, 50),
                CodexStreamEvent(type="final", content="done"),
            ]
            for event in events:
                yield event

        async def mock_stream_without_usage(
            prompt: str, **kwargs: Any
        ) -> AsyncIterator[CodexStreamEvent]:
            events: list[CodexStreamEvent] = [
                CodexStreamEvent(type="final", content="done"),
            ]
            for event in events:
                yield event

        # First run: has usage
        with patch.object(driver, "_run_codex_stream", mock_stream_with_usage):
            _ = [m async for m in driver.execute_agentic("first", cwd="/tmp")]
        assert driver.get_usage() is not None

        # Second run: no usage events → get_usage returns None
        with patch.object(driver, "_run_codex_stream", mock_stream_without_usage):
            _ = [m async for m in driver.execute_agentic("second", cwd="/tmp")]
        assert driver.get_usage() is None

    @pytest.mark.asyncio
    async def test_turn_completed_without_usage_field_is_skipped(self) -> None:
        driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

        async def mock_run_codex_stream(
            prompt: str, **kwargs: Any
        ) -> AsyncIterator[CodexStreamEvent]:
            events: list[CodexStreamEvent] = [
                CodexStreamEvent(type="turn.completed"),  # no usage field
                CodexStreamEvent(type="final", content="done"),
            ]
            for event in events:
                yield event

        with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
            _ = [m async for m in driver.execute_agentic("task", cwd="/tmp")]

        assert driver.get_usage() is None


# ---------------------------------------------------------------------------
# Exception / early-exit usage tracking tests (Issue 4)
# ---------------------------------------------------------------------------


class TestCodexDriverUsageOnException:
    """Tests that usage data is captured even when streaming ends abnormally."""

    @pytest.mark.asyncio
    async def test_usage_captured_on_early_consumer_break(self) -> None:
        """Breaking out of execute_agentic early should still capture partial usage."""
        driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

        async def mock_run_codex_stream(
            prompt: str, **kwargs: Any
        ) -> AsyncIterator[CodexStreamEvent]:
            events: list[CodexStreamEvent] = [
                _make_turn_completed_event(100, 50, 10),
                _make_turn_completed_event(200, 80, 20),
                CodexStreamEvent(type="final", content="done"),
            ]
            for event in events:
                yield event

        with patch.object(driver, "_run_codex_stream", mock_run_codex_stream):
            async for _msg in driver.execute_agentic("task", cwd="/tmp"):
                break  # consume only the first yielded message

        usage = driver.get_usage()
        assert usage is not None
        # At least the first turn's tokens should be captured
        assert usage.input_tokens is not None and usage.input_tokens >= 100
        assert usage.output_tokens is not None and usage.output_tokens >= 50
        assert usage.model == "gpt-5-codex"

    @pytest.mark.asyncio
    async def test_usage_captured_on_stream_exception(self) -> None:
        """Usage accumulated before an exception should still be available."""
        driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

        async def mock_run_codex_stream(
            prompt: str, **kwargs: Any
        ) -> AsyncIterator[CodexStreamEvent]:
            yield _make_turn_completed_event(150, 60, 5)
            yield _make_turn_completed_event(250, 90, 15)
            raise RuntimeError("stream exploded")

        with (
            patch.object(driver, "_run_codex_stream", mock_run_codex_stream),
            pytest.raises(RuntimeError, match="stream exploded"),
        ):
            async for _msg in driver.execute_agentic("task", cwd="/tmp"):
                pass

        usage = driver.get_usage()
        assert usage is not None
        assert usage.input_tokens == 400
        assert usage.output_tokens == 150
        assert usage.cache_read_tokens == 20
        assert usage.num_turns == 2
        assert usage.model == "gpt-5-codex"

    @pytest.mark.asyncio
    async def test_usage_none_when_exception_before_any_turns(self) -> None:
        """If an exception fires before any turn.completed events, get_usage() is None."""
        driver = CodexCliDriver(model="gpt-5-codex", cwd="/tmp")

        async def mock_run_codex_stream(
            prompt: str, **kwargs: Any
        ) -> AsyncIterator[CodexStreamEvent]:
            raise RuntimeError("immediate failure")
            # Make this a generator (unreachable yield)
            yield CodexStreamEvent(type="final", content="never")

        with (
            patch.object(driver, "_run_codex_stream", mock_run_codex_stream),
            pytest.raises(RuntimeError, match="immediate failure"),
        ):
            async for _msg in driver.execute_agentic("task", cwd="/tmp"):
                pass

        assert driver.get_usage() is None
