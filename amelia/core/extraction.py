"""Generic LLM extraction utilities.

This module provides utilities for extracting structured data from text
using LLM calls. These are general-purpose helpers not tied to any
specific pipeline.
"""

from typing import cast

from pydantic import BaseModel

from amelia.drivers.factory import get_driver


async def extract_structured[T: BaseModel](
    prompt: str,
    schema: type[T],
    model: str,
    driver_type: str,
) -> T:
    """Extract structured output from text using direct model call.

    Args:
        prompt: The prompt containing text to extract from.
        schema: Pydantic model class defining the expected structure.
        model: Model identifier to use for extraction.
        driver_type: Driver type string (e.g., "api:openrouter").

    Returns:
        Instance of schema populated with extracted data.
    """
    driver = get_driver(
        driver_key=driver_type,
        model=model,
        cwd=".",
    )

    result, _ = await driver.generate(prompt=prompt, schema=schema)
    return cast(T, result)
