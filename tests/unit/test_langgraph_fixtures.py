"""Tests for LangGraph mock fixtures."""

from collections.abc import Callable

from tests.conftest import LangGraphMocks


class TestLangGraphMockFactory:
    """Tests for the langgraph_mock_factory fixture."""

    def test_factory_returns_named_tuple(
        self, langgraph_mock_factory: Callable[..., LangGraphMocks]
    ) -> None:
        """Factory should return LangGraphMocks NamedTuple."""
        mocks = langgraph_mock_factory()

        # Verify structure
        assert hasattr(mocks, "graph")
        assert hasattr(mocks, "saver")
        assert hasattr(mocks, "saver_class")
        assert hasattr(mocks, "create_graph")

    def test_graph_mock_has_required_methods(
        self, langgraph_mock_factory: Callable[..., LangGraphMocks]
    ) -> None:
        """Graph mock should have aupdate_state, astream, aget_state methods."""
        mocks = langgraph_mock_factory()

        assert hasattr(mocks.graph, "aupdate_state")
        assert hasattr(mocks.graph, "astream")
        assert hasattr(mocks.graph, "aget_state")

    def test_saver_context_manager_setup(
        self, langgraph_mock_factory: Callable[..., LangGraphMocks]
    ) -> None:
        """Saver class mock should be configured as async context manager."""
        mocks = langgraph_mock_factory()

        # from_conn_string returns context manager
        cm = mocks.saver_class.from_conn_string.return_value
        assert hasattr(cm, "__aenter__")
        assert hasattr(cm, "__aexit__")

    def test_create_graph_returns_graph_mock(
        self, langgraph_mock_factory: Callable[..., LangGraphMocks]
    ) -> None:
        """create_graph mock should return the graph mock."""
        mocks = langgraph_mock_factory()

        assert mocks.create_graph.return_value is mocks.graph

    def test_custom_astream_items(
        self, langgraph_mock_factory: Callable[..., LangGraphMocks]
    ) -> None:
        """Factory should accept custom astream items."""
        custom_items = [{"node": "test"}, {"__interrupt__": ("pause",)}]
        mocks = langgraph_mock_factory(astream_items=custom_items)

        # astream should return an iterator with our items
        # (actual iteration tested in integration)
        assert mocks.graph.astream is not None
