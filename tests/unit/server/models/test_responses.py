"""Tests for response schemas."""

from datetime import datetime, timezone

import pytest

from amelia.server.models.responses import (
    CreateWorkflowResponse,
    ErrorResponse,
    TokenSummary,
    WorkflowDetailResponse,
    WorkflowListResponse,
    WorkflowSummary,
)


class TestCreateWorkflowResponse:
    """Tests for CreateWorkflowResponse schema."""

    def test_valid_response(self):
        """Test valid workflow creation response."""
        resp = CreateWorkflowResponse(
            id="wf-123",
            status="pending",
            message="Workflow created successfully",
        )
        assert resp.id == "wf-123"
        assert resp.status == "pending"
        assert resp.message == "Workflow created successfully"


class TestWorkflowSummary:
    """Tests for WorkflowSummary schema."""

    def test_minimal_summary(self):
        """Test workflow summary with required fields only."""
        summary = WorkflowSummary(
            id="wf-123",
            issue_id="PROJ-123",
            worktree_name="worktree-123",
            status="pending",
        )
        assert summary.id == "wf-123"
        assert summary.issue_id == "PROJ-123"
        assert summary.worktree_name == "worktree-123"
        assert summary.status == "pending"
        assert summary.started_at is None
        assert summary.current_stage is None

    def test_full_summary(self):
        """Test workflow summary with all optional fields."""
        started = datetime.now(timezone.utc)
        summary = WorkflowSummary(
            id="wf-123",
            issue_id="PROJ-123",
            worktree_name="worktree-123",
            status="in_progress",
            started_at=started,
            current_stage="developer",
        )
        assert summary.id == "wf-123"
        assert summary.issue_id == "PROJ-123"
        assert summary.worktree_name == "worktree-123"
        assert summary.status == "in_progress"
        assert summary.started_at == started
        assert summary.current_stage == "developer"


class TestWorkflowListResponse:
    """Tests for WorkflowListResponse schema."""

    def test_empty_list(self):
        """Test empty workflow list response."""
        resp = WorkflowListResponse(
            workflows=[],
            total=0,
        )
        assert resp.workflows == []
        assert resp.total == 0
        assert resp.cursor is None
        assert resp.has_more is False

    def test_list_with_workflows(self):
        """Test workflow list with multiple workflows."""
        workflows = [
            WorkflowSummary(
                id="wf-1",
                issue_id="PROJ-1",
                worktree_name="worktree-1",
                status="pending",
            ),
            WorkflowSummary(
                id="wf-2",
                issue_id="PROJ-2",
                worktree_name="worktree-2",
                status="in_progress",
            ),
        ]
        resp = WorkflowListResponse(
            workflows=workflows,
            total=10,
            cursor="next-page-token",
            has_more=True,
        )
        assert len(resp.workflows) == 2
        assert resp.total == 10
        assert resp.cursor == "next-page-token"
        assert resp.has_more is True


class TestWorkflowDetailResponse:
    """Tests for WorkflowDetailResponse schema."""

    def test_minimal_detail(self):
        """Test workflow detail with required fields only."""
        detail = WorkflowDetailResponse(
            id="wf-123",
            issue_id="PROJ-123",
            worktree_path="/path/to/worktree",
            worktree_name="worktree-123",
            status="pending",
            recent_events=[],
        )
        assert detail.id == "wf-123"
        assert detail.issue_id == "PROJ-123"
        assert detail.worktree_name == "worktree-123"
        assert detail.status == "pending"
        assert detail.started_at is None
        assert detail.current_stage is None
        assert detail.plan is None
        assert detail.token_usage is None
        assert detail.recent_events == []

    def test_full_detail(self):
        """Test workflow detail with all optional fields."""
        started = datetime.now(timezone.utc)
        token_usage = TokenSummary(
            total_tokens=1000,
            total_cost_usd=0.05,
        )
        detail = WorkflowDetailResponse(
            id="wf-123",
            issue_id="PROJ-123",
            worktree_path="/path/to/worktree",
            worktree_name="worktree-123",
            status="in_progress",
            started_at=started,
            current_stage="developer",
            plan={"tasks": [{"id": 1, "description": "Task 1"}]},
            token_usage=token_usage,
            recent_events=[
                {"type": "workflow.started", "timestamp": started.isoformat()}
            ],
        )
        assert detail.id == "wf-123"
        assert detail.status == "in_progress"
        assert detail.started_at == started
        assert detail.current_stage == "developer"
        assert detail.plan == {"tasks": [{"id": 1, "description": "Task 1"}]}
        assert detail.token_usage == token_usage
        assert len(detail.recent_events) == 1


class TestTokenSummary:
    """Tests for TokenSummary schema."""

    def test_valid_summary(self):
        """Test valid token usage summary."""
        summary = TokenSummary(
            total_tokens=1500,
            total_cost_usd=0.075,
        )
        assert summary.total_tokens == 1500
        assert summary.total_cost_usd == 0.075


class TestErrorResponse:
    """Tests for ErrorResponse schema."""

    def test_minimal_error(self):
        """Test error response with required fields only."""
        error = ErrorResponse(
            error="Something went wrong",
            code="INTERNAL_ERROR",
        )
        assert error.error == "Something went wrong"
        assert error.code == "INTERNAL_ERROR"
        assert error.details is None

    def test_error_with_details(self):
        """Test error response with details."""
        error = ErrorResponse(
            error="Validation failed",
            code="VALIDATION_ERROR",
            details={"field": "issue_id", "message": "Invalid format"},
        )
        assert error.error == "Validation failed"
        assert error.code == "VALIDATION_ERROR"
        assert error.details == {"field": "issue_id", "message": "Invalid format"}
