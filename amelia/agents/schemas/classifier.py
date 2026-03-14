"""Classifier agent schema definitions.

Provides the typed contracts for PR comment classification:
- CommentCategory enum (6 categories)
- CommentClassification and ClassificationOutput Pydantic models
- CATEGORY_THRESHOLD mapping and is_actionable helper
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from amelia.core.types import AggressivenessLevel


class CommentCategory(StrEnum):
    """Category for a PR review comment.

    Attributes:
        BUG: Code defect or incorrect behavior.
        SECURITY: Security vulnerability or concern.
        STYLE: Code style or formatting issue.
        SUGGESTION: Improvement suggestion or enhancement idea.
        QUESTION: Question requesting clarification.
        PRAISE: Positive feedback (never actionable).
    """

    BUG = "bug"
    SECURITY = "security"
    STYLE = "style"
    SUGGESTION = "suggestion"
    QUESTION = "question"
    PRAISE = "praise"


class CommentClassification(BaseModel):
    """Classification result for a single PR review comment.

    Attributes:
        comment_id: GitHub comment ID.
        category: Classified category.
        confidence: Classification confidence score (0.0 to 1.0).
        actionable: Whether this comment should be acted on.
        reason: Brief explanation of the classification.
    """

    model_config = ConfigDict(frozen=True)

    comment_id: int = Field(description="GitHub comment ID")
    category: CommentCategory = Field(description="Classified category")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Classification confidence score"
    )
    actionable: bool = Field(description="Whether this comment should be acted on")
    reason: str = Field(description="Brief explanation of the classification")


class ClassificationOutput(BaseModel):
    """Schema for batch LLM classification output.

    Attributes:
        classifications: List of individual comment classifications.
    """

    classifications: list[CommentClassification] = Field(
        description="List of individual comment classifications"
    )


CATEGORY_THRESHOLD: dict[CommentCategory, AggressivenessLevel | None] = {
    CommentCategory.BUG: AggressivenessLevel.CRITICAL,
    CommentCategory.SECURITY: AggressivenessLevel.CRITICAL,
    CommentCategory.STYLE: AggressivenessLevel.STANDARD,
    CommentCategory.SUGGESTION: AggressivenessLevel.THOROUGH,
    CommentCategory.QUESTION: AggressivenessLevel.THOROUGH,
    CommentCategory.PRAISE: None,
}
"""Maps each comment category to the minimum aggressiveness level required.

None means the category is never actionable (e.g., praise).
"""


def is_actionable(category: CommentCategory, level: AggressivenessLevel) -> bool:
    """Check whether a comment category is actionable at the given aggressiveness level.

    Args:
        category: The comment category.
        level: The configured aggressiveness level.

    Returns:
        True if the aggressiveness level meets or exceeds the category threshold.
        Always False for categories with no threshold (praise).
    """
    threshold = CATEGORY_THRESHOLD[category]
    if threshold is None:
        return False
    return level >= threshold
