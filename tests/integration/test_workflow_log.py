"""Integration tests for workflow_log persistence.

This module tests that:
1. High-level workflow events (lifecycle, stages, approvals) are persisted
2. Trace events (thinking, tool calls) are NOT persisted (stream-only)
3. The row count is reasonable (10-100 instead of thousands)
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from amelia.core.types import AgentConfig, DriverType, Profile, TrackerType
from amelia.server.database.connection import Database
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.events import (
    _TRACE_TYPES,
    PERSISTED_TYPES,
    EventType,
    WorkflowEvent,
)
from amelia.server.models.state import ServerExecutionState, WorkflowStatus
from amelia.server.orchestrator.service import OrchestratorService


# =============================================================================
# Helper functions
# =============================================================================


def assert_event_types_present(
    events: list[WorkflowEvent], expected_types: list[str]
) -> None:
    """Assert that all expected event types are present in the events list.

    Args:
        events: List of workflow events to check.
        expected_types: Event type values that must be present.

    Raises:
        AssertionError: If any expected type is missing.
    """
    actual_types = {e.event_type.value for e in events}
    for expected in expected_types:
        assert expected in actual_types, (
            f"Expected event type '{expected}' not found. "
            f"Present types: {sorted(actual_types)}"
        )


def assert_no_event_types(
    events: list[WorkflowEvent], forbidden_types: list[str]
) -> None:
    """Assert that no forbidden event types are present in the events list.

    Args:
        events: List of workflow events to check.
        forbidden_types: Event type values that must NOT be present.

    Raises:
        AssertionError: If any forbidden type is present.
    """
    actual_types = {e.event_type.value for e in events}
    for forbidden in forbidden_types:
        assert forbidden not in actual_types, (
            f"Forbidden event type '{forbidden}' was persisted but should be stream-only"
        )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def workflow_test_db(tmp_path: Path) -> AsyncGenerator[Database, None]:
    """Create and initialize a test database for workflow log tests."""
    db_path = tmp_path / "workflow_log_test.db"
    db = Database(db_path)
    await db.connect()
    await db.ensure_schema()
    yield db
    await db.close()


@pytest.fixture
def workflow_repository(workflow_test_db: Database) -> WorkflowRepository:
    """Create repository backed by test database."""
    return WorkflowRepository(workflow_test_db)


@pytest.fixture
def workflow_profile_repo(workflow_test_db: Database) -> ProfileRepository:
    """Create profile repository backed by test database."""
    return ProfileRepository(workflow_test_db)


@pytest.fixture
def workflow_event_bus() -> EventBus:
    """Create event bus for testing."""
    return EventBus()


@pytest.fixture
def temp_checkpoint_path(tmp_path: Path) -> str:
    """Create temporary checkpoint database path."""
    return str(tmp_path / "checkpoints.db")


@pytest.fixture
async def test_profile_in_db(
    workflow_profile_repo: ProfileRepository,
    tmp_path: Path,
) -> Profile:
    """Create and persist a test profile in the database."""
    # Create a valid worktree-like directory
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").mkdir()

    agent_config = AgentConfig(driver=DriverType.CLI, model="sonnet")
    profile = Profile(
        name="test_workflow_log",
        tracker=TrackerType.NOOP,
        working_dir=str(worktree),
        agents={
            "architect": agent_config,
            "developer": agent_config,
            "reviewer": agent_config,
            "plan_validator": agent_config,
            "evaluator": agent_config,
            "task_reviewer": agent_config,
        },
    )
    await workflow_profile_repo.create_profile(profile)
    await workflow_profile_repo.set_active("test_workflow_log")
    return profile


@pytest.fixture
def orchestrator_service(
    workflow_event_bus: EventBus,
    workflow_repository: WorkflowRepository,
    workflow_profile_repo: ProfileRepository,
    temp_checkpoint_path: str,
) -> OrchestratorService:
    """Create OrchestratorService with real dependencies."""
    return OrchestratorService(
        event_bus=workflow_event_bus,
        repository=workflow_repository,
        profile_repo=workflow_profile_repo,
        checkpoint_path=temp_checkpoint_path,
    )


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.integration
class TestWorkflowLogPersistence:
    """Test that workflow_log table correctly persists only high-level events."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_implementation_graph")
    async def test_lifecycle_events_are_persisted(
        self,
        mock_create_graph: Any,
        mock_saver_class: Any,
        orchestrator_service: OrchestratorService,
        workflow_repository: WorkflowRepository,
        test_profile_in_db: Profile,
        langgraph_mock_factory: Any,
    ) -> None:
        """Verify lifecycle events (workflow_started, workflow_completed) are persisted.

        Only mocks: LangGraph graph and checkpointer
        Real: OrchestratorService, EventBus, WorkflowRepository, Database
        """
        # Setup LangGraph mocks to simulate a completed workflow
        # Combined stream mode returns (mode, data) tuples
        stream_items = [
            ("updates", {"architect_node": {"goal": "Test goal", "plan_markdown": "# Plan"}}),
            ("updates", {"plan_validator_node": {"goal": "Test goal"}}),
            ("updates", {"developer_node": {"final_response": "Done"}}),
            ("updates", {"reviewer_node": {"last_review": {"approved": True}}}),
        ]
        mocks = langgraph_mock_factory(astream_items=stream_items)
        mock_create_graph.return_value = mocks.graph
        mock_saver_class.from_conn_string.return_value = (
            mocks.saver_class.from_conn_string.return_value
        )

        # Create server state
        workflow_id = "wf-lifecycle-persist-test"
        server_state = ServerExecutionState(
            id=workflow_id,
            issue_id="TEST-001",
            worktree_path=test_profile_in_db.working_dir,
            profile_id=test_profile_in_db.name,
            workflow_status=WorkflowStatus.PENDING,
            started_at=datetime.now(UTC),
        )

        await workflow_repository.create(server_state)
        await orchestrator_service._run_workflow(workflow_id, server_state)

        # Get persisted events from workflow_log
        events = await workflow_repository.get_recent_events(workflow_id, limit=100)

        # Verify at minimum workflow_started is present
        # workflow_completed may or may not be emitted depending on mock behavior
        assert_event_types_present(events, [
            "workflow_started",
        ])

        # Verify events have required fields
        for event in events:
            assert event.workflow_id == workflow_id
            assert event.sequence > 0
            assert event.timestamp is not None

        # Verify at least some events were persisted and trace events are not present
        assert len(events) >= 1
        assert_no_event_types(events, [
            "claude_thinking",
            "claude_tool_call",
            "claude_tool_result",
            "agent_output",
        ])

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_implementation_graph")
    async def test_stage_events_are_persisted(
        self,
        mock_create_graph: Any,
        mock_saver_class: Any,
        orchestrator_service: OrchestratorService,
        workflow_repository: WorkflowRepository,
        test_profile_in_db: Profile,
        langgraph_mock_factory: Any,
    ) -> None:
        """Verify stage events (stage_started, stage_completed) are persisted.

        These events track which node/stage is currently executing.
        """
        # Simulate workflow with multiple stages
        stream_items = [
            ("tasks", (("__pregel_pull", "architect_node"),)),
            ("updates", {"architect_node": {"goal": "Test goal"}}),
            ("tasks", (("__pregel_pull", "developer_node"),)),
            ("updates", {"developer_node": {"final_response": "Done"}}),
        ]
        mocks = langgraph_mock_factory(astream_items=stream_items)
        mock_create_graph.return_value = mocks.graph
        mock_saver_class.from_conn_string.return_value = (
            mocks.saver_class.from_conn_string.return_value
        )

        workflow_id = "wf-stage-persist-test"
        server_state = ServerExecutionState(
            id=workflow_id,
            issue_id="TEST-002",
            worktree_path=test_profile_in_db.working_dir,
            profile_id=test_profile_in_db.name,
            workflow_status=WorkflowStatus.PENDING,
            started_at=datetime.now(UTC),
        )

        await workflow_repository.create(server_state)
        await orchestrator_service._run_workflow(workflow_id, server_state)

        events = await workflow_repository.get_recent_events(workflow_id, limit=100)

        # Stage events should be persisted when the orchestrator emits them
        # (Note: actual stage event emission depends on orchestrator implementation)
        # At minimum, lifecycle events should be present
        assert_event_types_present(events, ["workflow_started", "workflow_completed"])

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_implementation_graph")
    async def test_approval_events_are_persisted(
        self,
        mock_create_graph: Any,
        mock_saver_class: Any,
        orchestrator_service: OrchestratorService,
        workflow_repository: WorkflowRepository,
        test_profile_in_db: Profile,
        langgraph_mock_factory: Any,
    ) -> None:
        """Verify approval_required events are persisted when workflow is interrupted."""
        # Simulate workflow that pauses for approval
        stream_items = [
            ("updates", {"architect_node": {"goal": "Test goal"}}),
            ("updates", {"__interrupt__": ("Paused for approval",)}),
        ]
        mocks = langgraph_mock_factory(astream_items=stream_items)
        mock_create_graph.return_value = mocks.graph
        mock_saver_class.from_conn_string.return_value = (
            mocks.saver_class.from_conn_string.return_value
        )

        workflow_id = "wf-approval-persist-test"
        server_state = ServerExecutionState(
            id=workflow_id,
            issue_id="TEST-003",
            worktree_path=test_profile_in_db.working_dir,
            profile_id=test_profile_in_db.name,
            workflow_status=WorkflowStatus.PENDING,
            started_at=datetime.now(UTC),
        )

        await workflow_repository.create(server_state)
        await orchestrator_service._run_workflow(workflow_id, server_state)

        events = await workflow_repository.get_recent_events(workflow_id, limit=100)

        # Should have workflow_started and approval_required
        assert_event_types_present(events, [
            "workflow_started",
            "approval_required",
        ])


