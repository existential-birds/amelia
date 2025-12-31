"""Amelia: A local agentic coding system."""

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
