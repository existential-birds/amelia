# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Unit tests for amelia.ext.hooks module."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from amelia.core.types import Profile
from amelia.ext.hooks import (
    check_policy_approval,
    check_policy_workflow_start,
    emit_workflow_event,
    flush_exporters,
    record_metric,
)
from amelia.ext.protocols import WorkflowEvent, WorkflowEventType
from amelia.ext.registry import ExtensionRegistry


# Mock Protocol Implementations


class MockPolicyHook:
    """Mock implementation of PolicyHook protocol."""

    def __init__(
        self,
        workflow_start_result: bool = True,
        approval_request_result: bool | None = None,
    ) -> None:
        self.workflow_start_result = workflow_start_result
        self.approval_request_result = approval_request_result
        self.on_workflow_start = AsyncMock(return_value=workflow_start_result)
        self.on_approval_request = AsyncMock(return_value=approval_request_result)


class MockAuditExporter:
    """Mock implementation of AuditExporter protocol."""

    def __init__(self, export_error: Exception | None = None) -> None:
        self.export_error = export_error
        self.export = AsyncMock(side_effect=export_error)
        self.flush = AsyncMock()


class MockAnalyticsSink:
    """Mock implementation of AnalyticsSink protocol."""

    def __init__(
        self,
        metric_error: Exception | None = None,
        event_error: Exception | None = None,
    ) -> None:
        self.metric_error = metric_error
        self.event_error = event_error
        self.record_metric = AsyncMock(side_effect=metric_error)
        self.record_event = AsyncMock(side_effect=event_error)


# Fixtures


@pytest.fixture
def mock_registry() -> ExtensionRegistry:
    """Create a mock ExtensionRegistry for testing."""
    return ExtensionRegistry()


@pytest.fixture
def mock_profile() -> Profile:
    """Create a mock Profile for testing."""
    return Profile(
        name="test",
        driver="cli:claude",
        tracker="noop",
        strategy="single",
    )


# Tests for emit_workflow_event


async def test_emit_workflow_event_success_with_exporters_and_sinks(
    mock_registry: ExtensionRegistry,
) -> None:
    """Test emit_workflow_event successfully exports to multiple exporters and sinks."""
    # Setup
    exporter1 = MockAuditExporter()
    exporter2 = MockAuditExporter()
    sink1 = MockAnalyticsSink()
    sink2 = MockAnalyticsSink()

    mock_registry.register_audit_exporter(exporter1)
    mock_registry.register_audit_exporter(exporter2)
    mock_registry.register_analytics_sink(sink1)
    mock_registry.register_analytics_sink(sink2)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        await emit_workflow_event(
            event_type=WorkflowEventType.STARTED,
            workflow_id="test-workflow-123",
            stage="architect",
            metadata={"issue_id": "TEST-456", "profile": "work"},
        )

    # Verify exporters called with WorkflowEvent
    assert exporter1.export.call_count == 1
    assert exporter2.export.call_count == 1

    event = exporter1.export.call_args[0][0]
    assert isinstance(event, WorkflowEvent)
    assert event.event_type == WorkflowEventType.STARTED
    assert event.workflow_id == "test-workflow-123"
    assert event.stage == "architect"
    assert event.metadata == {"issue_id": "TEST-456", "profile": "work"}

    # Verify sinks called with event name and properties
    assert sink1.record_event.call_count == 1
    assert sink2.record_event.call_count == 1

    sink1.record_event.assert_called_once_with(
        "workflow.started",
        properties={
            "workflow_id": "test-workflow-123",
            "stage": "architect",
            "issue_id": "TEST-456",
            "profile": "work",
        },
    )


async def test_emit_workflow_event_handles_exporter_failure_gracefully() -> None:
    """Test emit_workflow_event handles exporter failures without raising."""
    # Setup
    failing_exporter = MockAuditExporter(export_error=RuntimeError("Export failed"))
    working_exporter = MockAuditExporter()

    mock_registry = ExtensionRegistry()
    mock_registry.register_audit_exporter(failing_exporter)
    mock_registry.register_audit_exporter(working_exporter)

    # Execute - should not raise
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        await emit_workflow_event(
            event_type=WorkflowEventType.COMPLETED,
            workflow_id="test-workflow",
        )

    # Verify both were called (failure didn't stop execution)
    assert failing_exporter.export.call_count == 1
    assert working_exporter.export.call_count == 1


