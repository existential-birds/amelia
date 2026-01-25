"""Tests for request schema validation.

These tests verify security validators and format constraints.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from amelia.server.models.requests import (
    BatchStartRequest,
    CreateReviewWorkflowRequest,
    CreateWorkflowRequest,
    RejectRequest,
)


class TestCreateWorkflowRequest:
    """Tests for CreateWorkflowRequest schema."""

    @pytest.mark.parametrize(
        "issue_id",
        [
            "A",
            "PROJ-123",
            "my_issue_123",
            "FEATURE-456-update",
            "bug_fix_789",
            "a" * 100,  # Max length
        ],
    )
    def test_issue_id_valid_patterns(self, issue_id: str) -> None:
        """Test issue_id accepts valid patterns."""
        # Should not raise - validates alphanumeric, dashes, underscores
        CreateWorkflowRequest(issue_id=issue_id, worktree_path="/absolute/path")

    @pytest.mark.parametrize(
        "dangerous_id",
        [
            "../etc/passwd",
            "issue/123",
            "issue;rm -rf",
            "issue|cat",
            "issue$USER",
            "issue`whoami`",
            "issue\0null",
            "issue\nnewline",
            "issue\ttab",
            "issue with spaces",
            "issue@host",
            "issue#anchor",
        ],
    )
    def test_issue_id_rejects_dangerous_characters(self, dangerous_id: str) -> None:
        """Test issue_id rejects path traversal and injection characters."""
        with pytest.raises(ValidationError):
            CreateWorkflowRequest(
                issue_id=dangerous_id,
                worktree_path="/absolute/path",
            )

    @pytest.mark.parametrize(
        "relative_path",
        [
            "relative/path",
            "./current/dir",
            "../parent/dir",
            "~/home/path",
        ],
    )
    def test_worktree_path_must_be_absolute(self, relative_path: str) -> None:
        """Test worktree_path rejects relative paths."""
        with pytest.raises(ValidationError, match="worktree_path.*must be absolute"):
            CreateWorkflowRequest(
                issue_id="PROJ-123",
                worktree_path=relative_path,
            )

    def test_worktree_path_resolves_canonical_form(self) -> None:
        """Test worktree_path is resolved to canonical form."""
        req = CreateWorkflowRequest(
            issue_id="PROJ-123",
            worktree_path="/path/with/../canonical",
        )
        assert ".." not in req.worktree_path
        assert req.worktree_path == "/path/canonical"

    def test_worktree_path_rejects_null_bytes(self) -> None:
        """Test worktree_path rejects null bytes."""
        with pytest.raises(ValidationError):
            CreateWorkflowRequest(
                issue_id="PROJ-123",
                worktree_path="/path/with\0null",
            )

    @pytest.mark.parametrize(
        "profile",
        ["work", "personal", "my-profile", "profile_123"],
    )
    def test_profile_valid_patterns(self, profile: str) -> None:
        """Test profile accepts valid patterns."""
        # Should not raise
        CreateWorkflowRequest(
            issue_id="PROJ-123",
            worktree_path="/absolute/path",
            profile=profile,
        )

    @pytest.mark.parametrize(
        "invalid_profile",
        ["UPPERCASE", "has spaces", "has/slash", "has@symbol", ""],
    )
    def test_profile_rejects_invalid_patterns(self, invalid_profile: str) -> None:
        """Test profile rejects invalid patterns."""
        with pytest.raises(ValidationError):
            CreateWorkflowRequest(
                issue_id="PROJ-123",
                worktree_path="/absolute/path",
                profile=invalid_profile,
            )

    @pytest.mark.parametrize(
        "driver",
        ["sdk:claude", "api", "cli", "custom:my-driver"],
    )
    def test_driver_valid_patterns(self, driver: str) -> None:
        """Test driver accepts valid type:name patterns."""
        # Should not raise
        CreateWorkflowRequest(
            issue_id="PROJ-123",
            worktree_path="/absolute/path",
            driver=driver,
        )

    @pytest.mark.parametrize(
        "invalid_driver",
        ["no-colon", ":missing-type", "missing-name:", "too:many:colons", ""],
    )
    def test_driver_rejects_invalid_patterns(self, invalid_driver: str) -> None:
        """Test driver rejects patterns without type:name format."""
        with pytest.raises(ValidationError):
            CreateWorkflowRequest(
                issue_id="PROJ-123",
                worktree_path="/absolute/path",
                driver=invalid_driver,
            )

    def test_task_description_without_title_rejected(self) -> None:
        """task_description without task_title is rejected."""
        with pytest.raises(ValidationError):
            CreateWorkflowRequest(
                issue_id="TASK-1",
                worktree_path="/absolute/path",
                task_description="Some description without title",
            )

    def test_task_fields_valid(self) -> None:
        """task_title and task_description are accepted together."""
        req = CreateWorkflowRequest(
            issue_id="TASK-1",
            worktree_path="/absolute/path",
            task_title="Add logout button",
            task_description="Add to navbar with confirmation",
        )
        assert req.task_title == "Add logout button"
        assert req.task_description == "Add to navbar with confirmation"

    def test_task_title_only_valid(self) -> None:
        """task_title alone is valid (description defaults to None)."""
        req = CreateWorkflowRequest(
            issue_id="TASK-1",
            worktree_path="/absolute/path",
            task_title="Fix typo in README",
        )
        assert req.task_title == "Fix typo in README"
        assert req.task_description is None


class TestRejectRequest:
    """Tests for RejectRequest schema."""

    def test_valid_request(self) -> None:
        """Test valid reject request construction."""
        # Smoke test - should not raise
        RejectRequest(feedback="Please fix the typo in line 42")


class TestCreateReviewWorkflowRequest:
    """Tests for CreateReviewWorkflowRequest validation."""

    def test_valid_request(self, tmp_path: Path) -> None:
        """Valid request with all fields passes validation."""
        worktree = tmp_path / "repo"
        worktree.mkdir()

        request = CreateReviewWorkflowRequest(
            diff_content="+ added line",
            worktree_path=str(worktree),
            profile="default",
        )

        assert request.diff_content == "+ added line"
        assert request.worktree_path == str(worktree)
        assert request.profile == "default"

    def test_empty_diff_content_rejected(self, tmp_path: Path) -> None:
        """Empty diff_content is rejected."""
        worktree = tmp_path / "repo"
        worktree.mkdir()

        with pytest.raises(ValidationError) as exc_info:
            CreateReviewWorkflowRequest(
                diff_content="",
                worktree_path=str(worktree),
            )

        error_str = str(exc_info.value).lower()
        assert "at least 1 character" in error_str or "string_too_short" in error_str

    def test_invalid_worktree_path_rejected(self) -> None:
        """Relative worktree path is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CreateReviewWorkflowRequest(
                diff_content="+ line",
                worktree_path="relative/path/to/repo",
            )

        assert "must be absolute" in str(exc_info.value).lower()

    def test_optional_fields_default_to_none(self, tmp_path: Path) -> None:
        """Optional fields default to None when not provided."""
        worktree = tmp_path / "repo"
        worktree.mkdir()

        request = CreateReviewWorkflowRequest(
            diff_content="+ line",
            worktree_path=str(worktree),
        )

        assert request.profile is None


