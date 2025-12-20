# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Extension interfaces for optional integrations.

This package defines protocols that Enterprise or third-party integrations
can implement without modifying Core source files. Core provides no-op
default implementations.

Extension Points:
    - PolicyHook: Intercept decisions (approvals, resource limits)
    - AuditExporter: Export workflow events to external systems
    - AnalyticsSink: Send telemetry to observability platforms
    - AuthProvider: Plug in authentication mechanisms

Example:
    >>> from amelia.ext import get_registry
    >>> registry = get_registry()
    >>> registry.register_audit_exporter(my_exporter)

Hook Functions:
    For convenience, Core can use the hook functions to invoke extensions:

    >>> from amelia.ext.hooks import emit_workflow_event, check_policy_workflow_start
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
