"""Shared driver-initialization helper for agent classes.

Every agent in :mod:`amelia.agents` builds the same `(driver, options, prompts)`
triple from an :class:`~amelia.core.types.AgentConfig` plus an optional shared
sandbox provider. This helper centralises that wiring so the agent constructors
focus on agent-specific state.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, SkipValidation

from amelia.drivers.base import DriverInterface
from amelia.drivers.factory import get_driver


if TYPE_CHECKING:
    from amelia.core.types import AgentConfig
    from amelia.sandbox.provider import SandboxProvider


class AgentDriverInit(BaseModel):
    """Result of :func:`init_agent_driver`.

    Attributes:
        driver: Configured LLM driver instance.
        options: The agent's driver options dict (same reference as ``config.options``).
        prompts: Normalised prompt overrides (``{}`` when none provided).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    driver: SkipValidation[DriverInterface]
    options: dict[str, Any]
    prompts: dict[str, str]

    def __iter__(self) -> Iterator[Any]:  # type: ignore[override]
        """Support tuple unpacking for backward compatibility."""
        return iter((self.driver, self.options, self.prompts))

    def __len__(self) -> int:
        """Return number of fields for unpacking."""
        return 3


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
