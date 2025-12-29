# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Shared fixtures and helpers for all tests.

This module provides factory fixtures for creating test data and mocks
used throughout the test suite for the agentic execution model.
"""
from collections.abc import Callable, Generator
from datetime import UTC, datetime
from typing import Any, NamedTuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest import TempPathFactory

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.core.state import ExecutionState
from amelia.core.types import (
    Design,
    DriverType,
    Issue,
    Profile,
    Settings,
    StrategyType,
    StreamEvent,
    StreamEventType,
    TrackerType,
)
from amelia.drivers.base import DriverInterface


class AsyncIteratorMock:
    """Mock async iterator for testing async generators.

    Usage:
        mock_stream = AsyncIteratorMock([{"event": "a"}, {"event": "b"}])
        async for item in mock_stream:
            print(item)
    """

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


@pytest.fixture
def async_iterator_mock_factory() -> Callable[[list[Any]], AsyncIteratorMock]:
    """Factory fixture for creating AsyncIteratorMock instances."""
    def _create(items: list[Any]) -> AsyncIteratorMock:
        return AsyncIteratorMock(items)
    return _create


@pytest.fixture
def mock_issue_factory() -> Callable[..., Issue]:
    """Factory fixture for creating test Issue instances with sensible defaults."""
    def _create(
        id: str = "TEST-123",
        title: str = "Test Issue",
        description: str = "Test issue description for unit testing",
        status: str = "open"
    ) -> Issue:
        return Issue(id=id, title=title, description=description, status=status)
    return _create


@pytest.fixture
def mock_profile_factory(tmp_path_factory: TempPathFactory) -> Callable[..., Profile]:
    """Factory fixture for creating test Profile instances with presets.

    Uses tmp_path_factory to create a unique temp directory for working_dir,
    preventing tests from writing artifacts to the main codebase.
    """
    # Create a shared temp directory for all profiles in this test session
    base_tmp = tmp_path_factory.mktemp("workdir")

    def _create(
        preset: str | None = None,
        name: str = "test",
        driver: DriverType = "cli:claude",
        model: str = "sonnet",
        tracker: TrackerType = "noop",
        strategy: StrategyType = "single",
        **kwargs: Any
    ) -> Profile:
        # Use temp directory for working_dir unless explicitly overridden
        if "working_dir" not in kwargs:
            kwargs["working_dir"] = str(base_tmp)

        if preset == "cli_single":
            return Profile(name="test_cli", driver="cli:claude", model="sonnet", tracker="noop", strategy="single", **kwargs)
        elif preset == "api_single":
            return Profile(name="test_api", driver="api:openrouter", model="anthropic/claude-3.5-sonnet", tracker="noop", strategy="single", **kwargs)
        elif preset == "api_competitive":
            return Profile(name="test_comp", driver="api:openrouter", model="anthropic/claude-3.5-sonnet", tracker="noop", strategy="competitive", **kwargs)
        return Profile(name=name, driver=driver, model=model, tracker=tracker, strategy=strategy, **kwargs)
    return _create


@pytest.fixture
def mock_settings(mock_profile_factory: Callable[..., Profile]) -> Settings:
    """Create mock Settings instance with test profiles."""
    test_profile = mock_profile_factory(name="test", driver="cli:claude", tracker="noop", strategy="single")
    work_profile = mock_profile_factory(name="work", driver="cli:claude", tracker="jira", strategy="single")
    return Settings(
        active_profile="test",
        profiles={"test": test_profile, "work": work_profile}
    )


@pytest.fixture
def mock_execution_state_factory(
    mock_profile_factory: Callable[..., Profile],
    mock_issue_factory: Callable[..., Issue]
) -> Callable[..., tuple[ExecutionState, Profile]]:
    """Factory fixture for creating ExecutionState instances for agentic execution.

    Returns:
        Factory function that returns tuple[ExecutionState, Profile] where profile
        is the Profile object that was used to create the state.
    """
    def _create(
        profile: Profile | None = None,
        profile_preset: str = "cli_single",
        issue: Issue | None = None,
        goal: str | None = None,
        code_changes_for_review: str | None = None,
        design: Design | None = None,
        tool_calls: list[ToolCall] | None = None,
        tool_results: list[ToolResult] | None = None,
        **kwargs: Any
    ) -> tuple[ExecutionState, Profile]:
        if profile is None:
            profile = mock_profile_factory(preset=profile_preset)
        if issue is None:
            issue = mock_issue_factory()

        # Extract profile_id from profile
        profile_id = kwargs.pop("profile_id", profile.name)

        state = ExecutionState(
            profile_id=profile_id,
            issue=issue,
            goal=goal,
            code_changes_for_review=code_changes_for_review,
            design=design,
            tool_calls=tool_calls or [],
            tool_results=tool_results or [],
            **kwargs
        )
        return state, profile
    return _create


@pytest.fixture
def mock_driver() -> MagicMock:
    """Returns a mock driver that implements DriverInterface."""
    mock = MagicMock(spec=DriverInterface)
    mock.generate = AsyncMock(return_value=("mocked AI response", None))
    mock.execute_agentic = AsyncMock(return_value=AsyncIteratorMock([]))
    return mock


@pytest.fixture
def sample_stream_event() -> StreamEvent:
    """Create sample StreamEvent for testing stream broadcasting."""
    return StreamEvent(
        type=StreamEventType.CLAUDE_THINKING,
        content="Analyzing requirements",
        timestamp=datetime.now(UTC),
        agent="developer",
        workflow_id="wf-123",
    )


@pytest.fixture
def mock_deepagents() -> Generator[MagicMock, None, None]:
    """Fixture for mocking DeepAgents library calls.

    Mocks create_deep_agent, init_chat_model, and FilesystemBackend.
    The returned mock object contains references to all mocked components
    and allows setting return values for agent.ainvoke() and agent.astream().

    Usage:
        def test_example(mock_deepagents):
            mock_deepagents.agent_result["messages"] = [AIMessage(content="response")]
            # ... call driver.generate() ...
            mock_deepagents.create_deep_agent.assert_called_once()
    """
    from collections.abc import AsyncIterator

    with patch("amelia.drivers.api.deepagents.create_deep_agent") as mock_create_agent, \
         patch("amelia.drivers.api.deepagents.init_chat_model") as mock_init_model, \
         patch("amelia.drivers.api.deepagents.FilesystemBackend") as mock_backend_class:

        # Set up default agent result (can be modified by tests)
        agent_result: dict[str, Any] = {"messages": []}

        # Create container for all mocks first so closures can reference it
        mocks = MagicMock()
        mocks.stream_chunks = []  # Initialize default stream chunks

        # Create mock agent
        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(return_value=agent_result)

        async def mock_astream(*args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
            # Look up stream_chunks on mocks dynamically to allow test modification
            for chunk in mocks.stream_chunks:
                yield chunk

        mock_agent.astream = mock_astream

        mock_create_agent.return_value = mock_agent
        mock_init_model.return_value = MagicMock()
        mock_backend_class.return_value = MagicMock()

        # Set remaining attributes on mocks container
        mocks.create_deep_agent = mock_create_agent
        mocks.init_chat_model = mock_init_model
        mocks.backend_class = mock_backend_class
        mocks.agent = mock_agent
        mocks.agent_result = agent_result

        yield mocks


class LangGraphMocks(NamedTuple):
    """Container for LangGraph mock objects."""
    graph: MagicMock
    saver: AsyncMock
    saver_class: MagicMock
    create_graph: MagicMock


@pytest.fixture
def langgraph_mock_factory(
    async_iterator_mock_factory: Callable[[list[Any]], AsyncIteratorMock],
) -> Callable[..., LangGraphMocks]:
    """Factory fixture for creating LangGraph mock objects."""

    def _create(
        astream_items: list[Any] | None = None,
        aget_state_return: Any = None,
    ) -> LangGraphMocks:
        if astream_items is None:
            astream_items = []
        if aget_state_return is None:
            aget_state_return = MagicMock(values={}, next=[])

        mock_graph = MagicMock()
        mock_graph.aupdate_state = AsyncMock()
        mock_graph.aget_state = AsyncMock(return_value=aget_state_return)
        mock_graph.astream = lambda *args, **kwargs: async_iterator_mock_factory(
            astream_items
        )

        mock_saver = AsyncMock()
        mock_saver_class = MagicMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        mock_create_graph = MagicMock(return_value=mock_graph)

        return LangGraphMocks(
            graph=mock_graph,
            saver=mock_saver,
            saver_class=mock_saver_class,
            create_graph=mock_create_graph,
        )

    return _create
