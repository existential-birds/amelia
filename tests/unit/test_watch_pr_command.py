"""Unit tests for watch-pr CLI command."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from amelia.client.api import PRCommentsResponse, ServerUnreachableError
from amelia.client.streaming import WorkflowSummary
from amelia.core.types import PRReviewComment
from amelia.main import app


runner = CliRunner()


def _invoke_watch_pr(args: list[str], mock_client: AsyncMock, mock_summary: WorkflowSummary):
    with (
        patch("amelia.main.AmeliaClient", return_value=mock_client),
        patch(
            "amelia.main.stream_workflow_events",
            new_callable=AsyncMock,
            return_value=mock_summary,
        ),
    ):
        result = runner.invoke(app, ["watch-pr", *args])
    return result


class TestWatchPRCommand:
    """Tests for the watch-pr CLI command."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock AmeliaClient with default behavior."""
        client = AsyncMock()
        client.get_pr_autofix_status.return_value = AsyncMock(enabled=True)
        client.trigger_pr_autofix.return_value = AsyncMock(workflow_id="wf-watch-1")
        return client

    @pytest.fixture
    def mock_summary(self) -> WorkflowSummary:
        """Default workflow summary."""
        return WorkflowSummary(fixed=1, skipped=0, failed=0, commit_sha="abc123")

    def test_auto_stop_zero_comments(
        self, mock_client: AsyncMock, mock_summary: WorkflowSummary
    ) -> None:
        """watch-pr stops when zero unresolved comments after first cycle."""
        # After cycle: zero comments -> stop
        mock_client.get_pr_comments.return_value = PRCommentsResponse(comments=[])

        result = _invoke_watch_pr(["42", "--profile", "myprofile"], mock_client, mock_summary)

        assert result.exit_code == 0
        assert "All comments resolved" in result.output
        # Should only trigger once (single cycle)
        mock_client.trigger_pr_autofix.assert_called_once()

    def test_two_cycles_then_stop(
        self, mock_client: AsyncMock, mock_summary: WorkflowSummary
    ) -> None:
        """watch-pr runs two cycles: first has comments, second has zero."""
        comment = PRReviewComment(
            id=1,
            body="Fix this",
            author="reviewer",
            created_at=datetime(2026, 1, 1),
            path="src/main.py",
            line=10,
        )
        # First call: comments remain; second call: zero comments
        mock_client.get_pr_comments.side_effect = [
            PRCommentsResponse(comments=[comment]),
            PRCommentsResponse(comments=[]),
        ]

        with (
            patch("amelia.main.AmeliaClient", return_value=mock_client),
            patch(
                "amelia.main.stream_workflow_events",
                new_callable=AsyncMock,
                return_value=mock_summary,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result = runner.invoke(
                app, ["watch-pr", "42", "--profile", "prof", "--interval", "10"]
            )

        assert result.exit_code == 0
        assert "All comments resolved" in result.output
        assert "Waiting for new comments" in result.output
        # Triggered twice
        assert mock_client.trigger_pr_autofix.call_count == 2
        # Sleep called with interval=10
        mock_sleep.assert_called_with(10)

    def test_keyboard_interrupt(
        self, mock_client: AsyncMock
    ) -> None:
        """KeyboardInterrupt prints 'Stopped watching.' gracefully."""
        mock_client.trigger_pr_autofix.side_effect = KeyboardInterrupt()

        with patch("amelia.main.AmeliaClient", return_value=mock_client):
            result = runner.invoke(
                app, ["watch-pr", "42", "--profile", "prof"]
            )

        # Should not crash
        assert "Stopped watching" in result.output

    def test_autofix_not_enabled(self, mock_client: AsyncMock) -> None:
        """When pr_autofix is not enabled, prints error and exits."""
        mock_client.get_pr_autofix_status.return_value = AsyncMock(enabled=False)

        with patch("amelia.main.AmeliaClient", return_value=mock_client):
            result = runner.invoke(
                app, ["watch-pr", "42", "--profile", "myprofile"]
            )

        assert result.exit_code == 1
        assert "PR auto-fix not enabled on profile myprofile" in result.output
        mock_client.trigger_pr_autofix.assert_not_called()

    def test_server_unreachable(self, mock_client: AsyncMock) -> None:
        """Server unreachable prints error and exits."""
        mock_client.get_pr_autofix_status.side_effect = ServerUnreachableError(
            "Cannot connect"
        )

        with patch("amelia.main.AmeliaClient", return_value=mock_client):
            result = runner.invoke(
                app, ["watch-pr", "42", "--profile", "prof"]
            )

        assert result.exit_code == 1
        assert "Server not running" in result.output

    def test_profile_required(self) -> None:
        """--profile is required."""
        result = runner.invoke(app, ["watch-pr", "42"])
        assert result.exit_code != 0

    def test_aggressiveness_passed(
        self, mock_client: AsyncMock, mock_summary: WorkflowSummary
    ) -> None:
        """--aggressiveness is forwarded on each trigger cycle."""
        mock_client.get_pr_comments.return_value = PRCommentsResponse(comments=[])

        result = _invoke_watch_pr(
            ["42", "--profile", "prof", "--aggressiveness", "thorough"],
            mock_client,
            mock_summary,
        )

        assert result.exit_code == 0
        mock_client.trigger_pr_autofix.assert_called_once_with(
            42, "prof", "thorough"
        )
