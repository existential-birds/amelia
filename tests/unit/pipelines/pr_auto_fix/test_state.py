"""Unit tests for PR auto-fix state models."""

import uuid
from datetime import datetime, timezone
from enum import StrEnum

import pytest

from amelia.pipelines.pr_auto_fix.state import (
    GroupFixResult,
    GroupFixStatus,
    PRAutoFixState,
)


class TestGroupFixStatus:
    """Tests for GroupFixStatus enum."""

    def test_is_str_enum(self) -> None:
        """GroupFixStatus should be a StrEnum."""
        assert issubclass(GroupFixStatus, StrEnum)

    def test_has_fixed_value(self) -> None:
        assert GroupFixStatus.FIXED == "fixed"

    def test_has_failed_value(self) -> None:
        assert GroupFixStatus.FAILED == "failed"

    def test_has_no_changes_value(self) -> None:
        assert GroupFixStatus.NO_CHANGES == "no_changes"


class TestGroupFixResult:
    """Tests for GroupFixResult model."""

    def test_create_with_all_fields(self) -> None:
        result = GroupFixResult(
            file_path="src/app.py",
            status=GroupFixStatus.FIXED,
            error=None,
            comment_ids=[1, 2, 3],
        )
        assert result.file_path == "src/app.py"
        assert result.status == GroupFixStatus.FIXED
        assert result.error is None
        assert result.comment_ids == [1, 2, 3]

    def test_file_path_nullable(self) -> None:
        result = GroupFixResult(
            file_path=None,
            status=GroupFixStatus.NO_CHANGES,
        )
        assert result.file_path is None

    def test_error_defaults_to_none(self) -> None:
        result = GroupFixResult(
            file_path="a.py",
            status=GroupFixStatus.FIXED,
        )
        assert result.error is None

    def test_comment_ids_defaults_to_empty(self) -> None:
        result = GroupFixResult(
            file_path="a.py",
            status=GroupFixStatus.FIXED,
        )
        assert result.comment_ids == []

    def test_is_frozen(self) -> None:
        result = GroupFixResult(
            file_path="a.py",
            status=GroupFixStatus.FIXED,
        )
        with pytest.raises(Exception):
            result.status = GroupFixStatus.FAILED  # type: ignore[misc]


class TestPRAutoFixState:
    """Tests for PRAutoFixState model."""

    @pytest.fixture()
    def minimal_state(self) -> PRAutoFixState:
        """Create a PRAutoFixState with minimal required fields."""
        return PRAutoFixState(
            workflow_id=uuid.uuid4(),
            profile_id="test-profile",
            created_at=datetime.now(tz=timezone.utc),
            pr_number=42,
            head_branch="fix/typo",
            repo="owner/repo",
        )

    def test_pipeline_type_defaults_to_pr_auto_fix(self, minimal_state: PRAutoFixState) -> None:
        assert minimal_state.pipeline_type == "pr_auto_fix"

    def test_status_defaults_to_pending(self, minimal_state: PRAutoFixState) -> None:
        assert minimal_state.status == "pending"

    def test_required_fields(self, minimal_state: PRAutoFixState) -> None:
        assert minimal_state.pr_number == 42
        assert minimal_state.head_branch == "fix/typo"
        assert minimal_state.repo == "owner/repo"

    def test_classified_comments_defaults_empty(self, minimal_state: PRAutoFixState) -> None:
        assert minimal_state.classified_comments == []

    def test_file_groups_defaults_empty(self, minimal_state: PRAutoFixState) -> None:
        assert minimal_state.file_groups == {}

    def test_goal_defaults_none(self, minimal_state: PRAutoFixState) -> None:
        assert minimal_state.goal is None

    def test_agentic_status_defaults_running(self, minimal_state: PRAutoFixState) -> None:
        from amelia.core.agentic_state import AgenticStatus

        assert minimal_state.agentic_status == AgenticStatus.RUNNING

    def test_commit_sha_defaults_none(self, minimal_state: PRAutoFixState) -> None:
        assert minimal_state.commit_sha is None

    def test_group_results_defaults_empty(self, minimal_state: PRAutoFixState) -> None:
        assert minimal_state.group_results == []

    def test_autofix_config_defaults(self, minimal_state: PRAutoFixState) -> None:
        from amelia.core.types import PRAutoFixConfig

        assert isinstance(minimal_state.autofix_config, PRAutoFixConfig)

    def test_comments_defaults_empty(self, minimal_state: PRAutoFixState) -> None:
        assert minimal_state.comments == []

    def test_is_frozen(self, minimal_state: PRAutoFixState) -> None:
        with pytest.raises(Exception):
            minimal_state.pr_number = 99  # type: ignore[misc]

    def test_extends_base_pipeline_state(self) -> None:
        from amelia.pipelines.base import BasePipelineState

        assert issubclass(PRAutoFixState, BasePipelineState)


class TestPromptDefaults:
    """Tests for developer.pr_fix.system prompt registration."""

    def test_developer_pr_fix_system_registered(self) -> None:
        from amelia.agents.prompts.defaults import PROMPT_DEFAULTS

        assert "developer.pr_fix.system" in PROMPT_DEFAULTS

    def test_developer_pr_fix_system_agent(self) -> None:
        from amelia.agents.prompts.defaults import PROMPT_DEFAULTS

        prompt = PROMPT_DEFAULTS["developer.pr_fix.system"]
        assert prompt.agent == "developer"
