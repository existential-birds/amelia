"""Unit tests for fix-pr CLI command."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from amelia.client.api import ServerUnreachableError
from amelia.client.streaming import WorkflowSummary
from amelia.main import app


runner = CliRunner()


def _invoke_fix_pr(args: list[str], mock_client: AsyncMock, mock_summary: WorkflowSummary):
    with (
        patch("amelia.main.AmeliaClient", return_value=mock_client),
        patch("amelia.main.stream_workflow_events", new_callable=AsyncMock, return_value=mock_summary) as mock_stream,
    ):
        result = runner.invoke(app, ["fix-pr", *args])
    return result, mock_stream


class TestFixPRCommand:
    """Tests for the fix-pr CLI command."""

    def test_happy_path(self, mock_client: AsyncMock, mock_summary: WorkflowSummary) -> None:
        """fix-pr triggers fix, streams events, prints summary."""
        result, _ = _invoke_fix_pr(["42", "--profile", "myprofile"], mock_client, mock_summary)

        assert result.exit_code == 0
        assert "2 comments fixed" in result.output
        assert "1 skipped" in result.output
        assert "0 failed" in result.output
        assert "abc123de" in result.output  # First 8 chars of commit SHA
        mock_client.get_pr_autofix_status.assert_called_once_with("myprofile")
        mock_client.trigger_pr_autofix.assert_called_once_with(42, "myprofile", None)

    def test_quiet_mode(self, mock_client: AsyncMock, mock_summary: WorkflowSummary) -> None:
        """--quiet calls stream_workflow_events with display=False, still prints summary."""
        result, mock_stream = _invoke_fix_pr(["42", "--profile", "prof", "--quiet"], mock_client, mock_summary)

        assert result.exit_code == 0
        assert "2 comments fixed" in result.output
        # Verify display=False was passed
        mock_stream.assert_called_once()
        call_kwargs = mock_stream.call_args
        assert call_kwargs.kwargs.get("display") is False or (len(call_kwargs.args) > 1 and call_kwargs.args[1] is False)

    def test_aggressiveness_passed(self, mock_client: AsyncMock, mock_summary: WorkflowSummary) -> None:
        """--aggressiveness is forwarded to trigger_pr_autofix."""
        result, _ = _invoke_fix_pr(["42", "--profile", "prof", "--aggressiveness", "thorough"], mock_client, mock_summary)

        assert result.exit_code == 0
        mock_client.trigger_pr_autofix.assert_called_once_with(42, "prof", "thorough")

    def test_autofix_not_enabled(self, mock_client: AsyncMock) -> None:
        """When pr_autofix is not enabled, prints error and exits with code 1."""
        mock_client.get_pr_autofix_status.return_value = AsyncMock(enabled=False)

        with patch("amelia.main.AmeliaClient", return_value=mock_client):
            result = runner.invoke(app, ["fix-pr", "42", "--profile", "myprofile"])

        assert result.exit_code == 1
        assert "PR auto-fix not enabled on profile myprofile" in result.output
        assert "Configure it in the dashboard" in result.output
        # trigger should NOT be called
        mock_client.trigger_pr_autofix.assert_not_called()

    def test_server_unreachable(self, mock_client: AsyncMock) -> None:
        """Server unreachable prints error and exits with code 1."""
        mock_client.get_pr_autofix_status.side_effect = ServerUnreachableError("Cannot connect")

        with patch("amelia.main.AmeliaClient", return_value=mock_client):
            result = runner.invoke(app, ["fix-pr", "42", "--profile", "prof"])

        assert result.exit_code == 1
        assert "Server not running" in result.output

    def test_profile_required(self) -> None:
        """--profile is required; missing it produces error."""
        result = runner.invoke(app, ["fix-pr", "42"])
        assert result.exit_code != 0

    def test_no_commit_sha_in_summary(self, mock_client: AsyncMock) -> None:
        """When commit_sha is None, summary line omits commit info."""
        summary = WorkflowSummary(fixed=1, skipped=0, failed=0, commit_sha=None)
        result, _ = _invoke_fix_pr(["42", "--profile", "prof"], mock_client, summary)

        assert result.exit_code == 0
        assert "1 comments fixed" in result.output
        assert "commit" not in result.output.lower()
