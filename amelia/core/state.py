# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import operator
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from amelia.core.types import Design, DeveloperStatus, Issue


Severity = Literal["low", "medium", "high", "critical"]
RiskLevel = Literal["low", "medium", "high"]
ActionType = Literal["code", "command", "validation", "manual"]
BlockerType = Literal[
    "command_failed",
    "validation_failed",
    "needs_judgment",
    "unexpected_state",
    "dependency_skipped",
    "user_cancelled",
]
StepStatus = Literal["completed", "skipped", "failed", "cancelled"]
BatchStatus = Literal["complete", "blocked", "partial"]

# Constants for output truncation
MAX_OUTPUT_LINES = 100
MAX_OUTPUT_CHARS = 4000


def merge_sets(left: set[str], right: set[str] | list[str]) -> set[str]:
    """LangGraph reducer for set union operations.

    Accepts both set and list for right because node returns provide sets in-memory
    while initial state and checkpoint restore pass lists (JSON has no set type).

    Args:
        left: Existing set to merge into.
        right: New values as set or list to merge.

    Returns:
        Union of left and right as a set.
    """
    if isinstance(right, list):
        right = set(right)
    return left | right


def truncate_output(output: str | None) -> str | None:
    """Truncate command output to prevent state bloat.

    Keeps first 50 lines and last 50 lines if output exceeds MAX_OUTPUT_LINES.
    Also enforces MAX_OUTPUT_CHARS character limit.

    Args:
        output: The output string to truncate.

    Returns:
        Truncated output string or None if input was None.
    """
    if not output:
        return output

    lines = output.split("\n")
    if len(lines) <= MAX_OUTPUT_LINES:
        truncated = output
    else:
        # Keep first 50 + last 50 lines
        first = lines[:50]
        last = lines[-50:]
        truncated = "\n".join(
            first + [f"\n... ({len(lines) - 100} lines truncated) ...\n"] + last
        )

    if len(truncated) > MAX_OUTPUT_CHARS:
        truncated = truncated[:MAX_OUTPUT_CHARS] + f"\n... (truncated at {MAX_OUTPUT_CHARS} chars)"

    return truncated


