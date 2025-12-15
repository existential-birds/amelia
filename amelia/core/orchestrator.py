# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""LangGraph state machine orchestrator for coordinating AI agents.

Implements the core workflow: Issue → Architect (plan) → Human Approval →
Developer (execute) ↔ Reviewer (review) → Done. Provides node functions for
the state machine and the create_orchestrator_graph() factory.
"""
import subprocess
from datetime import UTC, datetime
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
from amelia.core.state import BatchApproval, ExecutionBatch, ExecutionState, TaskDAG
from amelia.core.types import DeveloperStatus, Profile, StreamEmitter, TrustLevel
from amelia.drivers.factory import DriverFactory
from amelia.tools.git_utils import revert_to_git_snapshot


def should_checkpoint(batch: ExecutionBatch, profile: Profile) -> bool:
    """Determine if we should pause for human approval.

    Logic based on trust_level:
    1. If batch_checkpoint_enabled is False → never checkpoint
    2. TrustLevel.PARANOID → always checkpoint (return True)
    3. TrustLevel.STANDARD → always checkpoint (return True)
    4. TrustLevel.AUTONOMOUS → only checkpoint for high-risk batches (risk_summary == "high")

    Args:
        batch: The execution batch to evaluate.
        profile: The profile containing trust level and checkpoint settings.

    Returns:
        True if we should pause for human approval, False otherwise.
    """
    # Rule 1: If checkpoints are disabled, never checkpoint
    if not profile.batch_checkpoint_enabled:
        return False

    # Rule 2 & 3: PARANOID and STANDARD always checkpoint
    if profile.trust_level in (TrustLevel.PARANOID, TrustLevel.STANDARD):
        return True

    # Rule 4: AUTONOMOUS only checkpoints for high-risk batches
    if profile.trust_level == TrustLevel.AUTONOMOUS:
        return batch.risk_summary == "high"

    # Default to safe behavior: checkpoint
    return True


def _extract_config_params(config: RunnableConfig | None) -> tuple[StreamEmitter | None, str]:
    """Extract stream_emitter and workflow_id from RunnableConfig.

    Args:
        config: Optional RunnableConfig with configurable parameters.

    Returns:
        Tuple of (stream_emitter, workflow_id).

    Raises:
        ValueError: If workflow_id (thread_id) is not provided in config.configurable.
    """
    config = config or {}
    configurable = config.get("configurable", {})
    stream_emitter = configurable.get("stream_emitter")
    workflow_id = configurable.get("thread_id")
    if not workflow_id:
        raise ValueError("workflow_id (thread_id) is required in config.configurable")
    return stream_emitter, workflow_id


# Define nodes for the graph
async def call_architect_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Architect agent to generate a plan.

    Args:
        state: Current execution state containing the issue and profile.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with the generated plan.

    Raises:
        ValueError: If no issue is provided in the state.
    """
    issue_id_for_log = state.issue.id if state.issue else "No Issue Provided"
    logger.info(f"Orchestrator: Calling Architect for issue {issue_id_for_log}")

    if state.issue is None:
        raise ValueError("Cannot call Architect: no issue provided in state.")

    # Extract stream_emitter and workflow_id from config if available
    stream_emitter, workflow_id = _extract_config_params(config)

    driver = DriverFactory.get_driver(state.profile.driver)
    architect = Architect(driver, stream_emitter=stream_emitter)
    plan_output = await architect.plan(state, workflow_id=workflow_id)

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

async def batch_approval_node(state: ExecutionState) -> dict[str, Any]:
    """Human reviews completed batch. Graph interrupts before this node.

    This node records the human approval decision for a batch.
    The graph should be configured to interrupt before this node,
    allowing the human to review batch results and set human_approved.

    Args:
        state: Current execution state with human_approved already set from resume.

    Returns:
        Partial state dict with batch_approvals and reset human_approved.
    """
    # Create BatchApproval record from state
    approval = BatchApproval(
        batch_number=state.current_batch_index,
        approved=state.human_approved or False,
        feedback=getattr(state, "human_feedback", None),
        approved_at=datetime.now(UTC),
    )

    # Append to existing batch_approvals
    updated_approvals = list(state.batch_approvals)
    updated_approvals.append(approval)

    # Log the batch approval
    logger.info(
        "Batch approval recorded",
        batch_number=approval.batch_number,
        approved=approval.approved,
        has_feedback=approval.feedback is not None,
    )

    # Return partial state with updated approvals and reset human_approved
    return {
        "batch_approvals": updated_approvals,
        "human_approved": None,
    }

