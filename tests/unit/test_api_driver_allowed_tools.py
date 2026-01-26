"""Tests for ApiDriver allowed_tools parameter."""

import pytest

from amelia.drivers.api.deepagents import ApiDriver


async def test_api_driver_allowed_tools_raises_not_implemented() -> None:
    """ApiDriver raises NotImplementedError when allowed_tools is set."""
    driver = ApiDriver(model="test-model")
    with pytest.raises(NotImplementedError, match="allowed_tools"):
        async for _ in driver.execute_agentic(
            prompt="test",
            cwd="/tmp",
            allowed_tools=["read_file"],
        ):
            pass
