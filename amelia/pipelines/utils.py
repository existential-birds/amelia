"""Shared utilities for pipeline infrastructure.

This module contains helper functions used across multiple pipelines
for LangGraph configuration handling, token tracking, and the
request-scoped driver-override seam.
"""

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Union

from langchain_core.runnables.config import RunnableConfig

from amelia.core.types import Profile
from amelia.drivers.base import DriverInterface
from amelia.trajectory import RecordingDriver


if TYPE_CHECKING:
    from collections.abc import Callable

    from amelia.sandbox.provider import SandboxProvider
    from amelia.server.database.repository import WorkflowRepository
    from amelia.server.events.bus import EventBus
    from amelia.trajectory.recorder import WorkflowTrajectoryRecorder


# A driver override is either a single instance applied to every agent in the
# run, or a callable that picks a driver per agent name (``"architect"`` /
# ``"developer"`` / ``"reviewer"`` / pass name). The callable form lets a
# future caller vary the driver per agent without changing the seam.
DriverOverride = Union[
    DriverInterface,
    "Callable[[str], DriverInterface]",
]


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
    recorder: "WorkflowTrajectoryRecorder | None"
    driver_override: DriverOverride | None = None


def resolve_driver_override(
    override: DriverOverride | None, agent_name: str
) -> DriverInterface | None:
    """Resolve a (possibly callable) override to the driver for *agent_name*.

    A bare :class:`~amelia.drivers.base.DriverInterface` applies to every
    agent in the run; a callable is invoked once per agent with the agent's
    name (``"architect"``, ``"developer"``, ``"reviewer"``, or the reviewer
    pass name). Returns ``None`` when no override is configured, leaving the
    agent's key-built driver in place.
    """
    if override is None:
        return None
    # ``DriverInterface`` is a Protocol without ``@runtime_checkable``, so we
    # duck-type via the ``execute_agentic`` attribute. A callable returning a
    # driver is also accepted (``agent_name -> driver`` form). A bare driver
    # instance is NOT callable, so the callable branch only fires for the
    # factory form.
    if callable(override) and not hasattr(override, "execute_agentic"):
        return override(agent_name)
    return override  # type: ignore[return-value]


def apply_driver_override(
    agent: Any,
    override: DriverOverride | None,
    agent_name: str,
) -> None:
    """Swap ``agent.driver`` for the override, when one is configured.

    Applied in-place at every agent-construction seam, **before**
    :func:`wrap_with_recording`, so the recording driver still wraps the
    injected driver (replay recordings stay observable). When the override
    is ``None`` the call is a no-op — the agent keeps its key-built driver
    (the live path).

    Args:
        agent: Agent instance exposing a settable ``driver`` attribute.
        override: Override value from the run config (instance or callable).
        agent_name: Logical name of the agent being prepared.
    """
    resolved = resolve_driver_override(override, agent_name)
    if resolved is not None:
        agent.driver = resolved


def wrap_with_recording(agent: Any, recorder: "WorkflowTrajectoryRecorder | None", agent_name: str, model: str) -> None:
    """Wrap an agent's driver with RecordingDriver if a recorder is active.

    This is the single canonical recording-seam guard used at every node site.
    When ``recorder`` is None (CLI / non-server mode) the call is a no-op.

    Args:
        agent: An agent instance that exposes a ``driver`` attribute.
        recorder: The active WorkflowTrajectoryRecorder, or None.
        agent_name: Logical name for the invocation (e.g. ``"developer"``).
        model: Model identifier string from the agent's config.
    """
    if recorder is not None:
        inv = recorder.begin_invocation(agent_name, model=model)
        agent.driver = RecordingDriver(agent.driver, inv)


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
    repository/prompts/sandbox_provider/recorder extraction that every
    node function repeats. The recorder is read from the
    ``trajectory_recorder`` configurable key and is None outside server
    mode (e.g. CLI runs). The ``driver_override`` key carries the
    request-scoped :data:`DriverOverride` (None on the live path).

    Args:
        config: LangGraph RunnableConfig (may be None).

    Returns:
        NodeConfigParams with all commonly needed values.

    Raises:
        ValueError: If workflow_id (thread_id) or profile is missing.
    """
    resolved = config or {}
    configurable = resolved.get("configurable", {})
    event_bus, workflow_id, profile = extract_config_params(resolved)

    return NodeConfigParams(
        event_bus=event_bus,
        workflow_id=workflow_id,
        profile=profile,
        repository=configurable.get("repository"),
        prompts=configurable.get("prompts") or {},
        sandbox_provider=configurable.get("sandbox_provider"),
        recorder=configurable.get("trajectory_recorder"),
        driver_override=configurable.get("driver_override"),
    )
