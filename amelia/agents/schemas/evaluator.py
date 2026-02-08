"""Evaluator agent schema definitions."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Disposition(str, Enum):
    """Disposition for evaluated feedback items.

    Attributes:
        IMPLEMENT: Correct and in scope - will fix.
        REJECT: Technically incorrect - won't fix.
        DEFER: Out of scope - backlog.
        CLARIFY: Ambiguous - needs clarification.

    """

    IMPLEMENT = "implement"
    REJECT = "reject"
    DEFER = "defer"
    CLARIFY = "clarify"


class EvaluatedItem(BaseModel):
    """Single evaluated feedback item.

    Attributes:
        number: Original issue number from review.
        title: Brief title describing the issue.
        file_path: Path to the file containing the issue.
        line: Line number where the issue occurs.
        disposition: The evaluation decision for this item.
        reason: Evidence supporting the disposition decision.
        original_issue: The issue description from review.
        suggested_fix: The suggested fix from review.

    """

    model_config = ConfigDict(frozen=True)

    number: int
    title: str
    file_path: str
    line: int
    disposition: Disposition
    reason: str
    original_issue: str
    suggested_fix: str


class EvaluationResult(BaseModel):
    """Result of evaluating review feedback.

    Attributes:
        items_to_implement: Items marked for implementation.
        items_rejected: Items rejected as technically incorrect.
        items_deferred: Items deferred as out of scope.
        items_needing_clarification: Items requiring clarification.
        summary: Brief summary of evaluation decisions.

    """

    model_config = ConfigDict(frozen=True)

    items_to_implement: list[EvaluatedItem] = Field(default_factory=list)
    items_rejected: list[EvaluatedItem] = Field(default_factory=list)
    items_deferred: list[EvaluatedItem] = Field(default_factory=list)
    items_needing_clarification: list[EvaluatedItem] = Field(default_factory=list)
    summary: str


class EvaluationOutput(BaseModel):
    """Schema for LLM-generated evaluation output.

    This is the schema the LLM uses to generate evaluation results.

    Attributes:
        evaluated_items: All evaluated items with their dispositions.
        summary: Brief summary of the evaluation decisions.

    """

    evaluated_items: list[EvaluatedItem]
    summary: str
