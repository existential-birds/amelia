"""Unit tests for PR auto-fix state models."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

import pytest
from pydantic import ValidationError

from amelia.core.agentic_state import AgenticStatus
from amelia.core.types import PRAutoFixConfig
from amelia.pipelines.base import BasePipelineState
from amelia.pipelines.pr_auto_fix.state import (
    GroupFixResult,
    GroupFixStatus,
    PRAutoFixState,
)


class TestGroupFixStatus:
    """Tests for GroupFixStatus enum."""

    def test_is_str_enum(self) -> None:
        assert issubclass(GroupFixStatus, StrEnum)

    @pytest.mark.parametrize(
        ("member", "value"),
        [("FIXED", "fixed"), ("FAILED", "failed"), ("NO_CHANGES", "no_changes")],
    )
    def test_member_values(self, member: str, value: str) -> None:
        assert getattr(GroupFixStatus, member) == value


class TestGroupFixResult:
    """Tests for GroupFixResult model."""

    def test_create_with_all_fields(self) -> None:
        result = GroupFixResult(
            file_path="src/app.py", status=GroupFixStatus.FIXED,
            error=None, comment_ids=[1, 2, 3],
        )
        assert result.file_path == "src/app.py"
        assert result.status == GroupFixStatus.FIXED
        assert result.error is None
        assert result.comment_ids == [1, 2, 3]

    def test_file_path_nullable(self) -> None:
        assert GroupFixResult(file_path=None, status=GroupFixStatus.NO_CHANGES).file_path is None

    @pytest.mark.parametrize(
        ("field", "expected"),
        [("error", None), ("comment_ids", [])],
    )
    def test_defaults(self, field: str, expected: object) -> None:
        result = GroupFixResult(file_path="a.py", status=GroupFixStatus.FIXED)
        assert getattr(result, field) == expected

    def test_is_frozen(self) -> None:
        result = GroupFixResult(file_path="a.py", status=GroupFixStatus.FIXED)
        with pytest.raises(ValidationError):
            result.status = GroupFixStatus.FAILED  # type: ignore[misc]


class TestPRAutoFixState:
    """Tests for PRAutoFixState model."""

    @pytest.fixture()
    def minimal_state(self) -> PRAutoFixState:
        return PRAutoFixState(
            workflow_id=uuid.uuid4(),
            profile_id="test-profile",
            created_at=datetime.now(tz=UTC),
            pr_number=42,
            head_branch="fix/typo",
            repo="owner/repo",
        )

    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("pipeline_type", "pr_auto_fix"),
            ("status", "pending"),
            ("pr_number", 42),
            ("head_branch", "fix/typo"),
            ("repo", "owner/repo"),
            ("classified_comments", []),
            ("file_groups", {}),
            ("goal", None),
            ("commit_sha", None),
            ("group_results", []),
            ("comments", []),
        ],
    )
    def test_field_values(self, minimal_state: PRAutoFixState, field: str, expected: object) -> None:
        assert getattr(minimal_state, field) == expected

    def test_agentic_status_defaults_running(self, minimal_state: PRAutoFixState) -> None:
        assert minimal_state.agentic_status == AgenticStatus.RUNNING

    def test_autofix_config_defaults(self, minimal_state: PRAutoFixState) -> None:
        assert isinstance(minimal_state.autofix_config, PRAutoFixConfig)

    def test_is_frozen(self, minimal_state: PRAutoFixState) -> None:
        with pytest.raises(ValidationError):
            minimal_state.pr_number = 99  # type: ignore[misc]

    def test_extends_base_pipeline_state(self) -> None:
        assert issubclass(PRAutoFixState, BasePipelineState)


class TestPromptDefaults:
    """Tests for developer.pr_fix.system prompt registration."""

    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("agent", "developer"),
        ],
    )
    def test_developer_pr_fix_system_prompt(self, field: str, expected: str) -> None:
        from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
        assert "developer.pr_fix.system" in PROMPT_DEFAULTS
        assert getattr(PROMPT_DEFAULTS["developer.pr_fix.system"], field) == expected
