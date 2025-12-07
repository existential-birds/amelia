"""Tests for workflow retry logic."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import TimeoutException

from amelia.core.state import ExecutionState
from amelia.core.types import Profile, RetryConfig, Settings
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import TRANSIENT_EXCEPTIONS, OrchestratorService


class TestTransientExceptions:
    """Test TRANSIENT_EXCEPTIONS constant."""

    def test_contains_expected_exceptions(self):
        """TRANSIENT_EXCEPTIONS contains expected exception types."""
        assert asyncio.TimeoutError in TRANSIENT_EXCEPTIONS
        assert TimeoutException in TRANSIENT_EXCEPTIONS
        assert ConnectionError in TRANSIENT_EXCEPTIONS


@pytest.fixture
def mock_event_bus():
    """Create a real EventBus for testing event emissions."""
    return EventBus()


@pytest.fixture
def mock_repository():
    repo = AsyncMock()
    repo.get_max_event_sequence.return_value = 0
    repo.save_event = AsyncMock()
    repo.set_status = AsyncMock()
    return repo


@pytest.fixture
def mock_settings():
    return Settings(
        active_profile="test",
        profiles={
            "test": Profile(name="test", driver="cli:claude"),
        },
    )


@pytest.fixture
def service(mock_event_bus, mock_repository, mock_settings):
    svc = OrchestratorService(mock_event_bus, mock_repository, mock_settings)
    svc._checkpoint_path = "/tmp/test.db"
    return svc


@pytest.fixture
def server_state():
    core_state = ExecutionState(
        profile=Profile(
            name="test",
            driver="cli:claude",
            retry=RetryConfig(max_retries=2, base_delay=0.1),
        ),
    )
    return ServerExecutionState(
        id="wf-123",
        issue_id="ISSUE-456",
        worktree_path="/tmp/test",
        worktree_name="test-branch",
        started_at=datetime.now(UTC),
        execution_state=core_state,
    )


class TestRunWorkflowWithRetry:
    """Test _run_workflow_with_retry method."""

    async def test_succeeds_on_first_attempt(self, service, server_state):
        """Workflow succeeds without retry if no error."""
        service._run_workflow = AsyncMock()

        await service._run_workflow_with_retry("wf-123", server_state)

        assert service._run_workflow.call_count == 1

    async def test_retries_on_transient_error(self, service, server_state):
        """Workflow retries on transient error."""
        call_count = 0

        async def fail_then_succeed(*args):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Connection timeout")
            return None

        service._run_workflow = fail_then_succeed

        await service._run_workflow_with_retry("wf-123", server_state)

        assert call_count == 2

    async def test_fails_immediately_on_permanent_error(self, service, server_state):
        """Workflow fails immediately on permanent error."""
        service._run_workflow = AsyncMock(side_effect=ValueError("Invalid config"))

        with pytest.raises(ValueError):
            await service._run_workflow_with_retry("wf-123", server_state)

        assert service._run_workflow.call_count == 1

    async def test_fails_after_max_retries(self, service, server_state):
        """Workflow fails after exhausting max_retries."""
        service._run_workflow = AsyncMock(
            side_effect=TimeoutError("Always timeout")
        )

        with pytest.raises(asyncio.TimeoutError):
            await service._run_workflow_with_retry("wf-123", server_state)

        # Initial attempt + 2 retries = 3 calls
        assert service._run_workflow.call_count == 3

        # Verify set_status was called with failure reason
        service._repository.set_status.assert_called_once_with(
            "wf-123",
            "failed",
            failure_reason="Failed after 3 attempts: Always timeout",
        )

    async def test_fails_when_execution_state_is_none(self, service):
        """Workflow fails immediately when execution_state is None."""
        # Create a ServerExecutionState with execution_state=None
        state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            worktree_name="test-branch",
            started_at=datetime.now(UTC),
            execution_state=None,
        )

        service._run_workflow = AsyncMock()

        await service._run_workflow_with_retry("wf-123", state)

        # Verify repository.set_status was called with correct args
        service._repository.set_status.assert_called_once_with(
            "wf-123", "failed", failure_reason="Missing execution state"
        )

        # Verify _run_workflow was NOT called (early return)
        service._run_workflow.assert_not_called()

    async def test_respects_max_delay_config(self, service, monkeypatch):
        """Workflow retry delay respects max_delay configuration."""
        # Track sleep durations
        sleep_durations = []
        original_sleep = asyncio.sleep

        async def mock_sleep(delay):
            sleep_durations.append(delay)
            # Use a very short sleep to speed up test
            await original_sleep(0.001)

        monkeypatch.setattr(asyncio, "sleep", mock_sleep)

        # Create state with custom retry config
        core_state = ExecutionState(
            profile=Profile(
                name="test",
                driver="cli:claude",
                retry=RetryConfig(max_retries=3, base_delay=10.0, max_delay=15.0),
            ),
        )
        state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            worktree_name="test-branch",
            started_at=datetime.now(UTC),
            execution_state=core_state,
        )

        # Make workflow fail with transient errors
        service._run_workflow = AsyncMock(
            side_effect=TimeoutError("Always timeout")
        )

        with pytest.raises(asyncio.TimeoutError):
            await service._run_workflow_with_retry("wf-123", state)

        # Verify delays: 10.0 (first retry), 15.0 (capped by max_delay), 15.0 (capped)
        # Without max_delay, it would be: 10.0, 20.0, 40.0
        assert len(sleep_durations) == 3
        assert sleep_durations[0] == 10.0  # base_delay * 2^0
        assert sleep_durations[1] == 15.0  # min(base_delay * 2^1, max_delay) = min(20, 15)
        assert sleep_durations[2] == 15.0  # min(base_delay * 2^2, max_delay) = min(40, 15)

    async def test_failure_event_emitted_only_after_retries_exhausted(
        self, service, server_state, mock_event_bus
    ):
        """WORKFLOW_FAILED event should only be emitted after all retries are exhausted."""
        # Track emitted events
        received_events = []
        mock_event_bus.subscribe(lambda e: received_events.append(e))

        # Make workflow always fail with transient error
        service._run_workflow = AsyncMock(
            side_effect=TimeoutError("Connection timeout")
        )

        with pytest.raises(asyncio.TimeoutError):
            await service._run_workflow_with_retry("wf-123", server_state)

        # Verify _run_workflow was called 3 times (initial + 2 retries)
        assert service._run_workflow.call_count == 3

        # Verify WORKFLOW_FAILED event was emitted exactly once at the end
        failed_events = [e for e in received_events if e.event_type == EventType.WORKFLOW_FAILED]
        assert len(failed_events) == 1, "WORKFLOW_FAILED should be emitted exactly once"

        # Verify the failure event has correct data
        failed_event = failed_events[0]
        assert "after 3 attempts" in failed_event.message
        assert failed_event.data["attempts"] == 3
        assert "Connection timeout" in failed_event.data["error"]

    async def test_failure_event_emitted_immediately_for_non_transient_error(
        self, service, server_state, mock_event_bus
    ):
        """WORKFLOW_FAILED event should be emitted immediately for non-transient errors."""
        # Track emitted events
        received_events = []
        mock_event_bus.subscribe(lambda e: received_events.append(e))

        # Make workflow fail with non-transient error
        service._run_workflow = AsyncMock(side_effect=ValueError("Invalid config"))

        with pytest.raises(ValueError):
            await service._run_workflow_with_retry("wf-123", server_state)

        # Verify _run_workflow was called only once (no retries)
        assert service._run_workflow.call_count == 1

        # Verify WORKFLOW_FAILED event was emitted
        failed_events = [e for e in received_events if e.event_type == EventType.WORKFLOW_FAILED]
        assert len(failed_events) == 1, "WORKFLOW_FAILED should be emitted once"

        # Verify the failure event has correct data
        failed_event = failed_events[0]
        assert "Invalid config" in failed_event.message
        assert failed_event.data["error_type"] == "non-transient"
        assert "Invalid config" in failed_event.data["error"]
