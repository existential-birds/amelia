"""No-op default implementations of extension protocols.

These implementations satisfy the protocols but do nothing, allowing
Core to function without any extensions registered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from amelia.ext.protocols import (
    AnalyticsSink,
    AuditExporter,
    AuthProvider,
    PolicyHook,
    WorkflowEvent,
)


if TYPE_CHECKING:
    from amelia.core.types import Profile


class NoopPolicyHook(PolicyHook):
    """No-op policy hook that allows all operations."""

    async def on_workflow_start(
        self,
        workflow_id: str,
        profile: Profile,
        issue_id: str,
    ) -> bool:
        """Always allow workflow start."""
        return True

    async def on_approval_request(
        self,
        workflow_id: str,
        approval_type: str,
    ) -> bool | None:
        """Proceed with normal approval flow."""
        return None


class NoopAuditExporter(AuditExporter):
    """No-op audit exporter that discards all events."""

    async def export(self, event: WorkflowEvent) -> None:
        """Discard the event."""
        pass

    async def flush(self) -> None:
        """Nothing to flush."""
        pass


class NoopAnalyticsSink(AnalyticsSink):
    """No-op analytics sink that discards all metrics."""

    async def record_metric(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Discard the metric."""
        pass

    async def record_event(
        self,
        name: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Discard the event."""
        pass


class NoopAuthProvider(AuthProvider):
    """No-op auth provider that allows all access.

    This provider authenticates all tokens as a default user and
    authorizes all actions. Use only when authentication is not required.
    """

    async def authenticate(self, token: str) -> dict[str, Any] | None:
        """Return a default user context for any token."""
        return {"user_id": "local", "name": "Local User"}

    async def authorize(
        self,
        user_context: dict[str, Any],
        action: str,
        resource: str | None = None,
    ) -> bool:
        """Always authorize."""
        return True
