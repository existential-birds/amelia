"""State models for the PR auto-fix pipeline.

Defines the state types used by the PR auto-fix workflow:
- GroupFixStatus: Enum for fix attempt outcomes
- GroupFixResult: Result of fixing a single file group
- PRAutoFixState: Full pipeline state extending BasePipelineState
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from amelia.agents.schemas.classifier import CommentClassification
from amelia.core.agentic_state import AgenticStatus
from amelia.core.types import PRAutoFixConfig, PRReviewComment
from amelia.pipelines.base import BasePipelineState


class GroupFixStatus(StrEnum):
    """Outcome status for a file group fix attempt."""

    FIXED = "fixed"
    FAILED = "failed"
    NO_CHANGES = "no_changes"


class GroupFixResult(BaseModel):
    """Result of fixing a single file group.

    Attributes:
        file_path: Path to the primary file in the group (None for cross-file groups).
        status: Outcome of the fix attempt.
        error: Error message if status is 'failed'.
        comment_ids: IDs of comments addressed by this fix.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str | None
    status: GroupFixStatus
    error: str | None = None
    comment_ids: list[int] = Field(default_factory=list)


class PRAutoFixState(BasePipelineState):
    """State for the PR auto-fix pipeline.

    Extends BasePipelineState with PR-specific fields for tracking
    comment classification, file grouping, and fix results.

    Attributes:
        pr_number: GitHub PR number.
        head_branch: Branch name of the PR head.
        repo: Repository in 'owner/repo' format.
        classified_comments: Classification results for each comment.
        file_groups: Mapping of file path to comment IDs.
        goal: High-level description of the fix task.
        agentic_status: Current agentic execution status.
        commit_sha: SHA of the fix commit (after push).
        group_results: Results of each file group fix attempt.
        autofix_config: Auto-fix configuration for this run.
        comments: Raw PR review comments to process.
    """

    model_config = ConfigDict(frozen=True)

    # Pipeline identity
    pipeline_type: Literal["pr_auto_fix"] = "pr_auto_fix"
    status: Literal["pending", "running", "paused", "completed", "failed"] = "pending"

    # PR context
    pr_number: int
    head_branch: str
    repo: str

    # Classification
    classified_comments: list[CommentClassification] = Field(default_factory=list)
    file_groups: dict[str | None, list[int]] = Field(default_factory=dict)

    # Agentic execution
    goal: str | None = None
    agentic_status: AgenticStatus = AgenticStatus.RUNNING

    # Results
    commit_sha: str | None = None
    group_results: list[GroupFixResult] = Field(default_factory=list)

    # Configuration
    autofix_config: PRAutoFixConfig = Field(default_factory=PRAutoFixConfig)
    comments: list[PRReviewComment] = Field(default_factory=list)
