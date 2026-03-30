"""Reviewer agent schema definitions."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ReviewSeverity(str, Enum):
    """Severity of review findings."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    NONE = "none"


class SubmitReviewInput(BaseModel):
    """Schema for the submit_review tool input."""

    model_config = ConfigDict(frozen=True)

    approved: bool = Field(description="True if the code is ready to merge as-is.")
    severity: ReviewSeverity = Field(
        description="Highest severity of issues found: critical, major, minor, or none."
    )
    comments: list[str] = Field(
        default_factory=list,
        description=(
            'List of review comments, each in format "[severity] [FILE:LINE] Description".'
        ),
    )
