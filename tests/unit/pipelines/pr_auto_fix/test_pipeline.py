"""Unit tests for PR auto-fix pipeline, graph, and registry integration."""

import uuid
from datetime import UTC, datetime

from amelia.pipelines.pr_auto_fix.graph import create_pr_auto_fix_graph
from amelia.pipelines.pr_auto_fix.pipeline import PRAutoFixPipeline
from amelia.pipelines.pr_auto_fix.state import PRAutoFixState


class TestPRAutoFixPipeline:
    """Tests for PRAutoFixPipeline class."""

    def test_metadata_name(self) -> None:
        pipeline = PRAutoFixPipeline()
        assert pipeline.metadata.name == "pr_auto_fix"

    def test_metadata_display_name(self) -> None:
        pipeline = PRAutoFixPipeline()
        assert pipeline.metadata.display_name == "PR Auto-Fix"

    def test_metadata_description(self) -> None:
        pipeline = PRAutoFixPipeline()
        assert pipeline.metadata.description == "Fix PR review comments automatically"

    def test_create_graph_returns_compiled(self) -> None:
        pipeline = PRAutoFixPipeline()
        graph = pipeline.create_graph()
        # CompiledStateGraph should have an invoke method
        assert hasattr(graph, "invoke")

    def test_get_initial_state_returns_pr_auto_fix_state(self) -> None:
        pipeline = PRAutoFixPipeline()
        state = pipeline.get_initial_state(
            workflow_id=uuid.uuid4(),
            profile_id="test",
            pr_number=1,
            head_branch="fix/bug",
            repo="owner/repo",
            created_at=datetime.now(tz=UTC),
        )
        assert isinstance(state, PRAutoFixState)
        assert state.pipeline_type == "pr_auto_fix"
        assert state.pr_number == 1
        assert state.head_branch == "fix/bug"
        assert state.repo == "owner/repo"

    def test_get_state_class(self) -> None:
        pipeline = PRAutoFixPipeline()
        assert pipeline.get_state_class() is PRAutoFixState


class TestPRAutoFixGraph:
    """Tests for create_pr_auto_fix_graph function."""

    def test_graph_compiles(self) -> None:
        graph = create_pr_auto_fix_graph()
        assert hasattr(graph, "invoke")

    def test_graph_has_classify_node(self) -> None:
        graph = create_pr_auto_fix_graph()
        node_names = set(graph.get_graph().nodes.keys())
        assert "classify_node" in node_names

    def test_graph_has_develop_node(self) -> None:
        graph = create_pr_auto_fix_graph()
        node_names = set(graph.get_graph().nodes.keys())
        assert "develop_node" in node_names

    def test_graph_has_commit_push_node(self) -> None:
        graph = create_pr_auto_fix_graph()
        node_names = set(graph.get_graph().nodes.keys())
        assert "commit_push_node" in node_names

    def test_graph_has_four_nodes(self) -> None:
        """Graph should have exactly 4 real nodes (plus __start__ and __end__)."""
        graph = create_pr_auto_fix_graph()
        node_names = set(graph.get_graph().nodes.keys()) - {"__start__", "__end__"}
        assert len(node_names) == 4

    def test_graph_entry_is_classify_node(self) -> None:
        """Entry point should route to classify_node."""
        graph = create_pr_auto_fix_graph()
        draw = graph.get_graph()
        # __start__ should have an edge to classify_node
        start_edges = [e for e in draw.edges if e.source == "__start__"]
        assert len(start_edges) == 1
        assert start_edges[0].target == "classify_node"

    def test_graph_linear_topology(self) -> None:
        """Graph should have linear edges: classify -> develop -> commit_push -> reply_resolve -> END."""
        graph = create_pr_auto_fix_graph()
        draw = graph.get_graph()
        edges = {(e.source, e.target) for e in draw.edges}
        assert ("classify_node", "develop_node") in edges
        assert ("develop_node", "commit_push_node") in edges
        assert ("commit_push_node", "reply_resolve_node") in edges
        assert ("reply_resolve_node", "__end__") in edges


class TestRegistryIntegration:
    """Tests for pr_auto_fix in PIPELINES registry."""

    def test_pr_auto_fix_in_pipelines(self) -> None:
        from amelia.pipelines.registry import PIPELINES

        assert "pr_auto_fix" in PIPELINES

    def test_get_pipeline_pr_auto_fix(self) -> None:
        from amelia.pipelines.registry import get_pipeline

        pipeline = get_pipeline("pr_auto_fix")
        assert pipeline.metadata.name == "pr_auto_fix"
