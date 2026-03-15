"""Shared utilities for pipeline infrastructure.

This module contains helper functions used across multiple pipelines
for LangGraph configuration handling and token tracking.
"""

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from langchain_core.runnables.config import RunnableConfig

from amelia.core.types import Profile


if TYPE_CHECKING:
    from amelia.sandbox.provider import SandboxProvider
    from amelia.server.database.repository import WorkflowRepository
    from amelia.server.events.bus import EventBus


@dataclass(frozen=True)
class NodeConfigParams:
    """Bundled configuration parameters extracted from LangGraph RunnableConfig.

    Groups the commonly needed values so node functions can destructure
    a single object instead of repeating the same extraction boilerplate.
    """

    event_bus: "EventBus | None"
    workflow_id: uuid.UUID
    profile: Profile
    repository: "WorkflowRepository | None"
    prompts: dict[str, Any]
    sandbox_provider: "SandboxProvider | None"


def extract_config_params(
    config: RunnableConfig | dict[str, Any],
) -> tuple["EventBus | None", uuid.UUID, Profile]:
    """Extract common parameters from LangGraph config.

    Args:
        config: LangGraph RunnableConfig containing configurable dict.

    Returns:
        Tuple of (event_bus, workflow_id, profile).
        event_bus may be None if not running in server mode.

    Raises:
        ValueError: If workflow_id (thread_id) or profile is missing from config.
    """
    configurable = config.get("configurable", {})

    event_bus = configurable.get("event_bus")
    workflow_id = configurable.get("thread_id")
    profile = configurable.get("profile")

    if not workflow_id:
        raise ValueError("workflow_id (thread_id) is required in config.configurable")
    if not profile:
        raise ValueError("profile is required in config.configurable")

    return event_bus, workflow_id, profile


def extract_node_config(
    config: RunnableConfig | dict[str, Any] | None,
) -> NodeConfigParams:
    """Extract all common node parameters from LangGraph config.

    Combines the event_bus/workflow_id/profile extraction with the
    repository/prompts/sandbox_provider extraction that every node
    function repeats.

    Args:
        config: LangGraph RunnableConfig (may be None).

    Returns:
        NodeConfigParams with all commonly needed values.

    Raises:
        ValueError: If workflow_id (thread_id) or profile is missing.
    """
    resolved = config or {}
    configurable = resolved.get("configurable", {})

    event_bus = configurable.get("event_bus")
    workflow_id = configurable.get("thread_id")
    profile = configurable.get("profile")

    if not workflow_id:
        raise ValueError("workflow_id (thread_id) is required in config.configurable")
    if not profile:
        raise ValueError("profile is required in config.configurable")

    return NodeConfigParams(
        event_bus=event_bus,
        workflow_id=workflow_id,
        profile=profile,
        repository=configurable.get("repository"),
        prompts=configurable.get("prompts", {}),
        sandbox_provider=configurable.get("sandbox_provider"),
    )
