"""Unit tests for conditional MoA wiring in the implementation graph.

These tests pin the *observable graph structure* (registered nodes and edges
introspected via ``graph.get_graph()``) rather than any dispatch, so a no-op
wiring change cannot pass them.
"""

from typing import Any

from amelia.core.types import AgentConfig
from amelia.pipelines.implementation.graph import create_implementation_graph


def _nodes(graph: Any) -> set[str]:
    return set(graph.nodes.keys())


def _edges(graph: Any) -> list[dict[str, Any]]:
    return graph.get_graph().to_json()["edges"]


def _targets_from(graph: Any, source: str) -> set[str]:
    return {edge["target"] for edge in _edges(graph) if edge["source"] == source}


class TestMoADisabledGraph:
    """The default (MoA-disabled) path must be structurally unchanged."""

    def test_single_architect_when_no_profile(self) -> None:
        graph = create_implementation_graph()
        nodes = _nodes(graph)
        assert "architect_node" in nodes
        assert "moa_proposers_node" not in nodes
        assert "aggregator_node" not in nodes

    def test_single_architect_when_moa_absent_in_profile(
        self, mock_profile_factory: Any
    ) -> None:
        profile = mock_profile_factory()  # default agents, no moa options
        graph = create_implementation_graph(profile=profile)
        nodes = _nodes(graph)
        assert "architect_node" in nodes
        assert "moa_proposers_node" not in nodes
        assert "aggregator_node" not in nodes


class TestMoAEnabledGraph:
    """When MoA is enabled, proposers/aggregator replace the single architect."""

    def _enabled_profile(self, mock_profile_factory: Any) -> Any:
        agents = {
            "architect": AgentConfig(
                driver="claude",
                model="sonnet",
                options={"moa": {"enabled": True, "proposer_count": 2}},
            ),
            "developer": AgentConfig(driver="claude", model="sonnet"),
            "reviewer": AgentConfig(driver="claude", model="sonnet"),
        }
        return mock_profile_factory(agents=agents)

    def test_moa_nodes_present_architect_absent(
        self, mock_profile_factory: Any
    ) -> None:
        graph = create_implementation_graph(profile=self._enabled_profile(mock_profile_factory))
        nodes = _nodes(graph)
        assert "moa_proposers_node" in nodes
        assert "aggregator_node" in nodes
        assert "architect_node" not in nodes

    def test_start_routes_to_proposers_not_architect(
        self, mock_profile_factory: Any
    ) -> None:
        graph = create_implementation_graph(profile=self._enabled_profile(mock_profile_factory))
        start_targets = _targets_from(graph, "__start__")
        assert "moa_proposers_node" in start_targets
        assert "architect_node" not in start_targets

    def test_proposers_flow_into_aggregator_then_validator(
        self, mock_profile_factory: Any
    ) -> None:
        graph = create_implementation_graph(profile=self._enabled_profile(mock_profile_factory))
        assert "aggregator_node" in _targets_from(graph, "moa_proposers_node")
        assert "plan_validator_node" in _targets_from(graph, "aggregator_node")

    def test_revise_branch_targets_proposers(
        self, mock_profile_factory: Any
    ) -> None:
        graph = create_implementation_graph(profile=self._enabled_profile(mock_profile_factory))
        validator_targets = _targets_from(graph, "plan_validator_node")
        # The "revise" branch (formerly -> architect_node) now loops to proposers.
        assert "moa_proposers_node" in validator_targets
        assert "architect_node" not in validator_targets
