# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for orchestrator graph creation and structure."""

from amelia.core.orchestrator import create_orchestrator_graph


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

    def test_graph_with_checkpoint_saver(self):
        """Graph should accept checkpoint saver."""
        from unittest.mock import MagicMock
        mock_saver = MagicMock()

        graph = create_orchestrator_graph(checkpoint_saver=mock_saver)

        # Verify graph was created successfully with checkpoint saver
        assert graph is not None
        # The checkpointer is stored in the graph's checkpointer attribute
        assert graph.checkpointer is mock_saver


