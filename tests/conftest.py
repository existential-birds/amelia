import pytest
from amelia.core.types import Issue, Profile
from amelia.drivers.base import DriverInterface
from amelia.trackers.noop import NoopTracker
from unittest.mock import AsyncMock, MagicMock

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
