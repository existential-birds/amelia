"""Tests for call_developer_node using profile from config."""

from collections.abc import AsyncGenerator, Callable, Sequence
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.orchestrator import call_developer_node
from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.server.models.events import EventType


def create_mock_execute_agentic(
    messages: Sequence[AgenticMessage],
) -> Callable[..., AsyncGenerator[AgenticMessage, None]]:
    """Create a mock execute_agentic async generator function.

    This helper reduces boilerplate in tests that need to mock driver.execute_agentic().
    Each test can specify the AgenticMessage objects to yield.

    Args:
        messages: Sequence of AgenticMessage objects to yield.

    Returns:
        An async generator function that yields the provided messages.

    Example:
        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(type=AgenticMessageType.THINKING, content="..."),
            AgenticMessage(type=AgenticMessageType.RESULT, content="Done"),
        ])
    """
    async def mock_execute_agentic(*args: Any, **kwargs: Any) -> AsyncGenerator[AgenticMessage, None]:
        for msg in messages:
            yield msg

    return mock_execute_agentic


class TestDeveloperNodeProfileFromConfig:
    """Tests for call_developer_node using profile from config."""

    async def test_developer_node_uses_profile_from_config(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
    ) -> None:
        """call_developer_node should get profile from config, not state."""
        profile = mock_profile_factory()
        issue = mock_issue_factory()

        # State has profile_id, not profile object
        # Uses goal and plan_markdown instead of execution_plan
        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test goal",
            plan_markdown="# Test Plan\n\n## Phase 1\n\n### Task 1.1\n\nTest step",
        )

        # Profile is in config
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-test",
                "profile": profile,
            }
        }

        # Mock the Developer to avoid actual execution
        with patch("amelia.core.orchestrator.Developer") as mock_dev:
            mock_dev_instance = MagicMock()
            # Developer.run is now an async generator
            async def mock_run(*args, **kwargs):
                yield state, MagicMock(type="thinking", content="test")
            mock_dev_instance.run = mock_run
            mock_dev.return_value = mock_dev_instance

            # Should not raise, should use profile from config
            await call_developer_node(state, config)

            # Verify Developer was created with profile from config
            mock_dev.assert_called_once()


