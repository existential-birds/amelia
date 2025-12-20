# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Convenience functions for calling extension hooks.

These functions provide a simple interface for Core to invoke
registered extensions without needing to handle the registry directly.

Usage in server layer:
    from amelia.ext.hooks import emit_workflow_event, check_policy

    # Emit lifecycle events
    await emit_workflow_event(
        WorkflowEventType.STARTED,
        workflow_id=workflow.id,
    )

    # Check policy before actions
    allowed = await check_policy_workflow_start(
        workflow_id=workflow.id,
        profile=profile,
        issue_id=issue_id,
    )
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from loguru import logger

from amelia.ext.protocols import JsonValue, WorkflowEvent, WorkflowEventType
from amelia.ext.registry import get_registry


if TYPE_CHECKING:
    from amelia.core.types import Profile


async def emit_workflow_event(
    event_type: WorkflowEventType,
    workflow_id: str,
    stage: str | None = None,
    metadata: dict[str, JsonValue] | None = None,
) -> None:
    """Emit a workflow lifecycle event to all registered exporters and sinks.

    This function handles errors gracefully - extension failures do not
    block workflow execution.

    Args:
        event_type: Type of event that occurred.
        workflow_id: Unique identifier for the workflow.
        stage: Current workflow stage (optional).
        metadata: Additional event data (optional).
    """
    event = WorkflowEvent(
        event_type=event_type,
        workflow_id=workflow_id,
        timestamp=datetime.now(UTC),
        stage=stage,
        metadata=metadata,
    )

    registry = get_registry()

    # Export to audit systems
    for exporter in registry.audit_exporters:
        try:
            await exporter.export(event)
        except Exception as e:
            logger.warning(
                "Audit exporter failed: {error}",
                error=str(e),
                exporter=type(exporter).__name__,
            )

    # Record analytics event
    for sink in registry.analytics_sinks:
        try:
            await sink.record_event(
                f"workflow.{event_type.value}",
                properties={
                    "workflow_id": workflow_id,
                    "stage": stage,
                    **(metadata or {}),
                },
            )
        except Exception as e:
            logger.warning(
                "Analytics sink failed: {error}",
                error=str(e),
                sink=type(sink).__name__,
            )


async def check_policy_workflow_start(
    workflow_id: str,
    profile: Profile,
    issue_id: str,
) -> tuple[bool, str | None]:
    """Check if a workflow is allowed to start.

    All registered policy hooks must return True for the workflow to proceed.

    Args:
        workflow_id: Unique identifier for the workflow.
        profile: Profile configuration being used.
        issue_id: Issue being worked on.

    Returns:
        Tuple of (allowed, denial_reason) where:
        - allowed: True if all policies allow the workflow, False otherwise.
        - denial_reason: Name of the hook that denied, or None if allowed.
    """
    registry = get_registry()

    for hook in registry.policy_hooks:
        hook_name = type(hook).__name__
        try:
            allowed = await hook.on_workflow_start(workflow_id, profile, issue_id)
            if not allowed:
                logger.info(
                    "Policy hook denied workflow start: {hook}",
                    hook=hook_name,
                    workflow_id=workflow_id,
                )
                return (False, hook_name)
        except Exception as e:
            logger.error(
                "Policy hook error, denying by default: {error}",
                error=str(e),
                hook=hook_name,
            )
            return (False, hook_name)

    return (True, None)


async def check_policy_approval(
    workflow_id: str,
    approval_type: str,
) -> bool | None:
    """Check if policy hooks want to override an approval request.

    This is an extension point for Enterprise packages to implement automatic
    approval/denial policies. It is not currently called by the orchestrator
    service but is exported and tested for future integration.

    Enterprise use cases:
        - Auto-approve workflows from trusted issuers
        - Auto-deny workflows that exceed cost thresholds
        - Integrate with external approval systems (e.g., PagerDuty, ServiceNow)

    Args:
        workflow_id: Unique identifier for the workflow.
        approval_type: Type of approval being requested.

    Returns:
        True to auto-approve, False to auto-deny, None for normal flow.
    """
    registry = get_registry()

    for hook in registry.policy_hooks:
        try:
            result = await hook.on_approval_request(workflow_id, approval_type)
            if result is not None:
                logger.info(
                    "Policy hook {action} approval: {hook}",
                    action="granted" if result else "denied",
                    hook=type(hook).__name__,
                    workflow_id=workflow_id,
                )
                return result
        except Exception as e:
            logger.warning(
                "Policy hook error during approval check: {error}",
                error=str(e),
                hook=type(hook).__name__,
            )
            # Continue to next hook on error.
            # Unlike on_workflow_start (which denies on error as fail-safe),
            # on_approval_request has three-state semantics (True/False/None).
            # An error doesn't imply approval or denial, so we skip to next hook.

    return None


async def record_metric(
    name: str,
    value: float,
    tags: dict[str, str] | None = None,
) -> None:
    """Record a metric to all registered analytics sinks.

    Args:
        name: Metric name (e.g., "workflow.duration_seconds").
        value: Metric value.
        tags: Optional tags for metric dimensions.

    Example:
        >>> await record_metric(
        ...     "workflow.duration_seconds",
        ...     45.2,
        ...     tags={"profile": "work", "status": "success"},
        ... )
    """
    registry = get_registry()

    for sink in registry.analytics_sinks:
        try:
            await sink.record_metric(name, value, tags)
        except Exception as e:
            logger.warning(
                "Analytics sink failed to record metric: {error}",
                error=str(e),
                sink=type(sink).__name__,
            )


async def flush_exporters() -> None:
    """Flush all audit exporters.

    Should be called during graceful shutdown to ensure all buffered
    audit events are exported before the process exits.

    Example:
        >>> import signal
        >>> async def shutdown_handler():
        ...     await flush_exporters()
        ...     # ... other cleanup
    """
    registry = get_registry()

    for exporter in registry.audit_exporters:
        try:
            await exporter.flush()
        except Exception as e:
            logger.warning(
                "Failed to flush audit exporter: {error}",
                error=str(e),
                exporter=type(exporter).__name__,
            )
