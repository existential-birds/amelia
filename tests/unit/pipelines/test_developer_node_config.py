from collections.abc import Callable
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.types import AgentConfig, DriverType, Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.nodes import call_developer_node
from tests.conftest import AsyncIteratorMock


@pytest.mark.asyncio
async def test_call_developer_node_uses_agent_config(
    mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    mock_profile_factory: Callable[..., Profile],
) -> None:
    """Call developer node should use profile.get_agent_config('developer')."""
    # Create profile with agents config
    profile = mock_profile_factory(
        preset="cli_single",
        agents={
            "developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
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
            "thread_id": str(uuid4()),
        }
    }

    with patch("amelia.pipelines.nodes.Developer") as MockDeveloper:
        mock_developer = MagicMock()
        event = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Done",
        ).to_workflow_event(workflow_id=uuid4(), agent="developer")
        # Use AsyncIteratorMock for async generator return
        mock_developer.run = MagicMock(return_value=AsyncIteratorMock([
            (state.model_copy(update={"agentic_status": "completed"}), event)
        ]))
        mock_developer.driver = MagicMock()
        MockDeveloper.return_value = mock_developer

        with patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock):
            await call_developer_node(state, cast(RunnableConfig, config))

        # Verify Developer was instantiated with AgentConfig
        call_args = MockDeveloper.call_args
        assert call_args is not None
        config_arg = call_args[0][0]  # First positional arg
        assert isinstance(config_arg, AgentConfig)
        assert config_arg.driver == DriverType.CLAUDE
        assert config_arg.model == "sonnet"


@pytest.mark.asyncio
async def test_call_developer_node_passes_prompts_to_developer(
    mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    mock_profile_factory: Callable[..., Profile],
) -> None:
    """Call developer node should pass resolved prompts into Developer.

    Args:
        mock_execution_state_factory: Factory for execution state and profile.
        mock_profile_factory: Factory for profile instances.
    """
    profile = mock_profile_factory(
        preset="cli_single",
        agents={
            "developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
        },
    )
    state, _ = mock_execution_state_factory(
        profile=profile,
        goal="Implement test feature",
        plan_markdown="## Task 1\n\nDo something",
    )
    prompts = {"developer.system": "Custom developer policy"}
    config: dict[str, Any] = {
        "configurable": {
            "profile": profile,
            "thread_id": str(uuid4()),
            "prompts": prompts,
        }
    }

    with patch("amelia.pipelines.nodes.Developer") as MockDeveloper:
        mock_developer = MagicMock()
        event = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Done",
        ).to_workflow_event(workflow_id=uuid4(), agent="developer")
        mock_developer.run = MagicMock(return_value=AsyncIteratorMock([
            (state.model_copy(update={"agentic_status": "completed"}), event)
        ]))
        mock_developer.driver = MagicMock()
        MockDeveloper.return_value = mock_developer

        with patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock):
            await call_developer_node(state, cast(RunnableConfig, config))

        assert MockDeveloper.call_args is not None
        assert MockDeveloper.call_args.kwargs["prompts"] == prompts


@pytest.mark.asyncio
async def test_call_developer_node_passes_workflow_id(
    mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    mock_profile_factory: Callable[..., Profile],
) -> None:
    """Call developer node should pass workflow_id to developer.run()."""
    profile = mock_profile_factory(
        preset="cli_single",
        agents={
            "developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
        },
    )
    state, _ = mock_execution_state_factory(
        profile=profile,
        goal="Implement test feature",
        plan_markdown="## Task 1\n\nDo something",
    )
    thread_id = str(uuid4())
    config: dict[str, Any] = {
        "configurable": {
            "profile": profile,
            "thread_id": thread_id,
        }
    }

    with patch("amelia.pipelines.nodes.Developer") as MockDeveloper:
        mock_developer = MagicMock()
        event = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Done",
        ).to_workflow_event(workflow_id=uuid4(), agent="developer")
        mock_developer.run = MagicMock(return_value=AsyncIteratorMock([
            (state.model_copy(update={"agentic_status": "completed"}), event)
        ]))
        mock_developer.driver = MagicMock()
        MockDeveloper.return_value = mock_developer

        with patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock):
            await call_developer_node(state, cast(RunnableConfig, config))

        # Verify workflow_id was passed to developer.run()
        mock_developer.run.assert_called_once()
        call_kwargs = mock_developer.run.call_args
        assert call_kwargs.kwargs["workflow_id"] == thread_id


