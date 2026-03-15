"""Unit tests for PR auto-fix pipeline, graph, and registry integration."""

import uuid
from datetime import UTC, datetime

import pytest

from amelia.pipelines.pr_auto_fix.graph import create_pr_auto_fix_graph
from amelia.pipelines.pr_auto_fix.pipeline import PRAutoFixPipeline
from amelia.pipelines.pr_auto_fix.state import PRAutoFixState


class TestPRAutoFixPipeline:
    """Tests for PRAutoFixPipeline class."""

    @pytest.fixture()
    def pipeline(self) -> PRAutoFixPipeline:
        return PRAutoFixPipeline()

    @pytest.mark.parametrize(
        ("attr", "expected"),
        [
            ("name", "pr_auto_fix"),
            ("display_name", "PR Auto-Fix"),
            ("description", "Fix PR review comments automatically"),
        ],
    )
    def test_metadata(self, pipeline: PRAutoFixPipeline, attr: str, expected: str) -> None:
        assert getattr(pipeline.metadata, attr) == expected

    def test_create_graph_returns_compiled(self, pipeline: PRAutoFixPipeline) -> None:
        assert hasattr(pipeline.create_graph(), "invoke")

    def test_get_initial_state_returns_pr_auto_fix_state(self, pipeline: PRAutoFixPipeline) -> None:
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

    def test_get_state_class(self, pipeline: PRAutoFixPipeline) -> None:
        assert pipeline.get_state_class() is PRAutoFixState


class TestPRAutoFixGraph:
    """Tests for create_pr_auto_fix_graph function."""

    @pytest.fixture()
    def graph_nodes(self) -> set[str]:
        return set(create_pr_auto_fix_graph().get_graph().nodes.keys())

    def test_graph_compiles(self) -> None:
        assert hasattr(create_pr_auto_fix_graph(), "invoke")

    @pytest.mark.parametrize(
        "node_name",
        ["classify_node", "develop_node", "commit_push_node", "reply_resolve_node"],
    )
    def test_graph_has_node(self, graph_nodes: set[str], node_name: str) -> None:
        assert node_name in graph_nodes

    def test_graph_has_four_nodes(self, graph_nodes: set[str]) -> None:
        assert len(graph_nodes - {"__start__", "__end__"}) == 4

    def test_graph_entry_is_classify_node(self) -> None:
        draw = create_pr_auto_fix_graph().get_graph()
        start_edges = [e for e in draw.edges if e.source == "__start__"]
        assert len(start_edges) == 1
        assert start_edges[0].target == "classify_node"

    def test_graph_linear_topology(self) -> None:
        edges = {(e.source, e.target) for e in create_pr_auto_fix_graph().get_graph().edges}
        for src, tgt in [
            ("classify_node", "develop_node"),
            ("develop_node", "commit_push_node"),
            ("commit_push_node", "reply_resolve_node"),
            ("reply_resolve_node", "__end__"),
        ]:
            assert (src, tgt) in edges


class TestRegistryIntegration:
    """Tests for pr_auto_fix in PIPELINES registry."""

    def test_pr_auto_fix_in_pipelines(self) -> None:
        from amelia.pipelines.registry import PIPELINES
        assert "pr_auto_fix" in PIPELINES

    def test_get_pipeline_pr_auto_fix(self) -> None:
        from amelia.pipelines.registry import get_pipeline
        assert get_pipeline("pr_auto_fix").metadata.name == "pr_auto_fix"
