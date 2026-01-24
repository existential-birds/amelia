"""Implementation pipeline utility functions.

This module contains helper functions specific to the implementation pipeline,
including plan parsing, task extraction, and git commit utilities.
"""

import asyncio
import os
import re
from pathlib import Path

from langchain_core.runnables.config import RunnableConfig
from loguru import logger

from amelia.core.types import Profile
from amelia.pipelines.implementation.state import ImplementationState


def extract_task_count(plan_markdown: str) -> int:
    """Extract task count from plan markdown by counting ### Task N: patterns.

    Supports both simple numbering (### Task 1:) and hierarchical numbering
    (### Task 1.1:) formats.

    Args:
        plan_markdown: The markdown content of the plan.

    Returns:
        Number of tasks found, defaults to 1 if no task patterns detected.
    """
    pattern = r"^### Task \d+(\.\d+)?:"
    matches = re.findall(pattern, plan_markdown, re.MULTILINE)
    count = len(matches) if matches else 1

    # Debug: Log task extraction details (without plan content)
    logger.debug(
        "extract_task_count analysis",
        pattern=pattern,
        match_count=len(matches) if matches else 0,
        result_count=count,
        plan_length=len(plan_markdown),
    )

    return count


def _looks_like_plan(text: str) -> bool:
    """Check if text looks like a plan document.

    Used as a fallback when the LLM doesn't use the write tool but outputs
    the plan as text instead.

    Args:
        text: The text to check.

    Returns:
        True if the text contains plan-like indicators.
    """
    if not text or len(text) < 100:
        return False

    # Count plan indicators
    indicators = 0
    lower_text = text.lower()

    # Check for common plan headers/sections
    plan_markers = [
        "# ",  # Markdown headers
        "## ",
        "### task",
        "### step",
        "## phase",
        "**goal:**",
        "**architecture:**",
        "**tech stack:**",
        "implementation plan",
        "```",  # Code blocks
    ]
    for marker in plan_markers:
        if marker in lower_text:
            indicators += 1

    # Need at least 3 indicators to consider it a plan
    return indicators >= 3


def _extract_goal_from_plan(plan_content: str) -> str:
    """Extract goal from plan content using simple pattern matching.

    Looks for common goal patterns in the plan markdown:
    - **Goal:** <text>
    - # <Title> (first h1 header)

    Args:
        plan_content: The markdown plan content.

    Returns:
        Extracted goal or a default placeholder.
    """
    # Try to find **Goal:** pattern
    goal_match = re.search(r"\*\*Goal:\*\*\s*(.+?)(?:\n|$)", plan_content)
    if goal_match:
        return goal_match.group(1).strip()

    # Try to find first # header as title
    title_match = re.search(r"^#\s+(.+?)(?:\n|$)", plan_content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
        # Remove "Implementation Plan" suffix if present
        title = re.sub(r"\s*Implementation Plan\s*$", "", title, flags=re.IGNORECASE)
        return f"Implement {title}" if title else "Implementation plan"

    return "Implementation plan"


def _extract_key_files_from_plan(plan_content: str) -> list[str]:
    """Extract key files from plan content using pattern matching.

    Looks for file paths in the plan, typically in **Files:** sections
    or code blocks with file paths.

    Args:
        plan_content: The markdown plan content.

    Returns:
        List of file paths found, or empty list.
    """
    key_files: list[str] = []

    # Look for patterns like:
    # - Create: `path/to/file.py`
    # - Modify: `path/to/file.py`
    # - Test: `tests/path/test.py`
    file_patterns = [
        r"(?:Create|Modify|Test|Edit|Update|Delete):\s*`([^`]+)`",
        r"(?:Create|Modify|Test|Edit|Update|Delete):\s*(\S+\.(?:py|ts|tsx|js|jsx|go|rs|md))",
    ]

    for pattern in file_patterns:
        matches = re.findall(pattern, plan_content, re.IGNORECASE)
        key_files.extend(matches)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_files: list[str] = []
    for f in key_files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)

    return unique_files


