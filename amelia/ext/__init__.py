"""Extension interfaces for optional integrations.

Define protocols that enterprise or third-party integrations can implement
without modifying core source files. Core provides no-op default
implementations for all extension points.

Extension Points:
    PolicyHook: Intercept decisions (approvals, resource limits).
    AuditExporter: Export workflow events to external systems.
    AnalyticsSink: Send telemetry to observability platforms.
    AuthProvider: Plug in authentication mechanisms.

Example:
    >>> from amelia.ext import get_registry
    >>> registry = get_registry()
    >>> registry.register_audit_exporter(my_exporter)

Exports:
    PolicyHook: Protocol for policy enforcement hooks.
    AuditExporter: Protocol for audit event exporters.
    AnalyticsSink: Protocol for analytics/telemetry sinks.
    AuthProvider: Protocol for authentication providers.
    WorkflowEvent: Event model for workflow state changes.
    WorkflowEventType: Enum of workflow event categories.
    JsonValue: Type alias for JSON-serializable values.
    ExtensionRegistry: Central registry for extension instances.
    get_registry: Retrieve the global extension registry singleton.
    emit_workflow_event: Emit an event to all registered exporters.
    check_policy_workflow_start: Check policy before workflow starts.
    check_policy_approval: Check policy before approving changes.
    record_metric: Record a metric to all analytics sinks.
    flush_exporters: Flush all pending audit events.
    PolicyDeniedError: Raised when a policy check fails.
"""

from amelia.ext.exceptions import PolicyDeniedError
from amelia.ext.hooks import (
    check_policy_approval,
    check_policy_workflow_start,
    emit_workflow_event,
    flush_exporters,
    record_metric,
)
from amelia.ext.protocols import (
    AnalyticsSink,
    AuditExporter,
    AuthProvider,
    JsonValue,
    PolicyHook,
    WorkflowEvent,
    WorkflowEventType,
)
from amelia.ext.registry import ExtensionRegistry, get_registry


__all__ = [
    # Protocols
    "PolicyHook",
    "AuditExporter",
    "AnalyticsSink",
    "AuthProvider",
    "WorkflowEvent",
    "WorkflowEventType",
    "JsonValue",
    # Registry
    "ExtensionRegistry",
    "get_registry",
    # Hook functions
    "emit_workflow_event",
    "check_policy_workflow_start",
    "check_policy_approval",
    "record_metric",
    "flush_exporters",
    # Exceptions
    "PolicyDeniedError",
]
