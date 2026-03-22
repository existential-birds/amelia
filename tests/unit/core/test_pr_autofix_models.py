"""Tests for PR auto-fix data models: AggressivenessLevel, PRSummary, PRReviewComment, PRAutoFixConfig."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from amelia.core.types import (
    AggressivenessLevel,
    PRAutoFixConfig,
    Profile,
    PRReviewComment,
    PRSummary,
    TrackerType,
)


class TestAggressivenessLevel:
    """DATA-04: AggressivenessLevel IntEnum tests."""

    def test_values(self) -> None:
        assert AggressivenessLevel.CRITICAL == 1
        assert AggressivenessLevel.STANDARD == 2
        assert AggressivenessLevel.THOROUGH == 3
        assert AggressivenessLevel.EXEMPLARY == 4

    def test_ordering(self) -> None:
        assert AggressivenessLevel.CRITICAL < AggressivenessLevel.STANDARD
        assert AggressivenessLevel.STANDARD < AggressivenessLevel.THOROUGH
        assert AggressivenessLevel.THOROUGH < AggressivenessLevel.EXEMPLARY
        assert AggressivenessLevel.CRITICAL < AggressivenessLevel.THOROUGH

    def test_threshold_comparison(self) -> None:
        level = AggressivenessLevel.STANDARD
        assert level >= AggressivenessLevel.CRITICAL
        assert level >= AggressivenessLevel.STANDARD
        assert not (level >= AggressivenessLevel.THOROUGH)

    def test_exemplary_threshold_comparison(self) -> None:
        level = AggressivenessLevel.EXEMPLARY
        assert level >= AggressivenessLevel.THOROUGH
        assert level >= AggressivenessLevel.STANDARD
        assert level >= AggressivenessLevel.CRITICAL

    def test_exactly_four_members(self) -> None:
        assert len(AggressivenessLevel) == 4


class TestPRSummary:
    """DATA-01: PRSummary frozen Pydantic model tests."""

    @pytest.fixture()
    def pr_summary(self) -> PRSummary:
        return PRSummary(
            number=42,
            title="Fix bug in auth",
            head_branch="fix/auth-bug",
            author="octocat",
            updated_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )

    def test_all_fields_required(self, pr_summary: PRSummary) -> None:
        assert pr_summary.number == 42
        assert pr_summary.title == "Fix bug in auth"
        assert pr_summary.head_branch == "fix/auth-bug"
        assert pr_summary.author == "octocat"
        assert pr_summary.updated_at == datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

    def test_immutable(self, pr_summary: PRSummary) -> None:
        with pytest.raises(ValidationError):
            pr_summary.number = 99  # type: ignore[misc]

    def test_missing_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            PRSummary(number=1, title="t", head_branch="b", author="a")  # type: ignore[call-arg]

    def test_round_trip_serialization(self, pr_summary: PRSummary) -> None:
        data = pr_summary.model_dump()
        restored = PRSummary.model_validate(data)
        assert restored == pr_summary


class TestPRReviewComment:
    """DATA-02: PRReviewComment frozen Pydantic model tests."""

    @pytest.fixture()
    def general_comment(self) -> PRReviewComment:
        return PRReviewComment(
            id=101,
            body="Looks good overall",
            author="reviewer1",
            created_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
        )

    @pytest.fixture()
    def inline_comment(self) -> PRReviewComment:
        return PRReviewComment(
            id=102,
            body="Use a constant here",
            author="reviewer2",
            created_at=datetime(2026, 1, 15, 13, 0, 0, tzinfo=UTC),
            path="src/auth.py",
            line=42,
            original_line=42,
            start_line=40,
            original_start_line=40,
            side="RIGHT",
            subject_type="line",
            diff_hunk="@@ -40,3 +40,5 @@\n some code",
            in_reply_to_id=100,
            thread_id="PRRT_abc123",
            node_id="MDI0OlB1bGxSZXF1ZXN0UmV2aWV3Q29tbWVudDEwMg==",
            pr_number=42,
        )

    def test_general_comment_defaults(self, general_comment: PRReviewComment) -> None:
        assert general_comment.path is None
        assert general_comment.line is None
        assert general_comment.original_line is None
        assert general_comment.start_line is None
        assert general_comment.original_start_line is None
        assert general_comment.side is None
        assert general_comment.subject_type is None
        assert general_comment.diff_hunk is None
        assert general_comment.in_reply_to_id is None
        assert general_comment.thread_id is None
        assert general_comment.node_id is None
        assert general_comment.pr_number is None

    def test_inline_comment_fields(self, inline_comment: PRReviewComment) -> None:
        assert inline_comment.path == "src/auth.py"
        assert inline_comment.line == 42
        assert inline_comment.original_line == 42
        assert inline_comment.start_line == 40
        assert inline_comment.original_start_line == 40
        assert inline_comment.side == "RIGHT"
        assert inline_comment.subject_type == "line"
        assert inline_comment.diff_hunk is not None
        assert inline_comment.in_reply_to_id == 100
        assert inline_comment.thread_id == "PRRT_abc123"
        assert inline_comment.node_id is not None
        assert inline_comment.pr_number == 42

    def test_immutable(self, general_comment: PRReviewComment) -> None:
        with pytest.raises(ValidationError):
            general_comment.body = "changed"  # type: ignore[misc]

    def test_round_trip_serialization(self, inline_comment: PRReviewComment) -> None:
        data = inline_comment.model_dump()
        restored = PRReviewComment.model_validate(data)
        assert restored == inline_comment


class TestPRAutoFixConfig:
    """DATA-03 / CONF-01: PRAutoFixConfig defaults and validation tests."""

    def test_defaults(self) -> None:
        config = PRAutoFixConfig()
        assert config.aggressiveness == AggressivenessLevel.STANDARD
        assert config.poll_interval == 60
        assert config.auto_resolve is True
        assert config.max_iterations == 3
        assert config.commit_prefix == "fix(review):"

    def test_immutable(self) -> None:
        config = PRAutoFixConfig()
        with pytest.raises(ValidationError):
            config.aggressiveness = AggressivenessLevel.THOROUGH  # type: ignore[misc]

    @pytest.mark.parametrize("value", [5, 7200])
    def test_poll_interval_out_of_range(self, value: int) -> None:
        with pytest.raises(ValidationError, match="poll_interval"):
            PRAutoFixConfig(poll_interval=value)

    def test_poll_interval_bounds_valid(self) -> None:
        assert PRAutoFixConfig(poll_interval=10).poll_interval == 10
        assert PRAutoFixConfig(poll_interval=3600).poll_interval == 3600

    @pytest.mark.parametrize("value", [0, 11])
    def test_max_iterations_out_of_range(self, value: int) -> None:
        with pytest.raises(ValidationError, match="max_iterations"):
            PRAutoFixConfig(max_iterations=value)

    def test_max_iterations_bounds_valid(self) -> None:
        assert PRAutoFixConfig(max_iterations=1).max_iterations == 1
        assert PRAutoFixConfig(max_iterations=10).max_iterations == 10

    def test_round_trip_serialization(self) -> None:
        config = PRAutoFixConfig(aggressiveness=AggressivenessLevel.THOROUGH, poll_interval=120)
        data = config.model_dump()
        restored = PRAutoFixConfig.model_validate(data)
        assert restored == config

    def test_aggressiveness_serializes_as_string(self) -> None:
        config = PRAutoFixConfig(aggressiveness=AggressivenessLevel.CRITICAL)
        data = config.model_dump(mode="json")
        assert data["aggressiveness"] == "critical"

    def test_aggressiveness_deserializes_from_string(self) -> None:
        config = PRAutoFixConfig.model_validate({"aggressiveness": "thorough"})
        assert config.aggressiveness == AggressivenessLevel.THOROUGH


class TestProfilePRAutoFix:
    """CONF-02: Profile.pr_autofix integration tests."""

    @pytest.fixture()
    def base_profile_kwargs(self) -> dict:
        return {"name": "test", "repo_root": "/tmp/repo", "tracker": TrackerType.GITHUB}

    @pytest.mark.parametrize("kwargs", [{}, {"pr_autofix": None}])
    def test_pr_autofix_is_none(self, base_profile_kwargs: dict, kwargs: dict) -> None:
        profile = Profile(**base_profile_kwargs, **kwargs)
        assert profile.pr_autofix is None

    def test_pr_autofix_enabled_with_defaults(self, base_profile_kwargs: dict) -> None:
        profile = Profile(**base_profile_kwargs, pr_autofix=PRAutoFixConfig())
        assert profile.pr_autofix is not None
        assert profile.pr_autofix.aggressiveness == AggressivenessLevel.STANDARD

    def test_pr_autofix_custom_config(self, base_profile_kwargs: dict) -> None:
        config = PRAutoFixConfig(aggressiveness=AggressivenessLevel.THOROUGH, poll_interval=120)
        profile = Profile(**base_profile_kwargs, pr_autofix=config)
        assert profile.pr_autofix is not None
        assert profile.pr_autofix.aggressiveness == AggressivenessLevel.THOROUGH
        assert profile.pr_autofix.poll_interval == 120


class TestPRAutoFixOverride:
    """CONF-03: PRAutoFixConfig per-PR override via model_copy."""

    def test_model_copy_override_aggressiveness(self) -> None:
        base = PRAutoFixConfig()
        overridden = base.model_copy(update={"aggressiveness": AggressivenessLevel.THOROUGH})
        assert overridden.aggressiveness == AggressivenessLevel.THOROUGH
        assert base.aggressiveness == AggressivenessLevel.STANDARD  # original unchanged

    def test_model_copy_override_multiple_fields(self) -> None:
        base = PRAutoFixConfig()
        overridden = base.model_copy(update={
            "aggressiveness": AggressivenessLevel.CRITICAL,
            "max_iterations": 5,
            "auto_resolve": False,
        })
        assert overridden.aggressiveness == AggressivenessLevel.CRITICAL
        assert overridden.max_iterations == 5
        assert overridden.auto_resolve is False
