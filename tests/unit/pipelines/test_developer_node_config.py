from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import AgentConfig, Profile
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.nodes import call_developer_node
from tests.conftest import AsyncIteratorMock


@pytest.mark.asyncio
async def test_call_developer_node_uses_agent_config(
    mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    mock_profile_factory: Callable[..., Profile],
):
    """call_developer_node should use profile.get_agent_config('developer')."""
    # Create profile with agents config
    profile = mock_profile_factory(
        preset="cli_single",
        agents={
            "developer": AgentConfig(driver="cli:claude", model="sonnet"),
        },
    )

    # Create state with the profile
    state, _ = mock_execution_state_factory(
        profile=profile,
        goal="Implement test feature",
        plan_markdown="## Task 1\n\nDo something",
    )

    config: dict[str, Any] = {
        "configurable": {
            "profile": profile,
            "thread_id": "wf-1",
        }
    }

    with patch("amelia.pipelines.nodes.Developer") as MockDeveloper:
        mock_developer = MagicMock()
        # Use AsyncIteratorMock for async generator return
        mock_developer.run = MagicMock(return_value=AsyncIteratorMock([
            (state.model_copy(update={"agentic_status": "completed"}), MagicMock())
        ]))
        mock_developer.driver = MagicMock()
        MockDeveloper.return_value = mock_developer

        with patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock):
            await call_developer_node(state, config)

        # Verify Developer was instantiated with AgentConfig
        call_args = MockDeveloper.call_args
        assert call_args is not None
        config_arg = call_args[0][0]  # First positional arg
        assert isinstance(config_arg, AgentConfig)
        assert config_arg.driver == "cli:claude"
        assert config_arg.model == "sonnet"
