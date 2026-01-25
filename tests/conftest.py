"""Shared fixtures and helpers for all tests.

This module provides factory fixtures for creating test data and mocks
used throughout the test suite for the agentic execution model.
"""
import os
import subprocess
from collections.abc import AsyncGenerator, Callable, Generator
from pathlib import Path
from typing import Any, NamedTuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest import TempPathFactory

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.core.types import (
    AgentConfig,
    DriverType,
    Issue,
    Profile,
    Settings,
    TrackerType,
)
from amelia.drivers.base import AgenticMessage, DriverInterface
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)
from amelia.server.database import ProfileRecord
from amelia.server.events.bus import EventBus


# Rebuild state models to resolve forward references for StructuredReviewResult
# and EvaluationResult. This must be called before any tests instantiate these states.
rebuild_implementation_state()


# =============================================================================
# Git Repository Test Fixture
# =============================================================================


def _get_repo_root() -> Path:
    """Get the root directory of this repository.

    Returns:
        Path to the repository root (directory containing .git).

    Raises:
        RuntimeError: If not inside a git repository.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Not inside a git repository")
    return Path(result.stdout.strip())


def _run_git_command(
    git_dir: Path,
    work_tree: Path,
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command with explicit --git-dir and --work-tree flags.

    Using explicit flags instead of relying on cwd ensures commands run in the
    intended directory even in worktree setups or when cwd is not respected.

    Args:
        git_dir: Path to the .git directory.
        work_tree: Path to the working tree.
        args: Git command arguments (without 'git' prefix).
        check: If True, raise CalledProcessError on failure.

    Returns:
        CompletedProcess instance.

    Raises:
        subprocess.CalledProcessError: If command fails and check=True.
            The error message includes stderr for easier debugging.
    """
    cmd = [
        "git",
        "--git-dir", str(git_dir),
        "--work-tree", str(work_tree),
        *args,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if check and result.returncode != 0:
        error_msg = f"Git command failed: {' '.join(cmd)}\nstderr: {result.stderr}"
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd,
            output=result.stdout,
            stderr=error_msg,
        )

    return result


def init_git_repo(path: Path) -> Path:
    """Initialize a git repo with initial commit for testing.

    Creates a minimal git repository with user config and an initial commit,
    suitable for tests that require git operations.

    Safety features:
    - Validates that path is not inside the actual repository root
    - Uses explicit --git-dir and --work-tree flags instead of cwd
    - Includes stderr in error messages for easier debugging

    Args:
        path: Directory to initialize as git repo. Must be outside the
            actual repository root (typically a tmp_path fixture).

    Returns:
        Path to the initialized git repository.

    Raises:
        ValueError: If path is inside the actual repository root.
        subprocess.CalledProcessError: If any git command fails.
    """
    # Safety check: Ensure we're not initializing a repo inside the actual repo
    try:
        repo_root = _get_repo_root()
        resolved_path = path.resolve()
        # Check if the path is inside the repo root
        try:
            resolved_path.relative_to(repo_root)
            raise ValueError(
                f"Cannot init git repo inside actual repository. "
                f"Path {resolved_path} is inside repo root {repo_root}. "
                f"Use tmp_path fixture for test repositories."
            )
        except ValueError as e:
            # ValueError from relative_to means path is NOT inside repo_root (good!)
            if "Cannot init git repo" in str(e):
                raise  # Re-raise our own ValueError
            # Otherwise, the path is outside the repo root, which is what we want
            pass
    except RuntimeError:
        # Not inside a git repository, so any path is safe
        pass

    # Initialize the repository using git init (special case - no existing .git dir)
    git_dir = path / ".git"
    init_cmd = ["git", "init", str(path)]
    result = subprocess.run(init_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            init_cmd,
            output=result.stdout,
            stderr=f"Git init failed: {result.stderr}",
        )

    # Configure user email
    _run_git_command(git_dir, path, ["config", "user.email", "test@test.com"])

    # Configure user name
    _run_git_command(git_dir, path, ["config", "user.name", "Test"])

    # Disable GPG signing
    _run_git_command(git_dir, path, ["config", "commit.gpgsign", "false"])

    # Create a README file
    (path / "README.md").write_text("# Test")

    # Stage all files
    _run_git_command(git_dir, path, ["add", "."])

    # Create initial commit
    _run_git_command(git_dir, path, ["commit", "-m", "Initial"])

    return path


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository for testing.

    This fixture creates a minimal git repository in a temporary directory
    with proper isolation from the actual repository.

    Returns:
        Path to the initialized git repository.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    return init_git_repo(repo_dir)


