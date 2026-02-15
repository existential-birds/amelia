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


async def read_plan_content(
    plan_file: str | None,
    plan_content: str | None,
    working_dir: Path,
) -> str:
    """Read plan content from a file or inline string.

    Args:
        plan_file: Path to plan file (relative to working_dir or absolute).
        plan_content: Inline plan markdown content.
        working_dir: Security boundary directory.

    Returns:
        The plan content string.

    Raises:
        FileNotFoundError: If plan_file doesn't exist.
        ValueError: If content is empty or path traversal detected.
    """
    working_dir = working_dir.expanduser().resolve()

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

        content = await asyncio.to_thread(plan_path.read_text, encoding="utf-8")
    else:
        content = plan_content or ""

    # Validate content is not empty
    if not content.strip():
        raise ValueError("Plan content is empty")

    return content


async def write_plan_to_target(
    content: str,
    target_path: Path,
    working_dir: Path,
    source_path: Path | None = None,
) -> None:
    """Write plan content to the target path.

    Skips writing if source_path equals target_path (file already in place).
    Creates parent directories as needed.

    Args:
        content: The plan content to write.
        target_path: Where to write the plan.
        working_dir: Security boundary directory.
        source_path: Original source file path (resolved), if any.

    Raises:
        ValueError: If target_path resolves outside working directory.
    """
    working_dir = working_dir.expanduser().resolve()
    target_path = target_path.expanduser().resolve()

    # Validate target_path is within working directory (prevent path traversal)
    try:
        target_path.relative_to(working_dir)
    except ValueError:
        raise ValueError(
            f"Target path '{target_path}' resolves outside working directory"
        ) from None

    # Check if source and target are the same file (both paths now resolved)
    if source_path is not None:
        source_path = source_path.expanduser().resolve()
        if source_path == target_path:
            logger.info(
                "External plan file already at target location, skipping write",
                plan_path=str(source_path),
            )
            return

    await asyncio.to_thread(target_path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(target_path.write_text, content, encoding="utf-8")
    logger.info(
        "External plan written",
        target_path=str(target_path),
        content_length=len(content),
    )


async def extract_plan_fields(
    content: str,
    profile: Profile | None,
) -> ExternalPlanImportResult:
    """Extract structured plan fields using LLM with regex fallback.

    When profile is None, skips LLM extraction and uses fallback only.

    Args:
        content: The raw plan markdown content.
        profile: Profile for LLM extraction config, or None for fallback-only.

    Returns:
        ExternalPlanImportResult with goal, plan_markdown, key_files, total_tasks.
        Note: plan_path is set to Path(".") as a placeholder; callers should
        set it to the actual target path.
    """
    goal: str | None = None
    plan_markdown: str | None = None
    key_files: list[str] = []

    if profile is not None:
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
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(
                "Structured extraction failed, using regex fallback",
                error=str(e),
            )
            # Fall through to fallback below

    # Fallback extraction (used when profile is None or LLM failed)
    if goal is None:
        goal = _extract_goal_from_plan(content)
        plan_markdown = content
        key_files = _extract_key_files_from_plan(content)

        goal_is_default = goal == "Implementation plan"
        logger.info(
            "Regex fallback extraction complete",
            goal_extracted=not goal_is_default,
            goal=goal if not goal_is_default else "(default)",
            key_files_count=len(key_files),
            key_files=key_files if key_files else "(none found)",
        )
        if goal_is_default or not key_files:
            logger.warning(
                "Fallback extraction produced partial data",
                goal_is_default=goal_is_default,
                key_files_empty=not key_files,
            )

    total_tasks = extract_task_count(content)

    return ExternalPlanImportResult(
        goal=goal,
        plan_markdown=plan_markdown,
        plan_path=Path("."),  # Placeholder; caller sets actual path
        key_files=key_files,
        total_tasks=total_tasks,
    )


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
    working_dir = (
        Path(profile.working_dir) if profile.working_dir else Path(".")
    ).expanduser().resolve()

    # Read content
    content = await read_plan_content(
        plan_file=plan_file,
        plan_content=plan_content,
        working_dir=working_dir,
    )

    # Determine resolved source path for skip-write check
    source_path: Path | None = None
    if plan_file is not None:
        source_path = Path(plan_file)
        if not source_path.is_absolute():
            source_path = working_dir / plan_file
        source_path = source_path.expanduser().resolve()

    # Write to target
    await write_plan_to_target(
        content=content,
        target_path=target_path,
        working_dir=working_dir,
        source_path=source_path,
    )

    # Extract structured fields
    result = await extract_plan_fields(content, profile=profile)

    # Resolve target_path for the result
    resolved_target = target_path.expanduser().resolve()

    logger.info(
        "External plan validated",
        goal=result.goal,
        key_files_count=len(result.key_files),
        total_tasks=result.total_tasks,
        workflow_id=workflow_id,
    )

    return ExternalPlanImportResult(
        goal=result.goal,
        plan_markdown=result.plan_markdown,
        plan_path=resolved_target,
        key_files=result.key_files,
        total_tasks=result.total_tasks,
    )
