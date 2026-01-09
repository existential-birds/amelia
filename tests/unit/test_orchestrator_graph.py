"""Tests for orchestrator graph creation and routing logic."""

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.graph import END

from amelia.agents.evaluator import Disposition, EvaluatedItem, EvaluationResult
from amelia.core.orchestrator import (
    call_reviewer_node,
    create_orchestrator_graph,
    create_review_graph,
    next_task_node,
    route_after_end_approval,
    route_after_evaluation,
    route_after_fixes,
    route_after_task_review,
)
from amelia.core.state import ExecutionState, ReviewResult
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


class TestRouteAfterTaskReview:
    """Tests for route_after_task_review routing function."""

    @pytest.fixture
    def mock_profile_task_review(self) -> Profile:
        return Profile(
            name="test",
            driver="cli:claude",
            model="sonnet",
            max_task_review_iterations=3,
        )

    @pytest.fixture
    def approved_review(self) -> ReviewResult:
        return ReviewResult(
            reviewer_persona="test",
            approved=True,
            comments=[],
            severity="low",
        )

    @pytest.fixture
    def rejected_review(self) -> ReviewResult:
        return ReviewResult(
            reviewer_persona="test",
            approved=False,
            comments=["Needs fixes"],
            severity="medium",
        )

    def test_route_after_task_review_ends_when_all_tasks_complete(
        self, mock_profile_task_review: Profile, approved_review: ReviewResult
    ) -> None:
        """Should END when approved and all tasks complete."""
        state = ExecutionState(
            profile_id="test",
            total_tasks=2,
            current_task_index=1,  # On task 2 (0-indexed)
            last_review=approved_review,
        )
        config = {"configurable": {"profile": mock_profile_task_review}}

        result = route_after_task_review(state, config)
        assert result == "__end__"

    def test_route_after_task_review_goes_to_next_task_when_approved(
        self, mock_profile_task_review: Profile, approved_review: ReviewResult
    ) -> None:
        """Should go to next_task_node when approved and more tasks remain."""
        state = ExecutionState(
            profile_id="test",
            total_tasks=3,
            current_task_index=0,  # On task 1, more tasks remain
            last_review=approved_review,
        )
        config = {"configurable": {"profile": mock_profile_task_review}}

        result = route_after_task_review(state, config)
        assert result == "next_task_node"

    def test_route_after_task_review_retries_developer_when_not_approved(
        self, mock_profile_task_review: Profile, rejected_review: ReviewResult
    ) -> None:
        """Should retry developer when review not approved and iterations remain."""
        state = ExecutionState(
            profile_id="test",
            total_tasks=2,
            current_task_index=0,
            task_review_iteration=1,  # Under limit of 3
            last_review=rejected_review,
        )
        config = {"configurable": {"profile": mock_profile_task_review}}

        result = route_after_task_review(state, config)
        assert result == "developer"

    def test_route_after_task_review_ends_on_max_iterations(
        self, mock_profile_task_review: Profile, rejected_review: ReviewResult
    ) -> None:
        """Should END when max iterations reached without approval."""
        state = ExecutionState(
            profile_id="test",
            total_tasks=2,
            current_task_index=0,
            task_review_iteration=3,  # At limit
            last_review=rejected_review,
        )
        config = {"configurable": {"profile": mock_profile_task_review}}

        result = route_after_task_review(state, config)
        assert result == "__end__"

    def test_route_after_task_review_uses_profile_max_iterations(self) -> None:
        """Should respect profile's max_task_review_iterations setting."""
        profile = Profile(
            name="test",
            driver="cli:claude",
            model="sonnet",
            max_task_review_iterations=10,
        )
        rejected_review = ReviewResult(
            reviewer_persona="test",
            approved=False,
            comments=["Needs fixes"],
            severity="medium",
        )
        state = ExecutionState(
            profile_id="test",
            total_tasks=2,
            current_task_index=0,
            task_review_iteration=5,  # Under custom limit of 10
            last_review=rejected_review,
        )
        config = {"configurable": {"profile": profile}}

        result = route_after_task_review(state, config)
        assert result == "developer"  # Should retry since under limit


