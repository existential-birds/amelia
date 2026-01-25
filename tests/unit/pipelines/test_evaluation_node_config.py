"""Tests for call_evaluation_node using profile.get_agent_config."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.agents.evaluator import EvaluationResult
from amelia.core.types import AgentConfig, Issue, Profile
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.review.nodes import call_evaluation_node


@pytest.fixture
def profile_with_agents():
    return Profile(
        name="test",
        tracker="none",
        working_dir="/tmp/test",
        agents={
            "evaluator": AgentConfig(driver="cli", model="sonnet"),
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
    )


@pytest.mark.asyncio
async def test_call_evaluation_node_uses_agent_config(profile_with_agents, mock_state):
    """call_evaluation_node should use profile.get_agent_config('evaluator')."""
    config = {
        "configurable": {
            "profile": profile_with_agents,
            "thread_id": "wf-1",
        }
    }

    mock_eval_result = EvaluationResult(
        items_to_implement=[],
        items_rejected=[],
        items_deferred=[],
        summary="No issues found",
    )

    with patch("amelia.pipelines.review.nodes.Evaluator") as MockEvaluator:
        mock_evaluator = MagicMock()
        mock_evaluator.evaluate = AsyncMock(return_value=(mock_eval_result, "session-1"))
        mock_evaluator.driver = MagicMock()
        MockEvaluator.return_value = mock_evaluator

        with patch("amelia.pipelines.review.nodes._save_token_usage", new_callable=AsyncMock):
            await call_evaluation_node(mock_state, config)

        # Verify Evaluator was instantiated with AgentConfig
        call_args = MockEvaluator.call_args
        assert call_args is not None
        config_arg = call_args.kwargs.get("config") or call_args[1].get("config")
        if config_arg is None:
            config_arg = call_args[0][0]  # First positional
        assert isinstance(config_arg, AgentConfig)
        assert config_arg.model == "sonnet"
