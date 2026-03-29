"""Review pipeline specific node functions.

This module contains node functions specific to the review pipeline
that evaluate review feedback.
"""

from typing import Any

from langchain_core.runnables.config import RunnableConfig
from loguru import logger

from amelia.agents.developer import Developer
from amelia.agents.evaluator import Evaluator
from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.nodes import _resolve_commit, _save_token_usage
from amelia.pipelines.review.developer_prompt import build_review_fix_prompt
from amelia.pipelines.utils import extract_node_config


async def call_evaluation_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Node that evaluates review feedback.

    Calls the Evaluator agent to process review results and
    apply the decision matrix for each item.

    Args:
        state: Current execution state containing the review feedback.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with evaluation_result and driver_session_id.
    """
    nc = extract_node_config(config)

    agent_config = nc.profile.get_agent_config("evaluator")
    evaluator = Evaluator(config=agent_config, event_bus=nc.event_bus, prompts=nc.prompts, sandbox_provider=nc.sandbox_provider)

    evaluation_result, new_session_id = await evaluator.evaluate(
        state, nc.profile, workflow_id=nc.workflow_id
    )

    await _save_token_usage(evaluator.driver, nc.workflow_id, "evaluator", nc.repository)

    logger.info(
        "Agent action completed",
        agent="evaluator",
        action="evaluation_completed",
        details={
            "items_to_implement": len(evaluation_result.items_to_implement),
            "items_rejected": len(evaluation_result.items_rejected),
            "items_deferred": len(evaluation_result.items_deferred),
        },
    )

    # Build a goal for the developer node from the items to implement.
    # Without this, the shared developer_node raises because goal is required.
    goal: str | None = None
    if evaluation_result.items_to_implement:
        lines = ["Fix the following review items:\n"]
        for item in evaluation_result.items_to_implement:
            lines.append(
                f"- [{item.file_path}:{item.line}] {item.title}: "
                f"{item.original_issue} — suggested fix: {item.suggested_fix}"
            )
        goal = "\n".join(lines)

    return {
        "evaluation_result": evaluation_result,
        "driver_session_id": new_session_id,
        "goal": goal,
    }


async def call_review_developer_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Run the Developer agent for review-fix work (no architect plan).

    Uses a dedicated user prompt and ``developer.review_fix`` system instructions
    so :meth:`Developer._build_prompt` (which requires ``plan_markdown``) is not used.

    Args:
        state: State with ``goal`` and ``evaluation_result`` from the evaluator.
        config: RunnableConfig with profile, thread_id, prompts, etc.

    Returns:
        Partial state update matching :func:`amelia.pipelines.nodes.call_developer_node`,
        plus ``review_pass`` incremented by one.

    """
    logger.info("Orchestrator: Calling Developer for review-fix execution.")
    logger.debug(
        "Review developer node state",
        base_commit=state.base_commit,
        goal_length=len(state.goal) if state.goal else 0,
    )

    if not state.goal:
        raise ValueError(
            "Review developer node has no goal. The evaluation node should set goal from items to implement."
        )

    nc = extract_node_config(config)

    pre_dev_commit = await _resolve_commit(nc.profile.repo_root, nc.sandbox_provider)

    task_number = state.current_task_index + 1
    logger.info(
        "Starting review-fix developer execution",
        task=task_number,
        total_tasks=state.total_tasks,
        fresh_session=True,
    )
    state = state.model_copy(update={"driver_session_id": None})

    agent_config = nc.profile.get_agent_config("developer")
    developer = Developer(agent_config, prompts=nc.prompts, sandbox_provider=nc.sandbox_provider)

    review_fix_instructions = nc.prompts.get(
        "developer.review_fix",
        PROMPT_DEFAULTS["developer.review_fix"].content,
    )

    final_state = state
    try:
        async for new_state, event in developer.run(
            state,
            nc.profile,
            nc.workflow_id,
            prompt_builder=build_review_fix_prompt,
            instructions=review_fix_instructions,
        ):
            final_state = new_state
            if nc.event_bus and event is not None:
                nc.event_bus.emit(event)
    except Exception:
        logger.exception(
            "Review-fix developer execution failed",
            task=task_number,
            total_tasks=state.total_tasks,
            workflow_id=str(nc.workflow_id),
        )
        raise

    await _save_token_usage(developer.driver, nc.workflow_id, "developer", nc.repository)

    logger.info(
        "Agent action completed",
        agent="developer",
        action="review_fix_agentic_execution",
        tool_calls_count=len(final_state.tool_calls),
        agentic_status=str(final_state.agentic_status),
    )

    return {
        "tool_calls": list(final_state.tool_calls),
        "tool_results": list(final_state.tool_results),
        "agentic_status": final_state.agentic_status,
        "final_response": final_state.final_response,
        "error": final_state.error,
        "driver_session_id": final_state.driver_session_id,
        "base_commit": pre_dev_commit or state.base_commit,
        "review_pass": state.review_pass + 1,
    }
