"""Architect agent schema definitions."""

from pydantic import BaseModel


class MarkdownPlanOutput(BaseModel):
    """Structured output for markdown plan generation.

    This is the schema the LLM uses to generate the plan content.

    Attributes:
        goal: High-level goal for the implementation.
        plan_markdown: The full markdown plan with phases, tasks, and steps.
        key_files: Files that will likely be modified.

    """

    goal: str
    plan_markdown: str
    key_files: list[str] = []
