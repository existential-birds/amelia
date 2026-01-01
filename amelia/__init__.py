"""Amelia: A local agentic coding orchestrator.

Provide a LangGraph-based orchestrator that coordinates specialized AI agents
(Architect, Developer, Reviewer) to autonomously implement features from issue
descriptions.

Exports:
    app: The Typer CLI application entry point.
    create_orchestrator_graph: Factory function for the LangGraph state machine.
    ExecutionState: The core state type passed through the orchestration graph.
    load_settings: Load configuration from settings.amelia.yaml.
    __version__: Package version string.
"""

from amelia.config import load_settings
from amelia.core.orchestrator import create_orchestrator_graph
from amelia.core.state import ExecutionState
from amelia.main import app


__version__ = "0.1.0"

__all__ = [
    "app",
    "create_orchestrator_graph",
    "ExecutionState",
    "load_settings",
    "__version__",
]