async def test_emit_workflow_event_handles_sink_failure_gracefully() -> None:
    """Test emit_workflow_event handles analytics sink failures without raising."""
    # Setup
    failing_sink = MockAnalyticsSink(event_error=RuntimeError("Sink failed"))
    working_sink = MockAnalyticsSink()

    mock_registry = ExtensionRegistry()
    mock_registry.register_analytics_sink(failing_sink)
    mock_registry.register_analytics_sink(working_sink)

    # Execute - should not raise
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        await emit_workflow_event(
            event_type=WorkflowEventType.FAILED,
            workflow_id="test-workflow",
        )

    # Verify both were called
    assert failing_sink.record_event.call_count == 1
    assert working_sink.record_event.call_count == 1


async def test_emit_workflow_event_with_no_metadata() -> None:
    """Test emit_workflow_event works correctly with no metadata."""
    # Setup
    exporter = MockAuditExporter()
    sink = MockAnalyticsSink()

    mock_registry = ExtensionRegistry()
    mock_registry.register_audit_exporter(exporter)
    mock_registry.register_analytics_sink(sink)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        await emit_workflow_event(
            event_type=WorkflowEventType.STARTED,
            workflow_id="test-workflow",
        )

    # Verify event created with None metadata
    event = exporter.export.call_args[0][0]
    assert event.metadata is None

    # Verify sink properties don't include metadata fields
    sink.record_event.assert_called_once_with(
        "workflow.started",
        properties={
            "workflow_id": "test-workflow",
            "stage": None,
        },
    )


# Tests for check_policy_workflow_start


async def test_check_policy_workflow_start_all_hooks_allow(
    mock_registry: ExtensionRegistry,
    mock_profile: Profile,
) -> None:
    """Test check_policy_workflow_start returns True when all hooks allow."""
    # Setup
    hook1 = MockPolicyHook(workflow_start_result=True)
    hook2 = MockPolicyHook(workflow_start_result=True)

    mock_registry.register_policy_hook(hook1)
    mock_registry.register_policy_hook(hook2)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        allowed, denial_reason = await check_policy_workflow_start(
            workflow_id="test-workflow",
            profile=mock_profile,
            issue_id="TEST-123",
        )

    # Verify
    assert allowed is True
    assert denial_reason is None
    assert hook1.on_workflow_start.call_count == 1
    assert hook2.on_workflow_start.call_count == 1

    hook1.on_workflow_start.assert_called_once_with(
        "test-workflow", mock_profile, "TEST-123"
    )


async def test_check_policy_workflow_start_any_hook_denies(
    mock_registry: ExtensionRegistry,
    mock_profile: Profile,
) -> None:
    """Test check_policy_workflow_start returns False when any hook denies."""
    # Setup
    hook1 = MockPolicyHook(workflow_start_result=True)
    hook2 = MockPolicyHook(workflow_start_result=False)
    hook3 = MockPolicyHook(workflow_start_result=True)

    mock_registry.register_policy_hook(hook1)
    mock_registry.register_policy_hook(hook2)
    mock_registry.register_policy_hook(hook3)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        allowed, denial_reason = await check_policy_workflow_start(
            workflow_id="test-workflow",
            profile=mock_profile,
            issue_id="TEST-123",
        )

    # Verify
    assert allowed is False
    assert denial_reason == "MockPolicyHook"
    # First two hooks should be called
    assert hook1.on_workflow_start.call_count == 1
    assert hook2.on_workflow_start.call_count == 1
    # Third hook should NOT be called (early return)
    assert hook3.on_workflow_start.call_count == 0


async def test_check_policy_workflow_start_hook_exception_denies(
    mock_registry: ExtensionRegistry,
    mock_profile: Profile,
) -> None:
    """Test check_policy_workflow_start returns False on hook exception (fail-safe)."""
    # Setup
    failing_hook = MockPolicyHook()
    failing_hook.on_workflow_start.side_effect = RuntimeError("Hook error")
    working_hook = MockPolicyHook(workflow_start_result=True)

    mock_registry.register_policy_hook(failing_hook)
    mock_registry.register_policy_hook(working_hook)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        allowed, denial_reason = await check_policy_workflow_start(
            workflow_id="test-workflow",
            profile=mock_profile,
            issue_id="TEST-123",
        )

    # Verify - fail-safe behavior: deny on error
    assert allowed is False
    assert denial_reason == "MockPolicyHook"
    assert failing_hook.on_workflow_start.call_count == 1
    # Working hook should NOT be called (early return on error)
    assert working_hook.on_workflow_start.call_count == 0


