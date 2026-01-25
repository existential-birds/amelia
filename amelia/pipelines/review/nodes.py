"""Review pipeline specific node functions.

This module contains node functions specific to the review pipeline
that evaluate review feedback.
"""

from typing import Any

from langchain_core.runnables.config import RunnableConfig
from loguru import logger

from amelia.agents.evaluator import Evaluator
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.nodes import _save_token_usage
from amelia.pipelines.utils import extract_config_params


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
    event_bus, workflow_id, profile = extract_config_params(config or {})

    config = config or {}
    configurable = config.get("configurable", {})
    prompts = configurable.get("prompts", {})
    repository = configurable.get("repository")

    agent_config = profile.get_agent_config("evaluator")
    evaluator = Evaluator(config=agent_config, event_bus=event_bus, prompts=prompts)

    evaluation_result, new_session_id = await evaluator.evaluate(
        state, profile, workflow_id=workflow_id
    )

    await _save_token_usage(evaluator.driver, workflow_id, "evaluator", repository)

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

    return {
        "evaluation_result": evaluation_result,
        "driver_session_id": new_session_id,
    }
