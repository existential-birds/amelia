"""Tests for the Aggregator agent's prompt default and tool profile.

The Aggregator synthesizes one canonical plan from N candidate plans and
writes it via the ``write_plan`` tool, mirroring the Architect's profile.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from amelia.agents.aggregator import Aggregator
from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
from amelia.agents.tool_profiles import resolve_agent_tools
from amelia.core.constants import resolve_plan_path
from amelia.core.types import AgentConfig, Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.tools.registry import ToolContext
from amelia.tools.registry.registry import discover_builtin_tools


def test_aggregator_prompt_default_exists_and_is_non_empty() -> None:
    default = PROMPT_DEFAULTS["aggregator.system"]
    assert default.content.strip()


def test_resolve_agent_tools_aggregator_includes_write_plan() -> None:
    discover_builtin_tools()
    ctx = ToolContext(cwd="/tmp")
    tools = resolve_agent_tools("aggregator", ctx)
    names = {t.name for t in tools}
    assert tools
    assert "write_plan" in names


class TestAggregatorAggregate:
    """Behavioral tests for Aggregator.aggregate()."""

    async def test_aggregate_synthesizes_plan_from_candidates(
        self,
        mock_profile_factory: Any,
    ) -> None:
        """aggregate() enumerates candidates, drives write_plan, yields plan_path."""
        discover_builtin_tools()
        config = AgentConfig(driver="claude", model="sonnet")
        profile: Profile = mock_profile_factory()
        issue_id = "TEST-42"
        canonical = Path(resolve_plan_path(profile.plan_path_pattern, issue_id))

        captured: dict[str, Any] = {}

        async def capture_execute(*args: Any, **kwargs: Any) -> AsyncIterator[AgenticMessage]:
            captured.update(kwargs)
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="write_plan",
                tool_input={"file_path": str(canonical), "goal": "Synthesized"},
                tool_call_id="call-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="write_plan",
                tool_output="Successfully wrote plan",
                tool_call_id="call-1",
            )
            yield AgenticMessage(type=AgenticMessageType.RESULT, content="Plan synthesized")

        drv = MagicMock()
        drv.execute_agentic = capture_execute

        with patch("amelia.agents._driver_init.get_driver", return_value=drv):
            aggregator = Aggregator(config)
            from amelia.agents.aggregator import AggregatorResult
            final_result: AggregatorResult | None = None
            async for agg_result, _ in aggregator.aggregate(
                candidate_plans=["# Plan A\n\nAlpha approach", "# Plan B\n\nBeta approach"],
                profile=profile,
                issue_id=issue_id,
                workflow_id=uuid4(),
            ):
                final_result = agg_result

        # (a) prompt enumerates both candidates with their contents
        prompt = captured["prompt"]
        assert "### Candidate 1" in prompt
        assert "### Candidate 2" in prompt
        assert "Alpha approach" in prompt
        assert "Beta approach" in prompt

        # (b) architect-style write_plan tool + required_tool
        assert [t.name for t in captured["tools"]] == ["write_plan"]
        assert captured["required_tool"] == "write_plan"

        # (c) yielded result carries the written canonical plan_path
        assert final_result is not None
        assert final_result.plan_path == canonical

    async def test_aggregate_raises_when_no_plan_written(
        self,
        mock_profile_factory: Any,
    ) -> None:
        """If the stream never calls write_plan, aggregate raises ValueError."""
        config = AgentConfig(driver="claude", model="sonnet")
        profile: Profile = mock_profile_factory()

        async def stream_without_plan(*args: Any, **kwargs: Any) -> AsyncIterator[AgenticMessage]:
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="read_file",
                tool_input={"path": "src/main.py"},
                tool_call_id="call-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="I could not produce a plan",
            )

        drv = MagicMock()
        drv.execute_agentic = stream_without_plan

        with patch("amelia.agents._driver_init.get_driver", return_value=drv):
            aggregator = Aggregator(config)
            with pytest.raises(ValueError, match="aggregator produced no plan"):
                async for _ in aggregator.aggregate(
                    candidate_plans=["# Plan A", "# Plan B"],
                    profile=profile,
                    issue_id="TEST-42",
                    workflow_id=uuid4(),
                ):
                    pass
