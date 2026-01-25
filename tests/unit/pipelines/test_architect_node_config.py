from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.types import AgentConfig, Issue, Profile
from amelia.pipelines.implementation.nodes import call_architect_node
from amelia.pipelines.implementation.state import ImplementationState


@pytest.fixture
def profile_with_agents() -> Profile:
    return Profile(
        name="test",
        tracker="none",
        working_dir="/tmp/test",
        agents={
            "architect": AgentConfig(driver="cli", model="opus"),
        },
    )


@pytest.fixture
def mock_state() -> ImplementationState:
    return ImplementationState(
        workflow_id=str(uuid4()),
        profile_id="test",
        created_at=datetime.now(UTC),
        status="pending",
        issue=Issue(id="TEST-1", title="Test", description="Test issue"),
    )


class AsyncIteratorMock:
    """Mock async iterator for testing async generators."""

    def __init__(self, items: list[Any]) -> None:
        self.items = items
        self.index = 0

    def __aiter__(self) -> "AsyncIteratorMock":
        return self

    async def __anext__(self) -> Any:
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


@pytest.mark.asyncio
async def test_call_architect_node_uses_agent_config(
    profile_with_agents: Profile, mock_state: ImplementationState
) -> None:
    """call_architect_node should use profile.get_agent_config('architect')."""
    config: dict[str, Any] = {
        "configurable": {
            "profile": profile_with_agents,
            "thread_id": "wf-1",  # Note: thread_id is used, not workflow_id
        }
    }

    with patch("amelia.pipelines.implementation.nodes.Architect") as MockArchitect:
        mock_architect = MagicMock()
        # Mock plan as an async iterator
        mock_architect.plan = MagicMock(return_value=AsyncIteratorMock([
            (mock_state, MagicMock())
        ]))
        # Mock driver for _save_token_usage
        mock_architect.driver = MagicMock()
        MockArchitect.return_value = mock_architect

        with (
            patch("amelia.pipelines.implementation.nodes._save_token_usage", new_callable=AsyncMock),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value="# Plan"),
        ):
            await call_architect_node(mock_state, cast(RunnableConfig, config))

        # Verify Architect was instantiated with AgentConfig, not driver
        call_args = MockArchitect.call_args
        assert call_args is not None
        config_arg = call_args[0][0]  # First positional arg
        assert isinstance(config_arg, AgentConfig)
        assert config_arg.driver == "cli"
        assert config_arg.model == "opus"
