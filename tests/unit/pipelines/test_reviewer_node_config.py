from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import AgentConfig, Issue, Profile, ReviewResult
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.nodes import call_reviewer_node


@pytest.fixture
def profile_with_agents():
    return Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "reviewer": AgentConfig(driver="cli", model="opus", options={"max_iterations": 3}),
            "task_reviewer": AgentConfig(driver="cli", model="sonnet", options={"max_iterations": 5}),
        },
    )


@pytest.fixture
def mock_state():
    return ImplementationState(
        workflow_id="wf-1",
        profile_id="test",
        created_at=datetime.now(UTC),
        status="running",
        issue=Issue(id="TEST-1", title="Test", description="Test issue"),
        goal="Implement test feature",
        base_commit="abc123",
    )


@pytest.mark.asyncio
async def test_call_reviewer_node_uses_agent_config(profile_with_agents, mock_state):
    """call_reviewer_node should use profile.get_agent_config('reviewer')."""
    config = {
        "configurable": {
            "profile": profile_with_agents,
            "thread_id": "wf-1",
        }
    }

    mock_review_result = ReviewResult(
        severity="none",
        approved=True,
        comments=[],
        reviewer_persona="Senior Engineer",
    )

    with patch("amelia.pipelines.nodes.Reviewer") as MockReviewer:
        mock_reviewer = MagicMock()
        mock_reviewer.agentic_review = AsyncMock(return_value=(mock_review_result, "session-1"))
        mock_reviewer.driver = MagicMock()
        MockReviewer.return_value = mock_reviewer

        with patch("amelia.pipelines.nodes._save_token_usage", new_callable=AsyncMock):
            await call_reviewer_node(mock_state, config)

        # Verify Reviewer was instantiated with AgentConfig
        call_args = MockReviewer.call_args
        assert call_args is not None
        config_arg = call_args[0][0]  # First positional arg
        assert isinstance(config_arg, AgentConfig)
        assert config_arg.driver == "cli"
        assert config_arg.model == "opus"  # reviewer, not task_reviewer
