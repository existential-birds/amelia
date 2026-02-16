"""Unit tests for graph routing with external plans."""

from datetime import UTC, datetime
from uuid import uuid4

from amelia.pipelines.implementation.graph import create_implementation_graph
from amelia.pipelines.implementation.state import ImplementationState


class TestGraphExternalPlanRouting:
    """Tests for graph routing when external_plan is set."""

    def test_graph_compiles_successfully(self) -> None:
        """Graph should compile without errors."""
        graph = create_implementation_graph()
        assert graph is not None

    def test_graph_has_architect_and_validator_nodes(self) -> None:
        """Graph should have both architect and plan_validator nodes."""
        graph = create_implementation_graph()
        nodes = list(graph.nodes.keys())
        assert "architect_node" in nodes
        assert "plan_validator_node" in nodes

    def test_graph_has_conditional_entry_from_start(self) -> None:
        """Graph should have conditional routing from START node.

        The graph should route from START to either architect_node or
        plan_validator_node based on the external_plan flag.
        """
        graph = create_implementation_graph()

        # Get the graph structure - START should have conditional edges
        # to both architect_node and plan_validator_node
        graph_dict = graph.get_graph().to_json()

        # Find START node edges
        start_edges = [
            edge for edge in graph_dict["edges"]
            if edge["source"] == "__start__"
        ]

        # START should have edges to both architect_node and plan_validator_node
        target_nodes = {edge["target"] for edge in start_edges}
        assert "architect_node" in target_nodes, "START should route to architect_node"
        assert "plan_validator_node" in target_nodes, "START should route to plan_validator_node"

    def test_external_plan_routing_logic(self) -> None:
        """Verify routing function returns correct values."""
        from amelia.pipelines.implementation.routing import route_after_start

        # External plan should route to validator
        external_state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
            external_plan=True,
        )
        assert route_after_start(external_state) == "plan_validator"

        # Normal plan should route to architect
        normal_state = ImplementationState(
            workflow_id=uuid4(),
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
            external_plan=False,
        )
        assert route_after_start(normal_state) == "architect"
