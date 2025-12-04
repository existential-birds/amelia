"""Tests for response schema defaults and computed behavior.

These tests verify default values and any custom behavior - NOT field assignment,
which Pydantic already guarantees.
"""

from amelia.server.models.responses import (
    WorkflowDetailResponse,
    WorkflowListResponse,
    WorkflowSummary,
)


class TestWorkflowSummaryDefaults:
    """Test WorkflowSummary default values."""

    def test_optional_fields_default_to_none(self):
        """Optional fields should default to None when not provided."""
        summary = WorkflowSummary(
            id="wf-123",
            issue_id="PROJ-123",
            worktree_name="worktree-123",
            status="pending",
        )
        assert summary.started_at is None
        assert summary.current_stage is None


class TestWorkflowListResponseDefaults:
    """Test WorkflowListResponse default values."""

    def test_pagination_defaults(self):
        """Pagination fields should have sensible defaults."""
        resp = WorkflowListResponse(workflows=[], total=0)
        assert resp.cursor is None
        assert resp.has_more is False


class TestWorkflowDetailResponseDefaults:
    """Test WorkflowDetailResponse default values."""

    def test_optional_fields_default_to_none(self):
        """Optional fields should default to None when not provided."""
        detail = WorkflowDetailResponse(
            id="wf-123",
            issue_id="PROJ-123",
            worktree_path="/path/to/worktree",
            worktree_name="worktree-123",
            status="pending",
            recent_events=[],
        )
        assert detail.started_at is None
        assert detail.current_stage is None
        assert detail.plan is None
        assert detail.token_usage is None
