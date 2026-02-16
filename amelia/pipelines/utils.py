"""Shared utilities for pipeline infrastructure.

This module contains helper functions used across multiple pipelines
for LangGraph configuration handling and token tracking.
"""

import uuid
from typing import TYPE_CHECKING, Any

from langchain_core.runnables.config import RunnableConfig

from amelia.core.types import Profile


if TYPE_CHECKING:
    from amelia.server.events.bus import EventBus


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
