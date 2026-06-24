"""Tests that read-only agents pass technical tool restrictions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch
from uuid import uuid4

from amelia.agents.architect import Architect
from amelia.core.types import AgentConfig, DriverType
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from tests.integration.conftest import make_execution_state, make_profile


async def test_api_architect_passes_readonly_allowed_tools_with_write_plan_exception(
    tmp_path,
) -> None:
    """Architect must not rely on prompt-only read-only instructions for API runs."""
    captured_kwargs: dict[str, object] = {}

    async def fake_execute_agentic(*args: object, **kwargs: object) -> AsyncIterator[AgenticMessage]:
        captured_kwargs.update(kwargs)
        yield AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="planned",
            session_id="session-1",
        )

    driver = MagicMock()
    driver.execute_agentic = fake_execute_agentic
    config = AgentConfig(driver=DriverType.API, model="test/model")

    with patch("amelia.agents.architect.init_agent_driver") as mock_init:
        mock_init.return_value = MagicMock(driver=driver, options={}, prompts={})
        architect = Architect(config)

    profile = make_profile(repo_root=str(tmp_path))
    state = make_execution_state(profile=profile)

    async for _state, _event in architect.plan(state, profile, workflow_id=uuid4()):
        pass

    allowed_tools = set(captured_kwargs["allowed_tools"])  # type: ignore[arg-type]
    assert "write_plan" in allowed_tools
    assert "read_file" in allowed_tools
    assert "glob" in allowed_tools
    assert "grep" in allowed_tools
    assert "write_file" not in allowed_tools
    assert "edit_file" not in allowed_tools
    assert "execute" not in allowed_tools
    assert captured_kwargs["tool_context"] is not None
