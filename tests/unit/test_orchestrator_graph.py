from amelia.core.orchestrator import create_orchestrator_graph

def test_orchestrator_graph_structure():
    graph = create_orchestrator_graph()
    assert graph is not None
    # Further assertions on graph structure would go here
    # once nodes are added.
