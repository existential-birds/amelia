"""Tests for orchestrator graph creation and routing logic."""

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from langgraph.graph import END

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


class TestGraphEdges:
    """Tests for graph edge routing - verifies nodes are connected correctly."""

    def test_graph_routes_architect_to_validator(self) -> None:
        """Graph should route from architect_node to plan_validator_node."""
        graph = create_orchestrator_graph()
        edges = graph.get_graph().edges
        architect_edges = [e for e in edges if e.source == "architect_node"]
        assert len(architect_edges) == 1
        assert architect_edges[0].target == "plan_validator_node"

    def test_graph_routes_validator_to_human_approval(self) -> None:
        """Graph should route from plan_validator_node to human_approval_node."""
        graph = create_orchestrator_graph()
        edges = graph.get_graph().edges
        validator_edges = [e for e in edges if e.source == "plan_validator_node"]
        assert len(validator_edges) == 1
        assert validator_edges[0].target == "human_approval_node"

    def test_graph_with_checkpoint_saver(self) -> None:
        """Graph should accept checkpoint saver."""
        mock_saver = MagicMock()
        graph = create_orchestrator_graph(checkpoint_saver=mock_saver)
        assert graph.checkpointer is mock_saver

    def test_review_graph_with_checkpoint_saver(self) -> None:
        """Review graph should accept checkpoint saver."""
        mock_saver = MagicMock()
        graph = create_review_graph(checkpoint_saver=mock_saver)
        assert graph.checkpointer is mock_saver

    def test_review_graph_without_checkpoint_saver(self) -> None:
        """Review graph can be created without checkpoint saver."""
        graph = create_review_graph()
        assert graph.checkpointer is None


class TestReviewRoutingFunctions:
    """Tests for review workflow routing functions - these are actual business logic."""

    @pytest.mark.parametrize(
        "auto_approve,expected",
        [
            (True, "developer_node"),
            (False, "review_approval_node"),
        ],
    )
    def test_route_after_evaluation(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
        auto_approve: bool,
        expected: str,
    ) -> None:
        """Test routing after evaluation based on auto_approve setting."""
        state, _ = mock_execution_state_factory(goal="Test", auto_approve=auto_approve)
        assert route_after_evaluation(state) == expected

    def test_route_after_fixes_max_passes_ends(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Reaching max_review_passes should end the workflow."""
        state, _ = mock_execution_state_factory(
            goal="Test",
            review_pass=3,
            max_review_passes=3,
        )
        assert route_after_fixes(state) == END

    def test_route_after_fixes_auto_approve_loops_when_items_remain(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Auto mode should loop back to reviewer if items remain."""
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
        assert route_after_fixes(state) == "reviewer_node"

    def test_route_after_fixes_auto_approve_ends_when_no_items(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Auto mode should end when no items remain."""
        evaluation_result = EvaluationResult(items_to_implement=[], summary="No items")

        state, _ = mock_execution_state_factory(
            goal="Test",
            auto_approve=True,
            review_pass=1,
            max_review_passes=3,
            evaluation_result=evaluation_result,
        )
        assert route_after_fixes(state) == END

    def test_route_after_fixes_manual_goes_to_end_approval(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
    ) -> None:
        """Manual mode should route to end_approval_node."""
        state, _ = mock_execution_state_factory(
            goal="Test",
            auto_approve=False,
            review_pass=1,
            max_review_passes=3,
        )
        assert route_after_fixes(state) == "end_approval_node"

    @pytest.mark.parametrize(
        "human_approved,expected",
        [
            (True, END),
            (False, "reviewer_node"),
            (None, "reviewer_node"),
        ],
    )
    def test_route_after_end_approval(
        self,
        mock_execution_state_factory: Callable[..., tuple[ExecutionState, Profile]],
        human_approved: bool | None,
        expected: str,
    ) -> None:
        """Test routing after end approval based on human_approved state."""
        state, _ = mock_execution_state_factory(goal="Test", human_approved=human_approved)
        assert route_after_end_approval(state) == expected