async def blocker_resolution_node(state: ExecutionState) -> dict[str, Any]:
    """Human resolves blocker. Graph interrupts before this node.

    Handles different resolution types based on state.blocker_resolution:
    1. "skip" → Mark step as skipped, return skipped_step_ids with the blocked step added
    2. "abort" → Keep changes, return workflow_status: "aborted"
    3. "abort_revert" → Revert batch using git, return workflow_status: "aborted"
    4. Anything else → Treat as fix instruction, pass to Developer by clearing blocker

    Args:
        state: Current execution state containing blocker and resolution.

    Returns:
        Partial state dict with appropriate fields based on resolution type.
    """
    resolution = state.blocker_resolution
    blocker = state.current_blocker

    if not blocker:
        logger.warning("blocker_resolution_node called with no current_blocker")
        return {}

    logger.info(
        "Processing blocker resolution",
        step_id=blocker.step_id,
        resolution=resolution,
        blocker_type=blocker.blocker_type,
    )

    # Handle skip resolution
    if resolution == "skip":
        updated_skipped = set(state.skipped_step_ids)
        updated_skipped.add(blocker.step_id)

        logger.info(
            "Blocker resolved by skipping step",
            step_id=blocker.step_id,
            total_skipped=len(updated_skipped),
        )

        return {
            "skipped_step_ids": updated_skipped,
            "current_blocker": None,
            "blocker_resolution": None,
        }

    # Handle abort resolution (keep changes)
    if resolution == "abort":
        logger.info(
            "Blocker resolved by aborting workflow (keeping changes)",
            step_id=blocker.step_id,
        )

        return {
            "workflow_status": "aborted",
            "current_blocker": None,
            "blocker_resolution": None,
        }

    # Handle abort with revert resolution
    if resolution == "abort_revert":
        logger.info(
            "Blocker resolved by aborting workflow with revert",
            step_id=blocker.step_id,
            has_snapshot=state.git_snapshot_before_batch is not None,
        )

        # Revert if snapshot exists
        if state.git_snapshot_before_batch:
            try:
                await revert_to_git_snapshot(state.git_snapshot_before_batch, None)
                logger.info("Successfully reverted batch changes")
            except Exception as e:
                logger.error(f"Failed to revert batch changes: {e}")
        else:
            logger.warning("No git snapshot available for revert")

        return {
            "workflow_status": "aborted",
            "current_blocker": None,
            "blocker_resolution": None,
        }

    # Any other resolution (including None/empty) is treated as a fix instruction
    # Clear the blocker and let Developer handle it
    logger.info(
        "Blocker resolved with fix instruction",
        step_id=blocker.step_id,
        instruction=resolution or "(empty - retry)",
    )

    return {
        "current_blocker": None,
        "blocker_resolution": None,
    }

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

