"""Pipeline abstraction layer for Amelia workflows.

This package provides the foundational types and registry for multiple
workflow pipelines (Implementation, Review, etc.).

Exports:
    Pipeline: Protocol that all pipelines implement.
    PipelineMetadata: Immutable metadata describing a pipeline.
    BasePipelineState: Common state fields shared by all pipelines.
    HistoryEntry: Structured history entry for agent actions.
    get_pipeline: Factory function to get a pipeline by name.
    list_pipelines: List all available pipelines.
"""

from amelia.pipelines.base import (
    BasePipelineState,
    HistoryEntry,
    Pipeline,
    PipelineMetadata,
)


__all__ = [
    "BasePipelineState",
    "HistoryEntry",
    "Pipeline",
    "PipelineMetadata",
]
