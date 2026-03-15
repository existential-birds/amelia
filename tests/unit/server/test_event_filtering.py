"""Tests for event type classification and response model fields."""

import uuid
from datetime import UTC, datetime

import pytest

from amelia.server.models.events import (
    PERSISTED_TYPES,
    EventLevel,
    EventType,
    get_event_level,
)
from amelia.server.models.responses import WorkflowDetailResponse, WorkflowSummary
from amelia.server.models.state import WorkflowStatus, WorkflowType


# ---------------------------------------------------------------------------
# PR auto-fix event types: existence and values
# ---------------------------------------------------------------------------


class TestPRAutoFixEventTypes:
    """Tests for new PR auto-fix lifecycle event types."""

    @pytest.mark.parametrize(
        ("member", "value"),
        [
            ("PR_COMMENTS_DETECTED", "pr_comments_detected"),
            ("PR_AUTO_FIX_STARTED", "pr_auto_fix_started"),
            ("PR_AUTO_FIX_COMPLETED", "pr_auto_fix_completed"),
            ("PR_COMMENTS_RESOLVED", "pr_comments_resolved"),
            ("PR_POLL_ERROR", "pr_poll_error"),
        ],
    )
    def test_event_type_exists_with_correct_value(
        self, member: str, value: str
    ) -> None:
        event = getattr(EventType, member)
        assert event == value
        assert isinstance(event, EventType)


# ---------------------------------------------------------------------------
# Event level classification
# ---------------------------------------------------------------------------


class TestPRAutoFixEventClassification:
    """Tests for correct INFO/ERROR classification of new event types."""

    @pytest.mark.parametrize(
        "event_type",
        [
            EventType.PR_COMMENTS_DETECTED,
            EventType.PR_AUTO_FIX_STARTED,
            EventType.PR_AUTO_FIX_COMPLETED,
            EventType.PR_COMMENTS_RESOLVED,
        ],
    )
    def test_info_events(self, event_type: EventType) -> None:
        assert get_event_level(event_type) == EventLevel.INFO

    def test_pr_poll_error_is_error(self) -> None:
        assert get_event_level(EventType.PR_POLL_ERROR) == EventLevel.ERROR


# ---------------------------------------------------------------------------
# Persistence classification
# ---------------------------------------------------------------------------


class TestPRAutoFixPersistence:
    """Tests for PERSISTED_TYPES membership of new event types."""

    @pytest.mark.parametrize(
        "event_type",
        [
            EventType.PR_AUTO_FIX_STARTED,
            EventType.PR_AUTO_FIX_COMPLETED,
            EventType.PR_POLL_ERROR,
        ],
    )
    def test_persisted_events(self, event_type: EventType) -> None:
        assert event_type in PERSISTED_TYPES

    @pytest.mark.parametrize(
        "event_type",
        [
            EventType.PR_COMMENTS_DETECTED,
            EventType.PR_COMMENTS_RESOLVED,
        ],
    )
    def test_non_persisted_events(self, event_type: EventType) -> None:
        assert event_type not in PERSISTED_TYPES


# ---------------------------------------------------------------------------
# WorkflowType.PR_AUTO_FIX
# ---------------------------------------------------------------------------


class TestWorkflowTypePRAutoFix:
    """Tests for the PR_AUTO_FIX workflow type."""

    def test_pr_auto_fix_value(self) -> None:
        assert WorkflowType.PR_AUTO_FIX == "pr_auto_fix"

    def test_pr_auto_fix_is_workflow_type(self) -> None:
        assert isinstance(WorkflowType.PR_AUTO_FIX, WorkflowType)


# ---------------------------------------------------------------------------
# WorkflowSummary new fields
# ---------------------------------------------------------------------------


