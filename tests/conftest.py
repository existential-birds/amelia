# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import os
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from pytest import TempPathFactory
from typer.testing import CliRunner

from amelia.agents.reviewer import ReviewResponse
from amelia.core.context import CompiledContext, ContextSection
from amelia.core.state import ExecutionState, ReviewResult, Severity, Task, TaskDAG, TaskStatus
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
from amelia.trackers.noop import NoopTracker


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
def mock_issue_proj_123(mock_issue_factory: Callable[..., Issue]) -> Issue:
    return mock_issue_factory(
        id="PROJ-123",
        title="Implement user authentication feature",
        description="As a user, I want to log in and out securely. This involves creating a login endpoint, a user model, and integrating with an authentication system. Requires email/password fields.",
        status="open"
    )

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
def mock_profile_work(mock_profile_factory: Callable[..., Profile]) -> Profile:
    return mock_profile_factory(name="work", driver="cli:claude", tracker="jira", strategy="single")


@pytest.fixture
def mock_profile_home(mock_profile_factory: Callable[..., Profile]) -> Profile:
    return mock_profile_factory(name="home", driver="api:openai", tracker="github", strategy="competitive")


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
def mock_task_factory() -> Callable[..., Task]:
    """Factory fixture for creating test Task instances with sensible defaults."""
    def _create(
        id: str,
        description: str | None = None,
        status: TaskStatus = "pending",
        dependencies: list[str] | None = None,
        files: list[Any] | None = None,
        steps: list[Any] | None = None,
        commit_message: str | None = None
    ) -> Task:
        return Task(
            id=id,
            description=description or f"Task {id}",
            status=status,
            dependencies=dependencies or [],
            files=files or [],
            steps=steps or [],
            commit_message=commit_message
        )
    return _create


@pytest.fixture
def mock_task_dag_factory(mock_task_factory: Callable[..., Task]) -> Callable[..., TaskDAG]:
    """Factory fixture for creating test TaskDAG instances."""
    def _create(
        tasks: list[Task] | None = None,
        num_tasks: int = 1,
        original_issue: str = "TEST-123",
        linear: bool = True
    ) -> TaskDAG:
        if tasks is None:
            tasks = []
            for i in range(1, num_tasks + 1):
                deps = [str(i-1)] if linear and i > 1 else []
                tasks.append(mock_task_factory(id=str(i), dependencies=deps))
        return TaskDAG(tasks=tasks, original_issue=original_issue)
    return _create


@pytest.fixture
def mock_execution_state_factory(mock_profile_factory: Callable[..., Profile], mock_issue_factory: Callable[..., Issue]) -> Callable[..., ExecutionState]:
    """Factory fixture for creating ExecutionState instances."""
    def _create(
        profile: Profile | None = None,
        profile_preset: str = "cli_single",
        issue: Issue | None = None,
        plan: TaskDAG | None = None,
        code_changes_for_review: str | None = None,
        design: Design | None = None,
        **kwargs: Any
    ) -> ExecutionState:
        if profile is None:
            profile = mock_profile_factory(preset=profile_preset)
        if issue is None:
            issue = mock_issue_factory()
        return ExecutionState(
            profile=profile,
            issue=issue,
            plan=plan,
            code_changes_for_review=code_changes_for_review,
            design=design,
            **kwargs
        )
    return _create


@pytest.fixture
def mock_noop_tracker() -> NoopTracker:
    return NoopTracker()

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
def section_helper() -> Any:
    """Helper for extracting and validating context sections.

    Provides utility methods for working with CompiledContext sections:
    - get(context, name): Extract a section by name, returns None if not found
    - get_names(context): Get set of all section names
    - assert_has(context, *names): Assert context has all specified sections
    - assert_missing(context, *names): Assert context doesn't have specified sections

    Example usage:
        def test_example(section_helper):
            context = strategy.compile(state)
            task_section = section_helper.get(context, "task")
            assert task_section is not None

            section_helper.assert_has(context, "task", "files")
            section_helper.assert_missing(context, "issue")
    """
    class SectionHelper:
        @staticmethod
        def get(context: CompiledContext, name: str) -> ContextSection | None:
            """Get section by name, returns None if not found."""
            return next((s for s in context.sections if s.name == name), None)

        @staticmethod
        def get_names(context: CompiledContext) -> set[str]:
            """Get set of all section names."""
            return {s.name for s in context.sections}

        @staticmethod
        def assert_has(context: CompiledContext, *names: str) -> None:
            """Assert context has all specified sections."""
            actual = {s.name for s in context.sections}
            for name in names:
                assert name in actual, f"Expected section '{name}' not found. Available: {actual}"

        @staticmethod
        def assert_missing(context: CompiledContext, *names: str) -> None:
            """Assert context doesn't have specified sections."""
            actual = {s.name for s in context.sections}
            for name in names:
                assert name not in actual, f"Section '{name}' should not be present. Found: {actual}"

    return SectionHelper()


@pytest.fixture
def reviewer_state_with_task(
    mock_execution_state_factory: Callable[..., ExecutionState],
    mock_task_factory: Callable[..., Task],
) -> Callable[..., ExecutionState]:
    """Factory fixture for creating ExecutionState with a task and TaskDAG for reviewer tests.

    Returns a callable that creates state with:
    - A single task with id="1"
    - A TaskDAG containing that task
    - Customizable issue, workflow_id, profile via kwargs
    """
    def _create(**kwargs: Any) -> ExecutionState:
        state = mock_execution_state_factory(**kwargs)
        task = mock_task_factory(id="1", description="Test task")
        state.plan = TaskDAG(tasks=[task], original_issue="TEST-123")
        return state
    return _create


@pytest.fixture
def developer_test_context(mock_task_factory: Callable[..., Task], mock_execution_state_factory: Callable[..., ExecutionState]) -> Callable[..., tuple[AsyncMock, ExecutionState]]:
    """Factory fixture for creating Developer test contexts with mock driver and state.

    Returns a callable that creates a tuple of (mock_driver, state) with configurable:
    - task_desc: Task description (default: "Test task")
    - driver_return: Return value for driver.execute_tool (default: "output")
    - driver_side_effect: Side effect for driver.execute_tool (overrides driver_return if set)

    Example usage:
        def test_example(developer_test_context):
            mock_driver, state = developer_test_context(
                task_desc="Run shell command: echo hello",
                driver_return="Command output"
            )
            developer = Developer(driver=mock_driver)
            result = await developer.execute_current_task(state, workflow_id="test-workflow")
    """
    def _create(task_desc: str = "Test task", driver_return: Any = "output", driver_side_effect: Any = None) -> tuple[AsyncMock, ExecutionState]:
        mock_driver = AsyncMock(spec=DriverInterface)
        if driver_side_effect:
            mock_driver.execute_tool.side_effect = driver_side_effect
        else:
            mock_driver.execute_tool.return_value = driver_return
        task = mock_task_factory(id="1", description=task_desc)
        state = mock_execution_state_factory(
            plan=TaskDAG(tasks=[task], original_issue="Test"),
            current_task_id=task.id
        )
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
