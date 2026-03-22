"""Pipeline registry for routing to pipeline implementations.

This module provides the central registry for all available pipelines
and factory functions to instantiate them.
"""

from typing import Any

from amelia.pipelines.base import Pipeline
from amelia.pipelines.implementation.pipeline import ImplementationPipeline
from amelia.pipelines.pr_auto_fix.pipeline import PRAutoFixPipeline
from amelia.pipelines.review.pipeline import ReviewPipeline


# Registry mapping pipeline names to their classes
PIPELINES: dict[str, type[Pipeline[Any]]] = {
    "implementation": ImplementationPipeline,
    "pr_auto_fix": PRAutoFixPipeline,
    "review": ReviewPipeline,
}


def get_pipeline(name: str) -> Pipeline[Any]:
    """Get a pipeline instance by name.

    Creates a fresh instance on each call (stateless factories).

    Args:
        name: Pipeline name (e.g., "implementation", "review").

    Returns:
        Pipeline instance ready for use.

    Raises:
        ValueError: If pipeline name is not registered.
    """
    if name not in PIPELINES:
        raise ValueError(f"Unknown pipeline: {name}")
    return PIPELINES[name]()