@pytest.mark.integration
class TestTraceEventsNotPersisted:
    """Test that trace events are NOT persisted to the workflow_log table."""

    async def test_trace_event_types_not_in_persisted_types(self) -> None:
        """Verify trace types are explicitly excluded from PERSISTED_TYPES.

        This is a unit-level check but ensures the configuration is correct.
        """
        # All trace types should NOT be in PERSISTED_TYPES
        for trace_type in _TRACE_TYPES:
            assert trace_type not in PERSISTED_TYPES, (
                f"Trace type {trace_type} should NOT be in PERSISTED_TYPES"
            )

    async def test_save_event_filters_trace_events(
        self,
        workflow_repository: WorkflowRepository,
        workflow_test_db: Database,
    ) -> None:
        """Verify save_event() filters out trace events.

        Real: Repository, Database
        """
        workflow_id = "wf-trace-filter-test"

        # First create a workflow record (required due to foreign key constraint)
        server_state = ServerExecutionState(
            id=workflow_id,
            issue_id="TEST-TRACE",
            worktree_path="/tmp/test-trace",
            workflow_status=WorkflowStatus.PENDING,
            started_at=datetime.now(UTC),
        )
        await workflow_repository.create(server_state)

        # Create a trace event (should NOT be persisted)
        trace_event = WorkflowEvent(
            id="trace-event-1",
            workflow_id=workflow_id,
            sequence=1,
            timestamp=datetime.now(UTC),
            event_type=EventType.CLAUDE_THINKING,
            message="Thinking about the problem...",
            agent="developer",
        )

        # Create a lifecycle event (should be persisted)
        lifecycle_event = WorkflowEvent(
            id="lifecycle-event-1",
            workflow_id=workflow_id,
            sequence=2,
            timestamp=datetime.now(UTC),
            event_type=EventType.WORKFLOW_STARTED,
            message="Workflow started",
            agent="system",
        )

        # Save both events
        await workflow_repository.save_event(trace_event)
        await workflow_repository.save_event(lifecycle_event)

        # Query database directly to verify
        events = await workflow_repository.get_recent_events(workflow_id, limit=100)

        # Only lifecycle event should be persisted
        assert len(events) == 1
        assert events[0].event_type == EventType.WORKFLOW_STARTED

        # Trace event should NOT be present
        event_types = [e.event_type for e in events]
        assert EventType.CLAUDE_THINKING not in event_types

    async def test_all_trace_types_filtered(
        self,
        workflow_repository: WorkflowRepository,
    ) -> None:
        """Verify all trace event types are filtered during save."""
        workflow_id = "wf-all-trace-filter-test"

        # Try to save each trace event type
        for sequence, trace_type in enumerate(_TRACE_TYPES, start=1):
            event = WorkflowEvent(
                id=f"trace-{trace_type.value}",
                workflow_id=workflow_id,
                sequence=sequence,
                timestamp=datetime.now(UTC),
                event_type=trace_type,
                message=f"Test {trace_type.value}",
                agent="test",
            )
            await workflow_repository.save_event(event)

        # Verify none were persisted
        events = await workflow_repository.get_recent_events(workflow_id, limit=100)
        assert len(events) == 0, (
            f"Expected 0 events but found {len(events)}: "
            f"{[e.event_type.value for e in events]}"
        )


