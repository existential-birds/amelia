"""LangGraph state machine orchestrator for coordinating AI agents.

Implements the core agentic workflow: Issue → Architect (analyze) → Human Approval →
Developer (execute agentically) ↔ Reviewer (review) → Done. Provides node functions for
the state machine and the create_orchestrator_graph() factory.
"""
import asyncio
from typing import Any, Literal

import typer
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from amelia.agents.architect import Architect, PlanOutput
from amelia.agents.developer import Developer
from amelia.agents.evaluator import Evaluator
from amelia.agents.reviewer import Reviewer
from amelia.core.state import ExecutionState
from amelia.core.types import Profile, StreamEmitter
from amelia.drivers.factory import DriverFactory


def _extract_config_params(
    config: RunnableConfig | None,
) -> tuple[StreamEmitter | None, str, Profile]:
    """Extract stream_emitter, workflow_id, and profile from RunnableConfig.

    Extracts values from config.configurable dictionary. workflow_id is required.

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


async def call_architect_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Architect agent to generate an implementation plan.

    Generates a rich markdown plan that the Developer agent can follow
    agentically. The plan is saved to docs/plans/.

    Args:
        state: Current execution state containing the issue and profile.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with goal, plan_markdown, and plan_path.

    Raises:
        ValueError: If no issue is provided in the state.
    """
    issue_id_for_log = state.issue.id if state.issue else "No Issue Provided"
    logger.info(f"Orchestrator: Calling Architect for issue {issue_id_for_log}")

    if state.issue is None:
        raise ValueError("Cannot call Architect: no issue provided in state.")

    # Extract stream_emitter, workflow_id, and profile from config
    stream_emitter, workflow_id, profile = _extract_config_params(config)

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    architect = Architect(driver, stream_emitter=stream_emitter)

    # Generate implementation plan
    output: PlanOutput = await architect.plan(
        state=state,
        profile=profile,
        workflow_id=workflow_id,
    )

    # Log the architect plan generation
    logger.info(
        "Agent action completed",
        agent="architect",
        action="generated_plan",
        details={
            "goal_length": len(output.goal),
            "key_files_count": len(output.key_files),
            "plan_path": str(output.markdown_path),
        },
    )

    # Return partial state update with goal and plan from architect
    return {
        "goal": output.goal,
        "plan_markdown": output.markdown_content,
        "plan_path": str(output.markdown_path),
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


async def get_code_changes_for_review(state: ExecutionState, profile: Profile) -> str:
    """Retrieve code changes for review from state or git diff.

    Priority order:
    1. state.code_changes_for_review (explicit changes from driver)
    2. git diff against state.base_commit (workflow start commit)
    3. git diff against merge-base with main/master (feature branch changes)
    4. git diff HEAD (uncommitted changes only)

    Args:
        state: Current execution state that may contain code changes.
        profile: Profile containing the working directory for git operations.

    Returns:
        Code changes as a string, either from state or from git diff.
    """
    logger.debug(
        "get_code_changes_for_review called",
        base_commit=state.base_commit,
        has_code_changes_for_review=bool(state.code_changes_for_review),
        working_dir=profile.working_dir,
    )

    if state.code_changes_for_review:
        return state.code_changes_for_review

    cwd = profile.working_dir

    async def git_diff(ref: str) -> str | None:
        """Run git diff against a reference, return output or None if empty/failed."""
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", ref,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0 and stdout.decode().strip():
            return stdout.decode()
        return None

    try:
        # Priority 1: Diff against base_commit if available (workflow start)
        if state.base_commit:
            diff = await git_diff(state.base_commit)
            if diff:
                logger.debug("Using diff against base_commit", base_commit=state.base_commit[:8])
                return diff
            logger.debug(
                "base_commit diff was empty",
                base_commit=state.base_commit[:8] if state.base_commit else None,
            )
        else:
            logger.debug("No base_commit available in state")

        # Priority 2: Find merge-base with main/master for feature branch changes
        for base_branch in ["main", "master"]:
            proc = await asyncio.create_subprocess_exec(
                "git", "merge-base", base_branch, "HEAD",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                merge_base = stdout.decode().strip()
                diff = await git_diff(merge_base)
                if diff:
                    logger.debug("Using diff against merge-base", merge_base=merge_base[:8])
                    return diff
                logger.debug(
                    "merge-base diff was empty",
                    base_branch=base_branch,
                    merge_base=merge_base[:8] if merge_base else None,
                )
                break  # Found merge-base but no diff, continue to fallback
            else:
                logger.debug(
                    "merge-base lookup failed",
                    base_branch=base_branch,
                    stderr=stderr.decode().strip(),
                )

        # Priority 3: Uncommitted changes (git diff HEAD)
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        head_stdout, head_stderr = await proc.communicate()
        diff_output = head_stdout.decode()
        head_returncode = proc.returncode
        logger.debug(
            "git diff HEAD result",
            returncode=head_returncode,
            diff_length=len(diff_output),
            diff_empty=not diff_output.strip(),
        )
        if head_returncode == 0 and diff_output.strip():
            return diff_output

        # Priority 4: Recent commits (for when developer committed changes)
        # Try to find commits that aren't pushed yet to remote tracking branch
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-list", "--count", "@{upstream}..HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        count_stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            unpushed_count = int(count_stdout.decode().strip() or "0")
            if unpushed_count > 0:
                # Diff against HEAD~N where N is unpushed commits
                proc = await asyncio.create_subprocess_exec(
                    "git", "diff", f"HEAD~{unpushed_count}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0 and stdout.decode().strip():
                    logger.debug(
                        "Using diff of unpushed commits",
                        unpushed_count=unpushed_count,
                    )
                    return stdout.decode()
        else:
            # No upstream tracking branch - try to diff against last commit
            # This handles new branches without upstream
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "HEAD~1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout.decode().strip():
                logger.debug("Using diff of last commit (no upstream)")
                return stdout.decode()

        # Final fallback: return empty or whatever git diff HEAD gave us
        if head_returncode == 0:
            return diff_output
        else:
            return f"Error getting git diff: {head_stderr.decode()}"
    except (FileNotFoundError, OSError) as e:
        return f"Failed to execute git diff: {str(e)}"


async def call_developer_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Developer agent to execute agentically.

    Uses the new agentic execution model where the Developer autonomously
    decides what tools to use rather than following a step-by-step plan.

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

    # Extract stream_emitter, workflow_id, and profile from config
    stream_emitter, workflow_id, profile = _extract_config_params(config)

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    developer = Developer(driver, stream_emitter=stream_emitter)

    # Collect the final state from the developer's agentic execution
    final_state = state
    async for new_state, event in developer.run(state, profile):
        final_state = new_state
        # Stream events are handled by the stream_emitter if provided
        if stream_emitter:
            await stream_emitter(event)

    logger.info(
        "Agent action completed",
        agent="developer",
        action="agentic_execution",
        details={
            "tool_calls_count": len(final_state.tool_calls),
            "agentic_status": final_state.agentic_status,
        },
    )

    # Return the accumulated state from agentic execution
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

    Uses agentic review when a base_commit is available, which allows the
    reviewer agent to fetch the diff using git tools. This avoids the
    "Argument list too long" error that can occur with large diffs.

    Args:
        state: Current execution state containing issue and goal information.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with review results.
    """
    logger.info(f"Orchestrator: Calling Reviewer for issue {state.issue.id if state.issue else 'N/A'}")
    logger.debug(
        "Reviewer node state",
        base_commit=state.base_commit,
        has_code_changes_for_review=bool(state.code_changes_for_review),
    )

    # Extract stream_emitter, workflow_id, and profile from config
    stream_emitter, workflow_id, profile = _extract_config_params(config)

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    reviewer = Reviewer(driver, stream_emitter=stream_emitter)

    # Use agentic review when we have a base_commit - this avoids large diff issues
    # The agent will fetch the diff using git tools and auto-detect technologies
    if state.base_commit:
        logger.info(
            "Using agentic review with base_commit",
            agent="reviewer",
            base_commit=state.base_commit,
        )
        review_result, new_session_id = await reviewer.agentic_review(
            state, state.base_commit, profile, workflow_id=workflow_id
        )
    else:
        # Fallback to traditional review if no base_commit
        code_changes = await get_code_changes_for_review(state, profile)
        review_result, new_session_id = await reviewer.review(
            state, code_changes, profile, workflow_id=workflow_id
        )

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
    stream_emitter, workflow_id, profile = _extract_config_params(config)

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    evaluator = Evaluator(driver=driver, stream_emitter=stream_emitter)

    evaluation_result, new_session_id = await evaluator.evaluate(
        state, profile, workflow_id=workflow_id
    )

    # Auto-approve all items to implement if auto_approve is set
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
        # Server mode: interrupt for human input, approval comes from resumed state
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

    # Check if we've hit max passes
    if state.review_pass >= max_passes:
        logger.warning(
            "Max review passes reached",
            review_pass=state.review_pass,
            max_passes=max_passes,
        )
        return END

    if state.auto_approve:
        # In auto mode, check if there are still items to fix
        if state.evaluation_result and state.evaluation_result.items_to_implement:
            return "reviewer_node"  # Loop back for another pass
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

    The simplified agentic graph flow:
    START → architect_node → human_approval_node → developer_node → reviewer_node → END
                                                        ↑                    │
                                                        └────────────────────┘
                                                        (if changes requested)

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
    workflow.add_node("human_approval_node", human_approval_node)
    workflow.add_node("developer_node", call_developer_node)
    workflow.add_node("reviewer_node", call_reviewer_node)

    # Set entry point
    workflow.set_entry_point("architect_node")

    # Define edges
    # Architect -> Human approval
    workflow.add_edge("architect_node", "human_approval_node")

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

    # Reviewer -> Developer (if not approved) or END (if approved)
    workflow.add_conditional_edges(
        "reviewer_node",
        route_after_review,
        {
            "developer": "developer_node",
            END: END,
        }
    )

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

    Flow: reviewer → evaluation → [approval] → developer → [end_approval] → END

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
