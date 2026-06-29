"""Unit tests for generative MoA graph wiring and approval routing."""

from datetime import UTC, datetime
from uuid import uuid4

from amelia.core.types import AgentConfig, DriverType, Profile
from amelia.pipelines.implementation.graph import create_implementation_graph
from amelia.pipelines.implementation.routing import (
    resolve_moa_config,
    route_approval_with_moa,
)
from amelia.pipelines.implementation.state import ImplementationState


def _profile(moa_options: dict | None) -> Profile:
    dev_options = {"moa": moa_options} if moa_options is not None else {}
    agents = {
        "architect": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
        "developer": AgentConfig(
            driver=DriverType.CLAUDE, model="sonnet", options=dev_options
        ),
        "reviewer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
    }
    return Profile(name="test", tracker="noop", repo_root="/tmp/x", agents=agents)


def _state(*, approved: bool | None) -> ImplementationState:
    return ImplementationState(
        workflow_id=uuid4(),
        created_at=datetime.now(UTC),
        status="running",
        profile_id="test",
        human_approved=approved,
    )


class TestGraphContainsMoANodes:
    def test_graph_compiles(self) -> None:
        assert create_implementation_graph() is not None

    def test_graph_has_moa_nodes(self) -> None:
        nodes = list(create_implementation_graph().nodes.keys())
        assert "generative_moa_proposers_node" in nodes
        assert "generative_moa_aggregator_node" in nodes

    def test_approval_routes_to_both_developer_and_moa(self) -> None:
        graph_dict = create_implementation_graph().get_graph().to_json()
        approval_targets = {
            edge["target"]
            for edge in graph_dict["edges"]
            if edge["source"] == "human_approval_node"
        }
        assert "developer_node" in approval_targets
        assert "generative_moa_proposers_node" in approval_targets

    def test_moa_path_chains_to_reviewer(self) -> None:
        graph_dict = create_implementation_graph().get_graph().to_json()
        edges = {(e["source"], e["target"]) for e in graph_dict["edges"]}
        assert ("generative_moa_proposers_node", "generative_moa_aggregator_node") in edges
        assert ("generative_moa_aggregator_node", "reviewer_node") in edges


class TestApprovalRouting:
    def test_not_approved_rejects(self) -> None:
        profile = _profile({"enabled": True, "mode": "generative"})
        assert route_approval_with_moa(_state(approved=False), profile) == "reject"

    def test_approved_moa_disabled_routes_to_developer(self) -> None:
        profile = _profile(None)
        assert route_approval_with_moa(_state(approved=True), profile) == "developer"

    def test_approved_generative_routes_to_moa(self) -> None:
        profile = _profile({"enabled": True, "mode": "generative"})
        assert route_approval_with_moa(_state(approved=True), profile) == "moa"

    def test_approved_advisory_routes_to_developer(self) -> None:
        profile = _profile({"enabled": True, "mode": "advisory"})
        assert route_approval_with_moa(_state(approved=True), profile) == "developer"

    def test_enabled_false_routes_to_developer(self) -> None:
        profile = _profile({"enabled": False, "mode": "generative"})
        assert route_approval_with_moa(_state(approved=True), profile) == "developer"


class TestResolveMoAConfig:
    def test_no_developer_agent_returns_default(self) -> None:
        profile = Profile(name="t", tracker="noop", repo_root="/tmp/x", agents={})
        cfg = resolve_moa_config(profile)
        assert cfg.enabled is False

    def test_reads_developer_options(self) -> None:
        profile = _profile({"enabled": True, "proposer_count": 3})
        cfg = resolve_moa_config(profile)
        assert cfg.enabled is True
        assert cfg.proposer_count == 3
