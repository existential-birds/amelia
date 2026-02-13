"""Unit tests for ContainerDriver."""
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverUsage,
)


class SampleSchema(BaseModel):
    """Test schema for generate() tests."""
    goal: str
    summary: str


def _make_provider_mock(lines: list[str]) -> AsyncMock:
    """Create a mock SandboxProvider whose exec_stream returns the given lines."""
    provider = AsyncMock()
    provider.ensure_running = AsyncMock()

    call_count = 0

    async def mock_exec_stream(
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> AsyncIterator[str]:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            for line in lines:
                yield line

    provider.exec_stream = mock_exec_stream
    return provider


class TestExecuteAgentic:
    """Tests for ContainerDriver.execute_agentic()."""

    async def test_happy_path_yields_messages(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        thinking = AgenticMessage(
            type=AgenticMessageType.THINKING, content="Planning...", model="test",
        )
        result = AgenticMessage(
            type=AgenticMessageType.RESULT, content="Done", model="test",
        )
        usage_msg = AgenticMessage(
            type=AgenticMessageType.USAGE,
            usage=DriverUsage(input_tokens=100, output_tokens=50, model="test"),
        )
        lines = [
            thinking.model_dump_json(),
            result.model_dump_json(),
            usage_msg.model_dump_json(),
        ]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        messages: list[AgenticMessage] = []
        async for msg in driver.execute_agentic(prompt="do something", cwd="/work"):
            messages.append(msg)

        assert len(messages) == 2
        assert messages[0].type == AgenticMessageType.THINKING
        assert messages[0].content == "Planning..."
        assert messages[1].type == AgenticMessageType.RESULT
        assert messages[1].content == "Done"

    async def test_usage_captured(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(type=AgenticMessageType.RESULT, content="Done")
        usage = DriverUsage(input_tokens=100, output_tokens=50, model="test")
        usage_msg = AgenticMessage(type=AgenticMessageType.USAGE, usage=usage)
        lines = [result.model_dump_json(), usage_msg.model_dump_json()]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        async for _ in driver.execute_agentic(prompt="test", cwd="/work"):
            pass

        result_usage = driver.get_usage()
        assert result_usage is not None
        assert result_usage.input_tokens == 100
        assert result_usage.output_tokens == 50

    async def test_empty_prompt_raises(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        provider = _make_provider_mock([])
        driver = ContainerDriver(model="test", provider=provider)

        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            async for _ in driver.execute_agentic(prompt="", cwd="/work"):
                pass

    async def test_malformed_json_raises(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        lines = ["not valid json"]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        with pytest.raises(RuntimeError, match="Failed to parse worker output"):
            async for _ in driver.execute_agentic(prompt="test", cwd="/work"):
                pass

    async def test_prompt_file_cleanup_on_success(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(type=AgenticMessageType.RESULT, content="Done")
        lines = [result.model_dump_json()]

        calls: list[list[str]] = []
        provider = AsyncMock()
        provider.ensure_running = AsyncMock()

        call_count = 0

        async def tracking_exec_stream(
            command: list[str], **kwargs: Any,
        ) -> AsyncIterator[str]:
            nonlocal call_count
            calls.append(command)
            call_count += 1
            if call_count == 2:
                for line in lines:
                    yield line

        provider.exec_stream = tracking_exec_stream
        driver = ContainerDriver(model="test", provider=provider)

        async for _ in driver.execute_agentic(prompt="test", cwd="/work"):
            pass

        assert len(calls) == 3
        assert calls[2][0] == "rm"
        assert calls[2][1] == "-f"

    async def test_prompt_file_cleanup_on_exception(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        calls: list[list[str]] = []
        provider = AsyncMock()
        provider.ensure_running = AsyncMock()

        call_count = 0

        async def failing_exec_stream(
            command: list[str], **kwargs: Any,
        ) -> AsyncIterator[str]:
            nonlocal call_count
            calls.append(command)
            call_count += 1
            if call_count == 2:
                yield "invalid json"

        provider.exec_stream = failing_exec_stream
        driver = ContainerDriver(model="test", provider=provider)

        with pytest.raises(RuntimeError):
            async for _ in driver.execute_agentic(prompt="test", cwd="/work"):
                pass

        assert any(cmd[0] == "rm" for cmd in calls)


class TestGenerate:
    """Tests for ContainerDriver.generate()."""

    async def test_happy_path_returns_content(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(
            type=AgenticMessageType.RESULT, content="Generated text",
        )
        usage_msg = AgenticMessage(
            type=AgenticMessageType.USAGE,
            usage=DriverUsage(input_tokens=50, output_tokens=25),
        )
        lines = [result.model_dump_json(), usage_msg.model_dump_json()]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        output, session_id = await driver.generate(prompt="generate something")

        assert output == "Generated text"
        assert session_id is None

    async def test_schema_round_trip(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        schema_instance = SampleSchema(goal="build feature", summary="details")
        result = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content=schema_instance.model_dump_json(),
        )
        lines = [result.model_dump_json()]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        output, _ = await driver.generate(
            prompt="generate", schema=SampleSchema,
        )

        assert isinstance(output, SampleSchema)
        assert output.goal == "build feature"
        assert output.summary == "details"

    async def test_schema_validation_failure_raises(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(
            type=AgenticMessageType.RESULT, content="not valid json for schema",
        )
        lines = [result.model_dump_json()]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        with pytest.raises(RuntimeError, match="Failed to validate worker output"):
            await driver.generate(prompt="generate", schema=SampleSchema)

    async def test_missing_result_raises(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        thinking = AgenticMessage(
            type=AgenticMessageType.THINKING, content="Thinking...",
        )
        lines = [thinking.model_dump_json()]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        with pytest.raises(RuntimeError, match="Worker did not emit a RESULT message"):
            await driver.generate(prompt="generate")

    async def test_empty_prompt_raises(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        provider = _make_provider_mock([])
        driver = ContainerDriver(model="test", provider=provider)

        with pytest.raises(ValueError, match="Prompt cannot be empty"):
            await driver.generate(prompt="")

    async def test_usage_captured(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(type=AgenticMessageType.RESULT, content="Done")
        usage = DriverUsage(input_tokens=200, output_tokens=100, model="test")
        usage_msg = AgenticMessage(type=AgenticMessageType.USAGE, usage=usage)
        lines = [result.model_dump_json(), usage_msg.model_dump_json()]
        provider = _make_provider_mock(lines)
        driver = ContainerDriver(model="test", provider=provider)

        await driver.generate(prompt="test")

        result_usage = driver.get_usage()
        assert result_usage is not None
        assert result_usage.input_tokens == 200


class TestCleanupSession:
    async def test_returns_false(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        provider = _make_provider_mock([])
        driver = ContainerDriver(model="test", provider=provider)

        result = await driver.cleanup_session("any-session-id")
        assert result is False


class TestGetUsage:
    def test_returns_none_before_execution(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        provider = _make_provider_mock([])
        driver = ContainerDriver(model="test", provider=provider)

        assert driver.get_usage() is None


class TestWorkflowId:
    """Tests for workflow_id propagation to prompt filenames."""

    async def test_execute_agentic_uses_workflow_id(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(type=AgenticMessageType.RESULT, content="Done")
        lines = [result.model_dump_json()]

        calls: list[tuple[list[str], dict]] = []
        provider = AsyncMock()
        provider.ensure_running = AsyncMock()

        call_count = 0

        async def tracking_exec_stream(
            command: list[str], **kwargs: Any,
        ) -> AsyncIterator[str]:
            nonlocal call_count
            calls.append((command, kwargs))
            call_count += 1
            if call_count == 2:
                for line in lines:
                    yield line

        provider.exec_stream = tracking_exec_stream
        driver = ContainerDriver(model="test", provider=provider)

        async for _ in driver.execute_agentic(
            prompt="test", cwd="/work", workflow_id="wf-abc",
        ):
            pass

        # calls[0] is the tee command for _write_prompt
        tee_cmd = calls[0][0]
        assert tee_cmd[0] == "tee"
        assert tee_cmd[1] == "/tmp/prompt-wf-abc.txt"

    async def test_generate_uses_workflow_id(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(
            type=AgenticMessageType.RESULT, content="Generated",
        )
        lines = [result.model_dump_json()]

        calls: list[tuple[list[str], dict]] = []
        provider = AsyncMock()
        provider.ensure_running = AsyncMock()

        call_count = 0

        async def tracking_exec_stream(
            command: list[str], **kwargs: Any,
        ) -> AsyncIterator[str]:
            nonlocal call_count
            calls.append((command, kwargs))
            call_count += 1
            if call_count == 2:
                for line in lines:
                    yield line

        provider.exec_stream = tracking_exec_stream
        driver = ContainerDriver(model="test", provider=provider)

        await driver.generate(prompt="test", workflow_id="wf-xyz")

        # calls[0] is the tee command for _write_prompt
        tee_cmd = calls[0][0]
        assert tee_cmd[0] == "tee"
        assert tee_cmd[1] == "/tmp/prompt-wf-xyz.txt"

    async def test_falls_back_to_random_when_no_workflow_id(self) -> None:
        from amelia.sandbox.driver import ContainerDriver

        result = AgenticMessage(type=AgenticMessageType.RESULT, content="Done")
        lines = [result.model_dump_json()]

        calls: list[tuple[list[str], dict]] = []
        provider = AsyncMock()
        provider.ensure_running = AsyncMock()

        call_count = 0

        async def tracking_exec_stream(
            command: list[str], **kwargs: Any,
        ) -> AsyncIterator[str]:
            nonlocal call_count
            calls.append((command, kwargs))
            call_count += 1
            if call_count == 2:
                for line in lines:
                    yield line

        provider.exec_stream = tracking_exec_stream
        driver = ContainerDriver(model="test", provider=provider)

        async for _ in driver.execute_agentic(prompt="test", cwd="/work"):
            pass

        # calls[0] is the tee command for _write_prompt
        tee_cmd = calls[0][0]
        assert tee_cmd[0] == "tee"
        # Without workflow_id, should use a random hex suffix
        prompt_path = tee_cmd[1]
        assert prompt_path.startswith("/tmp/prompt-")
        assert prompt_path.endswith(".txt")
        # The random suffix should not be "wf-" prefixed
        suffix = prompt_path.removeprefix("/tmp/prompt-").removesuffix(".txt")
        assert len(suffix) == 12  # uuid4().hex[:12]
