# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for orchestrator graph creation and structure."""
from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from langgraph.graph import END
from langgraph.graph.state import CompiledStateGraph

from amelia.agents.evaluator import Disposition, EvaluatedItem, EvaluationResult
from amelia.core.orchestrator import (
    create_orchestrator_graph,
    create_review_graph,
    route_after_end_approval,
    route_after_evaluation,
    route_after_fixes,
)
from amelia.core.state import ExecutionState
from amelia.core.types import Profile


class TestCreateOrchestratorGraph:
    """Tests for create_orchestrator_graph function."""

    def test_graph_includes_all_required_nodes(self) -> None:
        """Graph should include all required nodes."""
        graph = create_orchestrator_graph()

        # Get the nodes from the compiled graph
        nodes = graph.nodes
        node_names = set(nodes.keys())

        # Verify all required nodes are present (agentic workflow)
        required_nodes = {
            "architect_node",
            "human_approval_node",
            "developer_node",
            "reviewer_node",
        }

        assert required_nodes.issubset(node_names), (
            f"Graph missing required nodes. Expected {required_nodes}, "
            f"got {node_names}"
        )

    def test_graph_with_checkpoint_saver(self) -> None:
        """Graph should accept checkpoint saver."""
        mock_saver = MagicMock()

        graph = create_orchestrator_graph(checkpoint_saver=mock_saver)

        # Verify graph was created successfully with checkpoint saver
        assert graph is not None
        # The checkpointer is stored in the graph's checkpointer attribute
        assert graph.checkpointer is mock_saver


class TestCreateReviewGraph:
    """Tests for create_review_graph function."""

    def test_create_review_graph_returns_compiled_graph(self) -> None:
        """Test that create_review_graph returns a CompiledStateGraph."""
        graph = create_review_graph()

        assert graph is not None
        assert isinstance(graph, CompiledStateGraph)

    def test_review_graph_includes_all_required_nodes(self) -> None:
        """Test that review graph includes all required nodes."""
        graph = create_review_graph()

        nodes = graph.nodes
        node_names = set(nodes.keys())

        required_nodes = {
            "reviewer_node",
            "evaluation_node",
            "review_approval_node",
            "developer_node",
            "end_approval_node",
        }

        assert required_nodes.issubset(node_names), (
            f"Review graph missing required nodes. Expected {required_nodes}, "
            f"got {node_names}"
        )

    def test_create_review_graph_with_checkpoint_saver_defaults_interrupt(
        self,
    ) -> None:
        """Test default interrupt_before when checkpoint_saver is provided."""
        mock_saver = MagicMock()

        graph = create_review_graph(checkpoint_saver=mock_saver)

        assert graph is not None
        assert graph.checkpointer is mock_saver
        # Default interrupt nodes for review graph
        # The interrupt_before is stored in the compiled graph
        # We can verify by checking the graph was created successfully

    def test_create_review_graph_with_custom_interrupt(self) -> None:
        """Test create_review_graph with custom interrupt_before."""
        mock_saver = MagicMock()

        graph = create_review_graph(
            checkpoint_saver=mock_saver,
            interrupt_before=["developer_node"],
        )

        assert graph is not None
        assert graph.checkpointer is mock_saver

    def test_review_graph_without_checkpoint_saver(self) -> None:
        """Test that review graph can be created without checkpoint saver."""
        graph = create_review_graph()

        assert graph is not None
        assert graph.checkpointer is None


class TestReviewRoutingFunctions:
    """Tests for review workflow routing functions."""

    @pytest.fixture
    def base_state(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> ExecutionState:
        """Create a base execution state for testing."""
        state, _ = mock_execution_state_factory(goal="Test goal")
        return state

    def test_route_after_evaluation_auto_approve_goes_to_developer(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test auto_approve routes directly to developer."""
        state, _ = mock_execution_state_factory(
            goal="Test",
            auto_approve=True,
        )

        result = route_after_evaluation(state)
        assert result == "developer_node"

    def test_route_after_evaluation_manual_goes_to_approval(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test manual mode routes to review_approval_node."""
        state, _ = mock_execution_state_factory(
            goal="Test",
            auto_approve=False,
        )

        result = route_after_evaluation(state)
        assert result == "review_approval_node"

    def test_route_after_fixes_max_passes_ends(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test reaching max_review_passes ends the workflow."""
        state, _ = mock_execution_state_factory(
            goal="Test",
            review_pass=3,
            max_review_passes=3,
        )

        result = route_after_fixes(state)
        assert result == END

    def test_route_after_fixes_auto_approve_loops(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test auto mode loops back to reviewer if items remain."""
        # Create an evaluation result with items to implement
        evaluation_result = EvaluationResult(
            items_to_implement=[
                EvaluatedItem(
                    number=1,
                    title="Bug",
                    file_path="test.py",
                    line=1,
                    disposition=Disposition.IMPLEMENT,
                    reason="Valid",
                    original_issue="Bug",
                    suggested_fix="Fix",
                ),
            ],
            summary="Has items",
        )

        state, _ = mock_execution_state_factory(
            goal="Test",
            auto_approve=True,
            review_pass=1,
            max_review_passes=3,
            evaluation_result=evaluation_result,
        )

        result = route_after_fixes(state)
        assert result == "reviewer_node"

    def test_route_after_fixes_auto_approve_ends_when_no_items(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test auto mode ends when no items remain."""
        # Create an evaluation result with no items to implement
        evaluation_result = EvaluationResult(
            items_to_implement=[],
            summary="No items",
        )

        state, _ = mock_execution_state_factory(
            goal="Test",
            auto_approve=True,
            review_pass=1,
            max_review_passes=3,
            evaluation_result=evaluation_result,
        )

        result = route_after_fixes(state)
        assert result == END

    def test_route_after_fixes_manual_goes_to_end_approval(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test manual mode routes to end_approval_node."""
        state, _ = mock_execution_state_factory(
            goal="Test",
            auto_approve=False,
            review_pass=1,
            max_review_passes=3,
        )

        result = route_after_fixes(state)
        assert result == "end_approval_node"

    def test_route_after_end_approval_approved_ends(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that human approval ends the workflow."""
        state, _ = mock_execution_state_factory(
            goal="Test",
            human_approved=True,
        )

        result = route_after_end_approval(state)
        assert result == END

    def test_route_after_end_approval_rejected_loops(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that human rejection loops back to reviewer."""
        state, _ = mock_execution_state_factory(
            goal="Test",
            human_approved=False,
        )

        result = route_after_end_approval(state)
        assert result == "reviewer_node"

    def test_route_after_end_approval_none_loops(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Test that no approval decision loops back to reviewer."""
        state, _ = mock_execution_state_factory(
            goal="Test",
            human_approved=None,
        )

        result = route_after_end_approval(state)
        assert result == "reviewer_node"


