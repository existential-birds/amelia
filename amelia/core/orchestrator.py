"""LangGraph state machine orchestrator for coordinating AI agents.

Implements the core agentic workflow: Issue -> Architect (analyze) -> Human Approval ->
Developer (execute agentically) <-> Reviewer (review) -> Done. Provides node functions for
the state machine and the create_orchestrator_graph() factory.
"""
import asyncio
from pathlib import Path
from typing import Any, Literal

import typer
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from amelia.agents.architect import Architect, MarkdownPlanOutput
from amelia.agents.evaluator import Evaluator
from amelia.core.constants import ToolName, resolve_plan_path
from amelia.core.extraction import extract_structured
from amelia.core.state import ExecutionState, rebuild_execution_state
from amelia.core.types import Profile
from amelia.drivers.factory import DriverFactory
from amelia.pipelines.implementation.utils import (
    _extract_goal_from_plan,
    _extract_key_files_from_plan,
    _looks_like_plan,
    commit_task_changes,
    extract_task_count,
)
from amelia.pipelines.nodes import (
    _save_token_usage,
    call_developer_node,
    call_reviewer_node,
)
from amelia.pipelines.utils import extract_config_params


# Resolve forward references in ExecutionState. Must be done after importing
# Reviewer and Evaluator since they define StructuredReviewResult and EvaluationResult.
rebuild_execution_state()


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
    event_bus, workflow_id, profile = extract_config_params(config or {})

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
    model = profile.validator_model
    prompt = f"""Extract the implementation plan structure from the following markdown plan.

<plan>
{plan_content}
</plan>

Return:
- goal: 1-2 sentence summary of what this plan accomplishes
- plan_markdown: The full plan content (preserve as-is)
- key_files: List of files that will be created or modified"""

    try:
        output = await extract_structured(
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
    event_bus, workflow_id, profile = extract_config_params(config or {})

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
    event_bus, workflow_id, profile = extract_config_params(config or {})

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

    In server mode, this interrupts for human input via LangGraph interrupt.
    In CLI mode, this currently auto-approves all items (interactive prompts not yet implemented).

    Args:
        state: Current execution state containing the evaluation result.
        config: Optional RunnableConfig with execution_mode in configurable.

    Returns:
        Empty dict (approval handled via LangGraph interrupt in server mode,
        auto-approved in CLI mode).
    """
    config = config or {}
    execution_mode = config.get("configurable", {}).get("execution_mode", "cli")

    if execution_mode == "server":
        return {}

    # CLI mode: auto-approve all items marked for implementation
    # TODO: Implement interactive prompts using typer.confirm
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

    _, _, profile = extract_config_params(config or {})
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
