# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
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

from amelia.agents.reviewer import ReviewResponse
from amelia.core.state import (
    ExecutionBatch,
    ExecutionPlan,
    ExecutionState,
    PlanStep,
    ReviewResult,
    Severity,
)
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

    Uses tmp_path_factory to create a unique temp directory for plan_output_dir,
    preventing tests from writing artifacts to docs/plans/.
    """
    # Create a shared temp directory for all profiles in this test session
    base_tmp = tmp_path_factory.mktemp("plans")

    def _create(
        preset: str | None = None,
        name: str = "test",
        driver: DriverType = "cli:claude",
        tracker: TrackerType = "noop",
        strategy: StrategyType = "single",
        **kwargs: Any
    ) -> Profile:
        # Use temp directory for plan_output_dir unless explicitly overridden
        if "plan_output_dir" not in kwargs:
            kwargs["plan_output_dir"] = str(base_tmp)

        if preset == "cli_single":
            return Profile(name="test_cli", driver="cli:claude", tracker="noop", strategy="single", **kwargs)
        elif preset == "api_single":
            return Profile(name="test_api", driver="api:openai", tracker="noop", strategy="single", **kwargs)
        elif preset == "api_competitive":
            return Profile(name="test_comp", driver="api:openai", tracker="noop", strategy="competitive", **kwargs)
        return Profile(name=name, driver=driver, tracker=tracker, strategy=strategy, **kwargs)
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
def mock_execution_plan_factory() -> Callable[..., ExecutionPlan]:
    """Factory fixture for creating test ExecutionPlan instances."""
    def _create(
        goal: str = "Test goal",
        num_batches: int = 1,
        steps_per_batch: int = 1,
        risk_levels: list[str] | None = None,
        tdd_approach: bool = True,
    ) -> ExecutionPlan:
        if risk_levels is None:
            risk_levels = ["low"] * num_batches

        batches = []
        step_id = 1
        for batch_num in range(1, num_batches + 1):
            steps = []
            risk = risk_levels[batch_num - 1] if batch_num <= len(risk_levels) else "low"
            for _ in range(steps_per_batch):
                steps.append(PlanStep(
                    id=f"step-{step_id}",
                    description=f"Test step {step_id}",
                    action_type="command",
                    command=f"echo step-{step_id}",
                    risk_level=risk,
                ))
                step_id += 1
            batches.append(ExecutionBatch(
                batch_number=batch_num,
                steps=tuple(steps),
                risk_summary=risk,
                description=f"Test batch {batch_num}",
            ))
        return ExecutionPlan(
            goal=goal,
            batches=tuple(batches),
            total_estimated_minutes=num_batches * steps_per_batch * 2,
            tdd_approach=tdd_approach,
        )
    return _create


@pytest.fixture
def mock_execution_state_factory(mock_profile_factory: Callable[..., Profile], mock_issue_factory: Callable[..., Issue]) -> Callable[..., tuple[ExecutionState, Profile]]:
    """Factory fixture for creating ExecutionState instances.

    Returns:
        Factory function that returns tuple[ExecutionState, Profile] where profile
        is the Profile object that was used to create the state.
    """
    def _create(
        profile: Profile | None = None,
        profile_preset: str = "cli_single",
        issue: Issue | None = None,
        execution_plan: ExecutionPlan | None = None,
        code_changes_for_review: str | None = None,
        design: Design | None = None,
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
            execution_plan=execution_plan,
            code_changes_for_review=code_changes_for_review,
            design=design,
            **kwargs
        )
        return state, profile
    return _create


@pytest.fixture
def mock_config_factory(mock_profile_factory: Callable[..., Profile]) -> Callable[..., dict[str, Any]]:
    """Factory fixture for creating LangGraph config with configurable profile.

    Creates a config dict with profile in config["configurable"]["profile"]
    as expected by the orchestrator nodes after the profile_id refactor.
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
    mock.generate = AsyncMock(return_value="mocked AI response")
    mock.execute_tool = AsyncMock(return_value="mocked tool output")
    return mock


