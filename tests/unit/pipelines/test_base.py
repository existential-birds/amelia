"""Unit tests for pipeline base types."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from amelia.pipelines.base import (
    BasePipelineState,
    HistoryEntry,
    PipelineMetadata,
)


class TestPipelineMetadata:
    """Tests for PipelineMetadata Pydantic model."""

    def test_metadata_is_frozen(self) -> None:
        """PipelineMetadata should be immutable."""
        meta = PipelineMetadata(
            name="test",
            display_name="Test",
            description="A test pipeline",
        )
        with pytest.raises(ValidationError):
            meta.name = "changed"

    def test_metadata_fields(self) -> None:
        """PipelineMetadata should have required fields."""
        meta = PipelineMetadata(
            name="implementation",
            display_name="Implementation",
            description="Build features",
        )
        assert meta.name == "implementation"
        assert meta.display_name == "Implementation"
        assert meta.description == "Build features"


class TestHistoryEntry:
    """Tests for HistoryEntry Pydantic model."""

    def test_history_entry_is_frozen(self) -> None:
        """HistoryEntry should be immutable."""
        entry = HistoryEntry(
            timestamp=datetime.now(UTC),
            agent="architect",
            message="Started planning",
        )
        with pytest.raises(ValidationError):
            entry.agent = "developer"

    def test_history_entry_fields(self) -> None:
        """HistoryEntry should store timestamp, agent, and message."""
        ts = datetime.now(UTC)
        entry = HistoryEntry(timestamp=ts, agent="reviewer", message="Review complete")
        assert entry.timestamp == ts
        assert entry.agent == "reviewer"
        assert entry.message == "Review complete"


class TestBasePipelineState:
    """Tests for BasePipelineState."""

    def test_required_fields(self) -> None:
        """BasePipelineState should require identity fields."""
        with pytest.raises(ValidationError):
            BasePipelineState()  # type: ignore[call-arg]  # Intentional: testing ValidationError on missing required fields

    def test_valid_state_creation(self) -> None:
        """BasePipelineState should accept valid identity fields."""
        state = BasePipelineState(
            workflow_id="wf-123",
            pipeline_type="implementation",
            profile_id="default",
            created_at=datetime.now(UTC),
            status="pending",
        )
        assert state.workflow_id == "wf-123"
        assert state.pipeline_type == "implementation"
        assert state.status == "pending"
        assert state.history == []

    def test_status_values(self) -> None:
        """Status should only accept valid literals."""
        for status in ("pending", "running", "paused", "completed", "failed"):
            state = BasePipelineState(
                workflow_id="wf-1",
                pipeline_type="test",
                profile_id="p1",
                created_at=datetime.now(UTC),
                status=status,
            )
            assert state.status == status

    def test_defaults(self) -> None:
        """BasePipelineState should have sensible defaults."""
        state = BasePipelineState(
            workflow_id="wf-1",
            pipeline_type="test",
            profile_id="p1",
            created_at=datetime.now(UTC),
            status="pending",
        )
        assert state.pending_user_input is False
        assert state.user_message is None
        assert state.driver_session_id is None
        assert state.final_response is None
        assert state.error is None
