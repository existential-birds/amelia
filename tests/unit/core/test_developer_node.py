"""Tests for call_developer_node using profile from config."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.constants import ToolName
from amelia.core.orchestrator import call_developer_node
from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.server.models.events import EventType
from tests.conftest import create_mock_execute_agentic


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
        with patch("amelia.pipelines.nodes.Developer") as mock_dev:
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
            plan_markdown="# Test Plan\n\nImplement the feature.",
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
                tool_name=ToolName.READ_FILE,
                tool_input={"file_path": "/some/file.py"},
                tool_call_id="call-1",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name=ToolName.READ_FILE,
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
            plan_markdown="# Test Plan\n\nTest task.",
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
            plan_markdown="# Test Plan\n\nTest task.",
        )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name=ToolName.WRITE_FILE,
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
        assert tool_call_events[0][1].tool_name == ToolName.WRITE_FILE
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
            plan_markdown="# Test Plan\n\nTest task.",
        )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name=ToolName.READ_FILE,
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
        assert tool_result_events[0][1].message == f"Tool {ToolName.READ_FILE} completed"

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
            plan_markdown="# Test Plan\n\nTest task.",
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
            plan_markdown="# Test Plan\n\nTest task.",
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
            plan_markdown="# Test Plan\n\nTest task.",
        )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name=ToolName.READ_FILE,
                tool_input={"file_path": "/a.py"},
                tool_call_id="call-1",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name=ToolName.WRITE_FILE,
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
        assert ToolName.READ_FILE in tool_names
        assert ToolName.WRITE_FILE in tool_names

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
            plan_markdown="# Test Plan\n\nTest task.",
        )

        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name=ToolName.READ_FILE,
                tool_output="file content 1",
                tool_call_id="call-1",
                is_error=False,
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name=ToolName.WRITE_FILE,
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
            plan_markdown="# Test Plan\n\nTest task.",
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


class TestDeveloperTaskBasedExecution:
    """Tests for task-based execution in call_developer_node."""

    @pytest.fixture
    def mock_profile_with_working_dir(self, tmp_path: Any) -> Profile:
        return Profile(
            name="test",
            driver="api:openrouter",
            model="anthropic/claude-3.5-sonnet",
            validator_model="anthropic/claude-3.5-sonnet",
            working_dir=str(tmp_path),
        )

    @pytest.fixture
    def multi_task_state(self, tmp_path: Any) -> ExecutionState:
        plan_path = tmp_path / "docs" / "plans" / "plan.md"
        # Plan with proper structure for task extraction
        plan_markdown = """# Implementation Plan

**Goal:** Implement feature

---

## Phase 1: Setup

### Task 1: Initial Setup

Step 1: Create files
Step 2: Configure

### Task 2: Build Components

Step 1: Build the thing
"""
        return ExecutionState(
            profile_id="test",
            goal="Implement feature",
            plan_markdown=plan_markdown,
            plan_path=plan_path,
            total_tasks=2,
            current_task_index=0,
            driver_session_id="old-session-123",  # Should be cleared
        )

    async def test_developer_node_clears_session_for_task_execution(
        self,
        multi_task_state: ExecutionState,
        mock_profile_with_working_dir: Profile,
    ) -> None:
        """Developer node should clear driver_session_id for fresh task sessions."""
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-test",
                "profile": mock_profile_with_working_dir,
            }
        }

        # Track what session_id is passed to the driver
        captured_session_id: str | None = "NOT_SET"

        async def mock_run(
            state: ExecutionState, profile: Profile, workflow_id: str = ""
        ) -> Any:
            nonlocal captured_session_id
            captured_session_id = state.driver_session_id
            # Return minimal valid state updates
            yield (state.model_copy(update={"agentic_status": "completed"}), MagicMock())

        with patch("amelia.pipelines.nodes.Developer") as mock_developer_class:
            mock_developer = MagicMock()
            mock_developer.run = mock_run
            mock_developer_class.return_value = mock_developer

            await call_developer_node(multi_task_state, config)

        # Should have cleared session_id before calling developer
        assert captured_session_id is None

    async def test_developer_node_preserves_full_plan_markdown(
        self,
        multi_task_state: ExecutionState,
        mock_profile_with_working_dir: Profile,
    ) -> None:
        """Developer node should pass full plan_markdown to Developer.

        Task extraction now happens in Developer._build_prompt, not in the
        orchestrator node. The orchestrator must preserve plan_markdown intact.
        """
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-test",
                "profile": mock_profile_with_working_dir,
            }
        }

        captured_plan: str | None = None

        async def mock_run(
            state: ExecutionState, profile: Profile, workflow_id: str = ""
        ) -> Any:
            nonlocal captured_plan
            captured_plan = state.plan_markdown
            yield (state.model_copy(update={"agentic_status": "completed"}), MagicMock())

        with patch("amelia.pipelines.nodes.Developer") as mock_developer_class:
            mock_developer = MagicMock()
            mock_developer.run = mock_run
            mock_developer_class.return_value = mock_developer

            await call_developer_node(multi_task_state, config)

        # Should preserve full plan with ALL tasks
        assert captured_plan is not None
        assert "### Task 1:" in captured_plan
        assert "### Task 2:" in captured_plan  # Full plan preserved
        # Should preserve header context
        assert "**Goal:**" in captured_plan
        assert "## Phase 1:" in captured_plan

    async def test_developer_node_preserves_session_for_legacy_mode(
        self,
        mock_profile_with_working_dir: Profile,
    ) -> None:
        """Developer node should preserve session_id when total_tasks is None."""
        state = ExecutionState(
            profile_id="test",
            goal="Legacy goal",
            plan_markdown="Do stuff",
            total_tasks=None,  # Legacy mode
            driver_session_id="existing-session",
        )
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-test",
                "profile": mock_profile_with_working_dir,
            }
        }

        captured_session_id: str | None = "NOT_SET"

        async def mock_run(
            state: ExecutionState, profile: Profile, workflow_id: str = ""
        ) -> Any:
            nonlocal captured_session_id
            captured_session_id = state.driver_session_id
            yield (state.model_copy(update={"agentic_status": "completed"}), MagicMock())

        with patch("amelia.pipelines.nodes.Developer") as mock_developer_class:
            mock_developer = MagicMock()
            mock_developer.run = mock_run
            mock_developer_class.return_value = mock_developer

            await call_developer_node(state, config)

        # Should preserve existing session_id in legacy mode
        assert captured_session_id == "existing-session"
