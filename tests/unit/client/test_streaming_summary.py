"""Unit tests for stream_workflow_events WorkflowSummary return."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from tests.conftest import AsyncIteratorMock

from amelia.client.streaming import WorkflowSummary, stream_workflow_events


def _make_ws_messages(events: list[dict]) -> list[str]:
    """Create WebSocket message strings from event dicts."""
    messages = []
    for event in events:
        messages.append(json.dumps({"type": "event", "payload": event}))
    return messages


async def _run_streaming_events(
    messages: list[str], wf_id: str, **kwargs
) -> tuple[WorkflowSummary, AsyncIteratorMock]:
    mock_ws = AsyncIteratorMock(messages)
    mock_ws.send = AsyncMock()  # type: ignore[attr-defined]

    with patch("websockets.connect") as mock_connect:
        mock_connect.return_value.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.return_value.__aexit__ = AsyncMock(return_value=False)

        summary = await stream_workflow_events(wf_id, **kwargs)

    return summary, mock_ws


class TestStreamWorkflowSummary:
    """Tests for WorkflowSummary collection from streaming events."""

    async def test_returns_workflow_summary(self) -> None:
        """stream_workflow_events returns a WorkflowSummary instead of None."""
        events = [
            {"event_type": "workflow_started", "message": "Started"},
            {
                "event_type": "stage_completed",
                "message": "Done",
                "data": {"stage": "fix", "result": {"status": "fixed"}},
            },
            {
                "event_type": "stage_completed",
                "message": "Done",
                "data": {"stage": "fix", "result": {"status": "fixed"}},
            },
            {
                "event_type": "stage_completed",
                "message": "Done",
                "data": {"stage": "fix", "result": {"status": "skipped"}},
            },
            {
                "event_type": "stage_completed",
                "message": "Done",
                "data": {"stage": "fix", "result": {"status": "failed"}},
            },
            {
                "event_type": "workflow_completed",
                "message": "Complete",
                "data": {"commit_sha": "abc123def"},
            },
        ]
        summary, _ = await _run_streaming_events(_make_ws_messages(events), "wf-123")

        assert isinstance(summary, WorkflowSummary)
        assert summary.fixed == 2
        assert summary.skipped == 1
        assert summary.failed == 1
        assert summary.commit_sha == "abc123def"

    async def test_summary_defaults_to_zeros(self) -> None:
        """Summary has zeros when events lack result data."""
        events = [
            {"event_type": "workflow_started", "message": "Started"},
            {
                "event_type": "stage_completed",
                "message": "Done",
                "data": {"stage": "review"},
            },
            {
                "event_type": "workflow_completed",
                "message": "Complete",
                "data": {},
            },
        ]
        summary, _ = await _run_streaming_events(_make_ws_messages(events), "wf-456")

        assert summary.fixed == 0
        assert summary.skipped == 0
        assert summary.failed == 0
        assert summary.commit_sha is None

    async def test_display_false_collects_summary(self) -> None:
        """display=False still collects summary correctly."""
        events = [
            {"event_type": "workflow_started", "message": "Started"},
            {
                "event_type": "stage_completed",
                "message": "Done",
                "data": {"stage": "fix", "result": {"status": "fixed"}},
            },
            {
                "event_type": "workflow_completed",
                "message": "Complete",
                "data": {"commit_sha": "xyz789"},
            },
        ]
        summary, _ = await _run_streaming_events(
            _make_ws_messages(events), "wf-789", display=False
        )

        assert summary.fixed == 1
        assert summary.commit_sha == "xyz789"

    async def test_handles_ping_pong(self) -> None:
        """Ping messages are handled and don't affect summary."""
        raw_messages = [
            json.dumps({"type": "ping"}),
            json.dumps({
                "type": "event",
                "payload": {
                    "event_type": "workflow_completed",
                    "message": "Complete",
                    "data": {},
                },
            }),
        ]
        summary, mock_ws = await _run_streaming_events(raw_messages, "wf-ping")

        assert isinstance(summary, WorkflowSummary)
        # Verify pong was sent
        mock_ws.send.assert_any_call(json.dumps({"type": "pong"}))

    async def test_terminates_on_pr_auto_fix_completed(self) -> None:
        """stream_workflow_events breaks on pr_auto_fix_completed event."""
        events = [
            {"event_type": "pr_auto_fix_started", "message": "Started"},
            {
                "event_type": "pr_auto_fix_completed",
                "message": "Done",
                "data": {"commit_sha": "abc123", "workflow_id": "wf-pr"},
            },
        ]
        summary, _ = await _run_streaming_events(
            _make_ws_messages(events), "wf-pr-fix"
        )

        assert isinstance(summary, WorkflowSummary)
        assert summary.commit_sha == "abc123"

    async def test_terminates_on_pr_auto_fix_failed(self) -> None:
        """stream_workflow_events breaks on pr_auto_fix_failed event."""
        events = [
            {"event_type": "pr_auto_fix_started", "message": "Started"},
            {
                "event_type": "pr_auto_fix_failed",
                "message": "Something went wrong",
                "data": {"failure_reason": "LLM error"},
            },
        ]
        summary, _ = await _run_streaming_events(
            _make_ws_messages(events), "wf-pr-fail"
        )

        assert isinstance(summary, WorkflowSummary)

    async def test_collects_summary_before_pr_auto_fix_completed(self) -> None:
        """stage_completed events are counted before pr_auto_fix_completed."""
        events = [
            {"event_type": "pr_auto_fix_started", "message": "Started"},
            {
                "event_type": "stage_completed",
                "message": "Done",
                "data": {"stage": "develop_node", "result": {"status": "fixed"}},
            },
            {
                "event_type": "stage_completed",
                "message": "Done",
                "data": {"stage": "develop_node", "result": {"status": "fixed"}},
            },
            {
                "event_type": "stage_completed",
                "message": "Done",
                "data": {"stage": "develop_node", "result": {"status": "skipped"}},
            },
            {
                "event_type": "stage_completed",
                "message": "Done",
                "data": {"stage": "develop_node", "result": {"status": "failed"}},
            },
            {
                "event_type": "pr_auto_fix_completed",
                "message": "Complete",
                "data": {"commit_sha": "def456"},
            },
        ]
        summary, _ = await _run_streaming_events(
            _make_ws_messages(events), "wf-pr-summary"
        )

        assert summary.fixed == 2
        assert summary.skipped == 1
        assert summary.failed == 1
        assert summary.commit_sha == "def456"