@pytest.fixture
def event_bus() -> EventBus:
    """Create EventBus instance for testing."""
    return EventBus()


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Return a temporary database path."""
    return tmp_path / "test.db"


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


def create_mock_execute_agentic(
    messages: list[AgenticMessage],
    capture_kwargs: list[dict[str, Any]] | None = None,
) -> Callable[..., AsyncGenerator[AgenticMessage, None]]:
    """Create a mock execute_agentic async generator function.

    This helper reduces boilerplate in tests that need to mock driver.execute_agentic().
    Each test can specify the AgenticMessage objects to yield.

    Args:
        messages: Sequence of AgenticMessage objects to yield.
        capture_kwargs: Optional list to capture kwargs passed to the mock.

    Returns:
        An async generator function that yields the provided messages.

    Example:
        mock_driver = MagicMock()
        mock_driver.execute_agentic = create_mock_execute_agentic([
            AgenticMessage(type=AgenticMessageType.THINKING, content="..."),
            AgenticMessage(type=AgenticMessageType.RESULT, content="Done"),
        ])

        # With kwargs capture:
        captured: list[dict[str, Any]] = []
        mock_driver.execute_agentic = create_mock_execute_agentic(messages, captured)
        # After calling mock: captured[0] contains the kwargs
    """
    async def mock_execute_agentic(
        *args: Any, **kwargs: Any
    ) -> AsyncGenerator[AgenticMessage, None]:
        if capture_kwargs is not None:
            capture_kwargs.append(kwargs)
        for msg in messages:
            yield msg

    return mock_execute_agentic


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


def make_agents_json(
    driver: DriverType = "cli",
    model: str = "sonnet",
    validator_model: str | None = None,
) -> str:
    """Create agents JSON blob for ProfileRecord.

    Helper function to create the agents JSON string needed by ProfileRecord.
    This centralizes the default agent configuration for tests.

    Args:
        driver: Default driver for all agents.
        model: Default model for all agents.
        validator_model: Model for validator agents (defaults to model).

    Returns:
        JSON string containing agents configuration.
    """
    import json
    effective_validator = validator_model or model
    agents = {
        "architect": {"driver": driver, "model": model, "options": {}},
        "developer": {"driver": driver, "model": model, "options": {}},
        "reviewer": {"driver": driver, "model": model, "options": {}},
        "plan_validator": {"driver": driver, "model": effective_validator, "options": {}},
        "evaluator": {"driver": driver, "model": model, "options": {}},
        "task_reviewer": {"driver": driver, "model": effective_validator, "options": {}},
    }
    return json.dumps(agents)


@pytest.fixture
def mock_profile_record_factory() -> Callable[..., ProfileRecord]:
    """Factory fixture for creating test ProfileRecord instances.

    ProfileRecord is the database-level model that stores agents as JSON.
    Use this fixture when testing database operations or routes.
    """
    def _create(
        id: str = "test",
        tracker: str = "noop",
        working_dir: str = "/tmp/test",
        driver: DriverType = "cli",
        model: str = "sonnet",
        validator_model: str | None = None,
        agents: str | None = None,
        is_active: bool = False,
        **kwargs: Any
    ) -> ProfileRecord:
        if agents is None:
            agents = make_agents_json(driver, model, validator_model)
        return ProfileRecord(
            id=id,
            tracker=tracker,
            working_dir=working_dir,
            agents=agents,
            is_active=is_active,
            **kwargs
        )
    return _create


@pytest.fixture
def mock_profile_factory(tmp_path_factory: TempPathFactory) -> Callable[..., Profile]:
    """Factory fixture for creating test Profile instances with presets.

    Uses tmp_path_factory to create a unique temp directory for working_dir,
    preventing tests from writing artifacts to the main codebase.

    Profiles now use agents dict for per-agent driver/model configuration.
    """
    # Create a shared temp directory for all profiles in this test session
    base_tmp = tmp_path_factory.mktemp("workdir")

    def _create(
        preset: str | None = None,
        name: str = "test",
        tracker: TrackerType = "noop",
        agents: dict[str, AgentConfig] | None = None,
        **kwargs: Any
    ) -> Profile:
        # Use temp directory for working_dir unless explicitly overridden
        if "working_dir" not in kwargs:
            kwargs["working_dir"] = str(base_tmp)

        # Default agents configuration if not provided
        if agents is None:
            if preset == "cli_single":
                agents = {
                    "architect": AgentConfig(driver="cli", model="sonnet"),
                    "developer": AgentConfig(driver="cli", model="sonnet"),
                    "reviewer": AgentConfig(driver="cli", model="sonnet"),
                }
                return Profile(name="test_cli", tracker="noop", agents=agents, **kwargs)
            elif preset == "api_single":
                agents = {
                    "architect": AgentConfig(driver="api", model="anthropic/claude-sonnet-4-20250514"),
                    "developer": AgentConfig(driver="api", model="anthropic/claude-sonnet-4-20250514"),
                    "reviewer": AgentConfig(driver="api", model="anthropic/claude-sonnet-4-20250514"),
                }
                return Profile(name="test_api", tracker="noop", agents=agents, **kwargs)
            else:
                # Default: all agents use cli
                agents = {
                    "architect": AgentConfig(driver="cli", model="sonnet"),
                    "developer": AgentConfig(driver="cli", model="sonnet"),
                    "reviewer": AgentConfig(driver="cli", model="sonnet"),
                }
        return Profile(name=name, tracker=tracker, agents=agents, **kwargs)
    return _create


@pytest.fixture
def mock_settings(mock_profile_factory: Callable[..., Profile]) -> Settings:
    """Create mock Settings instance with test profiles."""
    test_profile = mock_profile_factory(name="test", tracker="noop")
    work_profile = mock_profile_factory(name="work", tracker="jira")
    return Settings(
        active_profile="test",
        profiles={"test": test_profile, "work": work_profile}
    )


@pytest.fixture
def mock_execution_state_factory(
    mock_profile_factory: Callable[..., Profile],
    mock_issue_factory: Callable[..., Issue]
) -> Callable[..., tuple[ImplementationState, Profile]]:
    """Factory fixture for creating ImplementationState instances for agentic execution.

    Returns:
        Factory function that returns tuple[ImplementationState, Profile] where profile
        is the Profile object that was used to create the state.
    """
    from datetime import UTC, datetime  # noqa: PLC0415
    from uuid import uuid4  # noqa: PLC0415

    def _create(
        profile: Profile | None = None,
        profile_preset: str = "cli_single",
        issue: Issue | None = None,
        goal: str | None = None,
        code_changes_for_review: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        tool_results: list[ToolResult] | None = None,
        **kwargs: Any
    ) -> tuple[ImplementationState, Profile]:
        if profile is None:
            profile = mock_profile_factory(preset=profile_preset)
        if issue is None:
            issue = mock_issue_factory()

        # Extract profile_id from profile
        profile_id = kwargs.pop("profile_id", profile.name)

        # Provide defaults for required BasePipelineState fields
        workflow_id = kwargs.pop("workflow_id", str(uuid4()))
        created_at = kwargs.pop("created_at", datetime.now(UTC))
        status = kwargs.pop("status", "pending")

        state = ImplementationState(
            workflow_id=workflow_id,
            created_at=created_at,
            status=status,
            profile_id=profile_id,
            issue=issue,
            goal=goal,
            code_changes_for_review=code_changes_for_review,
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

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-api-key"}), \
         patch("amelia.drivers.api.deepagents.create_deep_agent") as mock_create_agent, \
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
