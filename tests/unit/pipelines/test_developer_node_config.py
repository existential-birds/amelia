from collections.abc import Callable
from contextlib import ExitStack
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


def _setup_developer_mocks(
    state: ImplementationState,
) -> tuple[MagicMock, MagicMock]:
    """Create Developer class mock and developer instance mock.

    Returns (MockDeveloperCls, mock_developer_instance).
    """
    MockDeveloperCls = MagicMock()
    mock_developer = MagicMock()
    event = AgenticMessage(
        type=AgenticMessageType.RESULT,
        content="Done",
    ).to_workflow_event(workflow_id=uuid4(), agent="developer")
    mock_developer.run = MagicMock(return_value=AsyncIteratorMock([
        (state.model_copy(update={"agentic_status": "completed"}), event)
    ]))
    mock_developer.driver = MagicMock()
    MockDeveloperCls.return_value = mock_developer
    return MockDeveloperCls, mock_developer


async def _run_developer_node(
    state: ImplementationState,
    config: dict[str, Any],
    *,
    resolve_commit_return: Any = None,
) -> tuple[Any, MagicMock, MagicMock]:
    """Run call_developer_node with mocked Developer and _save_token_usage.

    Returns (result, MockDeveloperCls, mock_developer_instance).
    If resolve_commit_return is provided, _resolve_commit is also patched.
    """
    MockDeveloperCls, mock_developer = _setup_developer_mocks(state)
    with ExitStack() as stack:
        stack.enter_context(patch("amelia.pipelines.nodes.Developer", MockDeveloperCls))
        stack.enter_context(patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock))
        if resolve_commit_return is not None:
            stack.enter_context(
                patch(
                    "amelia.pipelines.nodes._resolve_commit",
                    new_callable=AsyncMock,
                    return_value=resolve_commit_return,
                )
            )
        result = await call_developer_node(state, cast(RunnableConfig, config))

    return result, MockDeveloperCls, mock_developer


def _make_state_and_config(
    mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    mock_profile_factory: Callable[..., Profile],
    *,
    prompts: dict[str, str] | None = None,
    base_commit: str | None = None,
) -> tuple[ImplementationState, dict[str, Any]]:
    """Create state and config from factories with common defaults."""
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
    if base_commit is not None:
        state = state.model_copy(update={"base_commit": base_commit})

    config: dict[str, Any] = {
        "configurable": {
            "profile": profile,
            "thread_id": str(uuid4()),
        }
    }
    if prompts is not None:
        config["configurable"]["prompts"] = prompts

    return state, config


@pytest.mark.asyncio
async def test_call_developer_node_uses_agent_config(
    mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    mock_profile_factory: Callable[..., Profile],
) -> None:
    """Call developer node should use profile.get_agent_config('developer')."""
    state, config = _make_state_and_config(
        mock_execution_state_factory, mock_profile_factory,
    )
    _, MockDeveloper, _ = await _run_developer_node(state, config)

    call_args = MockDeveloper.call_args
    assert call_args is not None
    config_arg = call_args[0][0]
    assert isinstance(config_arg, AgentConfig)
    assert config_arg.driver == DriverType.CLAUDE
    assert config_arg.model == "sonnet"


@pytest.mark.asyncio
async def test_call_developer_node_passes_prompts_to_developer(
    mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    mock_profile_factory: Callable[..., Profile],
) -> None:
    """Call developer node should pass resolved prompts into Developer."""
    prompts = {"developer.system": "Custom developer policy"}
    state, config = _make_state_and_config(
        mock_execution_state_factory, mock_profile_factory, prompts=prompts,
    )
    _, MockDeveloper, _ = await _run_developer_node(state, config)

    assert MockDeveloper.call_args is not None
    assert MockDeveloper.call_args.kwargs["prompts"] == prompts


@pytest.mark.asyncio
async def test_call_developer_node_passes_workflow_id(
    mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    mock_profile_factory: Callable[..., Profile],
) -> None:
    """Call developer node should pass workflow_id to developer.run()."""
    state, config = _make_state_and_config(
        mock_execution_state_factory, mock_profile_factory,
    )
    _, _, mock_developer = await _run_developer_node(state, config)

    mock_developer.run.assert_called_once()
    call_kwargs = mock_developer.run.call_args
    assert call_kwargs.kwargs["workflow_id"] == config["configurable"]["thread_id"]


@pytest.mark.asyncio
async def test_call_developer_node_updates_base_commit(
    mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    mock_profile_factory: Callable[..., Profile],
) -> None:
    """Developer node should update base_commit to current HEAD before running."""
    current_head = "new-head-commit-sha"
    state, config = _make_state_and_config(
        mock_execution_state_factory, mock_profile_factory,
        base_commit="old-commit-sha",
    )
    result, _, _ = await _run_developer_node(
        state, config, resolve_commit_return=current_head,
    )
    assert result["base_commit"] == current_head


@pytest.mark.asyncio
async def test_call_developer_node_keeps_base_commit_on_git_failure(
    mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
    mock_profile_factory: Callable[..., Profile],
) -> None:
    """Developer node should keep original base_commit if git fails."""
    original_base = "original-base-commit"
    state, config = _make_state_and_config(
        mock_execution_state_factory, mock_profile_factory,
        base_commit=original_base,
    )
    result, _, _ = await _run_developer_node(
        state, config, resolve_commit_return=None,
    )
    assert result["base_commit"] == original_base
