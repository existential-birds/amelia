# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""LangGraph state machine orchestrator for coordinating AI agents.

Implements the core agentic workflow: Issue → Architect (analyze) → Human Approval →
Developer (execute agentically) ↔ Reviewer (review) → Done. Provides node functions for
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

from amelia.agents.architect import Architect, PlanOutput
from amelia.agents.developer import Developer
from amelia.agents.reviewer import Reviewer
from amelia.core.state import ExecutionState
from amelia.core.types import Profile, StreamEmitter, StreamEvent, StreamEventType
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
        "plan_path": output.markdown_path,
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


async def get_code_changes_for_review(state: ExecutionState) -> str:
    """Retrieve code changes for review from state or git diff.

    Prioritizes changes from state.code_changes_for_review, falls back to git diff HEAD.

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
            # Map API event types to StreamEventType
            event_type_map = {
                "thinking": StreamEventType.CLAUDE_THINKING,
                "tool_use": StreamEventType.CLAUDE_TOOL_CALL,
                "tool_result": StreamEventType.CLAUDE_TOOL_RESULT,
                "result": StreamEventType.AGENT_OUTPUT,
            }
            stream_type = event_type_map.get(event.type, StreamEventType.CLAUDE_TOOL_RESULT)

            # Determine content based on event type
            if event.type == "tool_use":
                content = event.tool_name or ""
            elif event.type == "tool_result":
                content = event.tool_result or ""
            elif event.type == "result":
                content = event.result_text or ""
            else:
                content = event.content or ""

            stream_event = StreamEvent(
                type=stream_type,
                content=content,
                timestamp=datetime.now(UTC),
                agent="developer",
                workflow_id=workflow_id,
                tool_name=event.tool_name,
                tool_input=event.tool_input,
            )
            await stream_emitter(stream_event)

    logger.info(
        "Agent action completed",
        agent="developer",
        action="agentic_execution",
        details={
            "tool_calls_count": len(final_state.tool_calls),
            "status": final_state.status,
        },
    )

    # Return the accumulated state from agentic execution
    return {
        "tool_calls": list(final_state.tool_calls),
        "tool_results": list(final_state.tool_results),
        "status": final_state.status,
        "final_response": final_state.final_response,
        "error": final_state.error,
        "driver_session_id": final_state.driver_session_id,
    }


async def call_reviewer_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Reviewer agent to review code changes.

    Args:
        state: Current execution state containing issue and goal information.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with review results.
    """
    logger.info(f"Orchestrator: Calling Reviewer for issue {state.issue.id if state.issue else 'N/A'}")

    # Extract stream_emitter, workflow_id, and profile from config
    stream_emitter, workflow_id, profile = _extract_config_params(config)

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
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
