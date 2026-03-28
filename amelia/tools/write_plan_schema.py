"""Schema models for the write_plan tool.

Defines structured input types that the LLM must produce when writing
implementation plans. The tool validates these at call time and renders
them into consistent markdown.
"""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlanTask(BaseModel):
    """A single task in an implementation plan.

    Attributes:
        number: Task number as string. Simple ("1") or hierarchical ("1.1").
        title: Human-readable task title.
        files_to_create: Paths of new files to create.
        files_to_modify: Paths of existing files to modify (may include :line-range).
        steps: Markdown content for each step (includes code blocks, commands, etc).
    """

    model_config = ConfigDict(frozen=True)

    number: str = Field(
        ...,
        description="Task number: '1', '2', or hierarchical '1.1', '2.3'",
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Short descriptive title for the task",
    )
    files_to_create: list[str] = Field(
        default_factory=list,
        description="File paths to create (e.g., 'src/new_module.py')",
    )
    files_to_modify: list[str] = Field(
        default_factory=list,
        description="File paths to modify (e.g., 'src/existing.py:10-20')",
    )
    steps: list[str] = Field(
        ...,
        min_length=1,
        description="Markdown content for each step",
    )

    @field_validator("number")
    @classmethod
    def validate_number(cls, v: str) -> str:
        """Validate task number matches N or N.M format with N >= 1."""
        if not re.match(r"^[1-9]\d*(\.[1-9]\d*)?$", v):
            raise ValueError(
                f"Task number must match 'N' or 'N.M' format (N >= 1), got: {v!r}"
            )
        return v


class WritePlanInput(BaseModel):
    """Structured input for the write_plan tool.

    The LLM produces this structured data instead of free-form markdown.
    The tool validates the input and renders it into consistent markdown
    with guaranteed ### Task N: headers.

    Attributes:
        goal: One-sentence description of what the plan builds.
        architecture_summary: 2-3 sentences about the approach.
        tech_stack: Key technologies and libraries used.
        tasks: Ordered list of implementation tasks.
        file_path: Where to write the rendered plan markdown.
    """

    model_config = ConfigDict(frozen=True)

    goal: str = Field(
        ...,
        min_length=1,
        description="One sentence describing what this plan builds",
    )
    architecture_summary: str = Field(
        ...,
        min_length=1,
        description="2-3 sentences about the architectural approach",
    )
    tech_stack: list[str] = Field(
        default_factory=list,
        description="Key technologies and libraries (e.g., ['Python', 'FastAPI'])",
    )
    tasks: list[PlanTask] = Field(
        ...,
        min_length=1,
        description="Ordered list of implementation tasks",
    )
    file_path: str = Field(
        ...,
        min_length=1,
        description="Path where the rendered plan markdown will be written",
    )