class PlanStep(BaseModel):
    """A single step in an execution plan.

    Attributes:
        id: Unique identifier for tracking.
        description: Human-readable description.
        action_type: Type of action (code, command, validation, manual).
        file_path: File path for code actions.
        code_change: Exact code or diff for code actions.
        command: Shell command to execute.
        cwd: Working directory (relative to repo root).
        fallback_commands: Alternative commands to try if primary fails.
        expect_exit_code: Expected exit code (primary validation).
        expected_output_pattern: Regex for stdout (secondary, stripped of ANSI).
        validation_command: Command to run for validation actions.
        success_criteria: Description of what success looks like.
        risk_level: Risk level (low, medium, high).
        estimated_minutes: Estimated time to complete (2-5 min typically).
        requires_human_judgment: Whether step needs human review.
        depends_on: Step IDs this depends on.
        is_test_step: Whether this is a test step.
        validates_step: Step ID this validates.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    description: str
    action_type: ActionType

    # For code actions
    file_path: str | None = None
    code_change: str | None = None

    # For command actions
    command: str | None = None
    cwd: str | None = None
    fallback_commands: tuple[str, ...] = ()

    # Validation (exit code is ALWAYS checked; these are additional)
    expect_exit_code: int = 0
    expected_output_pattern: str | None = None

    # For validation actions
    validation_command: str | None = None
    success_criteria: str | None = None

    # Execution hints
    risk_level: RiskLevel = "medium"
    estimated_minutes: int = 2
    requires_human_judgment: bool = False

    # Dependencies
    depends_on: tuple[str, ...] = ()

    # TDD markers
    is_test_step: bool = False
    validates_step: str | None = None


class ExecutionBatch(BaseModel):
    """A batch of steps to execute before checkpoint.

    Architect defines batches based on semantic grouping.
    System enforces size limits (max 5 low-risk, max 3 medium-risk).

    Attributes:
        batch_number: Sequential batch number.
        steps: Steps in this batch.
        risk_summary: Overall risk level of the batch.
        description: Optional description of why these steps are grouped.
    """

    model_config = ConfigDict(frozen=True)

    batch_number: int
    steps: tuple[PlanStep, ...]
    risk_summary: RiskLevel
    description: str = ""


class ExecutionPlan(BaseModel):
    """Complete plan with batched execution.

    Created by Architect, consumed by Developer.
    Batches are defined upfront for predictable checkpoints.

    Attributes:
        goal: Overall goal or objective.
        batches: Sequence of execution batches.
        total_estimated_minutes: Total estimated time for all batches.
        tdd_approach: Whether to use TDD approach.
    """

    model_config = ConfigDict(frozen=True)

    goal: str
    batches: tuple[ExecutionBatch, ...]
    total_estimated_minutes: int
    tdd_approach: bool = True


class BlockerReport(BaseModel):
    """Report when execution is blocked.

    Attributes:
        step_id: ID of the step that blocked.
        step_description: Description of the blocked step.
        blocker_type: Type of blocker encountered.
        error_message: Error message describing the blocker.
        attempted_actions: Actions the agent already tried.
        suggested_resolutions: Agent's suggestions for human (labeled as AI suggestions in UI).
    """

    model_config = ConfigDict(frozen=True)

    step_id: str
    step_description: str
    blocker_type: BlockerType
    error_message: str
    attempted_actions: tuple[str, ...]
    suggested_resolutions: tuple[str, ...]


class StepResult(BaseModel):
    """Result of executing a single step.

    Attributes:
        step_id: ID of the step.
        status: Execution status (completed, skipped, failed, cancelled).
        output: Truncated command output.
        error: Error message if failed.
        executed_command: Actual command run (may differ from plan if fallback).
        duration_seconds: Time taken to execute.
        cancelled_by_user: Whether user cancelled the step.
    """

    model_config = ConfigDict(frozen=True)

    step_id: str
    status: StepStatus
    output: str | None = None
    error: str | None = None
    executed_command: str | None = None
    duration_seconds: float = 0.0
    cancelled_by_user: bool = False

    @field_validator("output", mode="before")
    @classmethod
    def truncate(cls, v: str | None) -> str | None:
        """Truncate output to prevent state bloat."""
        return truncate_output(v)


class BatchResult(BaseModel):
    """Result of executing a batch.

    Attributes:
        batch_number: The batch number.
        status: Batch status (complete, blocked, partial).
        completed_steps: Results for completed steps.
        blocker: Blocker report if execution was blocked.
    """

    model_config = ConfigDict(frozen=True)

    batch_number: int
    status: BatchStatus
    completed_steps: tuple[StepResult, ...]
    blocker: BlockerReport | None = None


class GitSnapshot(BaseModel):
    """Git state snapshot for potential revert.

    Attributes:
        head_commit: Git HEAD commit hash before batch.
        dirty_files: Files modified before batch started.
        stash_ref: Optional stash reference if changes were stashed.
    """

    model_config = ConfigDict(frozen=True)

    head_commit: str
    dirty_files: tuple[str, ...] = ()
    stash_ref: str | None = None


class BatchApproval(BaseModel):
    """Record of human approval for a batch.

    Attributes:
        batch_number: The batch number that was approved/rejected.
        approved: Whether the batch was approved.
        feedback: Optional feedback from human.
        approved_at: Timestamp of approval/rejection.
    """

    model_config = ConfigDict(frozen=True)

    batch_number: int
    approved: bool
    feedback: str | None = None
    approved_at: datetime


class ReviewResult(BaseModel):
    """Result from a code review.

    Attributes:
        reviewer_persona: The persona or role of the reviewer.
        approved: Whether the review approved the changes.
        comments: List of review comments or feedback.
        severity: Severity level of issues found (low, medium, high, critical).
    """
    model_config = ConfigDict(frozen=True)

    reviewer_persona: str
    approved: bool
    comments: list[str]
    severity: Severity


class AgentMessage(BaseModel):
    """Message from an agent in the orchestrator conversation.

    Attributes:
        role: Role of the message sender (system, assistant, user).
        content: The message content.
        tool_calls: Optional list of tool calls made by the agent.
    """

    model_config = ConfigDict(frozen=True)

    role: str
    content: str
    tool_calls: list[Any] | None = None

class ExecutionState(BaseModel):
    """State for the LangGraph orchestrator execution.

    This model is frozen (immutable) to support the stateless reducer pattern.
    Use model_copy(update={...}) to create modified copies.

    Attributes:
        profile_id: ID of the active profile (for replay determinism).
            The actual Profile object is passed via config["configurable"]["profile"].
        issue: The issue being worked on.
        design: Optional design context from brainstorming or external upload.
        human_approved: Whether human approval was granted for the plan.
        human_feedback: Optional feedback from human during approval.
        last_review: Most recent review result (only latest matters for decisions).
        code_changes_for_review: Staged code changes for review.
        driver_session_id: Session ID for CLI driver session continuity (works with any driver).
        workflow_status: Status of the workflow (running, completed, failed).
        plan_only: If True, complete after architect node without execution.
        agent_history: History of agent actions/messages for context tracking.
            Uses operator.add reducer - new entries are appended across state updates.
        execution_plan: Execution plan for Developer.
        current_batch_index: Index of the current batch being executed.
        batch_results: Results from completed batches.
            Uses operator.add reducer - new results are appended across state updates.
        developer_status: Current status of the Developer agent.
        current_blocker: Active blocker report if execution is blocked.
        blocker_resolution: Human's response to resolve blocker.
        batch_approvals: Records of human approvals for batches.
            Uses operator.add reducer - new approvals are appended across state updates.
        skipped_step_ids: IDs of steps that were skipped (for cascade handling).
            Uses merge_sets reducer - sets are unioned across state updates.
        git_snapshot_before_batch: Git state snapshot for potential revert.
        review_iteration: Current iteration in review-fix loop.
    """

    model_config = ConfigDict(frozen=True)

    profile_id: str
    issue: Issue | None = None
    design: Design | None = None
    human_approved: bool | None = None
    human_feedback: str | None = None
    last_review: ReviewResult | None = None
    code_changes_for_review: str | None = None
    driver_session_id: str | None = None
    workflow_status: Literal["running", "completed", "failed", "aborted"] = "running"
    plan_only: bool = False  # If True, complete after architect node without execution
    agent_history: Annotated[list[str], operator.add] = Field(default_factory=list)

    # Execution plan
    execution_plan: ExecutionPlan | None = None

    # Batch tracking
    current_batch_index: int = 0
    batch_results: Annotated[list[BatchResult], operator.add] = Field(default_factory=list)

    # Developer status
    developer_status: DeveloperStatus = DeveloperStatus.EXECUTING

    # Blocker handling
    current_blocker: BlockerReport | None = None
    blocker_resolution: str | None = None

    # Approval tracking
    batch_approvals: Annotated[list[BatchApproval], operator.add] = Field(default_factory=list)

    # Skip tracking (for cascade handling)
    skipped_step_ids: Annotated[set[str], merge_sets] = Field(default_factory=set)

    # Git state for revert capability
    git_snapshot_before_batch: GitSnapshot | None = None

    # Review iteration tracking (for review-fix loop)
    review_iteration: int = 0