class TestDeveloperUnifiedExecution:
    """Tests for Developer agent unified AgenticMessage processing.

    Verifies that Developer uses unified _run_agentic() without isinstance
    checks on driver types, processing AgenticMessage stream consistently.
    """

    async def test_developer_does_not_use_isinstance_on_driver_types(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
    ) -> None:
        """Developer.run should not check driver type with isinstance.

        The unified execution path should work with any driver that yields
        AgenticMessage without checking if it's ClaudeCliDriver or ApiDriver.
        """
        from amelia.agents.developer import Developer
        from amelia.drivers.base import DriverInterface

        profile = mock_profile_factory()
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Implement a feature",
        )

        # Create a mock driver that yields AgenticMessage
        mock_driver = MagicMock(spec=DriverInterface)
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Analyzing the task...",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="Read",
                tool_input={"file_path": "/some/file.py"},
                tool_call_id="call-1",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="Read",
                tool_output="file contents here",
                tool_call_id="call-1",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Task completed successfully",
                session_id="session-123",
            ),
        ])

        developer = Developer(driver=mock_driver)

        # Collect all yielded results
        results = []
        async for state_update, event in developer.run(state, profile, "wf-test"):
            results.append((state_update, event))

        # Should have yielded events for each AgenticMessage
        assert len(results) >= 3  # At least thinking, tool_call, result

        # Verify it didn't try to import driver types
        # (If it did and failed, we'd get an error)

    async def test_developer_processes_thinking_message(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
    ) -> None:
        """Developer should convert THINKING AgenticMessage to WorkflowEvent."""
        from amelia.agents.developer import Developer

        profile = mock_profile_factory()
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test goal",
        )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Thinking about the problem...",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Done",
                session_id=None,
            ),
        ])

        developer = Developer(driver=mock_driver)

        results = []
        async for state_update, event in developer.run(state, profile, "wf-test"):
            results.append((state_update, event))

        # Find the thinking event
        thinking_events = [r for r in results if r[1].event_type == EventType.CLAUDE_THINKING]
        assert len(thinking_events) >= 1
        assert thinking_events[0][1].message == "Thinking about the problem..."
        assert thinking_events[0][1].agent == "developer"
        assert thinking_events[0][1].workflow_id == "wf-test"

    async def test_developer_processes_tool_call_message(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
    ) -> None:
        """Developer should convert TOOL_CALL AgenticMessage to WorkflowEvent."""
        from amelia.agents.developer import Developer

        profile = mock_profile_factory()
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test goal",
        )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="Write",
                tool_input={"file_path": "/test/file.py", "content": "print('hello')"},
                tool_call_id="call-123",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Done",
                session_id=None,
            ),
        ])

        developer = Developer(driver=mock_driver)

        results = []
        async for state_update, event in developer.run(state, profile, "wf-test"):
            results.append((state_update, event))

        # Find the tool call event
        tool_call_events = [r for r in results if r[1].event_type == EventType.CLAUDE_TOOL_CALL]
        assert len(tool_call_events) >= 1
        assert tool_call_events[0][1].tool_name == "Write"
        assert tool_call_events[0][1].tool_input == {"file_path": "/test/file.py", "content": "print('hello')"}

    async def test_developer_processes_tool_result_message(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
    ) -> None:
        """Developer should convert TOOL_RESULT AgenticMessage to WorkflowEvent."""
        from amelia.agents.developer import Developer

        profile = mock_profile_factory()
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test goal",
        )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="Read",
                tool_output="File content here",
                tool_call_id="call-456",
                is_error=False,
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Done",
                session_id=None,
            ),
        ])

        developer = Developer(driver=mock_driver)

        results = []
        async for state_update, event in developer.run(state, profile, "wf-test"):
            results.append((state_update, event))

        # Find the tool result event
        tool_result_events = [r for r in results if r[1].event_type == EventType.CLAUDE_TOOL_RESULT]
        assert len(tool_result_events) >= 1
        assert tool_result_events[0][1].message == "Tool Read completed"

    async def test_developer_processes_result_message(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
    ) -> None:
        """Developer should convert RESULT AgenticMessage to WorkflowEvent and update state."""
        from amelia.agents.developer import Developer

        profile = mock_profile_factory()
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test goal",
        )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Task completed successfully",
                session_id="session-abc",
                is_error=False,
            ),
        ])

        developer = Developer(driver=mock_driver)

        results = []
        async for state_update, event in developer.run(state, profile, "wf-test"):
            results.append((state_update, event))

        # Find the agent output event
        output_events = [r for r in results if r[1].event_type == EventType.AGENT_OUTPUT]
        assert len(output_events) >= 1
        assert output_events[0][1].message == "Task completed successfully"

        # Check final state
        final_state = results[-1][0]
        assert final_state.agentic_status == "completed"
        assert final_state.final_response == "Task completed successfully"
        assert final_state.driver_session_id == "session-abc"

    async def test_developer_handles_error_result(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
    ) -> None:
        """Developer should handle is_error=True in RESULT message."""
        from amelia.agents.developer import Developer

        profile = mock_profile_factory()
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test goal",
        )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Error: Something went wrong",
                session_id="session-err",
                is_error=True,
            ),
        ])

        developer = Developer(driver=mock_driver)

        results = []
        async for state_update, event in developer.run(state, profile, "wf-test"):
            results.append((state_update, event))

        # Check final state reflects error
        final_state = results[-1][0]
        assert final_state.agentic_status == "failed"
        assert final_state.error == "Error: Something went wrong"

    async def test_developer_tracks_tool_calls_in_state(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
    ) -> None:
        """Developer should accumulate tool calls in state."""
        from amelia.agents.developer import Developer

        profile = mock_profile_factory()
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test goal",
        )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="Read",
                tool_input={"file_path": "/a.py"},
                tool_call_id="call-1",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="Write",
                tool_input={"file_path": "/b.py", "content": "code"},
                tool_call_id="call-2",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Done",
                session_id=None,
            ),
        ])

        developer = Developer(driver=mock_driver)

        results = []
        async for state_update, event in developer.run(state, profile, "wf-test"):
            results.append((state_update, event))

        # Check final state has tool calls
        final_state = results[-1][0]
        assert len(final_state.tool_calls) >= 2
        tool_names = [tc.tool_name for tc in final_state.tool_calls]
        assert "Read" in tool_names
        assert "Write" in tool_names

    async def test_developer_tracks_tool_results_in_state(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
    ) -> None:
        """Developer should accumulate tool results in state."""
        from amelia.agents.developer import Developer

        profile = mock_profile_factory()
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test goal",
        )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="Read",
                tool_output="file content 1",
                tool_call_id="call-1",
                is_error=False,
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="Write",
                tool_output="written successfully",
                tool_call_id="call-2",
                is_error=False,
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Done",
                session_id=None,
            ),
        ])

        developer = Developer(driver=mock_driver)

        results = []
        async for state_update, event in developer.run(state, profile, "wf-test"):
            results.append((state_update, event))

        # Check final state has tool results
        final_state = results[-1][0]
        assert len(final_state.tool_results) >= 2

    async def test_developer_uses_to_stream_event(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
    ) -> None:
        """Developer should use AgenticMessage.to_stream_event() for conversion."""
        from amelia.agents.developer import Developer

        profile = mock_profile_factory()
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test goal",
        )

        mock_driver = MagicMock()
        # We'll verify the event has the correct fields that to_stream_event produces
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Thinking...",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="Bash",
                tool_input={"command": "ls"},
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="Done",
                session_id=None,
            ),
        ])

        developer = Developer(driver=mock_driver)

        results = []
        async for state_update, event in developer.run(state, profile, "wf-test"):
            results.append((state_update, event))

        # All events should have agent and workflow_id set (from to_stream_event)
        for _state_update, event in results:
            assert event.agent == "developer"
            assert event.workflow_id == "wf-test"
            assert event.timestamp is not None

    async def test_developer_raises_without_goal(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
    ) -> None:
        """Developer.run should raise ValueError if state has no goal."""
        from amelia.agents.developer import Developer

        profile = mock_profile_factory()
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal=None,  # No goal set
        )

        mock_driver = MagicMock()
        developer = Developer(driver=mock_driver)

        with pytest.raises(ValueError, match="must have a goal"):
            async for _ in developer.run(state, profile, "wf-test"):
                pass