@pytest.fixture
def mock_async_driver_factory() -> Callable[..., AsyncMock]:
    """Factory fixture for creating mock DriverInterface instances."""
    def _create(
        generate_return: Any = "mocked AI response",
        execute_tool_return: Any = "mocked tool output",
    ) -> AsyncMock:
        mock = AsyncMock(spec=DriverInterface)
        mock.generate = AsyncMock(return_value=generate_return)
        mock.execute_tool = AsyncMock(return_value=execute_tool_return)
        return mock
    return _create


@pytest.fixture
def mock_review_response_factory() -> Callable[..., ReviewResponse]:
    """Factory fixture for creating ReviewResponse instances."""
    def _create(
        approved: bool = True,
        comments: list[str] | None = None,
        severity: Severity = "low",
    ) -> ReviewResponse:
        return ReviewResponse(
            approved=approved,
            comments=comments or (["Looks good"] if approved else ["Needs changes"]),
            severity=severity
        )
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
    """
    Factory fixture for creating mock subprocess processes.

    Returns a callable that creates a mock process with configurable:
    - stdout_lines: List of bytes for stdout (joined with newlines for read())
    - stderr_output: Bytes for stderr.read() response
    - return_code: Process return code

    Example usage:
        def test_example(mock_subprocess_process_factory):
            mock_process = mock_subprocess_process_factory(
                stdout_lines=[b"output line", b"another line"],
                stderr_output=b"",
                return_code=0
            )

    Note: The Claude CLI driver uses chunked reading via read() instead of readline().
    This fixture joins stdout_lines with newlines and returns them via read().
    """
    def _create_mock_process(
        stdout_lines: list[bytes] | None = None,
        stderr_output: bytes = b"",
        return_code: int = 0
    ) -> AsyncMock:
        if stdout_lines is None:
            stdout_lines = [b""]

        # Join lines with newlines to simulate what Claude CLI outputs
        # Filter out empty trailing bytes (used to signal end of readline())
        filtered_lines = [line for line in stdout_lines if line]
        stdout_data = b"\n".join(filtered_lines)

        # Track position in stdout data for read()
        read_position = [0]

        async def mock_read(n: int = -1) -> bytes:
            """Simulate read() by returning data in chunks."""
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
        # stdin: write() and close() are sync, drain() is async
        mock_process.stdin = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        # stdout.read() returns data in chunks (for chunked line reading)
        mock_process.stdout.read = mock_read
        # stderr.read() returns all stderr at once
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
    """Create a git repo with initial commit and unstaged changes.

    Uses environment variables for git identity and clears git hook
    environment variables to ensure isolation from any parent git context
    (e.g., when running inside a pre-push hook).
    """
    # Start with current environment and set identity
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@test.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@test.com",
    }

    # Remove git environment variables that might be set by hooks and would
    # cause git to use the wrong repository (e.g., GIT_DIR from pre-push hook)
    for var in ["GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_QUARANTINE_PATH"]:
        git_env.pop(var, None)

    # Initialize git repo (also needs clean env to avoid using parent repo)
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True, env=git_env)

    # Create initial file and commit
    (tmp_path / "file.txt").write_text("initial")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, env=git_env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, env=git_env)

    # Create unstaged changes
    (tmp_path / "file.txt").write_text("modified")

    return tmp_path


@pytest.fixture
def cli_runner() -> CliRunner:
    """Typer CLI test runner for command testing."""
    return CliRunner()


@pytest.fixture
def reviewer_state_with_plan(
    mock_execution_state_factory: Callable[..., ExecutionState],
    mock_execution_plan_factory: Callable[..., ExecutionPlan],
) -> Callable[..., ExecutionState]:
    """Factory fixture for creating ExecutionState for reviewer tests.

    Returns a callable that creates state with:
    - An ExecutionPlan with a single batch
    - Customizable issue, workflow_id, profile via kwargs
    """
    def _create(**kwargs: Any) -> ExecutionState:
        # Remove current_task_id if present (legacy parameter no longer used)
        kwargs.pop("current_task_id", None)
        if "execution_plan" not in kwargs:
            kwargs["execution_plan"] = mock_execution_plan_factory()
        return mock_execution_state_factory(**kwargs)
    return _create


