# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for orchestrator graph creation and structure."""

from amelia.core.orchestrator import (
    create_orchestrator_graph,
    route_after_developer,
    route_batch_approval,
    route_blocker_resolution,
)
from amelia.core.types import DeveloperStatus


class TestCreateOrchestratorGraph:
    """Tests for create_orchestrator_graph function."""

    def test_graph_includes_all_required_nodes(self):
        """Graph should include all required nodes."""
        graph = create_orchestrator_graph()

        # Get the nodes from the compiled graph
        nodes = graph.nodes
        node_names = set(nodes.keys())

        # Verify all required nodes are present
        required_nodes = {
            "architect_node",
            "human_approval_node",
            "developer_node",
            "reviewer_node",
            "batch_approval_node",
            "blocker_resolution_node",
        }

        assert required_nodes.issubset(node_names), (
            f"Graph missing required nodes. Expected {required_nodes}, "
            f"got {node_names}"
        )

    def test_graph_interrupts_default_includes_all_nodes_with_checkpointer(self):
        """Default interrupts should include all nodes when checkpoint_saver is provided."""
        from unittest.mock import MagicMock
        mock_saver = MagicMock()
        graph = create_orchestrator_graph(checkpoint_saver=mock_saver)

        # Get interrupt_before from the compiled graph
        # LangGraph stores this in interrupt_before_nodes attribute
        expected_interrupts = {
            "human_approval_node",
            "batch_approval_node",
            "blocker_resolution_node",
        }

        # Check that graph has interrupt_before_nodes set correctly
        assert hasattr(graph, "interrupt_before_nodes"), (
            "Compiled graph should have interrupt_before_nodes attribute"
        )

        actual_interrupts = set(graph.interrupt_before_nodes or [])
        assert actual_interrupts == expected_interrupts, (
            f"Default interrupts should be {expected_interrupts}, "
            f"got {actual_interrupts}"
        )

    def test_graph_no_interrupts_without_checkpointer(self):
        """Without checkpoint_saver, should have no default interrupts (backwards compat)."""
        graph = create_orchestrator_graph()

        # Without checkpoint_saver, interrupt_before_nodes should be empty for backwards compatibility
        actual_interrupts = set(graph.interrupt_before_nodes or [])
        assert actual_interrupts == set(), (
            f"Without checkpoint_saver, interrupts should be empty for backwards compatibility, "
            f"got {actual_interrupts}"
        )

    def test_graph_interrupts_custom(self):
        """Custom interrupt_before parameter should be respected."""
        custom_interrupts = ["human_approval_node"]
        graph = create_orchestrator_graph(interrupt_before=custom_interrupts)

        actual_interrupts = set(graph.interrupt_before_nodes or [])

        assert actual_interrupts == set(custom_interrupts), (
            f"Custom interrupts should be {set(custom_interrupts)}, "
            f"got {actual_interrupts}"
        )

    def test_graph_with_checkpoint_saver(self):
        """Graph should accept checkpoint saver."""
        from unittest.mock import MagicMock
        mock_saver = MagicMock()

        graph = create_orchestrator_graph(checkpoint_saver=mock_saver)

        # Verify graph was created successfully with checkpoint saver
        assert graph is not None
        # The checkpointer is stored in the graph's checkpointer attribute
        assert graph.checkpointer is mock_saver


class TestRouteBatchApproval:
    """Tests for route_batch_approval routing function."""

    def test_approved_routes_to_developer(self, mock_execution_state_factory):
        """When human_approved is True, should route to developer."""
        state = mock_execution_state_factory(human_approved=True)

        result = route_batch_approval(state)

        assert result == "developer", (
            "route_batch_approval should return 'developer' when "
            "human_approved is True (continue to next batch)"
        )

    def test_rejected_routes_to_end(self, mock_execution_state_factory):
        """When human_approved is False, should route to END."""
        state = mock_execution_state_factory(human_approved=False)

        result = route_batch_approval(state)

        assert result == "__end__", (
            "route_batch_approval should return END when "
            "human_approved is False (user rejected, stop workflow)"
        )

    def test_none_routes_to_end(self, mock_execution_state_factory):
        """When human_approved is None, should route to END."""
        state = mock_execution_state_factory(human_approved=None)

        result = route_batch_approval(state)

        assert result == "__end__", (
            "route_batch_approval should return END when "
            "human_approved is None (no decision made)"
        )


class TestRouteBlockerResolution:
    """Tests for route_blocker_resolution routing function."""

    def test_aborted_routes_to_end(self, mock_execution_state_factory):
        """When workflow_status is 'aborted', should route to END."""
        state = mock_execution_state_factory(workflow_status="aborted")

        result = route_blocker_resolution(state)

        assert result == "__end__", (
            "route_blocker_resolution should return END when "
            "workflow_status is 'aborted'"
        )

    def test_running_routes_to_developer(self, mock_execution_state_factory):
        """When workflow_status is 'running', should route to developer."""
        state = mock_execution_state_factory(workflow_status="running")

        result = route_blocker_resolution(state)

        assert result == "developer", (
            "route_blocker_resolution should return 'developer' when "
            "workflow_status is 'running' (continue after fix/skip)"
        )

    def test_default_running_routes_to_developer(self, mock_execution_state_factory):
        """When workflow_status is default 'running', should route to developer."""
        # Don't pass workflow_status - it defaults to "running"
        state = mock_execution_state_factory()

        result = route_blocker_resolution(state)

        assert result == "developer", (
            "route_blocker_resolution should return 'developer' when "
            "workflow_status is 'running' (default - continue)"
        )


class TestGraphRouting:
    """Tests for routing from developer node in the graph."""

    def test_developer_routes_to_reviewer_when_all_done(self, mock_execution_state_factory):
        """Developer should route to reviewer when status is ALL_DONE."""
        state = mock_execution_state_factory(developer_status=DeveloperStatus.ALL_DONE)

        # Test the routing function directly
        route = route_after_developer(state)

        assert route == "reviewer", (
            "Developer should route to reviewer when ALL_DONE"
        )

    def test_developer_routes_to_batch_approval_when_batch_complete(
        self, mock_execution_state_factory
    ):
        """Developer should route to batch_approval when status is BATCH_COMPLETE."""
        state = mock_execution_state_factory(developer_status=DeveloperStatus.BATCH_COMPLETE)

        route = route_after_developer(state)

        assert route == "batch_approval", (
            "Developer should route to batch_approval when BATCH_COMPLETE"
        )

    def test_developer_routes_to_blocker_resolution_when_blocked(
        self, mock_execution_state_factory
    ):
        """Developer should route to blocker_resolution when status is BLOCKED."""
        state = mock_execution_state_factory(developer_status=DeveloperStatus.BLOCKED)

        route = route_after_developer(state)

        assert route == "blocker_resolution", (
            "Developer should route to blocker_resolution when BLOCKED"
        )

    def test_developer_routes_to_developer_when_executing(
        self, mock_execution_state_factory
    ):
        """Developer should route back to developer when status is EXECUTING."""
        state = mock_execution_state_factory(developer_status=DeveloperStatus.EXECUTING)

        route = route_after_developer(state)

        assert route == "developer", (
            "Developer should route back to developer when EXECUTING"
        )
