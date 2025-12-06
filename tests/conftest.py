import subprocess
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from typer.testing import CliRunner

from amelia.agents.reviewer import ReviewResponse
from amelia.core.state import ExecutionState, ReviewResult, Task, TaskDAG
from amelia.core.types import Design, Issue, Profile
from amelia.drivers.base import DriverInterface
from amelia.trackers.noop import NoopTracker


@pytest.fixture
def mock_issue_factory():
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
def mock_issue_proj_123(mock_issue_factory):
    return mock_issue_factory(
        id="PROJ-123",
        title="Implement user authentication feature",
        description="As a user, I want to log in and out securely. This involves creating a login endpoint, a user model, and integrating with an authentication system. Requires email/password fields.",
        status="open"
    )

@pytest.fixture
def mock_profile_factory():
    """Factory fixture for creating test Profile instances with presets."""
    def _create(
        preset: str | None = None,
        name: str = "test",
        driver: str = "cli:claude",
        tracker: str = "noop",
        strategy: str = "single",
        **kwargs
    ) -> Profile:
        if preset == "cli_single":
            return Profile(name="test_cli", driver="cli:claude", tracker="noop", strategy="single", **kwargs)
        elif preset == "api_single":
            return Profile(name="test_api", driver="api:openai", tracker="noop", strategy="single", **kwargs)
        elif preset == "api_competitive":
            return Profile(name="test_comp", driver="api:openai", tracker="noop", strategy="competitive", **kwargs)
        return Profile(name=name, driver=driver, tracker=tracker, strategy=strategy, **kwargs)
    return _create


@pytest.fixture
def mock_profile_work(mock_profile_factory):
    return mock_profile_factory(name="work", driver="cli:claude", tracker="jira", strategy="single")


@pytest.fixture
def mock_profile_home(mock_profile_factory):
    return mock_profile_factory(name="home", driver="api:openai", tracker="github", strategy="competitive")


@pytest.fixture
def mock_task_factory():
    """Factory fixture for creating test Task instances with sensible defaults."""
    def _create(
        id: str,
        description: str | None = None,
        status: str = "pending",
        dependencies: list[str] | None = None,
        files: list | None = None,
        steps: list | None = None,
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
def mock_task_dag_factory(mock_task_factory):
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
def mock_execution_state_factory(mock_profile_factory, mock_issue_factory):
    """Factory fixture for creating ExecutionState instances."""
    def _create(
        profile: Profile | None = None,
        profile_preset: str = "cli_single",
        issue: Issue | None = None,
        plan: TaskDAG | None = None,
        code_changes_for_review: str | None = None,
        **kwargs
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
            **kwargs
        )
    return _create


@pytest.fixture
def mock_noop_tracker():
    return NoopTracker()

@pytest.fixture
def mock_driver():
    """Returns a mock driver that implements DriverInterface."""
    mock = MagicMock(spec=DriverInterface)
    mock.generate = AsyncMock(return_value="mocked AI response")
    mock.execute_tool = AsyncMock(return_value="mocked tool output")
    return mock


@pytest.fixture
def mock_async_driver_factory():
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
def mock_review_response_factory():
    """Factory fixture for creating ReviewResponse instances."""
    def _create(
        approved: bool = True,
        comments: list[str] | None = None,
        severity: str = "low",
    ) -> ReviewResponse:
        return ReviewResponse(
            approved=approved,
            comments=comments or (["Looks good"] if approved else ["Needs changes"]),
            severity=severity
        )
    return _create


@pytest.fixture
def mock_review_result_factory():
    """Factory fixture for creating ReviewResult instances."""
    def _create(
        approved: bool = True,
        comments: list[str] | None = None,
        severity: str = "low",
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
def mock_design_factory():
    """Factory fixture for creating Design instances."""
    def _create(
        title: str = "Test Feature",
        goal: str = "Build test feature",
        architecture: str = "Simple architecture",
        tech_stack: list[str] | None = None,
        components: list[str] | None = None,
        raw_content: str = "",
        **kwargs
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
def mock_subprocess_process_factory():
    """
    Factory fixture for creating mock subprocess processes.

    Returns a callable that creates a mock process with configurable:
    - stdout_lines: List of bytes for stdout.readline() responses
    - stderr_output: Bytes for stderr.read() response
    - return_code: Process return code

    Example usage:
        def test_example(mock_subprocess_process_factory):
            mock_process = mock_subprocess_process_factory(
                stdout_lines=[b"output line\\n", b""],
                stderr_output=b"",
                return_code=0
            )
    """
    def _create_mock_process(
        stdout_lines: list[bytes] = None,
        stderr_output: bytes = b"",
        return_code: int = 0
    ):
        if stdout_lines is None:
            stdout_lines = [b""]

        mock_process = AsyncMock()
        # stdin: write() and close() are sync, drain() is async
        mock_process.stdin = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        # stdout.readline() returns bytes sequentially
        mock_process.stdout.readline = AsyncMock(side_effect=stdout_lines)
        # stderr.read() returns all stderr at once
        mock_process.stderr.read = AsyncMock(return_value=stderr_output)
        mock_process.returncode = return_code
        mock_process.wait = AsyncMock(return_value=return_code)
        return mock_process

    return _create_mock_process


@pytest.fixture
def settings_file_factory(tmp_path):
    """Factory for creating settings.amelia.yaml files."""
    def _create(settings_data):
        path = tmp_path / "settings.amelia.yaml"
        with open(path, "w") as f:
            yaml.dump(settings_data, f)
        return path
    return _create


@pytest.fixture
def git_repo_with_changes(tmp_path):
    """Create a git repo with initial commit and unstaged changes."""
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)

    # Create initial file and commit
    (tmp_path / "file.txt").write_text("initial")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)

    # Create unstaged changes
    (tmp_path / "file.txt").write_text("modified")

    return tmp_path


@pytest.fixture
def cli_runner():
    """Typer CLI test runner for command testing."""
    return CliRunner()
