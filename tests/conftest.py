# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Shared fixtures and helpers for all tests.

This module provides factory fixtures for creating test data and mocks
used throughout the test suite for the agentic execution model.
"""
import os
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from pytest import TempPathFactory
from typer.testing import CliRunner

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.core.state import ExecutionState, ReviewResult, Severity
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
def mock_config_factory(mock_profile_factory: Callable[..., Profile]) -> Callable[..., dict[str, Any]]:
    """Factory fixture for creating LangGraph config with configurable profile.

    Creates a config dict with profile in config["configurable"]["profile"]
    as expected by the orchestrator nodes.
    """
    def _create(profile: Profile | None = None, **kwargs: Any) -> dict[str, Any]:
        if profile is None:
            profile = mock_profile_factory()
        return {
            "configurable": {
                "thread_id": kwargs.get("workflow_id", "test-wf"),
                "profile": profile,
                **kwargs,
            }
        }
    return _create


@pytest.fixture
def mock_driver() -> MagicMock:
    """Returns a mock driver that implements DriverInterface."""
    mock = MagicMock(spec=DriverInterface)
    mock.generate = AsyncMock(return_value=("mocked AI response", None))
    mock.execute_agentic = AsyncMock(return_value=AsyncIteratorMock([]))
    return mock


@pytest.fixture
def mock_async_driver_factory() -> Callable[..., AsyncMock]:
    """Factory fixture for creating mock DriverInterface instances."""
    def _create(
        generate_return: Any = ("mocked AI response", None),
    ) -> AsyncMock:
        mock = AsyncMock(spec=DriverInterface)
        mock.generate = AsyncMock(return_value=generate_return)
        mock.execute_agentic = AsyncMock(return_value=AsyncIteratorMock([]))
        return mock
    return _create


@pytest.fixture
def mock_review_result_factory() -> Callable[..., ReviewResult]:
    """Factory fixture for creating ReviewResult instances."""
    def _create(
        approved: bool = True,
        comments: list[str] | None = None,
        severity: Severity = "low",
        reviewer_persona: str = "Test Reviewer",
    ) -> ReviewResult:
        return ReviewResult(
            approved=approved,
            comments=comments or (["Looks good"] if approved else ["Needs changes"]),
            severity=severity,
            reviewer_persona=reviewer_persona
        )
    return _create


@pytest.fixture
def mock_design_factory() -> Callable[..., Design]:
    """Factory fixture for creating Design instances."""
    def _create(
        title: str = "Test Feature",
        goal: str = "Build test feature",
        architecture: str = "Simple architecture",
        tech_stack: list[str] | None = None,
        components: list[str] | None = None,
        raw_content: str = "",
        **kwargs: Any
    ) -> Design:
        return Design(
            title=title,
            goal=goal,
            architecture=architecture,
            tech_stack=tech_stack or ["Python"],
            components=components or ["ComponentA"],
            raw_content=raw_content,
            **kwargs
        )
    return _create


@pytest.fixture
def mock_subprocess_process_factory() -> Callable[..., AsyncMock]:
    """Factory fixture for creating mock subprocess processes."""
    def _create_mock_process(
        stdout_lines: list[bytes] | None = None,
        stderr_output: bytes = b"",
        return_code: int = 0
    ) -> AsyncMock:
        if stdout_lines is None:
            stdout_lines = [b""]

        filtered_lines = [line for line in stdout_lines if line]
        stdout_data = b"\n".join(filtered_lines)
        read_position = [0]

        async def mock_read(n: int = -1) -> bytes:
            if read_position[0] >= len(stdout_data):
                return b""
            if n == -1:
                chunk = stdout_data[read_position[0]:]
                read_position[0] = len(stdout_data)
            else:
                chunk = stdout_data[read_position[0]:read_position[0] + n]
                read_position[0] += n
            return chunk

        mock_process = AsyncMock()
        mock_process.stdin = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        mock_process.stdout.read = mock_read
        mock_process.stderr.read = AsyncMock(return_value=stderr_output)
        mock_process.returncode = return_code
        mock_process.wait = AsyncMock(return_value=return_code)
        return mock_process

    return _create_mock_process


@pytest.fixture
def settings_file_factory(tmp_path: Path) -> Callable[[Any], Path]:
    """Factory for creating settings.amelia.yaml files."""
    def _create(settings_data: Any) -> Path:
        path = tmp_path / "settings.amelia.yaml"
        with open(path, "w") as f:
            yaml.dump(settings_data, f)
        return path
    return _create


@pytest.fixture
def git_repo_with_changes(tmp_path: Path) -> Path:
    """Create a git repo with initial commit and unstaged changes."""
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@test.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@test.com",
    }

    for var in ["GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_QUARANTINE_PATH"]:
        git_env.pop(var, None)

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True, env=git_env)
    (tmp_path / "file.txt").write_text("initial")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, env=git_env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, env=git_env)
    (tmp_path / "file.txt").write_text("modified")

    return tmp_path


@pytest.fixture
def cli_runner() -> CliRunner:
    """Typer CLI test runner for command testing."""
    return CliRunner()


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
def mock_pydantic_agent() -> Callable[..., Any]:
    """Factory fixture for creating mock pydantic-ai Agent instances."""
    from collections.abc import AsyncIterator, Iterator
    from contextlib import contextmanager
    from unittest.mock import patch

    @contextmanager
    def _create() -> Iterator[dict[str, Any]]:
        with patch("amelia.drivers.api.openai.Agent") as mock_agent_class:
            async def empty_async_iter() -> AsyncIterator[None]:
                # Empty async generator - yield statement makes this a generator,
                # but never executes since there's nothing to iterate over
                if False:
                    yield

            mock_run = AsyncMock()
            mock_run.result = MagicMock(output="Done")
            mock_run.__aenter__ = AsyncMock(return_value=mock_run)
            mock_run.__aexit__ = AsyncMock(return_value=None)
            mock_run.__aiter__ = lambda self: empty_async_iter()

            mock_agent_instance = AsyncMock()
            mock_result = MagicMock()
            mock_result.output = "Test response"
            mock_agent_instance.run = AsyncMock(return_value=mock_result)
            mock_agent_instance.iter = MagicMock(return_value=mock_run)

            mock_agent_class.return_value = mock_agent_instance

            yield {
                "agent_class": mock_agent_class,
                "agent_instance": mock_agent_instance,
                "result": mock_result,
                "run": mock_run,
            }

    return _create


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
