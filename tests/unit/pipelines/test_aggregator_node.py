"""Tests for the MoA aggregator node (advisory MoA mode, Task 6)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.constants import resolve_plan_path
from amelia.core.types import AgentConfig, Issue
from amelia.pipelines.implementation.nodes import aggregator_node
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)


# Resolve forward references
rebuild_implementation_state()


SYNTHESIZED = "# Synthesized Plan\n\n### Task 1: do the thing\n"


def _make_stub_aggregator(captured: dict[str, Any]) -> type:
    """Build a stub Aggregator that records its constructor + aggregate args.

    On ``aggregate`` it resolves the canonical plan path from the profile/issue
    (exactly as the real Aggregator does) and writes ``SYNTHESIZED`` there, so the
    node's observable consequence — the canonical file on disk — is exercised.
    Construction is counted so the 1-survivor promotion path can assert the
    Aggregator was bypassed entirely.
    """

    class _StubAggregator:
        def __init__(
            self,
            config: AgentConfig,
            prompts: Any = None,
            sandbox_provider: Any = None,
        ) -> None:
            captured["construct_count"] = captured.get("construct_count", 0) + 1
            captured["config"] = config
            self.driver = MagicMock()

        async def aggregate(
            self,
            candidate_plans: list[str],
            state: ImplementationState,
            profile: Any,
            *,
            workflow_id: Any,
        ) -> Any:
            captured["candidate_plans"] = list(candidate_plans)
            rel = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
            path = Path(profile.repo_root) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(SYNTHESIZED)
            new_state = state.model_copy(
                update={"architect_raw_output": "synthesized", "plan_path": path}
            )
            yield (new_state, MagicMock())

    return _StubAggregator


def _build_profile(mock_profile_factory: Any, *, with_aggregator: bool = True) -> Any:
    agents = {
        "architect": AgentConfig(driver="claude", model="sonnet"),
        "developer": AgentConfig(driver="claude", model="sonnet"),
        "reviewer": AgentConfig(driver="claude", model="sonnet"),
    }
    if with_aggregator:
        agents["aggregator"] = AgentConfig(driver="claude", model="opus")
    return mock_profile_factory(agents=agents)


def _config(profile: Any) -> dict[str, Any]:
    return {"configurable": {"profile": profile, "thread_id": str(uuid4())}}


def _make_state(profile: Any, plans: list[str]) -> ImplementationState:
    return ImplementationState(
        workflow_id=uuid4(),
        pipeline_type="implementation",
        profile_id=profile.name,
        created_at=datetime.now(tz=UTC),
        status="pending",
        issue=Issue(id="TEST-1", title="Test", description="Test issue"),
        moa_proposer_plans=plans,
    )


def _seed_candidates(profile: Any, contents: list[str]) -> list[str]:
    """Write real candidate markdown files under repo_root; return relative paths."""
    rels: list[str] = []
    for i, content in enumerate(contents):
        rel = f"docs/plans/candidate{i}.md"
        path = Path(profile.repo_root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        rels.append(rel)
    return rels


class TestAggregatorNode:
    """Behavior tests for the aggregator node."""

    @pytest.mark.asyncio
    async def test_writes_canonical_plan_and_passes_contents(
        self, mock_profile_factory: Any
    ) -> None:
        """With >=2 survivors the node runs the Aggregator over candidate CONTENTS
        and returns the canonical plan path the validator reads."""
        profile = _build_profile(mock_profile_factory)
        contents = ["# Candidate A\n\n### Task 1: a\n", "# Candidate B\n\n### Task 1: b\n"]
        rels = _seed_candidates(profile, contents)
        state = _make_state(profile, rels)
        captured: dict[str, Any] = {}

        with patch(
            "amelia.pipelines.implementation.nodes.Aggregator",
            _make_stub_aggregator(captured),
        ):
            result = await aggregator_node(state, cast(RunnableConfig, _config(profile)))

        # (a) returned plan_path == the canonical path plan_validator_node re-resolves.
        canonical = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
        assert result["plan_path"] == canonical
        assert (Path(profile.repo_root) / canonical).read_text() == SYNTHESIZED

        # (b) the aggregator received candidate file CONTENTS, not paths.
        assert captured["candidate_plans"] == contents
        # Aggregator built from the explicit "aggregator" agent config.
        assert captured["construct_count"] == 1
        assert captured["config"].model == "opus"

    @pytest.mark.asyncio
    async def test_single_survivor_promotion_bypasses_aggregator(
        self, mock_profile_factory: Any
    ) -> None:
        """With exactly one survivor, the plan is promoted to the canonical path and
        the Aggregator is never constructed."""
        profile = _build_profile(mock_profile_factory)
        survivor = "# Lone Survivor\n\n### Task 1: ship it\n"
        rels = _seed_candidates(profile, [survivor])
        state = _make_state(profile, rels)
        captured: dict[str, Any] = {}

        with patch(
            "amelia.pipelines.implementation.nodes.Aggregator",
            _make_stub_aggregator(captured),
        ):
            result = await aggregator_node(state, cast(RunnableConfig, _config(profile)))

        canonical = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
        assert result["plan_path"] == canonical
        # Promoted content equals the survivor's content (not synthesized).
        assert (Path(profile.repo_root) / canonical).read_text() == survivor
        # Aggregator was BYPASSED.
        assert captured.get("construct_count", 0) == 0

    @pytest.mark.asyncio
    async def test_aggregator_config_falls_back_to_architect(
        self, mock_profile_factory: Any
    ) -> None:
        """With no 'aggregator' agent, the node falls back to the architect config
        without raising."""
        profile = _build_profile(mock_profile_factory, with_aggregator=False)
        rels = _seed_candidates(profile, ["# A\n\n### Task 1: a\n", "# B\n\n### Task 1: b\n"])
        state = _make_state(profile, rels)
        captured: dict[str, Any] = {}

        with patch(
            "amelia.pipelines.implementation.nodes.Aggregator",
            _make_stub_aggregator(captured),
        ):
            result = await aggregator_node(state, cast(RunnableConfig, _config(profile)))

        # Fell back to the architect's config (model "sonnet"), did not raise.
        assert captured["construct_count"] == 1
        assert captured["config"].model == "sonnet"
        canonical = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
        assert result["plan_path"] == canonical

    @pytest.mark.asyncio
    async def test_empty_proposer_plans_raises(self, mock_profile_factory: Any) -> None:
        """An empty survivor list is a guard failure (proposers node already enforces >=1)."""
        profile = _build_profile(mock_profile_factory)
        state = _make_state(profile, [])

        with patch(
            "amelia.pipelines.implementation.nodes.Aggregator",
            _make_stub_aggregator({}),
        ), pytest.raises(ValueError):
            await aggregator_node(state, cast(RunnableConfig, _config(profile)))
