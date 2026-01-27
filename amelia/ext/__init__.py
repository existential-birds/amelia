"""Extension interfaces for optional integrations.

Define protocols that enterprise or third-party integrations can implement
without modifying core source files. Core provides no-op default
implementations for all extension points.

Exports:
    WorkflowEventType: Enum of workflow event categories.
"""

from amelia.ext.protocols import WorkflowEventType


__all__ = [
    "WorkflowEventType",
]
