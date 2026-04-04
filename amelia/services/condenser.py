"""Condenser service — AI-powered condensation of long issue descriptions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS


if TYPE_CHECKING:
    from amelia.drivers.base import DriverInterface


async def condense_description(
    description: str,
    driver: DriverInterface,
    system_prompt: str | None = None,
) -> tuple[str, Any]:
    """Condense a long issue description using an LLM driver.

    Args:
        description: The issue body text to condense.
        driver: LLM driver instance to use for the call.
        system_prompt: Optional custom system prompt; defaults to PROMPT_DEFAULTS['condenser.system'].

    Returns:
        Tuple of (condensed_text, session_id) matching the driver.generate() return type.
    """
    effective_prompt = system_prompt or PROMPT_DEFAULTS["condenser.system"].content
    result, session_id = await driver.generate(
        prompt=description,
        system_prompt=effective_prompt,
    )
    logger.debug("Condense complete", description_len=len(description), result_len=len(str(result)))
    return str(result), session_id
