"""Tests for request schema validation.

These tests verify security validators and format constraints.
"""

import pytest
from pydantic import ValidationError

from amelia.server.models.requests import CreateWorkflowRequest, RejectRequest


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
    def test_issue_id_valid_patterns(self, issue_id):
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
    def test_issue_id_rejects_dangerous_characters(self, dangerous_id):
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
    def test_worktree_path_must_be_absolute(self, relative_path):
        """Test worktree_path rejects relative paths."""
        with pytest.raises(ValidationError, match="worktree_path.*must be absolute"):
            CreateWorkflowRequest(
                issue_id="PROJ-123",
                worktree_path=relative_path,
            )

    def test_worktree_path_resolves_canonical_form(self):
        """Test worktree_path is resolved to canonical form."""
        req = CreateWorkflowRequest(
            issue_id="PROJ-123",
            worktree_path="/path/with/../canonical",
        )
        assert ".." not in req.worktree_path
        assert req.worktree_path == "/path/canonical"

    def test_worktree_path_rejects_null_bytes(self):
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
    def test_profile_valid_patterns(self, profile):
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
    def test_profile_rejects_invalid_patterns(self, invalid_profile):
        """Test profile rejects invalid patterns."""
        with pytest.raises(ValidationError):
            CreateWorkflowRequest(
                issue_id="PROJ-123",
                worktree_path="/absolute/path",
                profile=invalid_profile,
            )

    @pytest.mark.parametrize(
        "driver",
        ["sdk:claude", "api:openai", "cli:claude", "custom:my-driver"],
    )
    def test_driver_valid_patterns(self, driver):
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
    def test_driver_rejects_invalid_patterns(self, invalid_driver):
        """Test driver rejects patterns without type:name format."""
        with pytest.raises(ValidationError):
            CreateWorkflowRequest(
                issue_id="PROJ-123",
                worktree_path="/absolute/path",
                driver=invalid_driver,
            )


class TestRejectRequest:
    """Tests for RejectRequest schema."""

    def test_valid_request(self):
        """Test valid reject request construction."""
        # Smoke test - should not raise
        RejectRequest(feedback="Please fix the typo in line 42")
