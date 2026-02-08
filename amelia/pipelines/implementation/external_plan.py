"""External plan import helper.

Provides shared logic for importing external plans from files or inline content,
used by both workflow creation and the POST /plan endpoint.
"""

import asyncio
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, Field

from amelia.agents.schemas.architect import MarkdownPlanOutput
from amelia.core.extraction import extract_structured
from amelia.core.types import Profile
from amelia.pipelines.implementation.utils import (
    _extract_goal_from_plan,
    _extract_key_files_from_plan,
    extract_task_count,
)


class ExternalPlanImportResult(BaseModel):
    """Result of importing an external plan."""

    goal: str
    plan_markdown: str | None = None
    plan_path: Path
    key_files: list[str] = Field(default_factory=list)
    total_tasks: int


def build_plan_extraction_prompt(plan_content: str) -> str:
    """Build prompt for extracting structured fields from a plan.

    Args:
        plan_content: The raw plan markdown content.

    Returns:
        Prompt string for LLM extraction.
    """
    return f"""Extract the implementation plan structure from the following markdown plan.

<plan>
{plan_content}
</plan>

Return:
- goal: 1-2 sentence summary of what this plan accomplishes
- plan_markdown: The full plan content (preserve as-is)
- key_files: List of files that will be created or modified"""


async def import_external_plan(
    plan_file: str | None,
    plan_content: str | None,
    target_path: Path,
    profile: Profile,
    workflow_id: str,
) -> ExternalPlanImportResult:
    """Import and validate an external plan.

    Args:
        plan_file: Path to plan file (relative to worktree or absolute).
        plan_content: Inline plan markdown content.
        target_path: Where to write the plan (standard plan location).
        profile: Profile for LLM extraction config.
        workflow_id: For logging.

    Returns:
        ExternalPlanImportResult with goal, plan_markdown, plan_path, key_files,
        total_tasks.

    Raises:
        FileNotFoundError: If plan_file doesn't exist.
        ValueError: If validation fails, content is empty, or path traversal detected.
    """
    # Establish working directory as security boundary
    working_dir = Path(profile.working_dir) if profile.working_dir else Path(".")
    working_dir = working_dir.expanduser().resolve()

    # Resolve content from file or use inline
    plan_path: Path | None
    if plan_file is not None:
        plan_path = Path(plan_file)
        if not plan_path.is_absolute():
            plan_path = working_dir / plan_file
        plan_path = plan_path.expanduser().resolve()

        # Validate plan_path is within working directory (prevent path traversal)
        try:
            plan_path.relative_to(working_dir)
        except ValueError:
            raise ValueError(
                f"Plan file '{plan_file}' resolves outside working directory"
            ) from None

        if not plan_path.exists():
            raise FileNotFoundError(f"Plan file not found: {plan_path}")

        content = await asyncio.to_thread(plan_path.read_text)
    else:
        content = plan_content or ""
        plan_path = None

    # Validate target_path is within working directory (prevent path traversal)
    target_path = target_path.expanduser().resolve()
    try:
        target_path.relative_to(working_dir)
    except ValueError:
        raise ValueError(
            f"Target path '{target_path}' resolves outside working directory"
        ) from None

    # Validate content is not empty
    if not content.strip():
        raise ValueError("Plan content is empty")

    # Check if source and target are the same file (both paths now resolved)
    file_already_at_target = plan_path == target_path if plan_path is not None else False

    # Write to target path (skip if file already there)
    if not file_already_at_target:
        await asyncio.to_thread(target_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target_path.write_text, content)
        logger.info(
            "External plan written",
            target_path=str(target_path),
            content_length=len(content),
            workflow_id=workflow_id,
        )
    else:
        logger.info(
            "External plan file already at target location, skipping write",
            plan_path=str(plan_path),
            workflow_id=workflow_id,
        )

    # Extract structured fields using LLM
    agent_config = profile.get_agent_config("plan_validator")
    prompt = build_plan_extraction_prompt(content)

    try:
        output = await extract_structured(
            prompt=prompt,
            schema=MarkdownPlanOutput,
            model=agent_config.model,
            driver_type=agent_config.driver,
        )
        goal = output.goal
        plan_markdown = output.plan_markdown
        key_files = output.key_files
    except RuntimeError as e:
        # Fallback extraction without LLM
        logger.warning(
            "Structured extraction failed, using fallback",
            error=str(e),
            workflow_id=workflow_id,
        )
        goal = _extract_goal_from_plan(content)
        plan_markdown = content
        key_files = _extract_key_files_from_plan(content)

    # Extract task count
    total_tasks = extract_task_count(content)

    logger.info(
        "External plan validated",
        goal=goal,
        key_files_count=len(key_files),
        total_tasks=total_tasks,
        workflow_id=workflow_id,
    )

    return ExternalPlanImportResult(
        goal=goal,
        plan_markdown=plan_markdown,
        plan_path=target_path,
        key_files=key_files,
        total_tasks=total_tasks,
    )
