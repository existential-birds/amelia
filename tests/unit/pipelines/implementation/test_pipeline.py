"""Unit tests for ImplementationPipeline."""

from amelia.pipelines.base import PipelineMetadata
from amelia.pipelines.implementation.pipeline import ImplementationPipeline
from amelia.pipelines.implementation.state import (
    ImplementationState,
    rebuild_implementation_state,
)


# Rebuild to resolve forward references for Pydantic
rebuild_implementation_state()


class TestImplementationPipelineProtocol:
    """Tests that ImplementationPipeline satisfies Pipeline protocol."""

    def test_has_metadata_property(self) -> None:
        """Should have metadata property returning PipelineMetadata."""
        pipeline = ImplementationPipeline()
        meta = pipeline.metadata
        assert isinstance(meta, PipelineMetadata)

    def test_metadata_name_is_implementation(self) -> None:
        """Metadata name should be 'implementation'."""
        pipeline = ImplementationPipeline()
        assert pipeline.metadata.name == "implementation"

    def test_metadata_display_name(self) -> None:
        """Metadata display_name should be 'Implementation'."""
        pipeline = ImplementationPipeline()
        assert pipeline.metadata.display_name == "Implementation"

    def test_metadata_has_description(self) -> None:
        """Metadata should have a description."""
        pipeline = ImplementationPipeline()
        assert pipeline.metadata.description
        assert len(pipeline.metadata.description) > 10

    def test_has_create_graph_method(self) -> None:
        """Should have create_graph method."""
        pipeline = ImplementationPipeline()
        assert hasattr(pipeline, "create_graph")
        assert callable(pipeline.create_graph)

    def test_get_state_class_returns_implementation_state(self) -> None:
        """Should return ImplementationState class."""
        pipeline = ImplementationPipeline()
        assert pipeline.get_state_class() is ImplementationState

    def test_creates_valid_initial_state(self) -> None:
        """Should create a valid ImplementationState."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id="wf-test",
            profile_id="default",
        )
        assert isinstance(state, ImplementationState)
        assert state.workflow_id == "wf-test"
        assert state.profile_id == "default"
        assert state.status == "pending"
        assert state.pipeline_type == "implementation"

    def test_creates_compiled_graph(self) -> None:
        """Should return a compiled LangGraph."""
        pipeline = ImplementationPipeline()
        graph = pipeline.create_graph()
        # Compiled graph should have nodes attribute
        assert hasattr(graph, "nodes")


class TestImplementationPipelineGraph:
    """Tests for the compiled graph structure."""

    def test_graph_has_required_nodes(self) -> None:
        """Graph should contain all required nodes."""
        pipeline = ImplementationPipeline()
        graph = pipeline.create_graph()

        # Check that expected node names exist
        node_names = set(graph.nodes.keys())
        expected_nodes = {
            "architect_node",
            "plan_validator_node",
            "human_approval_node",
            "developer_node",
            "reviewer_node",
            "next_task_node",
        }
        assert expected_nodes.issubset(node_names), (
            f"Missing nodes: {expected_nodes - node_names}"
        )

    def test_graph_accepts_checkpointer(self) -> None:
        """Should accept an optional checkpointer argument."""
        pipeline = ImplementationPipeline()
        # Should not raise when called with None
        graph = pipeline.create_graph(checkpointer=None)
        assert graph is not None


class TestImplementationPipelineInitialState:
    """Tests for initial state creation."""

    def test_initial_state_has_workflow_id(self) -> None:
        """Initial state should have workflow_id set."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id="wf-abc123",
            profile_id="default",
        )
        assert state.workflow_id == "wf-abc123"

    def test_initial_state_has_profile_id(self) -> None:
        """Initial state should have profile_id set."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id="wf-test",
            profile_id="my-profile",
        )
        assert state.profile_id == "my-profile"

    def test_initial_state_has_created_at(self) -> None:
        """Initial state should have created_at timestamp."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id="wf-test",
            profile_id="default",
        )
        assert state.created_at is not None

    def test_initial_state_is_pending(self) -> None:
        """Initial state should have status='pending'."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id="wf-test",
            profile_id="default",
        )
        assert state.status == "pending"

    def test_initial_state_has_empty_history(self) -> None:
        """Initial state should have empty history."""
        pipeline = ImplementationPipeline()
        state = pipeline.get_initial_state(
            workflow_id="wf-test",
            profile_id="default",
        )
        assert state.history == []