def extract_task_section(plan_markdown: str, task_index: int) -> str:
    """Extract a specific task section with context from plan markdown.

    Returns the plan header (Goal, Architecture, Tech Stack) plus the current
    Phase header and the specific Task section. This prevents the developer
    from implementing the entire plan when only one task should be executed.

    Args:
        plan_markdown: The full markdown content of the plan.
        task_index: 0-indexed task number to extract.

    Returns:
        Markdown containing header context plus the specific task section.
        Falls back to full plan if extraction fails.
    """
    # Split into lines for processing
    lines = plan_markdown.split("\n")

    # Find header section (before first ## Phase or ---)
    header_end = 0
    for i, line in enumerate(lines):
        if line.startswith("## Phase") or line.strip() == "---":
            header_end = i
            break
    else:
        # No phase marker found, return full plan
        return plan_markdown

    header_lines = lines[:header_end]

    # Find all task boundaries using regex
    task_pattern = re.compile(r"^### Task \d+(\.\d+)?:")
    phase_pattern = re.compile(r"^## Phase \d+:")

    task_starts: list[int] = []
    phase_for_task: list[tuple[int, str]] = []  # (task_idx, phase_header)
    current_phase_header = ""

    for i, line in enumerate(lines):
        if phase_pattern.match(line):
            current_phase_header = line
        if task_pattern.match(line):
            task_starts.append(i)
            phase_for_task.append((len(task_starts) - 1, current_phase_header))

    if not task_starts or task_index >= len(task_starts):
        # No tasks found or index out of range, return full plan
        return plan_markdown

    # Get the task section boundaries
    task_start = task_starts[task_index]
    task_end = (
        task_starts[task_index + 1]
        if task_index + 1 < len(task_starts)
        else len(lines)
    )

    # Get the phase header for this task
    phase_header = ""
    for idx, header in phase_for_task:
        if idx == task_index:
            phase_header = header
            break

    # Build the extracted section
    result_parts = []

    # Add header context
    result_parts.append("\n".join(header_lines).strip())
    result_parts.append("\n---\n")

    # Add phase header if available
    if phase_header:
        result_parts.append(phase_header)
        result_parts.append("\n\n")

    # Add the task section
    task_section = "\n".join(lines[task_start:task_end]).strip()
    result_parts.append(task_section)

    return "".join(result_parts)


async def commit_task_changes(state: ImplementationState, config: RunnableConfig) -> bool:
    """Commit changes for completed task.

    Args:
        state: Current execution state.
        config: Runnable config with profile.

    Returns:
        True if commit succeeded or no changes to commit, False if commit failed.
    """
    profile: Profile | None = config.get("configurable", {}).get("profile")
    if not profile:
        raise ValueError("profile is required in config.configurable")
    working_dir = Path(profile.working_dir) if profile.working_dir else Path.cwd()

    task_number = state.current_task_index + 1

    # Disable git prompts to prevent hangs in headless/server contexts
    git_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    timeout_seconds = 60

    # Stage all changes
    proc = await asyncio.create_subprocess_exec(
        "git", "add", "-A",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_dir,
        env=git_env,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning("Timeout staging changes for task commit", task=task_number)
        proc.kill()
        await proc.wait()
        return False
    if proc.returncode != 0:
        logger.warning(
            "Failed to stage changes for task commit",
            error=stderr.decode(),
        )
        return False

    # Check if there are staged changes
    proc = await asyncio.create_subprocess_exec(
        "git", "diff", "--cached", "--quiet",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_dir,
        env=git_env,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning("Timeout checking staged changes for task", task=task_number)
        proc.kill()
        await proc.wait()
        return False
    if proc.returncode == 0:
        # Exit code 0 means no changes (diff is quiet/empty)
        logger.info("No changes to commit for task", task=task_number)
        return True
    if proc.returncode != 1:
        # Exit code 1 means changes exist; any other code is an error
        logger.warning(
            "Failed to check staged diff for task commit",
            returncode=proc.returncode,
            task=task_number,
        )
        return False

    # Commit with task reference
    issue_key = state.issue.id if state.issue else "unknown"
    commit_msg = f"feat({issue_key}): complete task {task_number}"

    proc = await asyncio.create_subprocess_exec(
        "git", "commit", "-m", commit_msg,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_dir,
        env=git_env,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning("Timeout committing task changes", task=task_number)
        proc.kill()
        await proc.wait()
        return False
    if proc.returncode == 0:
        logger.info("Committed task changes", task=task_number, message=commit_msg)
        return True
    else:
        logger.warning("Failed to commit task changes", error=stderr.decode())
        return False
