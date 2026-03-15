"""Tests for CLI queue commands (start --queue, run)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from amelia.client.models import CreateWorkflowResponse
from amelia.main import app


class TestStartCommandQueue:
    """Tests for start command with queue flags."""

    @pytest.mark.parametrize(
        ("extra_flags", "expect_start", "expect_plan"),
        [
            ([], True, False),
            (["--queue"], False, False),
            (["--queue", "--plan"], False, True),
        ],
        ids=["default-immediate", "queue-only", "queue-and-plan"],
    )
    def test_start_queue_flags(
        self,
        runner: CliRunner,
        mock_worktree: Path,
        extra_flags: list[str],
        expect_start: bool,
        expect_plan: bool,
    ) -> None:
        """Start command passes correct queue/plan flags."""
        status = "running" if expect_start else "pending"
        with patch("amelia.client.cli._get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(mock_worktree), "repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(return_value=CreateWorkflowResponse(
                id=str(uuid4()), status=status, message="ok"
            ))

            result = runner.invoke(app, ["start", "ISSUE-123", *extra_flags])

            assert result.exit_code == 0, f"Command failed: {result.stdout}"
            call_kwargs = mock_client.create_workflow.call_args.kwargs
            assert call_kwargs.get("start", True) is expect_start
            if not expect_start:
                assert call_kwargs.get("plan_now", False) is expect_plan

    def test_plan_without_queue_is_error(self, runner: CliRunner) -> None:
        """--plan without --queue should error."""
        result = runner.invoke(app, ["start", "ISSUE-123", "--plan"])

        assert result.exit_code != 0
        output = result.stdout.lower() + result.output.lower()
        assert "--queue" in output or "queue" in output


class TestRunCommand:
    """Tests for run command."""

    def test_run_specific_workflow(self, runner: CliRunner) -> None:
        """Run a specific workflow by ID."""
        with patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.start_workflow = AsyncMock(
                return_value={"workflow_id": "wf-123", "status": "started"}
            )

            result = runner.invoke(app, ["run", "wf-123"])

            assert result.exit_code == 0, f"Command failed: {result.stdout}"
            mock_client.start_workflow.assert_called_once_with("wf-123")

    def test_run_all_pending(self, runner: CliRunner) -> None:
        """Run all pending workflows with --all flag."""
        with patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.start_batch = AsyncMock(
                return_value=MagicMock(started=["wf-1", "wf-2"], errors={})
            )

            result = runner.invoke(app, ["run", "--all"])

            assert result.exit_code == 0, f"Command failed: {result.stdout}"
            mock_client.start_batch.assert_called_once()

    def test_run_all_with_worktree_filter(self, runner: CliRunner) -> None:
        """Run all pending with worktree filter."""
        with patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.start_batch = AsyncMock(
                return_value=MagicMock(started=["wf-1"], errors={})
            )

            result = runner.invoke(app, ["run", "--all", "--worktree", "/path/to/repo"])

            assert result.exit_code == 0, f"Command failed: {result.stdout}"
            mock_client.start_batch.assert_called_once()
            call_kwargs = mock_client.start_batch.call_args.kwargs
            assert call_kwargs["worktree_path"] == "/path/to/repo"

    def test_run_requires_id_or_all(self, runner: CliRunner) -> None:
        """run command requires either workflow ID or --all flag."""
        result = runner.invoke(app, ["run"])

        assert result.exit_code != 0
        output = result.stdout.lower()
        assert "error" in output or "provide" in output or "missing" in output

    def test_run_displays_started_message(self, runner: CliRunner) -> None:
        """run command displays success message with workflow ID."""
        with patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.start_workflow = AsyncMock(
                return_value={"workflow_id": "wf-456", "status": "started"}
            )

            result = runner.invoke(app, ["run", "wf-456"])

            assert result.exit_code == 0
            assert "wf-456" in result.stdout
            assert "started" in result.stdout.lower()

    def test_run_all_displays_batch_results(self, runner: CliRunner) -> None:
        """run --all displays count of started workflows."""
        with patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.start_batch = AsyncMock(
                return_value=MagicMock(
                    started=["wf-1", "wf-2", "wf-3"],
                    errors={"wf-4": "Conflict error"},
                )
            )

            result = runner.invoke(app, ["run", "--all"])

            assert result.exit_code == 0
            assert "3" in result.stdout
            assert "wf-4" in result.stdout or "1" in result.stdout

    def test_run_handles_server_unreachable(self, runner: CliRunner) -> None:
        """run command handles server connection errors gracefully."""
        from amelia.client.api import ServerUnreachableError

        with patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.start_workflow = AsyncMock(
                side_effect=ServerUnreachableError("Cannot connect")
            )

            result = runner.invoke(app, ["run", "wf-123"])

            assert result.exit_code != 0
            output = result.stdout.lower()
            assert "server" in output or "connect" in output
