from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from amelia.core.types import Issue
from amelia.core.types import Profile
from amelia.drivers.base import DriverInterface
from amelia.trackers.noop import NoopTracker


@pytest.fixture
def mock_issue_proj_123():
    return Issue(
        id="PROJ-123",
        title="Implement user authentication feature",
        description="As a user, I want to log in and out securely. This involves creating a login endpoint, a user model, and integrating with an authentication system. Requires email/password fields.",
        status="open"
    )

@pytest.fixture
def mock_profile_work():
    return Profile(name="work", driver="cli:claude", tracker="jira", strategy="single")

@pytest.fixture
def mock_profile_home():
    return Profile(name="home", driver="api:openai", tracker="github", strategy="competitive")

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