@pytest.fixture
def developer_test_context(
    mock_execution_plan_factory: Callable[..., ExecutionPlan],
    mock_execution_state_factory: Callable[..., ExecutionState]
) -> Callable[..., tuple[AsyncMock, ExecutionState]]:
    """Factory fixture for creating Developer test contexts with mock driver and state.

    Returns a callable that creates a tuple of (mock_driver, state) with configurable:
    - step_desc: Step description (default: "Test step")
    - driver_return: Return value for driver.execute_tool (default: "output")
    - driver_side_effect: Side effect for driver.execute_tool (overrides driver_return if set)

    Example usage:
        def test_example(developer_test_context):
            mock_driver, state = developer_test_context(
                step_desc="Run shell command: echo hello",
                driver_return="Command output"
            )
            developer = Developer(driver=mock_driver)
            result = await developer.run(state)
    """
    def _create(
        step_desc: str = "Test step",
        driver_return: Any = "output",
        driver_side_effect: Any = None
    ) -> tuple[AsyncMock, ExecutionState]:
        mock_driver = AsyncMock(spec=DriverInterface)
        if driver_side_effect:
            mock_driver.execute_tool.side_effect = driver_side_effect
        else:
            mock_driver.execute_tool.return_value = driver_return
        # Create execution plan with single step
        step = PlanStep(
            id="step-1",
            description=step_desc,
            action_type="command",
            command="echo test",
        )
        batch = ExecutionBatch(
            batch_number=1,
            steps=(step,),
            risk_summary="low",
            description="Test batch",
        )
        execution_plan = ExecutionPlan(
            goal="Test goal",
            batches=(batch,),
            total_estimated_minutes=5,
            tdd_approach=True,
        )
        state = mock_execution_state_factory(execution_plan=execution_plan)
        return mock_driver, state
    return _create


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


class LangGraphMocks(NamedTuple):
    """Container for LangGraph mock objects.

    Attributes:
        graph: Mock CompiledStateGraph with aupdate_state, astream, aget_state.
        saver: Mock AsyncSqliteSaver instance.
        saver_class: Mock AsyncSqliteSaver class (for patching).
        create_graph: Mock create_orchestrator_graph function.
    """

    graph: MagicMock
    saver: AsyncMock
    saver_class: MagicMock
    create_graph: MagicMock


@pytest.fixture
def langgraph_mock_factory(
    async_iterator_mock_factory: Callable[[list[Any]], AsyncIteratorMock],
) -> Callable[..., LangGraphMocks]:
    """Factory fixture for creating LangGraph mock objects.

    Creates properly configured mocks for:
    - AsyncSqliteSaver (as async context manager)
    - create_orchestrator_graph (returns mock graph)
    - CompiledStateGraph (with aupdate_state, astream, aget_state)

    Args:
        astream_items: Items for the mock astream iterator. Defaults to [].
        aget_state_return: Return value for aget_state. Defaults to empty state.

    Returns:
        LangGraphMocks NamedTuple with all configured mocks.

    Example:
        def test_example(langgraph_mock_factory):
            mocks = langgraph_mock_factory(
                astream_items=[{"node": "data"}, {"__interrupt__": ("pause",)}]
            )
            # Use mocks.graph, mocks.saver_class in your test
    """

    def _create(
        astream_items: list[Any] | None = None,
        aget_state_return: Any = None,
    ) -> LangGraphMocks:
        if astream_items is None:
            astream_items = []
        if aget_state_return is None:
            aget_state_return = MagicMock(values={}, next=[])

        # Create mock graph with all required methods
        mock_graph = MagicMock()
        mock_graph.aupdate_state = AsyncMock()
        mock_graph.aget_state = AsyncMock(return_value=aget_state_return)
        # astream returns iterator directly (not wrapped in AsyncMock)
        mock_graph.astream = lambda *args, **kwargs: async_iterator_mock_factory(
            astream_items
        )

        # Create mock saver as async context manager
        mock_saver = AsyncMock()
        mock_saver_class = MagicMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        # Create mock create_graph that returns our graph
        mock_create_graph = MagicMock(return_value=mock_graph)

        return LangGraphMocks(
            graph=mock_graph,
            saver=mock_saver,
            saver_class=mock_saver_class,
            create_graph=mock_create_graph,
        )

    return _create