class TestCreateWorkflowRequestQueueParams:
    """Tests for queue-related parameters."""

    def test_start_defaults_to_true(self) -> None:
        """start should default to True for backward compatibility."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
        )
        assert request.start is True

    def test_plan_now_defaults_to_false(self) -> None:
        """plan_now should default to False."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
        )
        assert request.plan_now is False

    def test_queue_mode_start_false(self) -> None:
        """Setting start=False queues without immediate execution."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
        )
        assert request.start is False
        assert request.plan_now is False

    def test_queue_with_plan_mode(self) -> None:
        """Setting start=False, plan_now=True runs Architect then queues."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=False,
            plan_now=True,
        )
        assert request.start is False
        assert request.plan_now is True

    def test_plan_now_ignored_when_start_true(self) -> None:
        """plan_now is ignored when start=True (immediate execution)."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            start=True,
            plan_now=True,
        )
        # Should be valid - plan_now is simply ignored
        assert request.start is True
        assert request.plan_now is True  # Stored but not used


class TestCreateWorkflowRequestArtifactPath:
    """Tests for artifact_path field."""

    def test_artifact_path_accepts_valid_path(self) -> None:
        """artifact_path accepts absolute path."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            artifact_path="/path/to/artifact.md",
        )
        assert request.artifact_path == "/path/to/artifact.md"

    def test_artifact_path_defaults_to_none(self) -> None:
        """artifact_path defaults to None."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
        )
        assert request.artifact_path is None

    def test_artifact_path_accepts_none_explicitly(self) -> None:
        """artifact_path can be set to None explicitly."""
        request = CreateWorkflowRequest(
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            artifact_path=None,
        )
        assert request.artifact_path is None


class TestCreateWorkflowRequestPlanFields:
    """Tests for plan_file and plan_content fields."""

    def test_plan_file_is_optional(self) -> None:
        """plan_file should be optional and default to None."""
        request = CreateWorkflowRequest(
            issue_id="TEST-001",
            worktree_path="/path/to/repo",
        )
        assert request.plan_file is None

    def test_plan_content_is_optional(self) -> None:
        """plan_content should be optional and default to None."""
        request = CreateWorkflowRequest(
            issue_id="TEST-001",
            worktree_path="/path/to/repo",
        )
        assert request.plan_content is None

    def test_plan_file_and_plan_content_mutually_exclusive(self) -> None:
        """Cannot provide both plan_file and plan_content."""
        with pytest.raises(ValidationError, match="mutually exclusive"):
            CreateWorkflowRequest(
                issue_id="TEST-001",
                worktree_path="/path/to/repo",
                plan_file="plan.md",
                plan_content="# Plan content",
            )

    def test_plan_file_accepted_alone(self) -> None:
        """plan_file can be provided without plan_content (requires start=False)."""
        request = CreateWorkflowRequest(
            issue_id="TEST-001",
            worktree_path="/path/to/repo",
            plan_file="docs/plan.md",
            start=False,
        )
        assert request.plan_file == "docs/plan.md"
        assert request.plan_content is None

    def test_plan_content_accepted_alone(self) -> None:
        """plan_content can be provided without plan_file (requires start=False)."""
        request = CreateWorkflowRequest(
            issue_id="TEST-001",
            worktree_path="/path/to/repo",
            plan_content="# My Plan\n\n### Task 1: Do thing",
            start=False,
        )
        assert request.plan_content == "# My Plan\n\n### Task 1: Do thing"
        assert request.plan_file is None

    def test_plan_file_rejected_with_start_true(self) -> None:
        """plan_file cannot be provided when start=True."""
        with pytest.raises(ValidationError, match="start=False"):
            CreateWorkflowRequest(
                issue_id="TEST-001",
                worktree_path="/path/to/repo",
                plan_file="docs/plan.md",
                start=True,
            )

    def test_plan_content_rejected_with_plan_now_true(self) -> None:
        """plan_content cannot be provided when plan_now=True."""
        with pytest.raises(ValidationError, match="start=False"):
            CreateWorkflowRequest(
                issue_id="TEST-001",
                worktree_path="/path/to/repo",
                plan_content="# Plan",
                start=False,
                plan_now=True,
            )


class TestBatchStartRequest:
    """Tests for BatchStartRequest model."""

    def test_empty_request_valid(self) -> None:
        """Empty request means start all pending workflows."""
        request = BatchStartRequest()
        assert request.workflow_ids is None
        assert request.worktree_path is None

    def test_specific_workflow_ids(self) -> None:
        """Can specify exact workflow IDs to start."""
        request = BatchStartRequest(workflow_ids=["wf-1", "wf-2", "wf-3"])
        assert request.workflow_ids == ["wf-1", "wf-2", "wf-3"]

    def test_filter_by_worktree(self) -> None:
        """Can filter by worktree path."""
        request = BatchStartRequest(worktree_path="/path/to/repo")
        assert request.worktree_path == "/path/to/repo"

    def test_combined_filter(self) -> None:
        """Can combine workflow IDs and worktree filter."""
        request = BatchStartRequest(
            workflow_ids=["wf-1", "wf-2"],
            worktree_path="/path/to/repo",
        )
        assert request.workflow_ids == ["wf-1", "wf-2"]
        assert request.worktree_path == "/path/to/repo"


class TestSetPlanRequest:
    """Tests for SetPlanRequest model."""

    def test_requires_either_plan_file_or_plan_content(self) -> None:
        """Must provide either plan_file or plan_content."""
        from amelia.server.models.requests import SetPlanRequest

        with pytest.raises(ValidationError, match="Either plan_file or plan_content"):
            SetPlanRequest()

    def test_plan_file_and_plan_content_mutually_exclusive(self) -> None:
        """Cannot provide both plan_file and plan_content."""
        from amelia.server.models.requests import SetPlanRequest

        with pytest.raises(ValidationError, match="mutually exclusive"):
            SetPlanRequest(
                plan_file="plan.md",
                plan_content="# Plan",
            )

    def test_force_defaults_to_false(self) -> None:
        """force should default to False."""
        from amelia.server.models.requests import SetPlanRequest

        request = SetPlanRequest(plan_file="plan.md")
        assert request.force is False

    def test_force_can_be_set_true(self) -> None:
        """force can be explicitly set to True."""
        from amelia.server.models.requests import SetPlanRequest

        request = SetPlanRequest(plan_content="# Plan", force=True)
        assert request.force is True
