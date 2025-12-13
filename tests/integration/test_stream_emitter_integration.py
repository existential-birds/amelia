# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Integration tests for stream emitter workflow.

These tests verify that stream events are properly emitted during agent
execution through the complete workflow chain:
1. OrchestratorService creates stream emitter via _create_stream_emitter()
2. Stream emitter is passed to agents during execution
3. Agents emit StreamEvents during their work
4. EventBus.emit_stream broadcasts to WebSocket clients
"""

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.agents.architect import PlanOutput
from amelia.agents.reviewer import ReviewResponse
from amelia.core.state import ExecutionState, Task, TaskDAG
from amelia.core.types import Issue, Profile, StreamEvent, StreamEventType
from amelia.server.models import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService


class TestStreamEmitterIntegration:
    """Test that stream emitters are integrated into the workflow execution."""

    async def test_stream_emitter_factory_creates_valid_callback(
        self,
        mock_event_bus: MagicMock,
        mock_repository: AsyncMock,
        test_settings: MagicMock,
    ) -> None:
        """_create_stream_emitter returns a callable that broadcasts to EventBus."""
        service = OrchestratorService(
            event_bus=mock_event_bus,
            repository=mock_repository,
            settings=test_settings,
            max_concurrent=5,
        )

        # Create emitter for a workflow
        workflow_id = "wf-test-123"
        emitter = service._create_stream_emitter(workflow_id)

        # Verify emitter is callable
        assert callable(emitter)

        # Create a test stream event
        test_event = StreamEvent(
            type=StreamEventType.CLAUDE_THINKING,
            content="Testing stream emitter",
            timestamp=datetime.now(UTC),
            agent="developer",
            workflow_id=workflow_id,
        )

        # Emit the event
        await emitter(test_event)

        # Verify EventBus.emit_stream was called
        mock_event_bus.emit_stream.assert_called_once_with(test_event)

    async def test_workflow_execution_does_not_emit_stream_events_yet(
        self,
        mock_event_bus: MagicMock,
        mock_repository: AsyncMock,
        test_settings: MagicMock,
        test_profile: Profile,
        test_issue: Issue,
    ) -> None:
        """KNOWN LIMITATION: Stream emitter is not yet integrated into agent execution.

        This test documents the current state where _create_stream_emitter exists
        but is not actually used to inject emitters into agents. This is the
        missing integration that needs to be implemented.

        Once implemented, this test should be updated to assert that stream
        events ARE emitted during workflow execution.
        """
        # Create temporary git repository for worktree
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir) / "test-worktree"
            worktree_path.mkdir()
            git_dir = worktree_path / ".git"
            git_dir.mkdir()

            # Mock tracker to return test issue
            with patch("amelia.trackers.factory.create_tracker") as mock_create_tracker:
                mock_tracker = MagicMock()
                mock_tracker.get_issue.return_value = test_issue
                mock_create_tracker.return_value = mock_tracker

                # Mock driver and agents
                mock_driver = AsyncMock()
                mock_driver.generate.return_value = ReviewResponse(
                    approved=True,
                    comments=[],
                    severity="low",
                )

                mock_plan = PlanOutput(
                    task_dag=TaskDAG(
                        tasks=[
                            Task(
                                id="T1",
                                description="Test task",
                                status="pending",
                            )
                        ],
                        original_issue=test_issue.id,
                    ),
                    markdown_path=Path("/tmp/test-plan.md"),
                )

                with (
                    patch("amelia.drivers.factory.DriverFactory.get_driver", return_value=mock_driver),
                    patch("amelia.agents.architect.Architect.plan", new_callable=AsyncMock) as mock_plan_call,
                    patch("amelia.agents.developer.Developer.execute_current_task", new_callable=AsyncMock) as mock_execute,
                    patch("amelia.core.orchestrator.get_code_changes_for_review", new_callable=AsyncMock, return_value="test changes"),
                ):
                    mock_plan_call.return_value = mock_plan
                    mock_execute.return_value = {"status": "completed", "output": "Task completed"}

                    # Mock repository get to return workflow state
                    def mock_get_workflow(workflow_id: str) -> ServerExecutionState | None:
                        return ServerExecutionState(
                            id=workflow_id,
                            issue_id=test_issue.id,
                            worktree_path=str(worktree_path),
                            worktree_name="test-worktree",
                            execution_state=ExecutionState(
                                profile=test_profile,
                                issue=test_issue,
                                plan=mock_plan.task_dag,
                            ),
                            workflow_status="in_progress",
                            started_at=datetime.now(UTC),
                        )

                    mock_repository.get.side_effect = mock_get_workflow

                    service = OrchestratorService(
                        event_bus=mock_event_bus,
                        repository=mock_repository,
                        settings=test_settings,
                        max_concurrent=5,
                    )

                    # Start workflow (which will be interrupted at approval)
                    workflow_id = await service.start_workflow(
                        issue_id=test_issue.id,
                        worktree_path=str(worktree_path),
                        profile="test_profile",
                    )

                    # Wait for async workflow task to reach the approval gate and pause.
                    # This ensures the workflow has progressed through initialization before
                    # we assert on event bus state.
                    await asyncio.sleep(0.5)

                    # CURRENT STATE: emit_stream is NOT called because stream_emitter
                    # is not yet integrated into agent execution
                    # When integration is complete, change this to assert_called()
                    assert not mock_event_bus.emit_stream.called, (
                        "Stream events should not be emitted yet - integration pending. "
                        "If this assertion fails, the integration has been completed and "
                        "this test should be updated to verify proper stream event emission."
                    )

                    # Cleanup
                    await service.cancel_workflow(workflow_id, reason="Test cleanup")

    @pytest.mark.parametrize("event_type", list(StreamEventType))
    async def test_emitter_propagates_stream_event_type(
        self,
        event_type: StreamEventType,
        mock_event_bus: MagicMock,
        mock_repository: AsyncMock,
        test_settings: MagicMock,
    ) -> None:
        """Stream emitter correctly propagates a specific StreamEventType."""
        service = OrchestratorService(
            event_bus=mock_event_bus,
            repository=mock_repository,
            settings=test_settings,
        )

        workflow_id = "wf-types-test"
        emitter = service._create_stream_emitter(workflow_id)

        # Create event with type-specific fields
        event = StreamEvent(
            type=event_type,
            content=f"Testing {event_type.value}",
            timestamp=datetime.now(UTC),
            agent="developer",
            workflow_id=workflow_id,
            tool_name="TestTool" if event_type == StreamEventType.CLAUDE_TOOL_CALL else None,
            tool_input={"test": "input"} if event_type == StreamEventType.CLAUDE_TOOL_CALL else None,
        )

        await emitter(event)

        # Verify event was emitted
        mock_event_bus.emit_stream.assert_called_once()
        emitted_event = mock_event_bus.emit_stream.call_args[0][0]
        assert emitted_event.type == event_type
        assert emitted_event.workflow_id == workflow_id

    async def test_multiple_workflows_have_isolated_emitters(
        self,
        mock_event_bus: MagicMock,
        mock_repository: AsyncMock,
        test_settings: MagicMock,
    ) -> None:
        """Each workflow gets its own stream emitter with correct workflow_id."""
        service = OrchestratorService(
            event_bus=mock_event_bus,
            repository=mock_repository,
            settings=test_settings,
        )

        # Create emitters for different workflows
        workflow_1 = "wf-001"
        workflow_2 = "wf-002"

        emitter_1 = service._create_stream_emitter(workflow_1)
        emitter_2 = service._create_stream_emitter(workflow_2)

        # Emit from first workflow
        event_1 = StreamEvent(
            type=StreamEventType.CLAUDE_THINKING,
            content="Workflow 1 event",
            timestamp=datetime.now(UTC),
            agent="architect",
            workflow_id=workflow_1,
        )
        await emitter_1(event_1)

        # Emit from second workflow
        event_2 = StreamEvent(
            type=StreamEventType.AGENT_OUTPUT,
            content="Workflow 2 event",
            timestamp=datetime.now(UTC),
            agent="developer",
            workflow_id=workflow_2,
        )
        await emitter_2(event_2)

        # Verify both events were emitted separately
        assert mock_event_bus.emit_stream.call_count == 2

        # Verify workflow IDs are preserved
        first_call_event = mock_event_bus.emit_stream.call_args_list[0].args[0]
        second_call_event = mock_event_bus.emit_stream.call_args_list[1].args[0]
        assert first_call_event.workflow_id == workflow_1
        assert second_call_event.workflow_id == workflow_2


class TestFutureAgentIntegration:
    """Tests for future integration of stream_emitter into agents.

    These tests are currently SKIPPED but document the expected behavior
    once stream_emitter is properly injected into Architect, Developer,
    and Reviewer agents during workflow execution.
    """

    @pytest.mark.skip(reason="Stream emitter not yet integrated into agents - pending implementation")
    async def test_architect_emits_stream_events_during_planning(self) -> None:
        """Architect should emit CLAUDE_THINKING and AGENT_OUTPUT events during plan generation."""
        # This test will be implemented once agents receive stream_emitter
        # Expected flow:
        # 1. OrchestratorService creates emitter via _create_stream_emitter(workflow_id)
        # 2. Emitter is passed to Architect via config or state injection
        # 3. Architect emits CLAUDE_THINKING during LLM interactions
        # 4. Architect emits AGENT_OUTPUT when plan is complete
        pass

    @pytest.mark.skip(reason="Stream emitter not yet integrated into agents - pending implementation")
    async def test_developer_emits_stream_events_during_execution(self) -> None:
        """Developer should emit CLAUDE_TOOL_CALL and CLAUDE_TOOL_RESULT events during task execution."""
        # Expected flow:
        # 1. Developer receives stream_emitter from orchestrator
        # 2. During execute_current_task(), CLI driver emits ClaudeStreamEvents
        # 3. Driver converts to StreamEvent and calls stream_emitter
        # 4. EventBus broadcasts to WebSocket clients
        pass

    @pytest.mark.skip(reason="Stream emitter not yet integrated into agents - pending implementation")
    async def test_reviewer_emits_stream_events_during_review(self) -> None:
        """Reviewer should emit stream events during code review process."""
        # Expected flow:
        # 1. Reviewer receives stream_emitter
        # 2. During review(), emits CLAUDE_THINKING while analyzing
        # 3. Emits AGENT_OUTPUT when review is complete
        pass
