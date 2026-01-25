"""State model for the Implementation pipeline.

This module defines ImplementationState, which extends BasePipelineState with
fields specific to the implementation workflow (Architect -> Developer <-> Reviewer).
"""

from __future__ import annotations

import operator
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field

from amelia.core.agentic_state import AgenticStatus, ToolCall, ToolResult
from amelia.core.types import Design, Issue, ReviewResult
from amelia.pipelines.base import BasePipelineState


if TYPE_CHECKING:
    from amelia.agents.evaluator import EvaluationResult


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

    # Agentic execution tracking (from agent interactions)
    tool_calls: Annotated[list[ToolCall], operator.add] = Field(default_factory=list)
    tool_results: Annotated[list[ToolResult], operator.add] = Field(default_factory=list)
    agentic_status: AgenticStatus = AgenticStatus.RUNNING

    # Domain data (from planning phase)
    issue: Issue | None = None
    design: Design | None = None
    goal: str | None = None
    base_commit: str | None = None
    plan_markdown: str | None = None
    raw_architect_output: str | None = None
    plan_path: Path | None = None
    key_files: list[str] = Field(default_factory=list)

    # Human approval (plan review)
    human_approved: bool | None = None
    human_feedback: str | None = None

    # Code review tracking
    last_review: ReviewResult | None = None
    code_changes_for_review: str | None = None

    # Review iteration tracking
    review_iteration: int = 0

    # Task-based execution (multi-task plans)
    total_tasks: int = 1
    current_task_index: int = 0
    task_review_iteration: int = 0

    # Structured review workflow
    evaluation_result: EvaluationResult | None = None
    approved_items: list[int] = Field(default_factory=list)
    auto_approve: bool = False
    review_pass: int = 0
    max_review_passes: int = 3

    # External plan tracking
    external_plan: bool = False
    """True if plan was imported externally (bypasses Architect)."""


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

    from amelia.agents.evaluator import EvaluationResult  # noqa: PLC0415

    # Inject types into this module's namespace for get_type_hints() compatibility.
    # These dynamic assignments are required for Python's typing.get_type_hints()
    # to resolve forward references when used by LangGraph's StateGraph.
    module = sys.modules[__name__]
    module.EvaluationResult = EvaluationResult  # type: ignore[attr-defined]  # Dynamic module injection for LangGraph

    ImplementationState.model_rebuild(
        _types_namespace={
            "EvaluationResult": EvaluationResult,
        }
    )
