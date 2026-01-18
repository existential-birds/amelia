"""Amelia: A local agentic coding orchestrator.

Provide a LangGraph-based orchestrator that coordinates specialized AI agents
(Architect, Developer, Reviewer) to autonomously implement features from issue
descriptions.

Exports:
    app: The Typer CLI application entry point.
    create_orchestrator_graph: Factory function for the LangGraph state machine.
    ExecutionState: The core state type passed through the orchestration graph.
    load_settings: Load configuration from settings.amelia.yaml.
    get_pipeline: Factory function to get a pipeline by name.
    ImplementationState: State type for the implementation pipeline.
    create_implementation_graph: Factory for the implementation pipeline graph.
    __version__: Package version string.
"""

from amelia.config import load_settings
from amelia.core.orchestrator import create_orchestrator_graph
from amelia.core.state import ExecutionState
from amelia.main import app
from amelia.pipelines import get_pipeline
from amelia.pipelines.implementation import (
    ImplementationState,
    create_implementation_graph,
)


# Backward compatibility alias (temporary)
# ExecutionState from core.state is kept for backward compatibility
# New code should use ImplementationState from pipelines.implementation

__version__ = "0.9.0"

__all__ = [
    "ExecutionState",
    "ImplementationState",
    "__version__",
    "app",
    "create_implementation_graph",
    "create_orchestrator_graph",
    "get_pipeline",
    "load_settings",
]