class TestNextTaskNode:
    """Tests for next_task_node function."""

    @pytest.fixture
    def task_state_for_next(self) -> ExecutionState:
        return ExecutionState(
            profile_id="test",
            total_tasks=3,
            current_task_index=0,
            task_review_iteration=2,
            driver_session_id="session-123",
        )

    @pytest.mark.asyncio
    async def test_next_task_node_increments_task_index(
        self, task_state_for_next: ExecutionState
    ) -> None:
        """next_task_node should increment current_task_index."""
        config = {"configurable": {"profile": MagicMock()}}

        with patch(
            "amelia.core.orchestrator.commit_task_changes", new_callable=AsyncMock
        ):
            result = await next_task_node(task_state_for_next, config)

        assert result["current_task_index"] == 1

    @pytest.mark.asyncio
    async def test_next_task_node_resets_review_iteration(
        self, task_state_for_next: ExecutionState
    ) -> None:
        """next_task_node should reset task_review_iteration to 0."""
        config = {"configurable": {"profile": MagicMock()}}

        with patch(
            "amelia.core.orchestrator.commit_task_changes", new_callable=AsyncMock
        ):
            result = await next_task_node(task_state_for_next, config)

        assert result["task_review_iteration"] == 0

    @pytest.mark.asyncio
    async def test_next_task_node_clears_session_id(
        self, task_state_for_next: ExecutionState
    ) -> None:
        """next_task_node should clear driver_session_id for fresh session."""
        config = {"configurable": {"profile": MagicMock()}}

        with patch(
            "amelia.core.orchestrator.commit_task_changes", new_callable=AsyncMock
        ):
            result = await next_task_node(task_state_for_next, config)

        assert result["driver_session_id"] is None

    @pytest.mark.asyncio
    async def test_next_task_node_commits_changes(
        self, task_state_for_next: ExecutionState
    ) -> None:
        """next_task_node should commit current task changes."""
        config = {"configurable": {"profile": MagicMock()}}

        with patch(
            "amelia.core.orchestrator.commit_task_changes", new_callable=AsyncMock
        ) as mock_commit:
            await next_task_node(task_state_for_next, config)

        mock_commit.assert_called_once_with(task_state_for_next, config)

    @pytest.mark.asyncio
    async def test_next_task_node_raises_on_commit_failure(
        self, task_state_for_next: ExecutionState
    ) -> None:
        """next_task_node should raise RuntimeError when commit fails.

        This halts the workflow to preserve one-commit-per-task semantics,
        allowing manual intervention before proceeding.
        """
        config = {"configurable": {"profile": MagicMock()}}

        with patch(
            "amelia.core.orchestrator.commit_task_changes",
            new_callable=AsyncMock,
            return_value=False,
        ), pytest.raises(RuntimeError) as exc_info:
            await next_task_node(task_state_for_next, config)

        assert "Failed to commit changes for task 1" in str(exc_info.value)
        assert "one-commit-per-task" in str(exc_info.value)


class TestReviewerNodeTaskIteration:
    """Tests for call_reviewer_node task_review_iteration behavior."""

    @pytest.mark.asyncio
    async def test_reviewer_node_increments_task_review_iteration(self) -> None:
        """Reviewer node should increment task_review_iteration for task-based execution."""
        state = ExecutionState(
            profile_id="test",
            total_tasks=2,  # Task-based mode
            current_task_index=0,
            task_review_iteration=1,
            code_changes_for_review="diff --git a/test.py\n+# test",
        )
        profile = Profile(name="test", driver="cli:claude", model="sonnet")
        config = {"configurable": {"profile": profile, "thread_id": "test-wf"}}

        # Mock reviewer to return a review result
        mock_review = ReviewResult(
            reviewer_persona="test",
            approved=False,
            comments=["Needs work"],
            severity="medium",
        )

        with patch("amelia.core.orchestrator.Reviewer") as mock_reviewer_class:
            mock_reviewer = MagicMock()
            mock_reviewer.review = AsyncMock(return_value=(mock_review, "session-123"))
            mock_reviewer_class.return_value = mock_reviewer

            result = await call_reviewer_node(state, config)

        assert result["task_review_iteration"] == 2


class TestOrchestratorGraphTaskBasedRouting:
    """Tests for task-based routing wired into the orchestrator graph."""

    def test_orchestrator_graph_has_next_task_node(self) -> None:
        """Orchestrator graph should include next_task_node."""
        graph = create_orchestrator_graph()
        graph_obj = graph.get_graph()
        node_names = [node.name for node in graph_obj.nodes.values()]
        assert "next_task_node" in node_names

    def test_orchestrator_graph_next_task_node_routes_to_developer(self) -> None:
        """Graph should have edge from next_task_node to developer_node."""
        graph = create_orchestrator_graph()
        graph_obj = graph.get_graph()
        edges = graph_obj.edges

        # Find edge from next_task_node
        next_task_edges = [e for e in edges if e.source == "next_task_node"]
        assert len(next_task_edges) == 1
        assert next_task_edges[0].target == "developer_node"

    def test_orchestrator_graph_reviewer_can_route_to_next_task(self) -> None:
        """Graph should allow routing from reviewer to next_task_node."""
        graph = create_orchestrator_graph()
        graph_obj = graph.get_graph()
        edges = graph_obj.edges

        # Find edges from reviewer_node
        reviewer_edges = [e for e in edges if e.source == "reviewer_node"]

        # Reviewer should have conditional edges that include next_task_node as a target
        targets = [e.target for e in reviewer_edges]
        assert (
            "next_task_node" in targets
        ), "reviewer_node should be able to route to next_task_node"