async def call_reviewer_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Reviewer agent to review code changes.

    The orchestrator is responsible for ensuring state is properly prepared
    before calling agents. This includes setting current_task_id when a plan
    has tasks.

    Args:
        state: Current execution state containing issue and plan information.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with review results.
    """
    logger.info(f"Orchestrator: Calling Reviewer for issue {state.issue.id if state.issue else 'N/A'}")

    # Ensure current_task_id is set if plan has tasks (orchestrator owns state management)
    review_state = state
    if state.plan and state.plan.tasks and not state.current_task_id:
        # Use the first task as fallback - this shouldn't happen in normal flow
        # since developer_node sets current_task_id, but handle defensively
        logger.warning(
            "current_task_id not set despite plan having tasks. "
            "Setting to first task. This may indicate a workflow issue."
        )
        review_state = state.model_copy(update={"current_task_id": state.plan.tasks[0].id})

    # Extract stream_emitter and workflow_id from config if available
    stream_emitter, workflow_id = _extract_config_params(config)

    driver = DriverFactory.get_driver(state.profile.driver)
    reviewer = Reviewer(driver, stream_emitter=stream_emitter)

    code_changes = await get_code_changes_for_review(review_state)
    review_result = await reviewer.review(review_state, code_changes, workflow_id=workflow_id)

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

async def call_developer_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Developer agent to execute tasks.

    Executes ready tasks, passing execution_mode and working directory from profile.

    Args:
        state: Current execution state containing the plan and tasks.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with task results.
    """
    logger.info("Orchestrator: Calling Developer to execute tasks.")

    if not state.plan or not state.plan.tasks:
        logger.info("Orchestrator: No plan or tasks to execute.")
        return {}

    # Extract stream_emitter and workflow_id from config if available
    stream_emitter, workflow_id = _extract_config_params(config)

    driver = DriverFactory.get_driver(state.profile.driver)
    developer = Developer(
        driver,
        execution_mode=state.profile.execution_mode,
        stream_emitter=stream_emitter,
    )

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
            # Create state with current task ID for execution
            current_state = state.model_copy(update={"current_task_id": task.id})
            result = await developer.execute_current_task(current_state, workflow_id=workflow_id)

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

    # Determine developer_status for routing
    # Check if there are more ready tasks after this execution
    remaining_ready_tasks = updated_plan.get_ready_tasks()

    if remaining_ready_tasks:
        # More tasks to execute - continue developer loop
        developer_status = DeveloperStatus.EXECUTING
    else:
        # No more ready tasks - all done, go to reviewer
        developer_status = DeveloperStatus.ALL_DONE

    return {
        "plan": updated_plan,
        "current_task_id": ready_tasks[0].id if ready_tasks else state.current_task_id,
        "developer_status": developer_status,
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

def route_after_developer(state: ExecutionState) -> str:
    """Route based on Developer status.

    Args:
        state: Current execution state containing developer_status.

    Returns:
        Route string based on developer_status:
        - 'reviewer' if ALL_DONE (all batches completed)
        - 'batch_approval' if BATCH_COMPLETE (batch finished, needs approval)
        - 'blocker_resolution' if BLOCKED (execution blocked, needs human help)
        - 'developer' if EXECUTING (continue executing steps)
    """
    if state.developer_status == DeveloperStatus.ALL_DONE:
        return "reviewer"
    elif state.developer_status == DeveloperStatus.BATCH_COMPLETE:
        return "batch_approval"
    elif state.developer_status == DeveloperStatus.BLOCKED:
        return "blocker_resolution"
    else:  # EXECUTING or default
        return "developer"

def route_batch_approval(state: ExecutionState) -> str:
    """Route based on batch approval status.

    Args:
        state: Current execution state containing human_approved flag.

    Returns:
        Route string based on approval:
        - 'developer' if human_approved is True (continue to next batch)
        - END if human_approved is False or None (user rejected, stop workflow)
    """
    if state.human_approved:
        return "developer"
    return END

def route_blocker_resolution(state: ExecutionState) -> str:
    """Route based on blocker resolution outcome.

    Args:
        state: Current execution state containing workflow_status.

    Returns:
        Route string based on workflow status:
        - END if workflow_status is 'aborted'
        - 'developer' otherwise (continue after fix/skip)
    """
    if state.workflow_status == "aborted":
        return END
    return "developer"

def create_orchestrator_graph(
    checkpoint_saver: BaseCheckpointSaver[Any] | None = None,
    interrupt_before: list[str] | None = None,
) -> CompiledStateGraph[Any]:
    """Creates and compiles the LangGraph state machine for the orchestrator.

    Args:
        checkpoint_saver: Optional checkpoint saver for state persistence.
        interrupt_before: List of node names to interrupt before executing.
            If None and checkpoint_saver is provided, defaults to:
            ["human_approval_node", "batch_approval_node", "blocker_resolution_node"]
            for server-mode human-in-the-loop.
            If None and checkpoint_saver is not provided, no interrupts (backwards compatible).

    Returns:
        Compiled StateGraph ready for execution.
    """
    workflow = StateGraph(ExecutionState)

    # Add nodes
    workflow.add_node("architect_node", call_architect_node)
    workflow.add_node("human_approval_node", human_approval_node)
    workflow.add_node("developer_node", call_developer_node)
    workflow.add_node("reviewer_node", call_reviewer_node)
    workflow.add_node("batch_approval_node", batch_approval_node)
    workflow.add_node("blocker_resolution_node", blocker_resolution_node)

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

    # Developer -> route based on developer_status
    # - "reviewer" if ALL_DONE (all batches completed)
    # - "batch_approval" if BATCH_COMPLETE (batch finished, needs approval)
    # - "blocker_resolution" if BLOCKED (execution blocked, needs human help)
    # - "developer" if EXECUTING (continue executing steps)
    workflow.add_conditional_edges(
        "developer_node",
        route_after_developer,
        {
            "reviewer": "reviewer_node",
            "batch_approval": "batch_approval_node",
            "blocker_resolution": "blocker_resolution_node",
            "developer": "developer_node",
        }
    )

    # Batch approval -> continue to developer or END based on approval
    workflow.add_conditional_edges(
        "batch_approval_node",
        route_batch_approval,
        {
            "developer": "developer_node",
            END: END,
        }
    )

    # Blocker resolution -> continue to developer or END based on resolution
    workflow.add_conditional_edges(
        "blocker_resolution_node",
        route_blocker_resolution,
        {
            "developer": "developer_node",
            END: END,
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

    # Set default interrupt_before only if checkpoint_saver is provided and interrupt_before is None
    # This maintains backwards compatibility - old code without checkpointer won't interrupt
    if interrupt_before is None and checkpoint_saver is not None:
        interrupt_before = [
            "human_approval_node",
            "batch_approval_node",
            "blocker_resolution_node",
        ]

    return workflow.compile(
        checkpointer=checkpoint_saver,
        interrupt_before=interrupt_before,
    )
