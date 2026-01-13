"""LangGraph state machine orchestrator for coordinating AI agents.

Implements the core agentic workflow: Issue -> Architect (analyze) -> Human Approval ->
Developer (execute agentically) <-> Reviewer (review) -> Done. Provides node functions for
the state machine and the create_orchestrator_graph() factory.
"""
import asyncio
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import typer
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from loguru import logger
from pydantic import BaseModel

from amelia.agents.architect import Architect, MarkdownPlanOutput
from amelia.agents.developer import Developer
from amelia.agents.evaluator import Evaluator
from amelia.agents.reviewer import Reviewer
from amelia.core.constants import ToolName, resolve_plan_path
from amelia.core.state import ExecutionState, rebuild_execution_state
from amelia.core.types import Profile
from amelia.drivers.factory import DriverFactory
from amelia.server.models.tokens import TokenUsage
from amelia.tools.git_utils import get_current_commit


# Resolve forward references in ExecutionState. Must be done after importing
# Reviewer and Evaluator since they define StructuredReviewResult and EvaluationResult.
rebuild_execution_state()


if TYPE_CHECKING:
    from amelia.server.database.repository import WorkflowRepository
    from amelia.server.events.bus import EventBus


def extract_task_count(plan_markdown: str) -> int | None:
    """Extract task count from plan markdown by counting ### Task N: patterns.

    Supports both simple numbering (### Task 1:) and hierarchical numbering
    (### Task 1.1:) formats.

    Args:
        plan_markdown: The markdown content of the plan.

    Returns:
        Number of tasks found, or None if no task patterns detected.
    """
    pattern = r"^### Task \d+(\.\d+)?:"
    matches = re.findall(pattern, plan_markdown, re.MULTILINE)
    count = len(matches) if matches else None

    # Debug: Log task extraction details
    task_lines = [
        line for line in plan_markdown.split("\n")
        if line.strip().startswith("### Task") or line.strip().startswith("## Task")
    ]
    logger.debug(
        "extract_task_count analysis",
        pattern=pattern,
        match_count=len(matches) if matches else 0,
        result_count=count,
        sample_task_lines=task_lines[:5],  # First 5 task-like lines for debugging
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


async def _extract_structured[T: BaseModel](
    prompt: str,
    schema: type[T],
    model: str,
    driver_type: str,
    system_prompt: str | None = None,
) -> T:
    """Extract structured output from text using direct model call.

    This is a lightweight extraction function for parsing text into structured
    data WITHOUT using the full agent framework. Use this when you just need
    to parse/extract data and don't need filesystem tools.

    For agentic tasks that need codebase exploration, use the driver's
    generate() or execute_agentic() methods instead.

    Args:
        prompt: The text prompt to process.
        schema: Pydantic model class to parse output into.
        model: Model identifier (e.g., 'gpt-4o-mini').
        driver_type: Driver type string (e.g., 'api:openrouter') for provider config.
        system_prompt: Optional system prompt.

    Returns:
        Instance of the schema class with extracted data.

    Raises:
        RuntimeError: If extraction fails.
    """
    # Import here to avoid circular dependency
    from amelia.drivers.api.deepagents import (  # noqa: PLC0415
        _create_chat_model,
    )

    # Determine provider from driver type
    provider: str | None = None
    if driver_type.startswith("api:"):
        provider = driver_type.split(":", 1)[1]  # e.g., "openrouter"

    try:
        chat_model = _create_chat_model(model, provider=provider)
        structured_model = chat_model.with_structured_output(schema)

        messages: list[HumanMessage | SystemMessage] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        result = await structured_model.ainvoke(messages)
        if result is None:
            raise RuntimeError(
                f"Model returned output that could not be parsed into {schema.__name__}"
            )
        logger.debug(
            "Structured extraction completed",
            schema=schema.__name__,
            model=model,
        )
        return result  # type: ignore[return-value]
    except Exception as e:
        raise RuntimeError(f"Structured extraction failed: {e}") from e


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


def _extract_config_params(
    config: RunnableConfig | None,
) -> tuple["EventBus | None", str, Profile]:
    """Extract event_bus, workflow_id, and profile from config.

    Extracts values from config.configurable dictionary. workflow_id is required.

    Args:
        config: Optional RunnableConfig with configurable parameters.

    Returns:
        Tuple of (event_bus, workflow_id, profile).

    Raises:
        ValueError: If workflow_id (thread_id) or profile is not provided.
    """
    config = config or {}
    configurable = config.get("configurable", {})
    event_bus = configurable.get("event_bus")
    workflow_id = configurable.get("thread_id")
    profile = configurable.get("profile")

    if not workflow_id:
        raise ValueError("workflow_id (thread_id) is required in config.configurable")
    if not profile:
        raise ValueError("profile is required in config.configurable")

    return event_bus, workflow_id, profile


async def _save_token_usage(
    driver: Any,
    workflow_id: str,
    agent: str,
    repository: "WorkflowRepository | None",
) -> None:
    """Extract token usage from driver and save to repository.

    This is a best-effort operation - failures are logged but don't fail the workflow.
    Uses the driver-agnostic get_usage() method when available.

    Args:
        driver: The driver that was used for execution.
        workflow_id: Current workflow ID.
        agent: Agent name (architect, developer, reviewer).
        repository: Repository to save usage to (may be None in CLI mode).
    """
    if repository is None:
        return

    # Get usage via the driver-agnostic get_usage() method
    driver_usage = driver.get_usage() if hasattr(driver, "get_usage") else None
    if driver_usage is None:
        return

    try:
        usage = TokenUsage(
            workflow_id=workflow_id,
            agent=agent,
            model=driver_usage.model or getattr(driver, "model", "unknown"),
            input_tokens=driver_usage.input_tokens or 0,
            output_tokens=driver_usage.output_tokens or 0,
            cache_read_tokens=driver_usage.cache_read_tokens or 0,
            cache_creation_tokens=driver_usage.cache_creation_tokens or 0,
            cost_usd=driver_usage.cost_usd or 0.0,
            duration_ms=driver_usage.duration_ms or 0,
            num_turns=driver_usage.num_turns or 1,
            timestamp=datetime.now(UTC),
        )
        await repository.save_token_usage(usage)
        logger.debug(
            "Token usage saved",
            agent=agent,
            workflow_id=workflow_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
        )
    except Exception:
        # Best-effort - don't fail workflow on token tracking errors
        logger.exception(
            "Failed to save token usage",
            agent=agent,
            workflow_id=workflow_id,
        )


async def plan_validator_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Validate and extract structure from architect's plan file.

    Reads the plan file written by the architect and uses an LLM to extract
    structured fields (goal, plan_markdown, key_files) using the MarkdownPlanOutput schema.

    Args:
        state: Current execution state with raw_architect_output.
        config: RunnableConfig with profile in configurable.

    Returns:
        Partial state dict with goal, plan_markdown, plan_path, key_files.

    Raises:
        ValueError: If plan file not found or empty.
    """
    event_bus, workflow_id, profile = _extract_config_params(config)

    if not state.issue:
        raise ValueError("Issue is required in state for plan validation")

    # Resolve plan path - use working_dir to match call_architect_node
    plan_rel_path = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
    working_dir = Path(profile.working_dir) if profile.working_dir else Path(".")
    plan_path = working_dir / plan_rel_path

    logger.info(
        "Orchestrator: Validating plan structure",
        plan_path=str(plan_path),
        workflow_id=workflow_id,
    )

    # Emit start event to UI (trace level event not persisted)
    # Validator doesn't use event_bus directly for trace events

    # Read plan file - fail fast if not found
    if not plan_path.exists():
        raise ValueError(f"Plan file not found at {plan_path}")

    plan_content = await asyncio.to_thread(plan_path.read_text)
    if not plan_content.strip():
        raise ValueError(f"Plan file is empty at {plan_path}")

    # Extract structured fields using lightweight extraction (no tools needed)
    # The plan already exists - we just need to parse it into structured format
    model = profile.validator_model or profile.model
    prompt = f"""Extract the implementation plan structure from the following markdown plan.

<plan>
{plan_content}
</plan>

Return:
- goal: 1-2 sentence summary of what this plan accomplishes
- plan_markdown: The full plan content (preserve as-is)
- key_files: List of files that will be created or modified"""

    try:
        output = await _extract_structured(
            prompt=prompt,
            schema=MarkdownPlanOutput,
            model=model,
            driver_type=profile.driver,
        )
        goal = output.goal
        plan_markdown = output.plan_markdown
        key_files = output.key_files
    except RuntimeError as e:
        # Fallback: extract what we can from the plan content directly
        logger.warning(
            "Structured extraction failed, using fallback",
            error=str(e),
            workflow_id=workflow_id,
        )
        goal = _extract_goal_from_plan(plan_content)
        plan_markdown = plan_content
        key_files = _extract_key_files_from_plan(plan_content)

    # Parse task count from plan markdown
    total_tasks = extract_task_count(plan_content)

    logger.info(
        "Plan validated",
        goal=goal,
        key_files_count=len(key_files),
        total_tasks=total_tasks,
        workflow_id=workflow_id,
    )

    return {
        "goal": goal,
        "plan_markdown": plan_markdown,
        "plan_path": plan_path,
        "key_files": key_files,
        "total_tasks": total_tasks,
    }


async def call_architect_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Architect agent to generate an implementation plan.

    Consumes the Architect's async generator, streaming events and collecting
    the final state. The plan_validator_node handles extracting structured
    fields (goal, plan_markdown, key_files) from the written plan file.

    Args:
        state: Current execution state containing the issue and profile.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with raw_architect_output, tool_calls, and tool_results.

    Raises:
        ValueError: If no issue is provided in the state.
    """
    issue_id_for_log = state.issue.id if state.issue else "No Issue Provided"
    logger.info(f"Orchestrator: Calling Architect for issue {issue_id_for_log}")

    if state.issue is None:
        raise ValueError("Cannot call Architect: no issue provided in state.")

    # Extract event_bus, workflow_id, and profile from config
    event_bus, workflow_id, profile = _extract_config_params(config)

    config = config or {}
    configurable = config.get("configurable", {})
    repository = configurable.get("repository")
    prompts = configurable.get("prompts", {})

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    architect = Architect(driver, event_bus=event_bus, prompts=prompts)

    # Ensure the plan directory exists before the architect runs
    plan_rel_path = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
    working_dir = Path(profile.working_dir) if profile.working_dir else Path(".")
    plan_path = working_dir / plan_rel_path
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    logger.debug("Ensured plan directory exists", plan_dir=str(plan_path.parent))

    final_state = state
    async for new_state, event in architect.plan(
        state=state,
        profile=profile,
        workflow_id=workflow_id,
    ):
        final_state = new_state
        if event_bus:
            event_bus.emit(event)

    await _save_token_usage(driver, workflow_id, "architect", repository)

    # Fallback: If plan file doesn't exist, write it from Write tool call content
    # This handles cases where Claude Code's Write tool didn't persist the file
    if not plan_path.exists():
        logger.warning(
            "Plan file not found after architect execution, attempting fallback",
            plan_path=str(plan_path),
            tool_calls_count=len(final_state.tool_calls),
        )

        # DEBUG: Log all tool calls for diagnosis
        logger.debug(
            "DEBUG: All tool calls from architect",
            tool_calls_detail=[
                {
                    "tool_name": tc.tool_name,
                    "tool_name_type": type(tc.tool_name).__name__,
                    "input_keys": list(tc.tool_input.keys()) if tc.tool_input else [],
                    "has_content": "content" in tc.tool_input if tc.tool_input else False,
                    "has_file_path": "file_path" in tc.tool_input if tc.tool_input else False,
                }
                for tc in final_state.tool_calls
            ],
            expected_write_file=ToolName.WRITE_FILE,
            expected_write_file_value=str(ToolName.WRITE_FILE),
        )

        # Look for Write tool call with plan content
        # Log all tool names explicitly for debugging
        tool_names = [tc.tool_name for tc in final_state.tool_calls]
        logger.debug(
            "Looking for write_file in tool calls",
            tool_names=tool_names,
        )
        for tc in final_state.tool_calls:
            input_keys = list(tc.tool_input.keys()) if tc.tool_input else []
            is_match = tc.tool_name == ToolName.WRITE_FILE and "content" in tc.tool_input
            logger.debug(
                "Checking tool call for write_file",
                tool_name=tc.tool_name,
                input_keys=input_keys,
                is_write_file=is_match,
            )
            if tc.tool_name == ToolName.WRITE_FILE and "content" in tc.tool_input:
                plan_content = tc.tool_input.get("content", "")
                if plan_content:
                    await asyncio.to_thread(plan_path.write_text, plan_content)
                    logger.info(
                        "Wrote plan file from Write tool call content",
                        plan_path=str(plan_path),
                        content_length=len(plan_content),
                    )
                    break
        else:
            # No Write tool call found - try to salvage plan from raw output
            # Some models output the plan as text instead of using the write tool
            raw_output = final_state.raw_architect_output or ""
            if raw_output and _looks_like_plan(raw_output):
                await asyncio.to_thread(plan_path.write_text, raw_output)
                logger.warning(
                    "Wrote plan file from raw output (model didn't use write tool)",
                    plan_path=str(plan_path),
                    content_length=len(raw_output),
                )
            else:
                logger.error(
                    "No Write tool call found and raw output doesn't look like a plan",
                    plan_path=str(plan_path),
                    tool_calls=[tc.tool_name for tc in final_state.tool_calls],
                    tool_calls_count=len(final_state.tool_calls),
                    raw_output_preview=raw_output[:500] if raw_output else "EMPTY",
                )

    logger.info(
        "Agent action completed",
        agent="architect",
        action="generated_plan",
        details={
            "raw_output_length": len(final_state.raw_architect_output) if final_state.raw_architect_output else 0,
            "tool_calls_count": len(final_state.tool_calls),
        },
    )

    return {
        "raw_architect_output": final_state.raw_architect_output,
        "tool_calls": list(final_state.tool_calls),
        "tool_results": list(final_state.tool_results),
    }


async def human_approval_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Node to prompt for human approval before proceeding.

    Behavior depends on execution mode:
    - CLI mode: Blocking prompt via typer.confirm
    - Server mode: Returns empty dict (interrupt mechanism handles pause)

    Args:
        state: Current execution state containing the goal and plan to be reviewed.
        config: Optional RunnableConfig with execution_mode in configurable.

    Returns:
        Partial state dict with approval status, or empty dict for server mode.
    """
    config = config or {}
    execution_mode = config.get("configurable", {}).get("execution_mode", "cli")

    if execution_mode == "server":
        # Server mode: approval comes from resumed state after interrupt
        # If human_approved is already set (from resume), use it
        # Otherwise, just return empty dict - the interrupt mechanism will pause here
        return {}

    # CLI mode: blocking prompt
    typer.secho("\n--- HUMAN APPROVAL REQUIRED ---", fg=typer.colors.BRIGHT_YELLOW)
    typer.echo("Review the generated plan before proceeding.")
    if state.goal:
        typer.echo(f"\nGoal: {state.goal}")
    if state.plan_path:
        typer.echo(f"\nPlan saved to: {state.plan_path}")

    approved = typer.confirm("Do you approve this plan to proceed with development?", default=True)
    comment = typer.prompt("Add an optional comment for the audit log (press Enter to skip)", default="")

    # Log the approval decision
    logger.info(
        "Human approval received",
        approved=approved,
        comment=comment,
    )

    return {"human_approved": approved}


async def call_developer_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Developer agent to execute agentically.

    Uses the new agentic execution model where the Developer autonomously
    decides what tools to use rather than following a step-by-step plan.

    For task-based execution (when total_tasks is set), this node:
    - Clears driver_session_id for fresh context per task
    - Injects task-scoped prompt pointing to the current task in the plan

    Args:
        state: Current execution state containing the goal.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with tool_calls, tool_results, and status.
    """
    logger.info("Orchestrator: Calling Developer to execute agentically.")
    logger.debug(
        "Developer node state",
        base_commit=state.base_commit,
        goal_length=len(state.goal) if state.goal else 0,
    )

    if not state.goal:
        raise ValueError("Developer node has no goal. The architect should have generated a goal first.")

    # Extract event_bus, workflow_id, and profile from config
    event_bus, workflow_id, profile = _extract_config_params(config)

    # Task-based execution: clear session and inject task-scoped context
    if state.total_tasks is not None:
        task_number = state.current_task_index + 1  # 1-indexed for display
        logger.info(
            "Starting task execution",
            task=task_number,
            total_tasks=state.total_tasks,
            fresh_session=True,
        )
        # Extract only the current task section from the full plan
        task_plan = (
            extract_task_section(state.plan_markdown, state.current_task_index)
            if state.plan_markdown
            else None
        )
        state = state.model_copy(update={
            "driver_session_id": None,  # Fresh session for each task
            "plan_markdown": task_plan,  # Only current task, not full plan
        })

    config = config or {}
    repository = config.get("configurable", {}).get("repository")

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    developer = Developer(driver)

    final_state = state
    async for new_state, event in developer.run(state, profile):
        final_state = new_state
        # Stream events are emitted via event_bus if provided
        if event_bus:
            event_bus.emit(event)

    await _save_token_usage(driver, workflow_id, "developer", repository)

    logger.info(
        "Agent action completed",
        agent="developer",
        action="agentic_execution",
        details={
            "tool_calls_count": len(final_state.tool_calls),
            "agentic_status": final_state.agentic_status,
        },
    )

    return {
        "tool_calls": list(final_state.tool_calls),
        "tool_results": list(final_state.tool_results),
        "agentic_status": final_state.agentic_status,
        "final_response": final_state.final_response,
        "error": final_state.error,
        "driver_session_id": final_state.driver_session_id,
    }


async def call_reviewer_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Reviewer agent to review code changes.

    Always uses agentic review which fetches the diff via git tools. This avoids
    the "Argument list too long" error that can occur with large diffs.

    If base_commit is not set in state, computes it using get_current_commit().

    Args:
        state: Current execution state containing issue and goal information.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with review results.
    """
    logger.info(f"Orchestrator: Calling Reviewer for issue {state.issue.id if state.issue else 'N/A'}")

    # Extract event_bus, workflow_id, and profile from config
    event_bus, workflow_id, profile = _extract_config_params(config)

    config = config or {}
    configurable = config.get("configurable", {})
    repository = configurable.get("repository")
    prompts = configurable.get("prompts", {})

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    # Use "task_reviewer" only for non-final tasks in task-based execution
    is_non_final_task = state.total_tasks is not None and state.current_task_index + 1 < state.total_tasks
    agent_name = "task_reviewer" if is_non_final_task else "reviewer"
    reviewer = Reviewer(driver, event_bus=event_bus, prompts=prompts, agent_name=agent_name)

    # Compute base_commit if not in state
    base_commit = state.base_commit
    if not base_commit:
        computed_commit = await get_current_commit(cwd=profile.working_dir)
        if computed_commit:
            base_commit = computed_commit
            logger.info(
                "Computed base_commit for agentic review",
                agent=agent_name,
                base_commit=base_commit,
            )
        else:
            # Fallback to HEAD if get_current_commit fails
            base_commit = "HEAD"
            logger.warning(
                "Could not compute base_commit, falling back to HEAD",
                agent=agent_name,
            )
    else:
        logger.debug(
            "Using existing base_commit for agentic review",
            agent=agent_name,
            base_commit=base_commit,
        )

    # Always use agentic review - it fetches the diff via git tools
    review_result, new_session_id = await reviewer.agentic_review(
        state, base_commit, profile, workflow_id=workflow_id
    )

    await _save_token_usage(driver, workflow_id, agent_name, repository)

    next_iteration = state.review_iteration + 1
    logger.info(
        "Agent action completed",
        agent=agent_name,
        action="review_completed",
        details={
            "severity": review_result.severity,
            "approved": review_result.approved,
            "issue_count": len(review_result.comments),
            "review_iteration": next_iteration,
        },
    )

    # Build return dict
    result_dict = {
        "last_review": review_result,
        "driver_session_id": new_session_id,
        "review_iteration": next_iteration,
    }

    # Increment task review iteration for task-based execution
    if state.total_tasks is not None:
        result_dict["task_review_iteration"] = state.task_review_iteration + 1

    # Debug: Log the full state update being returned
    logger.debug(
        "call_reviewer_node returning state update",
        last_review_approved=review_result.approved,
        last_review_severity=review_result.severity,
        last_review_persona=review_result.reviewer_persona,
        last_review_comment_count=len(review_result.comments),
        review_iteration=next_iteration,
        task_review_iteration=result_dict.get("task_review_iteration"),
        total_tasks=state.total_tasks,
        current_task_index=state.current_task_index,
    )

    return result_dict


async def call_evaluation_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Node that evaluates review feedback.

    Calls the Evaluator agent to process review results and
    apply the decision matrix for each item.

    Args:
        state: Current execution state containing the review feedback.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with evaluation_result, approved_items, and driver_session_id.
    """
    event_bus, workflow_id, profile = _extract_config_params(config)

    config = config or {}
    configurable = config.get("configurable", {})
    prompts = configurable.get("prompts", {})

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    evaluator = Evaluator(driver=driver, event_bus=event_bus, prompts=prompts)

    evaluation_result, new_session_id = await evaluator.evaluate(
        state, profile, workflow_id=workflow_id
    )

    approved_items: list[int] = []
    if state.auto_approve:
        approved_items = [item.number for item in evaluation_result.items_to_implement]

    logger.info(
        "Agent action completed",
        agent="evaluator",
        action="evaluation_completed",
        details={
            "items_to_implement": len(evaluation_result.items_to_implement),
            "items_rejected": len(evaluation_result.items_rejected),
            "items_deferred": len(evaluation_result.items_deferred),
            "auto_approved_count": len(approved_items),
        },
    )

    return {
        "evaluation_result": evaluation_result,
        "approved_items": approved_items,
        "driver_session_id": new_session_id,
    }


async def review_approval_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Node for human approval of which review items to fix.

    In server mode, this interrupts for human input.
    In CLI mode, this prompts interactively.

    Args:
        state: Current execution state containing the evaluation result.
        config: Optional RunnableConfig with execution_mode in configurable.

    Returns:
        Partial state dict with approved_items (CLI mode) or empty dict (server mode).
    """
    config = config or {}
    execution_mode = config.get("configurable", {}).get("execution_mode", "cli")

    if execution_mode == "server":
        return {}

    # CLI mode: prompt user (this would use typer.confirm or similar)
    # For now, auto-approve all items marked for implementation
    return {}


def route_approval(state: ExecutionState) -> Literal["approve", "reject"]:
    """Route based on human approval status.

    Args:
        state: Current execution state containing human_approved flag.

    Returns:
        'approve' if approved (continue to developer).
        'reject' if not approved.
    """
    return "approve" if state.human_approved else "reject"


def route_after_review(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> Literal["developer", "__end__"]:
    """Route after review based on approval and iteration count.

    Args:
        state: Current execution state with last_review and review_iteration.
        config: Optional RunnableConfig with profile in configurable.

    Returns:
        "developer" if review rejected and under max iterations,
        "__end__" if approved or max iterations reached.
    """
    logger.debug(
        "route_after_review decision",
        has_last_review=state.last_review is not None,
        approved=state.last_review.approved if state.last_review else None,
        review_iteration=state.review_iteration,
    )
    if state.last_review and state.last_review.approved:
        return "__end__"

    _, _, profile = _extract_config_params(config)
    max_iterations = profile.max_review_iterations

    if state.review_iteration >= max_iterations:
        logger.warning(
            "Max review iterations reached, terminating loop",
            max_iterations=max_iterations,
        )
        return "__end__"

    return "developer"


async def next_task_node(
    state: ExecutionState, config: RunnableConfig
) -> dict[str, Any]:
    """Transition to next task: commit changes, increment index, reset iteration.

    Args:
        state: Current execution state with task tracking.
        config: Runnable config.

    Returns:
        State update with incremented task index, reset iteration, cleared session.

    Raises:
        RuntimeError: If commit fails, halting the workflow to preserve
            one-commit-per-task semantics per issue #188.
    """
    completed_task = state.current_task_index + 1
    next_task = state.current_task_index + 2

    logger.info(
        "NEXT_TASK_NODE: Transitioning to next task",
        completed=completed_task,
        next=next_task,
        total_tasks=state.total_tasks,
    )

    # Commit current task changes - halt on failure to preserve clean commit history
    commit_success = await commit_task_changes(state, config)
    if not commit_success:
        logger.error(
            "Cannot proceed to next task: commit failed",
            completed_task=completed_task,
        )
        raise RuntimeError(
            f"Failed to commit changes for task {completed_task}. "
            "Halting workflow to preserve one-commit-per-task semantics."
        )

    return {
        "current_task_index": state.current_task_index + 1,
        "task_review_iteration": 0,
        "driver_session_id": None,  # Fresh session for next task
    }


async def commit_task_changes(state: ExecutionState, config: RunnableConfig) -> bool:
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
        return False
    if proc.returncode == 0:
        logger.info("Committed task changes", task=task_number, message=commit_msg)
        return True
    else:
        logger.warning("Failed to commit task changes", error=stderr.decode())
        return False


def route_after_task_review(
    state: ExecutionState, config: RunnableConfig
) -> Literal["developer", "next_task_node", "__end__"]:
    """Route after task review: next task, retry developer, or end.

    Args:
        state: Current execution state with task tracking fields.
        config: Runnable config with profile.

    Returns:
        "next_task_node" if approved and more tasks remain.
        "developer" if not approved and iterations remain.
        "__end__" if all tasks complete or max iterations reached.
    """
    profile: Profile | None = config.get("configurable", {}).get("profile")
    if not profile:
        raise ValueError("profile is required in config.configurable")

    task_number = state.current_task_index + 1
    approved = state.last_review.approved if state.last_review else False

    if approved:
        # Task approved - check if more tasks remain
        # total_tasks should always be set when using task-based routing,
        # but handle None for safety (treat as single task complete)
        if state.total_tasks is None or state.current_task_index + 1 >= state.total_tasks:
            logger.debug(
                "Task routing decision",
                task=task_number,
                approved=True,
                route="__end__",
                reason="all_tasks_complete",
            )
            return "__end__"  # All tasks complete
        logger.debug(
            "Task routing decision",
            task=task_number,
            approved=True,
            route="next_task_node",
        )
        return "next_task_node"  # Move to next task

    # Not approved - check iteration limit
    max_iterations = profile.max_task_review_iterations
    if state.task_review_iteration >= max_iterations:
        logger.debug(
            "Task routing decision",
            task=task_number,
            approved=False,
            iteration=state.task_review_iteration,
            max_iterations=max_iterations,
            route="__end__",
            reason="max_iterations_reached",
        )
        return "__end__"  # Halt on repeated failure

    logger.debug(
        "Task routing decision",
        task=task_number,
        approved=False,
        iteration=state.task_review_iteration,
        max_iterations=max_iterations,
        route="developer",
    )
    return "developer"  # Retry with feedback


def route_after_review_or_task(
    state: ExecutionState, config: RunnableConfig
) -> Literal["developer", "developer_node", "next_task_node", "__end__"]:
    """Route after review: handles both legacy and task-based execution.

    For task-based execution (total_tasks is set), uses route_after_task_review.
    For legacy execution (total_tasks is None), uses route_after_review.

    Args:
        state: Current execution state.
        config: Runnable config with profile.

    Returns:
        Routing target: developer_node (legacy), developer (task retry),
        next_task_node (task approved), or __end__.
    """
    if state.total_tasks is not None:
        result = route_after_task_review(state, config)
        logger.debug(
            "route_after_review_or_task: task mode",
            route=result,
            current_task_index=state.current_task_index,
            total_tasks=state.total_tasks,
        )
        return result

    # Legacy mode: route_after_review returns "developer" but graph uses "developer_node"
    result = route_after_review(state, config)
    final_result: Literal["developer_node", "__end__"] = (
        "developer_node" if result == "developer" else "__end__"
    )
    logger.debug(
        "route_after_review_or_task: legacy mode",
        inner_result=result,
        final_route=final_result,
    )
    return final_result


def route_after_evaluation(state: ExecutionState) -> str:
    """Route after evaluation node.

    If auto_approve is set, skip to developer.
    Otherwise, go to human approval.

    Args:
        state: Current execution state with auto_approve flag.

    Returns:
        "developer_node" if auto_approve is set, otherwise "review_approval_node".
    """
    if state.auto_approve:
        return "developer_node"
    return "review_approval_node"


def route_after_fixes(state: ExecutionState) -> str:
    """Route after developer fixes.

    Check if there are still critical/major items to fix.
    If auto_approve, loop back for another review pass.
    Otherwise, go to end approval.

    Args:
        state: Current execution state with review_pass and evaluation_result.

    Returns:
        "reviewer_node" to loop back, "end_approval_node" for human approval, or END.
    """
    max_passes = state.max_review_passes

    if state.review_pass >= max_passes:
        logger.warning(
            "Max review passes reached",
            review_pass=state.review_pass,
            max_passes=max_passes,
        )
        return END

    if state.auto_approve:
        if state.evaluation_result and state.evaluation_result.items_to_implement:
            return "reviewer_node"
        return END

    return "end_approval_node"


def route_after_end_approval(state: ExecutionState) -> str:
    """Route after end approval.

    If human approves, end. Otherwise, loop back to reviewer.

    Args:
        state: Current execution state with human_approved flag.

    Returns:
        END if human approved, otherwise "reviewer_node".
    """
    if state.human_approved:
        return END
    return "reviewer_node"


def create_orchestrator_graph(
    checkpoint_saver: BaseCheckpointSaver[Any] | None = None,
    interrupt_before: list[str] | None = None,
) -> CompiledStateGraph[Any]:
    """Creates and compiles the LangGraph state machine for agentic orchestration.

    The graph flow supports both legacy and task-based execution:

    Legacy flow (total_tasks is None):
    START -> architect_node -> plan_validator_node -> human_approval_node
          -> developer_node <-> reviewer_node -> END

    Task-based flow (total_tasks is set):
    START -> architect_node -> plan_validator_node -> human_approval_node
          -> developer_node -> reviewer_node -> next_task_node -> developer_node
          (loops for each task until all complete or max iterations reached)

    Args:
        checkpoint_saver: Optional checkpoint saver for state persistence.
        interrupt_before: List of node names to interrupt before executing.
            If None and checkpoint_saver is provided, defaults to:
            ["human_approval_node"] for server-mode human-in-the-loop.

    Returns:
        Compiled StateGraph ready for execution.
    """
    workflow = StateGraph(ExecutionState)

    # Add nodes
    workflow.add_node("architect_node", call_architect_node)
    workflow.add_node("plan_validator_node", plan_validator_node)
    workflow.add_node("human_approval_node", human_approval_node)
    workflow.add_node("developer_node", call_developer_node)
    workflow.add_node("reviewer_node", call_reviewer_node)
    workflow.add_node("next_task_node", next_task_node)  # Task-based execution

    # Set entry point
    workflow.set_entry_point("architect_node")

    # Define edges
    # Architect -> Plan Validator -> Human approval
    workflow.add_edge("architect_node", "plan_validator_node")
    workflow.add_edge("plan_validator_node", "human_approval_node")

    # Conditional edge from human_approval_node:
    # - approve: continue to developer_node
    # - reject: go to END
    workflow.add_conditional_edges(
        "human_approval_node",
        route_approval,
        {
            "approve": "developer_node",
            "reject": END
        }
    )

    # Developer -> Reviewer
    workflow.add_edge("developer_node", "reviewer_node")

    # Reviewer routing: handles both legacy and task-based execution
    # - Legacy: developer_node (retry) or __end__ (approved)
    # - Task-based: developer (retry), next_task_node (task approved), or __end__ (all done)
    workflow.add_conditional_edges(
        "reviewer_node",
        route_after_review_or_task,
        {
            "developer": "developer_node",
            "developer_node": "developer_node",
            "next_task_node": "next_task_node",
            "__end__": END,
        }
    )

    # next_task_node loops back to developer for the next task
    workflow.add_edge("next_task_node", "developer_node")

    # Set default interrupt_before only if checkpoint_saver is provided and interrupt_before is None
    if interrupt_before is None and checkpoint_saver is not None:
        interrupt_before = ["human_approval_node"]

    return workflow.compile(
        checkpointer=checkpoint_saver,
        interrupt_before=interrupt_before,
    )


def create_review_graph(
    checkpoint_saver: BaseCheckpointSaver[Any] | None = None,
    interrupt_before: list[str] | None = None,
) -> CompiledStateGraph[Any]:
    """Creates review-fix workflow graph.

    Flow: reviewer -> evaluation -> [approval] -> developer -> [end_approval] -> END

    The workflow loops between reviewer and developer until:
    - No more critical/major items (auto mode), OR
    - Human approves the fixes (manual mode), OR
    - Max review passes reached

    Args:
        checkpoint_saver: Optional checkpoint saver for persistence.
        interrupt_before: Optional list of nodes to interrupt before.
            Defaults to ["review_approval_node", "end_approval_node"] when
            checkpoint_saver is provided.

    Returns:
        Compiled LangGraph state graph ready for execution.
    """
    workflow = StateGraph(ExecutionState)

    # Add nodes
    workflow.add_node("reviewer_node", call_reviewer_node)
    workflow.add_node("evaluation_node", call_evaluation_node)
    workflow.add_node("review_approval_node", review_approval_node)
    workflow.add_node("developer_node", call_developer_node)
    workflow.add_node("end_approval_node", review_approval_node)  # Reuse approval node

    # Set entry point
    workflow.set_entry_point("reviewer_node")

    # Add edges
    workflow.add_edge("reviewer_node", "evaluation_node")
    workflow.add_conditional_edges(
        "evaluation_node",
        route_after_evaluation,
        {"developer_node": "developer_node", "review_approval_node": "review_approval_node"},
    )
    workflow.add_edge("review_approval_node", "developer_node")
    workflow.add_conditional_edges(
        "developer_node",
        route_after_fixes,
        {"reviewer_node": "reviewer_node", "end_approval_node": "end_approval_node", END: END},
    )
    workflow.add_conditional_edges(
        "end_approval_node",
        route_after_end_approval,
        {"reviewer_node": "reviewer_node", END: END},
    )

    # Set default interrupt_before for server mode
    if interrupt_before is None and checkpoint_saver is not None:
        interrupt_before = ["review_approval_node", "end_approval_node"]

    return workflow.compile(
        checkpointer=checkpoint_saver,
        interrupt_before=interrupt_before,
    )