async def test_check_policy_workflow_start_no_hooks_allows(
    mock_profile: Profile,
) -> None:
    """Test check_policy_workflow_start returns True when no hooks are registered."""
    # Setup - empty registry
    mock_registry = ExtensionRegistry()

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        allowed, denial_reason = await check_policy_workflow_start(
            workflow_id="test-workflow",
            profile=mock_profile,
            issue_id="TEST-123",
        )

    # Verify - no hooks means allow
    assert allowed is True
    assert denial_reason is None


# Tests for check_policy_approval


async def test_check_policy_approval_no_override_returns_none(
    mock_registry: ExtensionRegistry,
) -> None:
    """Test check_policy_approval returns None when no hooks override."""
    # Setup - hooks return None (no override)
    hook1 = MockPolicyHook(approval_request_result=None)
    hook2 = MockPolicyHook(approval_request_result=None)

    mock_registry.register_policy_hook(hook1)
    mock_registry.register_policy_hook(hook2)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        result = await check_policy_approval(
            workflow_id="test-workflow",
            approval_type="plan",
        )

    # Verify
    assert result is None
    assert hook1.on_approval_request.call_count == 1
    assert hook2.on_approval_request.call_count == 1


async def test_check_policy_approval_hook_overrides_to_approve(
    mock_registry: ExtensionRegistry,
) -> None:
    """Test check_policy_approval returns True when hook overrides to approve."""
    # Setup
    hook1 = MockPolicyHook(approval_request_result=None)
    hook2 = MockPolicyHook(approval_request_result=True)
    hook3 = MockPolicyHook(approval_request_result=None)

    mock_registry.register_policy_hook(hook1)
    mock_registry.register_policy_hook(hook2)
    mock_registry.register_policy_hook(hook3)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        result = await check_policy_approval(
            workflow_id="test-workflow",
            approval_type="review",
        )

    # Verify
    assert result is True
    assert hook1.on_approval_request.call_count == 1
    assert hook2.on_approval_request.call_count == 1
    # Third hook should NOT be called (early return on override)
    assert hook3.on_approval_request.call_count == 0


async def test_check_policy_approval_hook_overrides_to_deny(
    mock_registry: ExtensionRegistry,
) -> None:
    """Test check_policy_approval returns False when hook overrides to deny."""
    # Setup
    hook = MockPolicyHook(approval_request_result=False)
    mock_registry.register_policy_hook(hook)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        result = await check_policy_approval(
            workflow_id="test-workflow",
            approval_type="plan",
        )

    # Verify
    assert result is False
    assert hook.on_approval_request.call_count == 1


async def test_check_policy_approval_continues_on_hook_error(
    mock_registry: ExtensionRegistry,
) -> None:
    """Test check_policy_approval continues to next hook on error (not fail-safe)."""
    # Setup
    failing_hook = MockPolicyHook()
    failing_hook.on_approval_request.side_effect = RuntimeError("Hook error")
    working_hook = MockPolicyHook(approval_request_result=True)

    mock_registry.register_policy_hook(failing_hook)
    mock_registry.register_policy_hook(working_hook)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        result = await check_policy_approval(
            workflow_id="test-workflow",
            approval_type="plan",
        )

    # Verify - continues to next hook on error
    assert result is True
    assert failing_hook.on_approval_request.call_count == 1
    assert working_hook.on_approval_request.call_count == 1


async def test_check_policy_approval_multiple_errors_returns_none(
    mock_registry: ExtensionRegistry,
) -> None:
    """Test check_policy_approval returns None when all hooks error."""
    # Setup
    hook1 = MockPolicyHook()
    hook1.on_approval_request.side_effect = RuntimeError("Hook 1 error")
    hook2 = MockPolicyHook()
    hook2.on_approval_request.side_effect = RuntimeError("Hook 2 error")

    mock_registry.register_policy_hook(hook1)
    mock_registry.register_policy_hook(hook2)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        result = await check_policy_approval(
            workflow_id="test-workflow",
            approval_type="plan",
        )

    # Verify - returns None when all hooks error
    assert result is None
    assert hook1.on_approval_request.call_count == 1
    assert hook2.on_approval_request.call_count == 1


# Tests for record_metric


async def test_record_metric_success(mock_registry: ExtensionRegistry) -> None:
    """Test record_metric records to all sinks successfully."""
    # Setup
    sink1 = MockAnalyticsSink()
    sink2 = MockAnalyticsSink()

    mock_registry.register_analytics_sink(sink1)
    mock_registry.register_analytics_sink(sink2)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        await record_metric(
            name="workflow.duration_seconds",
            value=45.2,
            tags={"profile": "work", "status": "success"},
        )

    # Verify
    assert sink1.record_metric.call_count == 1
    assert sink2.record_metric.call_count == 1

    sink1.record_metric.assert_called_once_with(
        "workflow.duration_seconds",
        45.2,
        {"profile": "work", "status": "success"},
    )


