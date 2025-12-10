# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""LangGraph state machine orchestrator for coordinating AI agents.

Implements the core workflow: Issue → Architect (plan) → Human Approval →
Developer (execute) ↔ Reviewer (review) → Done. Provides node functions for
the state machine and the create_orchestrator_graph() factory.
"""
import os
import subprocess
from typing import Any, Literal

import typer
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from amelia.agents.architect import Architect
from amelia.agents.developer import Developer
from amelia.agents.reviewer import Reviewer
from amelia.core.state import ExecutionState, TaskDAG
from amelia.drivers.factory import DriverFactory


# Define nodes for the graph
async def call_architect_node(state: ExecutionState) -> dict[str, Any]:
    """Orchestrator node for the Architect agent to generate a plan.

    Args:
        state: Current execution state containing the issue and profile.

    Returns:
        Partial state dict with the generated plan.

    Raises:
        ValueError: If no issue is provided in the state.
    """
    issue_id_for_log = state.issue.id if state.issue else "No Issue Provided"
    logger.info(f"Orchestrator: Calling Architect for issue {issue_id_for_log}")

    if state.issue is None:
        raise ValueError("Cannot call Architect: no issue provided in state.")

    driver = DriverFactory.get_driver(state.profile.driver)
    architect = Architect(driver)
    plan_output = await architect.plan(state.issue, output_dir=state.profile.plan_output_dir)

    # Log the agent action
    logger.info(
        "Agent action completed",
        agent="architect",
        action="generated_plan",
        details={"task_count": len(plan_output.task_dag.tasks)},
    )

    # Return partial state update
    return {"plan": plan_output.task_dag}

async def human_approval_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Node to prompt for human approval before proceeding.

    Behavior depends on execution mode:
    - CLI mode: Blocking prompt via typer.confirm
    - Server mode: Returns empty dict (interrupt mechanism handles pause)

    Args:
        state: Current execution state containing the plan to be reviewed.
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
    typer.echo("Review the proposed plan before proceeding. State snapshot (for debug):")
    typer.echo(f"Plan for issue {state.issue.id if state.issue else 'N/A'}:")
    if state.plan:
        for task in state.plan.tasks:
            typer.echo(f"  - [{task.id}] {task.description} (Dependencies: {', '.join(task.dependencies)})")

    approved = typer.confirm("Do you approve this plan to proceed with development?", default=True)
    comment = typer.prompt("Add an optional comment for the audit log (press Enter to skip)", default="")

    # Log the approval decision
    logger.info(
        "Human approval received",
        approved=approved,
        comment=comment,
    )

    return {"human_approved": approved}

async def get_code_changes_for_review(state: ExecutionState) -> str:
    """Retrieves code changes for review.

    Prioritizes changes from state, otherwise attempts to get git diff.

    Args:
        state: Current execution state that may contain code changes.

    Returns:
        Code changes as a string, either from state or from git diff.
    """
    if state.code_changes_for_review:
        return state.code_changes_for_review

    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            return result.stdout
        else:
            return f"Error getting git diff: {result.stderr}"
    except Exception as e:
        return f"Failed to execute git diff: {str(e)}"

async def call_reviewer_node(state: ExecutionState) -> dict[str, Any]:
    """Orchestrator node for the Reviewer agent to review code changes.

    Args:
        state: Current execution state containing issue and plan information.

    Returns:
        Partial state dict with review results.
    """
    logger.info(f"Orchestrator: Calling Reviewer for issue {state.issue.id if state.issue else 'N/A'}")
    driver = DriverFactory.get_driver(state.profile.driver)
    reviewer = Reviewer(driver)

    code_changes = await get_code_changes_for_review(state)
    review_result = await reviewer.review(state, code_changes)

    # Log the review completion
    logger.info(
        "Agent action completed",
        agent="reviewer",
        action="review_completed",
        details={
            "severity": review_result.severity,
            "approved": review_result.approved,
            "comment_count": len(review_result.comments),
        },
    )

    return {"last_review": review_result}

async def call_developer_node(state: ExecutionState) -> dict[str, Any]:
    """Orchestrator node for the Developer agent to execute tasks.

    Executes ready tasks, passing execution_mode and working directory from profile.

    Args:
        state: Current execution state containing the plan and tasks.

    Returns:
        Partial state dict with task results.
    """
    logger.info("Orchestrator: Calling Developer to execute tasks.")

    if not state.plan or not state.plan.tasks:
        logger.info("Orchestrator: No plan or tasks to execute.")
        return {}

    driver = DriverFactory.get_driver(state.profile.driver)
    developer = Developer(driver, execution_mode=state.profile.execution_mode)

    # Get working directory for agentic execution
    cwd = state.profile.working_dir or os.getcwd()

    ready_tasks = state.plan.get_ready_tasks()

    if not ready_tasks:
        logger.info("Orchestrator: No ready tasks found to execute in this iteration.")
        return {}

    logger.info(f"Orchestrator: Executing {len(ready_tasks)} ready tasks.")

    # Create a mutable copy of tasks to update immutably
    updated_tasks = list(state.plan.tasks)

    for task in ready_tasks:
        # Find the index of this task in the updated_tasks list
        task_idx = next(j for j, t in enumerate(updated_tasks) if t.id == task.id)

        # Update status to in_progress (immutably)
        updated_tasks[task_idx] = task.model_copy(update={"status": "in_progress"})
        logger.info(f"Orchestrator: Developer executing task {task.id}")

        try:
            result = await developer.execute_task(task, cwd=cwd)

            if result.get("status") == "completed":
                # Update status to completed (immutably)
                updated_tasks[task_idx] = updated_tasks[task_idx].model_copy(update={"status": "completed"})
                output_content = result.get("output", "No output")
                logger.info(
                    "Task completed",
                    task_id=task.id,
                    output=output_content,
                )
            else:
                # Update status to failed (immutably)
                updated_tasks[task_idx] = updated_tasks[task_idx].model_copy(update={"status": "failed"})
                logger.error(
                    "Task failed",
                    task_id=task.id,
                    error=result.get("error", "Unknown"),
                )

        except Exception as e:
            # Update status to failed (immutably)
            updated_tasks[task_idx] = updated_tasks[task_idx].model_copy(update={"status": "failed"})
            logger.error(f"Task {task.id} failed: {e}")

            # For agentic mode, fail fast
            if state.profile.execution_mode == "agentic":
                updated_plan = TaskDAG(
                    tasks=updated_tasks, original_issue=state.plan.original_issue
                )
                return {"plan": updated_plan, "workflow_status": "failed"}

    updated_plan = TaskDAG(
        tasks=updated_tasks, original_issue=state.plan.original_issue
    )

    return {
        "plan": updated_plan,
        "current_task_id": ready_tasks[0].id if ready_tasks else state.current_task_id
    }

# Define a conditional edge to decide if more tasks need to be run
def should_continue_developer(state: ExecutionState) -> Literal["continue", "end"]:
    """Determine whether to continue the developer loop.

    Args:
        state: Current execution state containing the plan and task status.

    Returns:
        'continue' if there are ready tasks to execute.
        'end' if no plan exists, all tasks are completed, or pending tasks are blocked.
    """
    if not state.plan:
        return "end"

    # Check for ready tasks, not just pending tasks.
    # This prevents infinite loops when tasks are blocked by failed dependencies.
    ready_tasks = state.plan.get_ready_tasks()
    if ready_tasks:
        return "continue"
    return "end"

def should_continue_review_loop(state: ExecutionState) -> Literal["re_evaluate", "end"]:
    """Determine if review loop should continue based on last review.

    Args:
        state: Current execution state containing last review and plan.

    Returns:
        're_evaluate' if review was not approved AND there are tasks to execute.
        'end' if review was approved or no tasks are ready (workflow is stuck).
    """
    if state.last_review and not state.last_review.approved:
        # Only re-evaluate if there are tasks that can be executed
        if state.plan and state.plan.get_ready_tasks():
            return "re_evaluate"
        # No tasks available - log and exit to prevent infinite loop
        logger.warning(
            "Review not approved but no tasks available to execute. "
            "Ending workflow - manual intervention may be required."
        )
        return "end"
    return "end"

def route_approval(state: ExecutionState) -> Literal["approve", "reject"]:
    """Route based on human approval status.

    Args:
        state: Current execution state containing human_approved flag.

    Returns:
        'approve' if human_approved is True, 'reject' otherwise.
    """
    return "approve" if state.human_approved else "reject"

def create_orchestrator_graph(
    checkpoint_saver: BaseCheckpointSaver[Any] | None = None,
    interrupt_before: list[str] | None = None,
) -> CompiledStateGraph[Any]:
    """Creates and compiles the LangGraph state machine for the orchestrator.

    Args:
        checkpoint_saver: Optional checkpoint saver for state persistence.
        interrupt_before: List of node names to interrupt before executing.
            Use ["human_approval_node"] for server-mode human-in-the-loop.

    Returns:
        Compiled StateGraph ready for execution.
    """
    workflow = StateGraph(ExecutionState)

    # Add nodes
    workflow.add_node("architect_node", call_architect_node)
    workflow.add_node("human_approval_node", human_approval_node)
    workflow.add_node("developer_node", call_developer_node)
    workflow.add_node("reviewer_node", call_reviewer_node)

    # Set entry point
    workflow.set_entry_point("architect_node")

    # Define edges
    workflow.add_edge("architect_node", "human_approval_node")

    # Conditional edge from human_approval_node: if approved, go to developer_node, else END
    workflow.add_conditional_edges(
        "human_approval_node",
        route_approval,
        {
            "approve": "developer_node",
            "reject": END
        }
    )

    # Developer -> Reviewer (after all development tasks are done)
    workflow.add_conditional_edges(
        "developer_node",
        should_continue_developer,
        {
            "continue": "developer_node",
            "end": "reviewer_node"
        }
    )

    # Reviewer -> Developer (if not approved) or END (if approved)
    workflow.add_conditional_edges(
        "reviewer_node",
        should_continue_review_loop,
        {
            "re_evaluate": "developer_node",
            "end": END
        }
    )

    return workflow.compile(
        checkpointer=checkpoint_saver,
        interrupt_before=interrupt_before,
    )
