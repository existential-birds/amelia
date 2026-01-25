"""Agent classes for the Amelia orchestrator.

Provide specialized AI agents that handle distinct phases of the development
workflow. Each agent wraps an LLM driver and implements domain-specific logic
for planning, implementation, evaluation, or review.

Exports:
    Architect: Plan implementation strategy from issue descriptions.
    Developer: Execute code changes following the architect's plan.
    Evaluator: Evaluate and prioritize review feedback items.
    Disposition: Enum for evaluation outcomes (accept, reject, defer).
    EvaluatedItem: A single evaluated feedback item with disposition.
    EvaluationResult: Collection of evaluated items with summary.
    Reviewer: Review code changes and provide structured feedback.
"""

from amelia.agents.architect import Architect
from amelia.agents.developer import Developer
from amelia.agents.evaluator import (
    Disposition,
    EvaluatedItem,
    EvaluationResult,
    Evaluator,
)
from amelia.agents.reviewer import Reviewer


__all__ = [
    "Architect",
    "Developer",
    "Disposition",
    "EvaluatedItem",
    "EvaluationResult",
    "Evaluator",
    "Reviewer",
]
