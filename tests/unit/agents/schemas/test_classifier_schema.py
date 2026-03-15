"""Tests for classifier schemas, CATEGORY_THRESHOLD, and is_actionable."""

import pytest
from pydantic import ValidationError

from amelia.agents.schemas.classifier import (
    CATEGORY_THRESHOLD,
    ClassificationOutput,
    CommentCategory,
    CommentClassification,
    is_actionable,
)
from amelia.core.types import AggressivenessLevel, PRAutoFixConfig


# ---------------------------------------------------------------------------
# CommentCategory enum
# ---------------------------------------------------------------------------


class TestCommentCategory:
    """CommentCategory is a StrEnum with 6 values."""

    def test_has_six_values(self) -> None:
        assert len(CommentCategory) == 6

    def test_values(self) -> None:
        assert CommentCategory.BUG == "bug"
        assert CommentCategory.SECURITY == "security"
        assert CommentCategory.STYLE == "style"
        assert CommentCategory.SUGGESTION == "suggestion"
        assert CommentCategory.QUESTION == "question"
        assert CommentCategory.PRAISE == "praise"

    def test_is_str_subclass(self) -> None:
        assert isinstance(CommentCategory.BUG, str)

    def test_string_comparison(self) -> None:
        assert CommentCategory.BUG == "bug"
        assert CommentCategory.SECURITY == "security"


# ---------------------------------------------------------------------------
# CommentClassification model
# ---------------------------------------------------------------------------


class TestCommentClassification:
    """CommentClassification is a frozen Pydantic model."""

    def test_construction(self) -> None:
        c = CommentClassification(
            comment_id=42,
            category=CommentCategory.BUG,
            confidence=0.95,
            actionable=True,
            reason="Null pointer dereference",
        )
        assert c.comment_id == 42
        assert c.category == CommentCategory.BUG
        assert c.confidence == 0.95
        assert c.actionable is True
        assert c.reason == "Null pointer dereference"

    def test_frozen(self) -> None:
        c = CommentClassification(
            comment_id=1,
            category=CommentCategory.PRAISE,
            confidence=0.8,
            actionable=False,
            reason="Nice work",
        )
        with pytest.raises(ValidationError):
            c.comment_id = 2  # type: ignore[misc]

    def test_confidence_lower_bound(self) -> None:
        with pytest.raises(ValidationError):
            CommentClassification(
                comment_id=1,
                category=CommentCategory.BUG,
                confidence=-0.1,
                actionable=True,
                reason="bad",
            )

    def test_confidence_upper_bound(self) -> None:
        with pytest.raises(ValidationError):
            CommentClassification(
                comment_id=1,
                category=CommentCategory.BUG,
                confidence=1.1,
                actionable=True,
                reason="bad",
            )

    def test_confidence_edge_zero(self) -> None:
        c = CommentClassification(
            comment_id=1,
            category=CommentCategory.BUG,
            confidence=0.0,
            actionable=False,
            reason="uncertain",
        )
        assert c.confidence == 0.0

    def test_confidence_edge_one(self) -> None:
        c = CommentClassification(
            comment_id=1,
            category=CommentCategory.BUG,
            confidence=1.0,
            actionable=True,
            reason="certain",
        )
        assert c.confidence == 1.0


# ---------------------------------------------------------------------------
# ClassificationOutput
# ---------------------------------------------------------------------------


class TestClassificationOutput:
    """ClassificationOutput wraps a list of CommentClassification."""

    def test_empty_list(self) -> None:
        out = ClassificationOutput(classifications=[])
        assert out.classifications == []

    def test_with_items(self) -> None:
        items = [
            CommentClassification(
                comment_id=i,
                category=CommentCategory.STYLE,
                confidence=0.7,
                actionable=True,
                reason=f"reason {i}",
            )
            for i in range(3)
        ]
        out = ClassificationOutput(classifications=items)
        assert len(out.classifications) == 3


# ---------------------------------------------------------------------------
# CATEGORY_THRESHOLD mapping
# ---------------------------------------------------------------------------


class TestCategoryThreshold:
    """CATEGORY_THRESHOLD maps categories to minimum AggressivenessLevel."""

    def test_bug_maps_to_critical(self) -> None:
        assert CATEGORY_THRESHOLD[CommentCategory.BUG] == AggressivenessLevel.CRITICAL

    def test_security_maps_to_critical(self) -> None:
        assert CATEGORY_THRESHOLD[CommentCategory.SECURITY] == AggressivenessLevel.CRITICAL

    def test_style_maps_to_standard(self) -> None:
        assert CATEGORY_THRESHOLD[CommentCategory.STYLE] == AggressivenessLevel.STANDARD

    def test_suggestion_maps_to_thorough(self) -> None:
        assert CATEGORY_THRESHOLD[CommentCategory.SUGGESTION] == AggressivenessLevel.THOROUGH

    def test_question_maps_to_thorough(self) -> None:
        assert CATEGORY_THRESHOLD[CommentCategory.QUESTION] == AggressivenessLevel.THOROUGH

    def test_praise_maps_to_none(self) -> None:
        assert CATEGORY_THRESHOLD[CommentCategory.PRAISE] is None

    def test_all_categories_mapped(self) -> None:
        for cat in CommentCategory:
            assert cat in CATEGORY_THRESHOLD


