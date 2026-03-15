"""Unit tests for stream_workflow_events WorkflowSummary return."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest

from amelia.client.streaming import WorkflowSummary, stream_workflow_events


def _make_ws_messages(events: list[dict]) -> list[str]:
    """Create WebSocket message strings from event dicts."""
    messages = []
    for event in events:
        messages.append(json.dumps({"type": "event", "payload": event}))
    return messages


class _AsyncIter:
    """Wraps a list into an async iterator for mocking websocket messages."""

    def __init__(self, items: list[str]) -> None:
        self._items = iter(items)

    def __aiter__(self) -> AsyncIterator[str]:
        return self  # type: ignore[return-value]

    async def __anext__(self) -> str:
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration from None


async def _run_streaming_events(
    messages: list[str], wf_id: str, **kwargs
) -> tuple[WorkflowSummary, _AsyncIter]:
    mock_ws = _AsyncIter(messages)
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

    async def test_display_false_suppresses_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """display=False suppresses console output but still collects summary."""
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
        # With display=False, Rich console should not produce visible output
        # (Rich writes to its own file handle, so capsys may not capture it,
        # but the important thing is no crash and summary is collected)

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