@pytest.mark.asyncio
async def test_call_developer_node_updates_base_commit(
    mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    mock_profile_factory: Callable[..., Profile],
) -> None:
    """Developer node should update base_commit to current HEAD before running.

    This ensures the next reviewer pass only diffs against the developer's
    latest changes, not the entire branch diff from workflow start.

    Args:
        mock_execution_state_factory: Factory for execution state and profile.
        mock_profile_factory: Factory for profile instances.
    """
    profile = mock_profile_factory(
        preset="cli_single",
        agents={
            "developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
        },
    )
    state, _ = mock_execution_state_factory(
        profile=profile,
        goal="Implement test feature",
        plan_markdown="## Task 1\n\nDo something",
    )
    # Simulate a base_commit from workflow start
    state = state.model_copy(update={"base_commit": "old-commit-sha"})

    config: dict[str, Any] = {
        "configurable": {
            "profile": profile,
            "thread_id": str(uuid4()),
        }
    }

    current_head = "new-head-commit-sha"

    with patch("amelia.pipelines.nodes.Developer") as MockDeveloper:
        mock_developer = MagicMock()
        event = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Done",
        ).to_workflow_event(workflow_id=uuid4(), agent="developer")
        mock_developer.run = MagicMock(return_value=AsyncIteratorMock([
            (state.model_copy(update={"agentic_status": "completed"}), event)
        ]))
        mock_developer.driver = MagicMock()
        MockDeveloper.return_value = mock_developer

        with (
            patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock),
            patch("amelia.pipelines.nodes.get_current_commit", new_callable=AsyncMock, return_value=current_head),
        ):
            result = await call_developer_node(state, cast(RunnableConfig, config))

    assert result["base_commit"] == current_head


@pytest.mark.asyncio
async def test_call_developer_node_keeps_base_commit_on_git_failure(
    mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    mock_profile_factory: Callable[..., Profile],
) -> None:
    """Developer node should keep original base_commit if git fails.

    Args:
        mock_execution_state_factory: Factory for execution state and profile.
        mock_profile_factory: Factory for profile instances.
    """
    profile = mock_profile_factory(
        preset="cli_single",
        agents={
            "developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
        },
    )
    state, _ = mock_execution_state_factory(
        profile=profile,
        goal="Implement test feature",
        plan_markdown="## Task 1\n\nDo something",
    )
    original_base = "original-base-commit"
    state = state.model_copy(update={"base_commit": original_base})

    config: dict[str, Any] = {
        "configurable": {
            "profile": profile,
            "thread_id": str(uuid4()),
        }
    }

    with patch("amelia.pipelines.nodes.Developer") as MockDeveloper:
        mock_developer = MagicMock()
        event = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Done",
        ).to_workflow_event(workflow_id=uuid4(), agent="developer")
        mock_developer.run = MagicMock(return_value=AsyncIteratorMock([
            (state.model_copy(update={"agentic_status": "completed"}), event)
        ]))
        mock_developer.driver = MagicMock()
        MockDeveloper.return_value = mock_developer

        with (
            patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock),
            patch("amelia.pipelines.nodes.get_current_commit", new_callable=AsyncMock, return_value=None),
        ):
            result = await call_developer_node(state, cast(RunnableConfig, config))

    assert result["base_commit"] == original_base
