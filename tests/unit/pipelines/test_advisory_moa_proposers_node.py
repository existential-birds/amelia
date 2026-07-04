"""Tests for MoA proposers fan-out (advisory MoA mode)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.constants import resolve_plan_path
from amelia.core.types import AgentConfig, Issue
from amelia.pipelines.implementation.nodes import advisory_moa_proposers_node
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)


# Resolve forward references
rebuild_implementation_state()


class TestMoAProposerPlansField:
    """Tests for the advisory_moa_proposer_plans state field."""

    def test_default_empty(self):
        """advisory_moa_proposer_plans should default to an empty list."""
        state = ImplementationState(
            workflow_id=uuid4(),
            pipeline_type="implementation",
            profile_id="prof-1",
            created_at=datetime.now(tz=UTC),
            status="pending",
        )
        assert state.advisory_moa_proposer_plans == []

    def test_accepts_list_of_paths(self):
        """advisory_moa_proposer_plans should accept and round-trip a list of plan paths."""
        state = ImplementationState(
            workflow_id=uuid4(),
            pipeline_type="implementation",
            profile_id="prof-1",
            created_at=datetime.now(tz=UTC),
            status="pending",
            advisory_moa_proposer_plans=["a.md", "b.md"],
        )
        assert state.advisory_moa_proposer_plans == ["a.md", "b.md"]


def _make_stub_architect(fail_markers: tuple[str, ...] = ()) -> type:
    """Build a stub Architect class that writes a distinct plan file per proposer.

    The stub resolves its plan path from the per-proposer ``profile.plan_path_pattern``
    it is handed (the node bakes ``-proposer{i}`` into the pattern), then writes a
    file whose content records the resolved path and the proposer's model. Patterns
    containing any of ``fail_markers`` raise instead of writing.
    """

    class _StubArchitect:
        def __init__(
            self,
            config: AgentConfig,
            prompts: Any = None,
            sandbox_provider: Any = None,
        ) -> None:
            self.config = config
            self.driver = MagicMock()

        async def plan(
            self,
            state: ImplementationState,
            profile: Any,
            *,
            workflow_id: Any,
        ) -> Any:
            rel = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
            if any(marker in rel for marker in fail_markers):
                raise RuntimeError(f"proposer boom: {rel}")
            path = Path(profile.repo_root) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# plan {rel}\nmodel={self.config.model}\n")
            yield (state, MagicMock())

    return _StubArchitect


def _build_config(mock_profile_factory: Any, proposer_count: int, **moa: Any) -> tuple[dict[str, Any], Any]:
    """Build a RunnableConfig dict + profile with MoA enabled on the architect agent."""
    moa_opts = {"enabled": True, "proposer_count": proposer_count, **moa}
    profile = mock_profile_factory(
        agents={
            "architect": AgentConfig(driver="claude", model="sonnet", options={"moa": moa_opts}),
            "developer": AgentConfig(driver="claude", model="sonnet"),
            "reviewer": AgentConfig(driver="claude", model="sonnet"),
        },
    )
    config: dict[str, Any] = {
        "configurable": {"profile": profile, "thread_id": str(uuid4())},
    }
    return config, profile


def _make_state(profile: Any) -> ImplementationState:
    return ImplementationState(
        workflow_id=uuid4(),
        pipeline_type="implementation",
        profile_id=profile.name,
        created_at=datetime.now(tz=UTC),
        status="pending",
        issue=Issue(id="TEST-1", title="Test", description="Test issue"),
    )


class TestMoAProposersNode:
    """Behavior tests for the best-effort proposers fan-out node."""

    @pytest.mark.asyncio
    async def test_fans_out_to_distinct_paths(self, mock_profile_factory: Any) -> None:
        """Three proposers yield three distinct plan paths, each written to disk."""
        config, profile = _build_config(mock_profile_factory, proposer_count=3)
        state = _make_state(profile)

        with patch(
            "amelia.pipelines.implementation.nodes.Architect",
            _make_stub_architect(),
        ):
            result = await advisory_moa_proposers_node(state, cast(RunnableConfig, config))

        plans = result["advisory_moa_proposer_plans"]
        assert len(plans) == 3
        assert len(set(plans)) == 3, "proposer paths must be distinct"
        for rel in plans:
            assert "-proposer" in rel
            written = Path(profile.repo_root) / rel
            assert written.exists()
            assert rel in written.read_text()

    @pytest.mark.asyncio
    async def test_single_proposer_edge(self, mock_profile_factory: Any) -> None:
        """N=1 yields exactly one path."""
        config, profile = _build_config(mock_profile_factory, proposer_count=1)
        state = _make_state(profile)

        with patch(
            "amelia.pipelines.implementation.nodes.Architect",
            _make_stub_architect(),
        ):
            result = await advisory_moa_proposers_node(state, cast(RunnableConfig, config))

        plans = result["advisory_moa_proposer_plans"]
        assert len(plans) == 1
        assert (Path(profile.repo_root) / plans[0]).exists()

    @pytest.mark.asyncio
    async def test_best_effort_one_proposer_fails(self, mock_profile_factory: Any) -> None:
        """One failing proposer (of three) leaves two survivors; the node does not raise."""
        config, profile = _build_config(mock_profile_factory, proposer_count=3)
        state = _make_state(profile)

        with patch(
            "amelia.pipelines.implementation.nodes.Architect",
            _make_stub_architect(fail_markers=("proposer1",)),
        ):
            result = await advisory_moa_proposers_node(state, cast(RunnableConfig, config))

        plans = result["advisory_moa_proposer_plans"]
        assert len(plans) == 2
        assert all("proposer1" not in rel for rel in plans)
        for rel in plans:
            assert (Path(profile.repo_root) / rel).exists()

    @pytest.mark.asyncio
    async def test_per_proposer_model_override(self, mock_profile_factory: Any) -> None:
        """Each proposer is constructed with its resolved per-proposer model."""
        config, profile = _build_config(
            mock_profile_factory,
            proposer_count=3,
            proposer_models=["m-a", "m-b"],  # third falls back to base "sonnet"
        )
        state = _make_state(profile)

        with patch(
            "amelia.pipelines.implementation.nodes.Architect",
            _make_stub_architect(),
        ):
            result = await advisory_moa_proposers_node(state, cast(RunnableConfig, config))

        models = {
            (Path(profile.repo_root) / rel).read_text().splitlines()[1]
            for rel in result["advisory_moa_proposer_plans"]
        }
        assert models == {"model=m-a", "model=m-b", "model=sonnet"}

    @pytest.mark.asyncio
    async def test_all_fail_raises(self, mock_profile_factory: Any) -> None:
        """When every proposer fails, the node raises (no survivors)."""
        config, profile = _build_config(mock_profile_factory, proposer_count=2)
        state = _make_state(profile)

        with patch(
            "amelia.pipelines.implementation.nodes.Architect",
            _make_stub_architect(fail_markers=("proposer",)),
        ), pytest.raises(RuntimeError):
            await advisory_moa_proposers_node(state, cast(RunnableConfig, config))
