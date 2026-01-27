"""Pipeline abstraction layer for Amelia workflows.

This package provides the foundational types and registry for multiple
workflow pipelines (Implementation, Review, etc.).

Exports:
    get_pipeline: Factory function to get a pipeline by name.
"""

from amelia.pipelines.registry import get_pipeline


__all__ = [
    "get_pipeline",
]