# ---------------------------------------------------------------------------
# is_actionable helper
# ---------------------------------------------------------------------------


class TestIsActionable:
    """is_actionable returns True when configured aggressiveness >= category threshold."""

    def test_praise_never_actionable(self) -> None:
        for level in AggressivenessLevel:
            assert is_actionable(CommentCategory.PRAISE, level) is False

    def test_bug_actionable_at_all_levels(self) -> None:
        for level in AggressivenessLevel:
            assert is_actionable(CommentCategory.BUG, level) is True

    def test_security_actionable_at_all_levels(self) -> None:
        for level in AggressivenessLevel:
            assert is_actionable(CommentCategory.SECURITY, level) is True

    def test_style_not_actionable_at_critical(self) -> None:
        assert is_actionable(CommentCategory.STYLE, AggressivenessLevel.CRITICAL) is False

    def test_style_actionable_at_standard(self) -> None:
        assert is_actionable(CommentCategory.STYLE, AggressivenessLevel.STANDARD) is True

    def test_style_actionable_at_thorough(self) -> None:
        assert is_actionable(CommentCategory.STYLE, AggressivenessLevel.THOROUGH) is True

    def test_suggestion_only_at_thorough(self) -> None:
        assert is_actionable(CommentCategory.SUGGESTION, AggressivenessLevel.CRITICAL) is False
        assert is_actionable(CommentCategory.SUGGESTION, AggressivenessLevel.STANDARD) is False
        assert is_actionable(CommentCategory.SUGGESTION, AggressivenessLevel.THOROUGH) is True

    def test_question_only_at_thorough(self) -> None:
        assert is_actionable(CommentCategory.QUESTION, AggressivenessLevel.CRITICAL) is False
        assert is_actionable(CommentCategory.QUESTION, AggressivenessLevel.STANDARD) is False
        assert is_actionable(CommentCategory.QUESTION, AggressivenessLevel.THOROUGH) is True

    def test_critical_level_only_bug_and_security(self) -> None:
        """CRITICAL aggressiveness should only pass bug and security."""
        level = AggressivenessLevel.CRITICAL
        actionable = {cat for cat in CommentCategory if is_actionable(cat, level)}
        assert actionable == {CommentCategory.BUG, CommentCategory.SECURITY}

    def test_standard_level_adds_style(self) -> None:
        """STANDARD aggressiveness adds style to bug + security."""
        level = AggressivenessLevel.STANDARD
        actionable = {cat for cat in CommentCategory if is_actionable(cat, level)}
        assert actionable == {CommentCategory.BUG, CommentCategory.SECURITY, CommentCategory.STYLE}

    def test_thorough_level_adds_suggestion_question(self) -> None:
        """THOROUGH adds suggestion + question."""
        level = AggressivenessLevel.THOROUGH
        actionable = {cat for cat in CommentCategory if is_actionable(cat, level)}
        assert actionable == {
            CommentCategory.BUG,
            CommentCategory.SECURITY,
            CommentCategory.STYLE,
            CommentCategory.SUGGESTION,
            CommentCategory.QUESTION,
        }


# ---------------------------------------------------------------------------
# PRAutoFixConfig.confidence_threshold
# ---------------------------------------------------------------------------


class TestPRAutoFixConfigConfidenceThreshold:
    """PRAutoFixConfig gains confidence_threshold field."""

    def test_default_value(self) -> None:
        config = PRAutoFixConfig()
        assert config.confidence_threshold == 0.7

    def test_custom_value(self) -> None:
        config = PRAutoFixConfig(confidence_threshold=0.5)
        assert config.confidence_threshold == 0.5

    def test_rejects_below_zero(self) -> None:
        with pytest.raises(ValidationError):
            PRAutoFixConfig(confidence_threshold=-0.1)

    def test_rejects_above_one(self) -> None:
        with pytest.raises(ValidationError):
            PRAutoFixConfig(confidence_threshold=1.1)

    def test_edge_zero(self) -> None:
        config = PRAutoFixConfig(confidence_threshold=0.0)
        assert config.confidence_threshold == 0.0

    def test_edge_one(self) -> None:
        config = PRAutoFixConfig(confidence_threshold=1.0)
        assert config.confidence_threshold == 1.0

    def test_existing_defaults_unchanged(self) -> None:
        """Adding confidence_threshold must not change other defaults."""
        config = PRAutoFixConfig()
        assert config.aggressiveness == AggressivenessLevel.STANDARD
        assert config.poll_interval == 60
        assert config.auto_resolve is True
        assert config.max_iterations == 3
        assert config.commit_prefix == "fix(review):"
        assert config.ignore_authors == []
