"""User prompt construction for review-fix developer runs."""

from __future__ import annotations

from amelia.core.types import collect_rejected_comments
from amelia.pipelines.implementation.state import ImplementationState


def build_review_fix_prompt(state: ImplementationState) -> str:
    """Build the user prompt for fixing evaluator-approved review items.

    This is not an architect plan: it lists structured items and the goal string
    from the evaluation node, optionally augmented with reviewer feedback.

    Args:
        state: Pipeline state with ``goal`` and ``evaluation_result``.

    Returns:
        Full user prompt for agentic execution.

    Raises:
        ValueError: If ``goal`` or ``evaluation_result`` is missing.

    """
    if not state.goal:
        raise ValueError("Review fix prompt requires state.goal")
    if state.evaluation_result is None:
        raise ValueError("Review fix prompt requires state.evaluation_result")

    lines: list[str] = [
        "You are fixing verified code review findings from the evaluator.",
        "This is scoped repair work, not a full implementation plan from an architect.",
        "Make minimal, surgical edits at the referenced locations.\n",
        "## Structured items\n",
    ]
    for item in state.evaluation_result.items_to_implement:
        lines.append(
            f"- **#{item.number}** `{item.file_path}:{item.line}` — **{item.title}**\n"
            f"  - Issue: {item.original_issue}\n"
            f"  - Suggested fix: {item.suggested_fix}\n"
        )

    lines.append("\nPlease complete the following task:\n\n")
    lines.append(state.goal)

    rejected_comments = collect_rejected_comments(state.last_reviews)
    if rejected_comments:
        feedback = "\n".join(f"- {c}" for c in rejected_comments)
        lines.append(f"\n\nThe reviewer requested the following changes:\n{feedback}")

    return "".join(lines)
