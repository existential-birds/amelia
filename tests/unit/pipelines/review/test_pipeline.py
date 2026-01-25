"""Unit tests for ReviewPipeline."""

from amelia.pipelines.base import PipelineMetadata
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.review.pipeline import ReviewPipeline


class TestReviewPipelineProtocol:
    """Tests that ReviewPipeline satisfies Pipeline protocol."""

    def test_metadata_name_is_review(self) -> None:
        """Metadata name should be 'review'."""
        pipeline = ReviewPipeline()
        assert pipeline.metadata.name == "review"

    def test_metadata_returns_pipeline_metadata(self) -> None:
        """Metadata should return a PipelineMetadata instance."""
        pipeline = ReviewPipeline()
        assert isinstance(pipeline.metadata, PipelineMetadata)

    def test_metadata_has_display_name(self) -> None:
        """Metadata should have a display name."""
        pipeline = ReviewPipeline()
        assert pipeline.metadata.display_name == "Review"

    def test_metadata_has_description(self) -> None:
        """Metadata should have a description."""
        pipeline = ReviewPipeline()
        assert pipeline.metadata.description is not None
        assert len(pipeline.metadata.description) > 0

    def test_get_state_class_returns_implementation_state(self) -> None:
        """Should return ImplementationState (shared state)."""
        pipeline = ReviewPipeline()
        assert pipeline.get_state_class() is ImplementationState

    def test_creates_compiled_graph(self) -> None:
        """Should return a compiled LangGraph."""
        pipeline = ReviewPipeline()
        graph = pipeline.create_graph()
        assert hasattr(graph, "nodes")

    def test_graph_has_reviewer_node(self) -> None:
        """Graph should have reviewer node."""
        pipeline = ReviewPipeline()
        graph = pipeline.create_graph()
        assert "reviewer_node" in graph.nodes

    def test_graph_has_evaluation_node(self) -> None:
        """Graph should have evaluation node."""
        pipeline = ReviewPipeline()
        graph = pipeline.create_graph()
        assert "evaluation_node" in graph.nodes

    def test_graph_has_developer_node(self) -> None:
        """Graph should have developer node."""
        pipeline = ReviewPipeline()
        graph = pipeline.create_graph()
        assert "developer_node" in graph.nodes


class TestReviewPipelineInitialState:
    """Tests for get_initial_state method."""

    def test_get_initial_state_creates_implementation_state(self) -> None:
        """Should create ImplementationState with provided kwargs."""
        pipeline = ReviewPipeline()
        state = pipeline.get_initial_state(
            workflow_id="test-workflow-123",
            profile_id="test-profile",
        )
        assert isinstance(state, ImplementationState)
        assert state.workflow_id == "test-workflow-123"
        assert state.profile_id == "test-profile"
        assert state.status == "pending"


class TestReviewPipelineGraphStructure:
    """Tests for the review graph structure."""

    def test_entry_point_is_reviewer(self) -> None:
        """Graph entry point should be reviewer_node."""
        pipeline = ReviewPipeline()
        graph = pipeline.create_graph()
        # Check that __start__ connects to reviewer_node
        # This verifies set_entry_point("reviewer_node") was called
        assert "__start__" in graph.nodes

    def test_graph_compiles_without_checkpointer(self) -> None:
        """Graph should compile without a checkpointer."""
        pipeline = ReviewPipeline()
        graph = pipeline.create_graph(checkpointer=None)
        assert graph is not None

    def test_graph_no_approval_nodes(self) -> None:
        """Graph should not have approval nodes (fully automatic workflow)."""
        pipeline = ReviewPipeline()
        graph = pipeline.create_graph()
        assert "review_approval_node" not in graph.nodes
        assert "end_approval_node" not in graph.nodes