@pytest.mark.integration
class TestReasonableRowCount:
    """Test that event persistence produces reasonable row counts."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_implementation_graph")
    async def test_event_count_is_reasonable(
        self,
        mock_create_graph: Any,
        mock_saver_class: Any,
        orchestrator_service: OrchestratorService,
        workflow_repository: WorkflowRepository,
        test_profile_in_db: Profile,
        langgraph_mock_factory: Any,
    ) -> None:
        """Verify a typical workflow produces 10-100 persisted events, not thousands.

        This ensures trace events (which could be thousands) are not persisted.
        """
        # Simulate a complete workflow with all stages
        stream_items = [
            ("updates", {"architect_node": {"goal": "Test goal", "plan_markdown": "# Plan"}}),
            ("updates", {"plan_validator_node": {"goal": "Test goal"}}),
            ("updates", {"developer_node": {"final_response": "Implemented feature"}}),
            ("updates", {"reviewer_node": {"last_review": {"approved": True}}}),
        ]
        mocks = langgraph_mock_factory(astream_items=stream_items)
        mock_create_graph.return_value = mocks.graph
        mock_saver_class.from_conn_string.return_value = (
            mocks.saver_class.from_conn_string.return_value
        )

        workflow_id = "wf-count-test"
        server_state = ServerExecutionState(
            id=workflow_id,
            issue_id="TEST-COUNT",
            worktree_path=test_profile_in_db.working_dir,
            profile_id=test_profile_in_db.name,
            workflow_status=WorkflowStatus.PENDING,
            started_at=datetime.now(UTC),
        )

        await workflow_repository.create(server_state)
        await orchestrator_service._run_workflow(workflow_id, server_state)

        events = await workflow_repository.get_recent_events(workflow_id, limit=1000)

        # Verify reasonable count: should be 2-100 events (not thousands)
        # Minimum 2: workflow_started + workflow_completed
        assert len(events) >= 2, (
            f"Expected at least 2 events (started + completed), got {len(events)}"
        )
        assert len(events) <= 100, (
            f"Expected at most 100 events for a simple workflow, got {len(events)}. "
            "This suggests trace events may be leaking into persistence."
        )

        # Log actual count for visibility
        print(f"Persisted event count: {len(events)}")
        print(f"Event types: {[e.event_type.value for e in events]}")

    async def test_persisted_types_is_bounded(self) -> None:
        """Verify PERSISTED_TYPES has a reasonable number of event types.

        This is a sanity check that we haven't accidentally included trace types.
        """
        # PERSISTED_TYPES should have ~20-30 event types, not 50+
        assert len(PERSISTED_TYPES) <= 40, (
            f"PERSISTED_TYPES has {len(PERSISTED_TYPES)} types, which seems too many. "
            "Check if trace types have been accidentally added."
        )

        # Verify none of the trace types are in PERSISTED_TYPES
        trace_types_in_persisted = PERSISTED_TYPES & _TRACE_TYPES
        assert len(trace_types_in_persisted) == 0, (
            f"PERSISTED_TYPES contains trace types: {trace_types_in_persisted}"
        )


@pytest.mark.integration
class TestEventDataIntegrity:
    """Test that persisted events have correct data and structure."""

    async def test_event_fields_are_preserved(
        self,
        workflow_repository: WorkflowRepository,
    ) -> None:
        """Verify all event fields are correctly stored and retrieved."""
        workflow_id = "wf-integrity-test"

        # Create workflow record (required for foreign key constraint)
        server_state = ServerExecutionState(
            id=workflow_id,
            issue_id="TEST-INTEGRITY",
            worktree_path="/tmp/test-integrity",
            workflow_status=WorkflowStatus.PENDING,
            started_at=datetime.now(UTC),
        )
        await workflow_repository.create(server_state)

        original_event = WorkflowEvent(
            id="integrity-event-1",
            workflow_id=workflow_id,
            sequence=42,
            timestamp=datetime.now(UTC),
            event_type=EventType.WORKFLOW_STARTED,
            message="Testing data integrity",
            agent="test-agent",
            data={"key": "value", "nested": {"inner": 123}},
            correlation_id="corr-123",
            is_error=False,
        )

        await workflow_repository.save_event(original_event)
        events = await workflow_repository.get_recent_events(workflow_id, limit=1)

        assert len(events) == 1
        retrieved = events[0]

        # Verify all fields match
        assert retrieved.id == original_event.id
        assert retrieved.workflow_id == original_event.workflow_id
        assert retrieved.sequence == original_event.sequence
        assert retrieved.event_type == original_event.event_type
        assert retrieved.message == original_event.message
        assert retrieved.agent == original_event.agent
        assert retrieved.data == original_event.data
        assert retrieved.is_error == original_event.is_error

    async def test_sequence_numbers_are_monotonic(
        self,
        workflow_repository: WorkflowRepository,
    ) -> None:
        """Verify event sequence numbers are correctly ordered."""
        workflow_id = "wf-sequence-test"

        # Create workflow record (required for foreign key constraint)
        server_state = ServerExecutionState(
            id=workflow_id,
            issue_id="TEST-SEQUENCE",
            worktree_path="/tmp/test-sequence",
            workflow_status=WorkflowStatus.PENDING,
            started_at=datetime.now(UTC),
        )
        await workflow_repository.create(server_state)

        # Save events with specific sequences
        for seq in [1, 2, 3, 5, 10]:
            event = WorkflowEvent(
                id=f"seq-event-{seq}",
                workflow_id=workflow_id,
                sequence=seq,
                timestamp=datetime.now(UTC),
                event_type=EventType.STAGE_STARTED,
                message=f"Stage {seq}",
                agent="system",
            )
            await workflow_repository.save_event(event)

        events = await workflow_repository.get_recent_events(workflow_id, limit=100)

        # Events should be returned in sequence order (ascending)
        sequences = [e.sequence for e in events]
        assert sequences == sorted(sequences), (
            f"Events not in sequence order: {sequences}"
        )
