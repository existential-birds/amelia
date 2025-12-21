# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""LangGraph state machine orchestrator for coordinating AI agents.

Implements the core workflow: Issue → Architect (plan) → Human Approval →
Developer (execute) ↔ Reviewer (review) → Done. Provides node functions for
the state machine and the create_orchestrator_graph() factory.
"""
import asyncio
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
from amelia.core.state import (
    BatchApproval,
    ExecutionBatch,
    ExecutionPlan,
    ExecutionState,
    PlanStep,
    ReviewResult,
)
from amelia.core.types import DeveloperStatus, Profile, StreamEmitter, TrustLevel
from amelia.drivers.factory import DriverFactory
from amelia.tools.git_utils import revert_to_git_snapshot


# TODO: Integrate trust level logic into batch execution flow
# This function is currently unused but will be called from call_developer_node
# to determine whether to route to batch_approval_node based on trust_level.
# See ExecutionBatch.risk_summary and Profile.trust_level for context.
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


def _extract_config_params(
    config: RunnableConfig | None,
) -> tuple[StreamEmitter | None, str, Profile]:
    """Extract stream_emitter, workflow_id, and profile from RunnableConfig.

    Args:
        config: Optional RunnableConfig with configurable parameters.

    Returns:
        Tuple of (stream_emitter, workflow_id, profile).

    Raises:
        ValueError: If workflow_id (thread_id) or profile is not provided.
    """
    config = config or {}
    configurable = config.get("configurable", {})
    stream_emitter = configurable.get("stream_emitter")
    workflow_id = configurable.get("thread_id")
    profile = configurable.get("profile")

    if not workflow_id:
        raise ValueError("workflow_id (thread_id) is required in config.configurable")
    if not profile:
        raise ValueError("profile is required in config.configurable")

    return stream_emitter, workflow_id, profile


# Define nodes for the graph
async def call_architect_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Architect agent to generate an execution plan.

    Args:
        state: Current execution state containing the issue and profile.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with the generated execution plan.

    Raises:
        ValueError: If no issue is provided in the state.
    """
    issue_id_for_log = state.issue.id if state.issue else "No Issue Provided"
    logger.info(f"Orchestrator: Calling Architect for issue {issue_id_for_log}")

    if state.issue is None:
        raise ValueError("Cannot call Architect: no issue provided in state.")

    # Extract stream_emitter, workflow_id, and profile from config
    stream_emitter, workflow_id, profile = _extract_config_params(config)

    driver = DriverFactory.get_driver(profile.driver)
    architect = Architect(driver, stream_emitter=stream_emitter)

    # Handle plan_only mode - generate plan with markdown and exit
    if state.plan_only:
        plan_output = await architect.plan(
            state=state,
            profile=profile,
            workflow_id=workflow_id or "plan-only",
        )
        logger.info(
            "Agent action completed",
            agent="architect",
            action="generated_plan",
            details={
                "batch_count": len(plan_output.execution_plan.batches),
                "markdown_path": str(plan_output.markdown_path),
            },
        )
        return {
            "execution_plan": plan_output.execution_plan,
            "workflow_status": "completed",
        }

    # Normal mode - generate execution plan
    execution_plan, new_session_id = await architect.generate_execution_plan(
        issue=state.issue,
        state=state,
        profile=profile,
    )

    # Log the agent action
    logger.info(
        "Agent action completed",
        agent="architect",
        action="generated_execution_plan",
        details={"batch_count": len(execution_plan.batches)},
    )

    # Return partial state update with execution plan and captured session_id
    return {
        "execution_plan": execution_plan,
        "driver_session_id": new_session_id,
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
    if state.execution_plan:
        for i, batch in enumerate(state.execution_plan.batches, 1):
            typer.echo(f"  Batch {i}:")
            for step in batch.steps:
                typer.echo(f"    - {step.description}")

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

    # Return single-item list - reducer will handle append via operator.add
    # Log the batch approval
    logger.info(
        "Batch approval recorded",
        batch_number=approval.batch_number,
        approved=approval.approved,
        has_feedback=approval.feedback is not None,
    )

    # Return partial state with updated approvals and reset human_approved
    return {
        "batch_approvals": [approval],
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
        # Import here to avoid circular imports
        from amelia.agents.developer import get_cascade_skips  # noqa: PLC0415

        # Mark the blocked step as skipped
        skip_reasons = {blocker.step_id: f"Skipped by user: {blocker.error_message}"}

        # Find all cascade skips (steps that depend on the skipped step)
        cascade_skips: dict[str, str] = {}
        if state.execution_plan:
            cascade_skips = get_cascade_skips(
                blocker.step_id, state.execution_plan, skip_reasons
            )

        # Combine original skip + cascade skips
        all_skipped = {blocker.step_id, *cascade_skips.keys()}

        logger.info(
            "Blocker resolved by skipping step",
            step_id=blocker.step_id,
            cascade_skipped=list(cascade_skips.keys()),
            total_skipped=len(all_skipped),
        )

        return {
            "skipped_step_ids": all_skipped,
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
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode()
        else:
            return f"Error getting git diff: {stderr.decode()}"
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

    # Extract stream_emitter, workflow_id, and profile from config
    stream_emitter, workflow_id, profile = _extract_config_params(config)

    driver = DriverFactory.get_driver(profile.driver)
    reviewer = Reviewer(driver, stream_emitter=stream_emitter)

    code_changes = await get_code_changes_for_review(state)
    review_result, new_session_id = await reviewer.review(state, code_changes, profile, workflow_id=workflow_id)

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

    return {
        "last_review": review_result,
        "driver_session_id": new_session_id,
    }

async def call_developer_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Developer agent to execute batches.

    Uses the new batch execution model via Developer.run(), which handles
    batch execution, blocker detection, and checkpoint logic internally.

    Args:
        state: Current execution state containing the execution plan.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with developer_status and batch results.
    """
    logger.info("Orchestrator: Calling Developer to execute batch.")

    # Diagnostic logging for debugging state issues
    logger.debug(
        "Developer node state",
        state_type=type(state).__name__,
        has_execution_plan=state.execution_plan is not None,
        execution_plan_type=type(state.execution_plan).__name__ if state.execution_plan else None,
        batch_count=len(state.execution_plan.batches) if state.execution_plan and state.execution_plan.batches else 0,
        human_approved=state.human_approved,
        current_batch_index=state.current_batch_index,
    )

    if not state.execution_plan or not state.execution_plan.batches:
        error_msg = (
            "Developer node has no execution plan or batches to execute. "
            "This indicates a state synchronization issue - the architect should have "
            "generated a plan before the developer runs."
        )
        logger.error(
            error_msg,
            has_execution_plan=state.execution_plan is not None,
            batches_empty=not state.execution_plan.batches if state.execution_plan else True,
            human_approved=state.human_approved,
            current_batch_index=state.current_batch_index,
        )
        raise ValueError(error_msg)

    # Extract stream_emitter, workflow_id, and profile from config if available
    stream_emitter, workflow_id, profile = _extract_config_params(config)

    driver = DriverFactory.get_driver(profile.driver)
    developer = Developer(
        driver,
        execution_mode=profile.execution_mode,
        stream_emitter=stream_emitter,
    )

    # Developer.run() handles all batch execution logic and returns state updates
    return await developer.run(state, profile)

def should_continue_review_loop(state: ExecutionState) -> Literal["re_evaluate", "end"]:
    """Determine if review loop should continue based on last review.

    Args:
        state: Current execution state containing last review and plan.

    Returns:
        're_evaluate' if review was not approved AND there are tasks to execute.
        'end' if review was approved or no tasks are ready (workflow is stuck).
    """
    if state.last_review and not state.last_review.approved:
        # Only re-evaluate if there are batches that can be executed
        if state.execution_plan and state.execution_plan.batches:
            return "re_evaluate"
        # No batches available - log and exit to prevent infinite loop
        logger.warning(
            "Review not approved but no batches available to execute. "
            "Ending workflow - manual intervention may be required."
        )
        return "end"
    return "end"

def route_after_architect(state: ExecutionState) -> Literal["end", "human_approval"]:
    """Route after architect based on plan_only mode.

    Args:
        state: Current execution state containing plan_only flag.

    Returns:
        'end' if plan_only is True (just generated plan, exit workflow).
        'human_approval' otherwise (continue to human approval).
    """
    return "end" if state.plan_only else "human_approval"

def route_approval(state: ExecutionState) -> Literal["approve", "reject"]:
    """Route based on human approval status.

    Args:
        state: Current execution state containing human_approved flag.

    Returns:
        'approve' if human_approved is True, 'reject' otherwise.
    """
    return "approve" if state.human_approved else "reject"

def route_after_developer(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> Literal["reviewer", "batch_approval", "blocker_resolution", "developer", "__end__"]:
    """Route based on Developer status.

    Args:
        state: Current execution state containing developer_status.
        config: Optional RunnableConfig with profile in configurable.

    Returns:
        Route string based on developer_status:
        - 'reviewer' if ALL_DONE (all batches completed)
        - 'batch_approval' if BATCH_COMPLETE and should_checkpoint returns True
        - 'developer' if BATCH_COMPLETE and should_checkpoint returns False (skip approval)
        - 'blocker_resolution' if BLOCKED (execution blocked, needs human help)
        - 'developer' if EXECUTING (continue executing steps)
    """
    logger.debug(
        "Routing after developer",
        developer_status=state.developer_status.value if state.developer_status else None,
        has_execution_plan=state.execution_plan is not None,
        current_batch_index=state.current_batch_index,
    )
    if state.developer_status == DeveloperStatus.ALL_DONE:
        return "reviewer"
    elif state.developer_status == DeveloperStatus.BATCH_COMPLETE:
        # Check if we should checkpoint for human approval
        # No execution plan at this point indicates state corruption - fail fast
        if state.execution_plan is None:
            logger.error(
                "route_after_developer called without an execution plan. "
                "This indicates a critical state issue. Aborting workflow.",
                developer_status=state.developer_status.value if state.developer_status else None,
            )
            return "__end__"

        # Bounds check: if we've processed all batches, route to reviewer
        if state.current_batch_index >= len(state.execution_plan.batches):
            logger.info(
                "All batches complete, routing to reviewer",
                current_batch_index=state.current_batch_index,
                total_batches=len(state.execution_plan.batches),
            )
            return "reviewer"

        # Extract profile from config
        _, _, profile = _extract_config_params(config)

        current_batch = state.execution_plan.batches[state.current_batch_index]
        if should_checkpoint(current_batch, profile):
            return "batch_approval"
        else:
            logger.info(
                "Skipping batch approval checkpoint",
                batch_number=current_batch.batch_number,
                risk_summary=current_batch.risk_summary,
                trust_level=profile.trust_level.value,
            )
            return "developer"
    elif state.developer_status == DeveloperStatus.BLOCKED:
        return "blocker_resolution"
    else:  # EXECUTING or default
        return "developer"

def route_batch_approval(state: ExecutionState) -> Literal["developer", "__end__"]:
    """Route based on batch approval status.

    Uses the batch_approvals record created by batch_approval_node, NOT human_approved.
    This is because batch_approval_node resets human_approved to None before routing.

    Args:
        state: Current execution state containing batch_approvals list.

    Returns:
        Route string based on approval:
        - 'developer' if last batch was approved (continue to next batch)
        - END if last batch was rejected or no approvals exist (stop workflow)
    """
    # Check the last batch approval record (just created by batch_approval_node)
    if state.batch_approvals and state.batch_approvals[-1].approved:
        return "developer"
    return "__end__"

def route_blocker_resolution(state: ExecutionState) -> Literal["developer", "__end__"]:
    """Route based on blocker resolution outcome.

    Args:
        state: Current execution state containing workflow_status.

    Returns:
        Route string based on workflow status:
        - END if workflow_status is 'aborted'
        - 'developer' otherwise (continue after fix/skip)
    """
    if state.workflow_status == "aborted":
        return "__end__"
    return "developer"

# Review-fix loop helper functions

def create_synthetic_plan_from_review(review: ReviewResult) -> ExecutionPlan:
    """Create a synthetic execution plan from review comments for the developer.

    Args:
        review: The review result with comments.

    Returns:
        An ExecutionPlan with a single batch containing a code action to fix review comments.
    """
    comments_text = "\n".join(f"- {c}" for c in review.comments)

    # Create a single step with the review feedback
    step = PlanStep(
        id="REVIEW-FIX-1",
        description=f"Address review comments:\n{comments_text}",
        action_type="code",
        risk_level="medium",
        estimated_minutes=5,
        requires_human_judgment=False,
        success_criteria="All review comments are addressed",
    )

    # Create a batch with the single step
    batch = ExecutionBatch(
        batch_number=1,
        steps=(step,),
        risk_summary="medium",
        description="Fix review comments",
    )

    # Create the execution plan
    return ExecutionPlan(
        goal="Address code review feedback",
        batches=(batch,),
        total_estimated_minutes=5,
        tdd_approach=False,
    )


def should_continue_review_fix(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> Literal["developer", "__end__"]:
    """Determine next step in review-fix loop.

    Args:
        state: Current execution state containing last_review.
        config: Optional RunnableConfig with profile in configurable.

    Returns:
        "developer" if review rejected and under max iterations,
        "__end__" if approved or max iterations reached.
    """
    if state.last_review and state.last_review.approved:
        return "__end__"

    # Extract profile from config
    _, _, profile = _extract_config_params(config)
    max_iterations = profile.max_review_iterations

    if state.review_iteration >= max_iterations:
        logger.warning(
            "Max review iterations reached, terminating loop",
            max_iterations=max_iterations,
        )
        return "__end__"
    return "developer"


async def call_developer_node_for_review(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Developer node for review-fix loop.

    Creates a synthetic plan from review comments and increments iteration counter.
    """
    if not state.last_review:
        raise ValueError("Cannot call developer for review without review results")

    synthetic_plan = create_synthetic_plan_from_review(state.last_review)
    new_review_iteration = state.review_iteration + 1

    updated_state = state.model_copy(update={
        "execution_plan": synthetic_plan,
        "current_batch_index": 0,
        "review_iteration": new_review_iteration,
    })

    developer_result = await call_developer_node(updated_state, config=config)

    # Include review_iteration in return so LangGraph persists the increment
    return {**developer_result, "review_iteration": new_review_iteration}


def create_review_graph(checkpointer: BaseCheckpointSaver[Any]) -> CompiledStateGraph[Any]:
    """Create a graph for review-fix loop: reviewer ↔ developer until approved.

    The graph runs autonomously without human approval pauses.
    Max 3 iterations to prevent infinite loops.
    """
    graph = StateGraph(ExecutionState)
    graph.add_node("reviewer", call_reviewer_node)
    graph.add_node("developer", call_developer_node_for_review)
    graph.add_conditional_edges("reviewer", should_continue_review_fix)
    graph.add_edge("developer", "reviewer")
    graph.set_entry_point("reviewer")
    return graph.compile(checkpointer=checkpointer)


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
    # Architect -> route based on plan_only mode
    workflow.add_conditional_edges(
        "architect_node",
        route_after_architect,
        {
            "end": END,
            "human_approval": "human_approval_node",
        }
    )

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
