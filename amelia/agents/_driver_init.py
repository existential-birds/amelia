"""Shared driver-initialization helper for agent classes.

Every agent in :mod:`amelia.agents` builds the same `(driver, options, prompts)`
triple from an :class:`~amelia.core.types.AgentConfig` plus an optional shared
sandbox provider. This helper centralises that wiring so the agent constructors
focus on agent-specific state.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from amelia.drivers.factory import get_driver


if TYPE_CHECKING:
    from amelia.core.types import AgentConfig
    from amelia.drivers.base import DriverInterface
    from amelia.sandbox.provider import SandboxProvider


class AgentDriverInit(NamedTuple):
    """Tuple of values produced by :func:`init_agent_driver`.

    Attributes:
        driver: Configured LLM driver instance.
        options: The agent's driver options dict (same reference as ``config.options``).
        prompts: Normalised prompt overrides (``{}`` when none provided).
    """

    driver: DriverInterface
    options: dict[str, Any]
    prompts: dict[str, str]


def init_agent_driver(
    config: AgentConfig,
    *,
    prompts: dict[str, str] | None = None,
    sandbox_provider: SandboxProvider | None = None,
) -> AgentDriverInit:
    """Build the shared driver/options/prompts triple for an agent.

    Args:
        config: Agent configuration with driver, model, sandbox, and options.
        prompts: Optional dict mapping prompt IDs to custom content.
        sandbox_provider: Optional shared sandbox provider for sandbox reuse.

    Returns:
        :class:`AgentDriverInit` containing the configured driver, the options
        dict, and the normalised prompts dict.
    """
    driver = get_driver(
        config.driver,
        model=config.model,
        sandbox_config=config.sandbox,
        sandbox_provider=sandbox_provider,
        profile_name=config.profile_name,
        options=config.options,
    )
    return AgentDriverInit(driver=driver, options=config.options, prompts=prompts or {})
