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


def _make_evaluation(*, count: int = 1) -> EvaluationResult:
    items = [
        EvaluatedItem(
            number=i,
            title=f"Item {i}",
            file_path="f.py",
            line=i * 10,
            disposition=Disposition.IMPLEMENT,
            reason="verified",
            original_issue=f"issue {i}",
            suggested_fix=f"fix {i}",
        )
        for i in range(1, count + 1)
    ]
    return EvaluationResult(summary="s", items_to_implement=items)


def _setup_mocks(
    state: Any,
    workflow_id: Any,
) -> tuple[MagicMock, MagicMock]:
    """Create Developer class mock and instance mock.

    Returns (MockDeveloperCls, mock_developer).
    """
    cls = MagicMock()
    dev = MagicMock()
    event = AgenticMessage(
        type=AgenticMessageType.RESULT, content="Done"
    ).to_workflow_event(workflow_id=workflow_id, agent="developer")
    dev.run = MagicMock(
        return_value=AsyncIteratorMock([
            (
                state.model_copy(update={
                    "agentic_status": "completed",
                    "tool_calls": [],
                    "tool_results": [],
                }),
                event,
            )
        ])
    )
    dev.driver = MagicMock()
    cls.return_value = dev
    return cls, dev


async def _run_node(
    state: Any,
    config: dict[str, Any],
    workflow_id: Any,
    *,
    resolve_commit: str | None = "abc123",
) -> tuple[dict[str, Any], MagicMock]:
    """Run call_review_developer_node with standard mocks.

    Returns (result_dict, mock_developer_instance).
    """
    cls, dev = _setup_mocks(state, workflow_id)
    with ExitStack() as stack:
        stack.enter_context(patch("amelia.pipelines.review.nodes.Developer", cls))
        stack.enter_context(patch("amelia.pipelines.review.nodes._save_token_usage", new_callable=AsyncMock))
        stack.enter_context(patch(
            "amelia.pipelines.review.nodes._resolve_commit",
            new_callable=AsyncMock,
            return_value=resolve_commit,
        ))
        result = await call_review_developer_node(state, cast(RunnableConfig, config))
    return result, dev


class TestCallReviewDeveloperNode:
    """Tests for the review-fix developer node."""

    @pytest.fixture
    def profile(self, mock_profile_factory: Any) -> Any:
        return mock_profile_factory(
            preset="cli_single",
            agents={"developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet")},
        )

    @pytest.fixture
    def state_and_config(
        self,
        profile: Any,
        mock_execution_state_factory: Any,
    ) -> tuple[Any, dict[str, Any], Any]:
        """Return (state, config_dict, workflow_id) with sensible defaults."""
        evaluation = _make_evaluation()
        goal = "Fix the following review items:\n\n- [f.py:10] Item 1"
        state, _ = mock_execution_state_factory(
            profile=profile,
            goal=goal,
            evaluation_result=evaluation,
            review_pass=0,
            status="running",
        )
        wf = uuid4()
        config: dict[str, Any] = {
            "configurable": {
                "profile": profile,
                "thread_id": wf,
                "prompts": {},
            }
        }
        return state, config, wf

    async def test_passes_review_fix_prompt_builder_and_instructions(
        self,
        state_and_config: tuple[Any, dict[str, Any], Any],
    ) -> None:
        """Developer.run receives build_review_fix_prompt and developer.review_fix instructions."""
        state, config, wf = state_and_config
        custom = "CUSTOM_REVIEW_FIX_SYSTEM"
        config["configurable"]["prompts"] = {"developer.review_fix": custom}

        result, dev = await _run_node(state, config, wf)

        dev.run.assert_called_once()
        _, kwargs = dev.run.call_args
        assert kwargs["prompt_builder"] is build_review_fix_prompt
        assert kwargs["instructions"] == custom

    async def test_uses_default_instructions_when_not_configured(
        self,
        state_and_config: tuple[Any, dict[str, Any], Any],
    ) -> None:
        """Falls back to PROMPT_DEFAULTS when developer.review_fix not in prompts."""
        state, config, wf = state_and_config

        _, dev = await _run_node(state, config, wf)

        expected = PROMPT_DEFAULTS["developer.review_fix"].content
        assert dev.run.call_args.kwargs["instructions"] == expected

    async def test_returns_correct_state_keys(
        self,
        state_and_config: tuple[Any, dict[str, Any], Any],
    ) -> None:
        """Result dict has expected keys and increments review_pass."""
        state, config, wf = state_and_config

        result, _ = await _run_node(state, config, wf)

        assert result["base_commit"] == "abc123"
        assert result["review_pass"] == 1
        assert result["agentic_status"] == "completed"
        assert "tool_calls" in result
        assert "tool_results" in result

    async def test_requires_goal(
        self,
        mock_execution_state_factory: Any,
        profile: Any,
    ) -> None:
        """Node raises when goal is missing."""
        evaluation = _make_evaluation()
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
