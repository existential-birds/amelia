"""Tests for Oracle agent."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from amelia.agents.oracle import Oracle, OracleConsultResult
from amelia.core.types import AgentConfig
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType
from tests.conftest import create_mock_execute_agentic


class TestOracleInit:
    """Tests for Oracle initialization."""

    def test_init_creates_driver(self):
        """Oracle should create a driver from AgentConfig."""
        config = AgentConfig(driver="cli", model="sonnet")

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_get_driver.return_value = mock_driver

            oracle = Oracle(config)

            mock_get_driver.assert_called_once_with("cli", model="sonnet")
            assert oracle._driver is mock_driver

    def test_init_accepts_event_bus(self):
        """Oracle should accept an optional EventBus."""
        config = AgentConfig(driver="cli", model="sonnet")
        event_bus = EventBus()

        with patch("amelia.agents.oracle.get_driver"):
            oracle = Oracle(config, event_bus=event_bus)
            assert oracle._event_bus is event_bus


class TestOracleConsult:
    """Tests for Oracle.consult() method."""

    async def test_consult_returns_result(self, tmp_path):
        """consult() should return OracleConsultResult with advice."""
        config = AgentConfig(driver="cli", model="sonnet")

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.execute_agentic = create_mock_execute_agentic([
                AgenticMessage(type=AgenticMessageType.THINKING, content="Analyzing..."),
                AgenticMessage(type=AgenticMessageType.RESULT, content="Use dependency injection."),
            ])
            mock_get_driver.return_value = mock_driver

            oracle = Oracle(config)
            result = await oracle.consult(
                problem="How to refactor auth?",
                working_dir=str(tmp_path),
            )

        assert isinstance(result, OracleConsultResult)
        assert result.advice == "Use dependency injection."
        assert result.consultation.problem == "How to refactor auth?"
        assert result.consultation.outcome == "success"
        assert result.consultation.session_id  # Should be a UUID

    async def test_consult_skips_bundling_without_files(self, tmp_path):
        """consult() should not call bundle_files when files is None."""
        config = AgentConfig(driver="cli", model="sonnet")

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.execute_agentic = create_mock_execute_agentic([
                AgenticMessage(type=AgenticMessageType.RESULT, content="Done"),
            ])
            mock_get_driver.return_value = mock_driver

            with patch("amelia.agents.oracle.bundle_files", new_callable=AsyncMock) as mock_bundle:
                oracle = Oracle(config)
                result = await oracle.consult(
                    problem="Analyze",
                    working_dir=str(tmp_path),
                )

                mock_bundle.assert_not_called()

        assert result.consultation.files_consulted == []
        assert result.consultation.tokens == {"context": 0}

    async def test_consult_passes_files_to_bundler(self, tmp_path):
        """consult() should pass file patterns to bundle_files."""
        config = AgentConfig(driver="cli", model="sonnet")

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.execute_agentic = create_mock_execute_agentic([
                AgenticMessage(type=AgenticMessageType.RESULT, content="Done"),
            ])
            mock_get_driver.return_value = mock_driver

            with patch("amelia.agents.oracle.bundle_files", new_callable=AsyncMock) as mock_bundle:
                from amelia.tools.file_bundler import FileBundle

                mock_bundle.return_value = FileBundle(
                    files=[], total_tokens=0, working_dir=str(tmp_path),
                )

                oracle = Oracle(config)
                await oracle.consult(
                    problem="Analyze",
                    working_dir=str(tmp_path),
                    files=["src/**/*.py"],
                )

                mock_bundle.assert_called_once_with(
                    working_dir=str(tmp_path),
                    patterns=["src/**/*.py"],
                )

    async def test_consult_emits_events(self, tmp_path):
        """consult() should emit start, thinking, and complete events."""
        config = AgentConfig(driver="cli", model="sonnet")
        event_bus = EventBus()
        emitted: list[Any] = []
        event_bus.subscribe(lambda e: emitted.append(e))

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.execute_agentic = create_mock_execute_agentic([
                AgenticMessage(type=AgenticMessageType.THINKING, content="Hmm"),
                AgenticMessage(type=AgenticMessageType.RESULT, content="Advice"),
            ])
            mock_get_driver.return_value = mock_driver

            oracle = Oracle(config, event_bus=event_bus)
            await oracle.consult(
                problem="Test",
                working_dir=str(tmp_path),
            )

        event_types = [e.event_type for e in emitted]
        assert EventType.ORACLE_CONSULTATION_STARTED in event_types
        assert EventType.ORACLE_CONSULTATION_COMPLETED in event_types

    async def test_consult_events_carry_session_id(self, tmp_path):
        """Emitted events should carry session_id independent from workflow_id."""
        config = AgentConfig(driver="cli", model="sonnet")
        event_bus = EventBus()
        emitted: list[Any] = []
        event_bus.subscribe(lambda e: emitted.append(e))

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.execute_agentic = create_mock_execute_agentic([
                AgenticMessage(type=AgenticMessageType.RESULT, content="Advice"),
            ])
            mock_get_driver.return_value = mock_driver

            oracle = Oracle(config, event_bus=event_bus)
            result = await oracle.consult(
                problem="Test",
                working_dir=str(tmp_path),
            )

        session_id = result.consultation.session_id
        assert session_id  # Should be a UUID

        # All emitted events should carry the session_id
        for event in emitted:
            assert event.session_id == session_id, (
                f"Event {event.event_type} missing session_id"
            )
            # workflow_id should also be set (falls back to session_id)
            assert event.workflow_id == session_id

    async def test_consult_emits_tool_call_events(self, tmp_path):
        """consult() should emit tool call and tool result events."""
        config = AgentConfig(driver="cli", model="sonnet")
        event_bus = EventBus()
        emitted: list[Any] = []
        event_bus.subscribe(lambda e: emitted.append(e))

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_driver.execute_agentic = create_mock_execute_agentic([
                AgenticMessage(type=AgenticMessageType.THINKING, content="Let me check..."),
                AgenticMessage(
                    type=AgenticMessageType.TOOL_CALL,
                    tool_name="read_file",
                    tool_input={"path": "src/main.py"},
                    tool_call_id="call-1",
                ),
                AgenticMessage(
                    type=AgenticMessageType.TOOL_RESULT,
                    tool_name="read_file",
                    tool_output="file contents here",
                    tool_call_id="call-1",
                ),
                AgenticMessage(type=AgenticMessageType.RESULT, content="Use injection."),
            ])
            mock_get_driver.return_value = mock_driver

            oracle = Oracle(config, event_bus=event_bus)
            result = await oracle.consult(
                problem="How to refactor?",
                working_dir=str(tmp_path),
            )

        event_types = [e.event_type for e in emitted]
        assert EventType.ORACLE_TOOL_CALL in event_types
        assert EventType.ORACLE_TOOL_RESULT in event_types

        # Verify tool call event details
        tool_call_events = [e for e in emitted if e.event_type == EventType.ORACLE_TOOL_CALL]
        assert len(tool_call_events) == 1
        assert tool_call_events[0].message == "Tool call: read_file"
        assert tool_call_events[0].tool_name == "read_file"
        assert tool_call_events[0].tool_input == {"path": "src/main.py"}

        # Verify tool result event details
        tool_result_events = [e for e in emitted if e.event_type == EventType.ORACLE_TOOL_RESULT]
        assert len(tool_result_events) == 1
        assert tool_result_events[0].message == "Tool result: read_file"
        assert tool_result_events[0].tool_name == "read_file"
        assert tool_result_events[0].is_error is False

        # Verify advice is still captured correctly
        assert result.advice == "Use injection."

    async def test_consult_handles_driver_error(self, tmp_path):
        """consult() should return error outcome on driver failure."""
        config = AgentConfig(driver="cli", model="sonnet")

        with patch("amelia.agents.oracle.get_driver") as mock_get_driver:
            mock_driver = MagicMock()

            async def _failing_agentic(*args, **kwargs):
                raise RuntimeError("Driver crashed")
                yield  # noqa: RET503 -- makes this an async generator

            mock_driver.execute_agentic = _failing_agentic
            mock_get_driver.return_value = mock_driver

            oracle = Oracle(config)
            result = await oracle.consult(
                problem="Test",
                working_dir=str(tmp_path),
            )

        assert result.consultation.outcome == "error"
        assert "Driver crashed" in (result.consultation.error_message or "")
        assert result.advice == ""
        assert result.consultation.tokens == {"context": 0}

    async def test_consult_handles_bundling_error(self, tmp_path):
        """consult() should return error outcome on file bundling failure."""
        config = AgentConfig(driver="cli", model="sonnet")

        with (
            patch("amelia.agents.oracle.get_driver") as mock_get_driver,
            patch("amelia.agents.oracle.bundle_files") as mock_bundle,
        ):
            mock_driver = MagicMock()
            mock_get_driver.return_value = mock_driver
            mock_bundle.side_effect = OSError("Permission denied: /secret")

            oracle = Oracle(config)
            result = await oracle.consult(
                problem="Test",
                working_dir=str(tmp_path),
                files=["*.py"],
            )

        assert result.consultation.outcome == "error"
        assert "File bundling failed" in (result.consultation.error_message or "")
        assert "Permission denied" in (result.consultation.error_message or "")
        assert result.advice == ""
        assert result.consultation.files_consulted == []

    async def test_consult_emits_failed_event_on_bundling_error(self, tmp_path):
        """consult() should emit STARTED and FAILED events on bundling failure."""
        config = AgentConfig(driver="cli", model="sonnet")
        event_bus = EventBus()
        emitted: list[Any] = []
        event_bus.subscribe(lambda e: emitted.append(e))

        with (
            patch("amelia.agents.oracle.get_driver") as mock_get_driver,
            patch("amelia.agents.oracle.bundle_files") as mock_bundle,
        ):
            mock_driver = MagicMock()
            mock_get_driver.return_value = mock_driver
            mock_bundle.side_effect = OSError("Disk full")

            oracle = Oracle(config, event_bus=event_bus)
            await oracle.consult(
                problem="Test",
                working_dir=str(tmp_path),
                files=["*.py"],
            )

        event_types = [e.event_type for e in emitted]
        assert EventType.ORACLE_CONSULTATION_STARTED in event_types
        assert EventType.ORACLE_CONSULTATION_FAILED in event_types
        assert EventType.ORACLE_CONSULTATION_COMPLETED not in event_types