async def test_record_metric_with_no_tags(mock_registry: ExtensionRegistry) -> None:
    """Test record_metric works with no tags."""
    # Setup
    sink = MockAnalyticsSink()
    mock_registry.register_analytics_sink(sink)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        await record_metric(
            name="workflow.task_count",
            value=5.0,
        )

    # Verify
    sink.record_metric.assert_called_once_with("workflow.task_count", 5.0, None)


async def test_record_metric_handles_failure_gracefully() -> None:
    """Test record_metric handles sink failures without raising."""
    # Setup
    failing_sink = MockAnalyticsSink(metric_error=RuntimeError("Metric failed"))
    working_sink = MockAnalyticsSink()

    mock_registry = ExtensionRegistry()
    mock_registry.register_analytics_sink(failing_sink)
    mock_registry.register_analytics_sink(working_sink)

    # Execute - should not raise
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        await record_metric(name="test.metric", value=1.0)

    # Verify both were called
    assert failing_sink.record_metric.call_count == 1
    assert working_sink.record_metric.call_count == 1


# Tests for flush_exporters


async def test_flush_exporters_success(mock_registry: ExtensionRegistry) -> None:
    """Test flush_exporters flushes all exporters successfully."""
    # Setup
    exporter1 = MockAuditExporter()
    exporter2 = MockAuditExporter()

    mock_registry.register_audit_exporter(exporter1)
    mock_registry.register_audit_exporter(exporter2)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        await flush_exporters()

    # Verify
    assert exporter1.flush.call_count == 1
    assert exporter2.flush.call_count == 1


async def test_flush_exporters_handles_failure_gracefully() -> None:
    """Test flush_exporters handles exporter failures without raising."""
    # Setup
    failing_exporter = MockAuditExporter()
    failing_exporter.flush.side_effect = RuntimeError("Flush failed")
    working_exporter = MockAuditExporter()

    mock_registry = ExtensionRegistry()
    mock_registry.register_audit_exporter(failing_exporter)
    mock_registry.register_audit_exporter(working_exporter)

    # Execute - should not raise
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        await flush_exporters()

    # Verify both were called
    assert failing_exporter.flush.call_count == 1
    assert working_exporter.flush.call_count == 1


async def test_flush_exporters_no_exporters() -> None:
    """Test flush_exporters works when no exporters are registered."""
    # Setup - empty registry
    mock_registry = ExtensionRegistry()

    # Execute - should not raise
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        await flush_exporters()

    # No exceptions means success


# Integration-style tests


async def test_emit_workflow_event_timestamp_is_recent() -> None:
    """Test emit_workflow_event creates events with recent timestamps."""
    # Setup
    exporter = MockAuditExporter()
    mock_registry = ExtensionRegistry()
    mock_registry.register_audit_exporter(exporter)

    before = datetime.now(UTC)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        await emit_workflow_event(
            event_type=WorkflowEventType.STARTED,
            workflow_id="test-workflow",
        )

    after = datetime.now(UTC)

    # Verify timestamp is between before and after
    event = exporter.export.call_args[0][0]
    assert before <= event.timestamp <= after


async def test_check_policy_workflow_start_hook_receives_correct_args(
    mock_profile: Profile,
) -> None:
    """Test check_policy_workflow_start passes correct arguments to hooks."""
    # Setup
    hook = MockPolicyHook(workflow_start_result=True)
    mock_registry = ExtensionRegistry()
    mock_registry.register_policy_hook(hook)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        allowed, denial_reason = await check_policy_workflow_start(
            workflow_id="workflow-abc",
            profile=mock_profile,
            issue_id="ISSUE-999",
        )

    # Verify exact arguments
    assert allowed is True
    assert denial_reason is None
    hook.on_workflow_start.assert_called_once_with(
        "workflow-abc", mock_profile, "ISSUE-999"
    )


async def test_check_policy_approval_hook_receives_correct_args() -> None:
    """Test check_policy_approval passes correct arguments to hooks."""
    # Setup
    hook = MockPolicyHook(approval_request_result=None)
    mock_registry = ExtensionRegistry()
    mock_registry.register_policy_hook(hook)

    # Execute
    with patch("amelia.ext.hooks.get_registry", return_value=mock_registry):
        await check_policy_approval(
            workflow_id="workflow-xyz",
            approval_type="review",
        )

    # Verify exact arguments
    hook.on_approval_request.assert_called_once_with("workflow-xyz", "review")
