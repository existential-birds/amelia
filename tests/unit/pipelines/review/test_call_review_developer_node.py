"""Unit tests for call_review_developer_node."""

from contextlib import ExitStack
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.agents.schemas.evaluator import Disposition, EvaluatedItem, EvaluationResult
from amelia.core.types import AgentConfig, DriverType
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.review.developer_prompt import build_review_fix_prompt
from amelia.pipelines.review.nodes import call_review_developer_node
from tests.conftest import AsyncIteratorMock


@pytest.mark.asyncio
async def test_call_review_developer_node_uses_review_fix_prompt_builder_and_instructions(
    mock_execution_state_factory: Any,
    mock_profile_factory: Any,
) -> None:
    """Developer.run receives build_review_fix_prompt and developer.review_fix instructions."""
    profile = mock_profile_factory(
        preset="cli_single",
        agents={"developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet")},
    )
    item = EvaluatedItem(
        number=1,
        title="T",
        file_path="f.py",
        line=1,
        disposition=Disposition.IMPLEMENT,
        reason="r",
        original_issue="i",
        suggested_fix="s",
    )
    evaluation = EvaluationResult(summary="s", items_to_implement=[item])
    goal = "Fix the following review items:\n\n- line"
    state, _ = mock_execution_state_factory(
        profile=profile,
        goal=goal,
        evaluation_result=evaluation,
        review_pass=0,
        status="running",
    )
    custom_review_fix = "CUSTOM_REVIEW_FIX_SYSTEM"
    workflow_uuid = uuid4()
    config: dict[str, Any] = {
        "configurable": {
            "profile": profile,
            "thread_id": workflow_uuid,
            "prompts": {"developer.review_fix": custom_review_fix},
        }
    }

    MockDeveloperCls = MagicMock()
    mock_developer = MagicMock()
    event = AgenticMessage(
        type=AgenticMessageType.RESULT,
        content="Done",
    ).to_workflow_event(workflow_id=workflow_uuid, agent="developer")
    mock_developer.run = MagicMock(
        return_value=AsyncIteratorMock([
            (
                state.model_copy(
                    update={
                        "agentic_status": "completed",
                        "tool_calls": [],
                        "tool_results": [],
                    }
                ),
                event,
            )
        ])
    )
    mock_developer.driver = MagicMock()
    MockDeveloperCls.return_value = mock_developer

    with ExitStack() as stack:
        stack.enter_context(patch("amelia.pipelines.review.nodes.Developer", MockDeveloperCls))
        stack.enter_context(patch("amelia.pipelines.review.nodes._save_token_usage", new_callable=AsyncMock))
        stack.enter_context(
            patch(
                "amelia.pipelines.review.nodes._resolve_commit",
                new_callable=AsyncMock,
                return_value="abc123",
            )
        )
        result = await call_review_developer_node(state, cast(RunnableConfig, config))

    mock_developer.run.assert_called_once()
    pos, kwargs = mock_developer.run.call_args
    assert pos[2] == workflow_uuid
    assert kwargs["prompt_builder"] is build_review_fix_prompt
    assert kwargs["instructions"] == custom_review_fix

    assert result["base_commit"] == "abc123"
    assert result["review_pass"] == 1
    assert result["agentic_status"] == "completed"


@pytest.mark.asyncio
async def test_call_review_developer_node_default_review_fix_instructions(
    mock_execution_state_factory: Any,
    mock_profile_factory: Any,
) -> None:
    """When developer.review_fix is not in config, use PROMPT_DEFAULTS content."""
    profile = mock_profile_factory(
        preset="cli_single",
        agents={"developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet")},
    )
    evaluation = EvaluationResult(
        summary="s",
        items_to_implement=[
            EvaluatedItem(
                number=1,
                title="T",
                file_path="f.py",
                line=1,
                disposition=Disposition.IMPLEMENT,
                reason="r",
                original_issue="i",
                suggested_fix="s",
            )
        ],
    )
    state, _ = mock_execution_state_factory(
        profile=profile,
        goal="g",
        evaluation_result=evaluation,
        status="running",
    )
    workflow_uuid = uuid4()
    config: dict[str, Any] = {
        "configurable": {
            "profile": profile,
            "thread_id": workflow_uuid,
            "prompts": {},
        }
    }

    MockDeveloperCls = MagicMock()
    mock_developer = MagicMock()
    event = AgenticMessage(
        type=AgenticMessageType.RESULT,
        content="x",
    ).to_workflow_event(workflow_id=workflow_uuid, agent="developer")
    mock_developer.run = MagicMock(
        return_value=AsyncIteratorMock([
            (state.model_copy(update={"agentic_status": "completed"}), event),
        ])
    )
    mock_developer.driver = MagicMock()
    MockDeveloperCls.return_value = mock_developer

    with ExitStack() as stack:
        stack.enter_context(patch("amelia.pipelines.review.nodes.Developer", MockDeveloperCls))
        stack.enter_context(patch("amelia.pipelines.review.nodes._save_token_usage", new_callable=AsyncMock))
        stack.enter_context(
            patch(
                "amelia.pipelines.review.nodes._resolve_commit",
                new_callable=AsyncMock,
                return_value=None,
            )
        )
        await call_review_developer_node(state, cast(RunnableConfig, config))

    expected = PROMPT_DEFAULTS["developer.review_fix"].content
    assert mock_developer.run.call_args.kwargs["instructions"] == expected


@pytest.mark.asyncio
async def test_call_review_developer_node_requires_goal(
    mock_execution_state_factory: Any,
    mock_profile_factory: Any,
) -> None:
    """Node raises when goal is missing."""
    profile = mock_profile_factory(
        preset="cli_single",
        agents={"developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet")},
    )
    evaluation = EvaluationResult(
        summary="s",
        items_to_implement=[
            EvaluatedItem(
                number=1,
                title="T",
                file_path="f.py",
                line=1,
                disposition=Disposition.IMPLEMENT,
                reason="r",
                original_issue="i",
                suggested_fix="s",
            )
        ],
    )
    state, _ = mock_execution_state_factory(
        profile=profile,
        goal=None,
        evaluation_result=evaluation,
        status="running",
    )
    config: dict[str, Any] = {
        "configurable": {
            "profile": profile,
            "thread_id": uuid4(),
        }
    }

    with pytest.raises(ValueError, match="goal"):
        await call_review_developer_node(state, cast(RunnableConfig, config))
