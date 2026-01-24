"""Unit tests for ImplementationState."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from amelia.core.types import Design, Issue
from amelia.pipelines.base import BasePipelineState
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)


# Rebuild to resolve forward references for Pydantic
rebuild_implementation_state()


class TestImplementationState:
    """Tests for ImplementationState model."""

    def test_inherits_from_base(self) -> None:
        """ImplementationState should inherit from BasePipelineState."""
        assert issubclass(ImplementationState, BasePipelineState)

    def test_pipeline_type_is_implementation(self) -> None:
        """ImplementationState should have pipeline_type='implementation'."""
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="default",
            created_at=datetime.now(UTC),
            status="pending",
        )
        assert state.pipeline_type == "implementation"

    def test_required_fields_inherited(self) -> None:
        """Should require workflow_id, profile_id, created_at, status."""
        with pytest.raises(ValidationError):
            ImplementationState()  # type: ignore[call-arg]  # Intentional: testing ValidationError on missing required fields

    def test_optional_domain_fields(self) -> None:
        """Should have optional domain fields with defaults."""
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="default",
            created_at=datetime.now(UTC),
            status="pending",
        )
        assert state.issue is None
        assert state.design is None
        assert state.goal is None
        assert state.plan_markdown is None
        assert state.key_files == []

    def test_with_issue(self) -> None:
        """Should accept Issue object."""
        issue = Issue(id="ISSUE-123", title="Test", description="Description")
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="default",
            created_at=datetime.now(UTC),
            status="running",
            issue=issue,
        )
        assert state.issue == issue

    def test_with_design(self) -> None:
        """Should accept Design object."""
        design = Design(content="# Design doc", source="file")
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="default",
            created_at=datetime.now(UTC),
            status="running",
            design=design,
        )
        assert state.design == design

    def test_task_tracking_fields(self) -> None:
        """Should have multi-task execution tracking fields."""
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="default",
            created_at=datetime.now(UTC),
            status="running",
            total_tasks=5,
            current_task_index=2,
            task_review_iteration=1,
        )
        assert state.total_tasks == 5
        assert state.current_task_index == 2
        assert state.task_review_iteration == 1

    def test_state_is_frozen(self) -> None:
        """ImplementationState should be immutable."""
        state = ImplementationState(
            workflow_id="wf-1",
            profile_id="default",
            created_at=datetime.now(UTC),
            status="pending",
        )
        with pytest.raises(ValidationError):
            state.status = "running"