class TestWorkflowSummaryFields:
    """Tests for pipeline_type, pr_number, pr_title, pr_comment_count on WorkflowSummary."""

    def test_pipeline_type_defaults_to_none(self) -> None:
        summary = WorkflowSummary(
            id=uuid.uuid4(),
            issue_id="ISSUE-1",
            worktree_path="/tmp/repo",
            status=WorkflowStatus.COMPLETED,
            created_at=datetime.now(UTC),
        )
        assert summary.pipeline_type is None

    def test_pipeline_type_accepts_value(self) -> None:
        summary = WorkflowSummary(
            id=uuid.uuid4(),
            issue_id="ISSUE-1",
            worktree_path="/tmp/repo",
            status=WorkflowStatus.COMPLETED,
            created_at=datetime.now(UTC),
            pipeline_type="pr_auto_fix",
        )
        assert summary.pipeline_type == "pr_auto_fix"

    def test_pr_number_defaults_to_none(self) -> None:
        summary = WorkflowSummary(
            id=uuid.uuid4(),
            issue_id="ISSUE-1",
            worktree_path="/tmp/repo",
            status=WorkflowStatus.COMPLETED,
            created_at=datetime.now(UTC),
        )
        assert summary.pr_number is None

    def test_pr_title_defaults_to_none(self) -> None:
        summary = WorkflowSummary(
            id=uuid.uuid4(),
            issue_id="ISSUE-1",
            worktree_path="/tmp/repo",
            status=WorkflowStatus.COMPLETED,
            created_at=datetime.now(UTC),
        )
        assert summary.pr_title is None

    def test_pr_comment_count_defaults_to_none(self) -> None:
        summary = WorkflowSummary(
            id=uuid.uuid4(),
            issue_id="ISSUE-1",
            worktree_path="/tmp/repo",
            status=WorkflowStatus.COMPLETED,
            created_at=datetime.now(UTC),
        )
        assert summary.pr_comment_count is None

    def test_pr_fields_accept_values(self) -> None:
        summary = WorkflowSummary(
            id=uuid.uuid4(),
            issue_id="PR-42",
            worktree_path="/tmp/repo",
            status=WorkflowStatus.COMPLETED,
            created_at=datetime.now(UTC),
            pipeline_type="pr_auto_fix",
            pr_number=42,
            pr_title="Fix: broken tests",
            pr_comment_count=5,
        )
        assert summary.pr_number == 42
        assert summary.pr_title == "Fix: broken tests"
        assert summary.pr_comment_count == 5


# ---------------------------------------------------------------------------
# WorkflowDetailResponse new fields
# ---------------------------------------------------------------------------


class TestWorkflowDetailResponseFields:
    """Tests for pipeline_type, pr_comments, pr_number, pr_title, pr_comment_count on WorkflowDetailResponse."""

    def _make_detail(self, **kwargs: object) -> WorkflowDetailResponse:
        defaults = {
            "id": uuid.uuid4(),
            "issue_id": "ISSUE-1",
            "worktree_path": "/tmp/repo",
            "status": WorkflowStatus.COMPLETED,
            "created_at": datetime.now(UTC),
            "recent_events": [],
        }
        defaults.update(kwargs)
        return WorkflowDetailResponse(**defaults)  # type: ignore[arg-type]

    def test_pipeline_type_defaults_to_none(self) -> None:
        detail = self._make_detail()
        assert detail.pipeline_type is None

    def test_pipeline_type_accepts_value(self) -> None:
        detail = self._make_detail(pipeline_type="pr_auto_fix")
        assert detail.pipeline_type == "pr_auto_fix"

    def test_pr_comments_defaults_to_none(self) -> None:
        detail = self._make_detail()
        assert detail.pr_comments is None

    def test_pr_comments_accepts_list(self) -> None:
        comments = [{"comment_id": 1, "status": "fixed"}]
        detail = self._make_detail(pr_comments=comments)
        assert detail.pr_comments == comments

    def test_pr_number_defaults_to_none(self) -> None:
        detail = self._make_detail()
        assert detail.pr_number is None

    def test_pr_title_defaults_to_none(self) -> None:
        detail = self._make_detail()
        assert detail.pr_title is None

    def test_pr_comment_count_defaults_to_none(self) -> None:
        detail = self._make_detail()
        assert detail.pr_comment_count is None

    def test_pr_fields_accept_values(self) -> None:
        detail = self._make_detail(
            pipeline_type="pr_auto_fix",
            pr_number=42,
            pr_title="Fix: broken tests",
            pr_comment_count=5,
            pr_comments=[{"comment_id": 1}],
        )
        assert detail.pr_number == 42
        assert detail.pr_title == "Fix: broken tests"
        assert detail.pr_comment_count == 5
        assert detail.pr_comments == [{"comment_id": 1}]
