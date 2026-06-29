"""State model for the Implementation pipeline.

This module defines ImplementationState, which extends BasePipelineState with
fields specific to the implementation workflow (Architect -> Developer <-> Reviewer).

Forward Reference Pattern
-------------------------
This module uses a forward reference pattern to avoid circular imports:

1. EvaluationResult is imported under TYPE_CHECKING for type hints only
2. At runtime, rebuild_implementation_state() must be called to:
   - Import the actual types
   - Inject them into this module's namespace (required by typing.get_type_hints())
   - Call model_rebuild() to refresh Pydantic's type resolution

This is necessary because LangGraph's StateGraph uses get_type_hints() to inspect
state fields, which fails on forward references unless the types are in the module's
global namespace. See rebuild_implementation_state() for the implementation.
"""

from __future__ import annotations

import operator
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from amelia.core.agentic_state import AgenticStatus, ToolCall, ToolResult
from amelia.core.types import Design, Issue, PlanValidationResult, ReviewResult
from amelia.pipelines.base import BasePipelineState
from amelia.tools.write_plan_schema import WritePlanInput


if TYPE_CHECKING:
    from amelia.agents.schemas.evaluator import EvaluationResult


class _GenerativeMoACandidateBase(BaseModel):
    """Common fields for a generative Mixture-of-Agents proposer result."""

    model_config = ConfigDict(frozen=True)

    proposer_id: int
    model: str


class GenerativeMoASucceededCandidate(_GenerativeMoACandidateBase):
    """A successful Developer proposer result with its collected diff."""

    status: Literal["succeeded"] = "succeeded"
    worktree_path: str | None = None
    diff: str
    summary: str | None = None


class GenerativeMoAFailedCandidate(_GenerativeMoACandidateBase):
    """A failed Developer proposer result with the failure reason."""

    status: Literal["failed"] = "failed"
    error: str


type GenerativeMoACandidate = Annotated[
    GenerativeMoASucceededCandidate | GenerativeMoAFailedCandidate,
    Field(discriminator="status"),
]


class ImplementationState(BasePipelineState):
    """State for the implementation pipeline.

    Extends BasePipelineState with implementation-specific fields for:
    - Domain data (issue, design, plan)
    - Human approval workflow
    - Code review tracking
    - Multi-task execution
    """

    # Override pipeline_type with literal
    pipeline_type: Literal["implementation"] = "implementation"

    tool_calls: Annotated[list[ToolCall], operator.add] = Field(default_factory=list)
    tool_results: Annotated[list[ToolResult], operator.add] = Field(default_factory=list)
    agentic_status: AgenticStatus = AgenticStatus.RUNNING

    issue: Issue | None = None
    design: Design | None = None
    goal: str | None = None
    base_commit: str | None = None
    architect_raw_output: str | None = None
    """Raw RESULT message from architect (e.g., 'I've written the plan...')."""
    plan_markdown: str | None = None
    """Validated plan content read from file. Only set after plan_validator_node."""
    architect_error: str | None = None
    plan_path: Path | None = None
    key_files: list[str] = Field(default_factory=list)

    human_approved: bool | None = None
    human_feedback: str | None = None

    last_reviews: list[ReviewResult] = Field(default_factory=list)
    code_changes_for_review: str | None = None

    review_iteration: int = 0

    # Plan validation feedback loop (mirrors last_reviews + task_review_iteration)
    plan_validation_result: PlanValidationResult | None = None
    plan_revision_count: int = 0

    total_tasks: int = 1
    current_task_index: int = 0
    task_review_iteration: int = 0

    evaluation_result: EvaluationResult | None = None
    approved_items: list[int] = Field(default_factory=list)
    review_pass: int = 0
    review_mode: str | None = None
    max_review_passes: int = 3

    plan_structured: WritePlanInput | None = None

    external_plan: bool = False
    """True if plan was imported externally (bypasses Architect)."""

    # Generative Mixture-of-Agents. No operator.add reducer: each proposer run
    # replaces the candidate list rather than concatenating across graph cycles.
    generative_moa_candidates: list[GenerativeMoACandidate] = Field(default_factory=list)
    generative_moa_selected: GenerativeMoACandidate | None = None


def rebuild_implementation_state() -> None:
    """Rebuild ImplementationState to resolve forward references.

    Must be called after importing EvaluationResult to enable Pydantic
    validation and Python's get_type_hints() to work.

    This function:
    1. Imports the forward-referenced types
    2. Injects them into this module's global namespace (required for get_type_hints)
    3. Calls model_rebuild() to refresh Pydantic's type resolution

    Example:
        from amelia.pipelines.implementation.state import rebuild_implementation_state
        rebuild_implementation_state()
    """
    import sys  # noqa: PLC0415

    from amelia.agents.schemas.evaluator import EvaluationResult  # noqa: PLC0415

    # Inject types into this module's namespace for get_type_hints() compatibility.
    # These dynamic assignments are required for Python's typing.get_type_hints()
    # to resolve forward references when used by LangGraph's StateGraph.
    module = sys.modules[__name__]
    setattr(module, "EvaluationResult", EvaluationResult)  # noqa: B010  # Dynamic module injection for LangGraph

    ImplementationState.model_rebuild(
        _types_namespace={
            "EvaluationResult": EvaluationResult,
        }
    )
