"""Extension protocols for optional integrations.

These protocols define the interfaces that Enterprise or third-party
integrations can implement. Core provides no-op default implementations
in amelia.ext.noop.

Note: These interfaces must have zero dependencies on any enterprise package.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, model_validator


# Type alias for JSON-compatible values used in metadata fields.
# Using Any here because metadata can contain arbitrary JSON-like structures
# (str, int, float, bool, None, lists, nested dicts) that vary by use case.
type JsonValue = Any


if TYPE_CHECKING:
    from amelia.core.types import Profile


class WorkflowEventType(Enum):
    """Types of workflow lifecycle events."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    RESUMED = "resumed"
    STAGE_ENTERED = "stage_entered"
    STAGE_EXITED = "stage_exited"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"


class WorkflowEvent(BaseModel):
    """Immutable record of a workflow lifecycle event.

    Attributes:
        event_type: The type of event that occurred.
        workflow_id: Unique identifier for the workflow.
        timestamp: When the event occurred.
        metadata: Additional event-specific data (immutable mapping).
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    event_type: WorkflowEventType
    workflow_id: str
    timestamp: datetime
    metadata: Mapping[str, JsonValue] | None = None

    @model_validator(mode="before")
    @classmethod
    def convert_metadata_to_immutable(
        cls, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert metadata dict to immutable MappingProxyType."""
        if isinstance(data, dict) and "metadata" in data:
            m = data["metadata"]
            if m is not None and not isinstance(m, MappingProxyType):
                data = dict(data)  # Make a copy to avoid mutating input
                data["metadata"] = MappingProxyType(m)
        return data


@runtime_checkable
class PolicyHook(Protocol):
    """Protocol for intercepting and controlling workflow decisions.

    Policy hooks can approve/deny actions, enforce resource limits,
    and inject custom validation logic into the workflow lifecycle.

    Enterprise implementations might enforce:
    - Rate limits per user/organization
    - Approval workflows for certain operations
    - Resource quotas (concurrent workflows, API calls, etc.)
    """

    async def on_workflow_start(
        self,
        workflow_id: str,
        profile: Profile,
        issue_id: str,
    ) -> bool:
        """Called before a workflow starts.

        Args:
            workflow_id: Unique identifier for the workflow.
            profile: The profile configuration being used.
            issue_id: The issue being worked on.

        Returns:
            True to allow the workflow to start, False to deny.
        """
        ...

    async def on_approval_request(
        self,
        workflow_id: str,
        approval_type: str,
    ) -> bool | None:
        """Called when the workflow requests human approval.

        Args:
            workflow_id: Unique identifier for the workflow.
            approval_type: Type of approval being requested (e.g., "plan", "review").

        Returns:
            True to auto-approve, False to auto-deny, None to proceed normally.
        """
        ...


@runtime_checkable
class AuditExporter(Protocol):
    """Protocol for exporting workflow events to external systems.

    Audit exporters receive all workflow lifecycle events and can
    forward them to:
    - SIEM systems
    - Compliance logging services
    - Data warehouses for analysis

    Enterprise implementations might:
    - Filter events based on sensitivity
    - Enrich events with organizational context
    - Batch and buffer events for efficiency
    """

    async def export(self, event: WorkflowEvent) -> None:
        """Export a workflow event to an external system.

        Args:
            event: The workflow event to export.

        Note:
            Implementations should handle their own error recovery.
            Failures should not block workflow execution.
        """
        ...

    async def flush(self) -> None:
        """Flush any buffered events.

        Called during graceful shutdown to ensure all events are exported.
        """
        ...


@runtime_checkable
class AnalyticsSink(Protocol):
    """Protocol for sending telemetry to observability platforms.

    Analytics sinks receive metrics and traces that can be used for:
    - Performance monitoring
    - Cost tracking
    - Usage analytics

    Enterprise implementations might send data to:
    - Prometheus/Grafana
    - Datadog
    - Custom analytics backends
    """

    async def record_metric(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Record a numeric metric.

        Args:
            name: Metric name (e.g., "workflow.duration_seconds").
            value: Metric value.
            tags: Optional tags for metric dimensions.
        """
        ...

    async def record_event(
        self,
        name: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Record a discrete event.

        Args:
            name: Event name (e.g., "workflow.completed").
            properties: Optional event properties.
        """
        ...


@runtime_checkable
class AuthProvider(Protocol):
    """Protocol for authentication mechanisms.

    Auth providers handle user authentication and can integrate with:
    - SSO/SAML providers
    - OAuth2/OIDC
    - API key validation

    Enterprise implementations might:
    - Validate tokens against an identity provider
    - Enforce session policies
    - Provide user context for audit logging
    """

    async def authenticate(self, token: str) -> dict[str, Any] | None:
        """Authenticate a user from a token.

        Args:
            token: Authentication token (JWT, API key, etc.).

        Returns:
            User context dict if authenticated, None if invalid.
            Context should include at minimum: {"user_id": str}
        """
        ...

    async def authorize(
        self,
        user_context: dict[str, Any],
        action: str,
        resource: str | None = None,
    ) -> bool:
        """Check if a user is authorized for an action.

        Args:
            user_context: User context from authenticate().
            action: Action being performed (e.g., "workflow:create").
            resource: Optional resource identifier.

        Returns:
            True if authorized, False otherwise.
        """
        ...
