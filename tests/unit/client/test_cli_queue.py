"""Tests for CLI queue commands (start --queue, run)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from amelia.client.models import CreateWorkflowResponse
from amelia.main import app


class TestStartCommandQueue:
    """Tests for start command with queue flags."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Typer CLI test runner."""
        return CliRunner()

    def test_start_default_immediate(self, runner: CliRunner, tmp_path) -> None:
        """Default start without flags starts immediately."""
        # Create mock git worktree
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").touch()

        with patch("amelia.client.cli._get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(worktree), "repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(return_value=CreateWorkflowResponse(
                id="wf-123", status="running", message="Workflow started"
            ))

            result = runner.invoke(app, ["start", "ISSUE-123"])

            assert result.exit_code == 0, f"Command failed: {result.stdout}"
            mock_client.create_workflow.assert_called_once()
            call_kwargs = mock_client.create_workflow.call_args.kwargs
            # Default should start immediately (start=True or not passed means start)
            assert call_kwargs.get("start", True) is True

    def test_start_with_queue_flag(self, runner: CliRunner, tmp_path) -> None:
        """--queue flag queues without starting."""
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").touch()

        with patch("amelia.client.cli._get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(worktree), "repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(return_value=CreateWorkflowResponse(
                id="wf-123", status="pending", message="Workflow queued"
            ))

            result = runner.invoke(app, ["start", "ISSUE-123", "--queue"])

            assert result.exit_code == 0, f"Command failed: {result.stdout}"
            call_kwargs = mock_client.create_workflow.call_args.kwargs
            assert call_kwargs["start"] is False
            assert call_kwargs.get("plan_now", False) is False

    def test_start_with_queue_and_plan_flags(self, runner: CliRunner, tmp_path) -> None:
        """--queue --plan flags queue with planning."""
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").touch()

        with patch("amelia.client.cli._get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(worktree), "repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(return_value=CreateWorkflowResponse(
                id="wf-123", status="pending", message="Workflow queued with planning"
            ))

            result = runner.invoke(app, ["start", "ISSUE-123", "--queue", "--plan"])

            assert result.exit_code == 0, f"Command failed: {result.stdout}"
            call_kwargs = mock_client.create_workflow.call_args.kwargs
            assert call_kwargs["start"] is False
            assert call_kwargs["plan_now"] is True

    def test_plan_without_queue_is_error(self, runner: CliRunner) -> None:
        """--plan without --queue should error."""
        result = runner.invoke(app, ["start", "ISSUE-123", "--plan"])

        assert result.exit_code != 0
        # Check output contains error message about needing --queue
        output = result.stdout.lower() + result.output.lower()
        assert "--queue" in output or "queue" in output


class TestRunCommand:
    """Tests for run command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_run_specific_workflow(self, runner) -> None:
        """Run a specific workflow by ID."""
        with patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.start_workflow = AsyncMock(
                return_value={"workflow_id": "wf-123", "status": "started"}
            )

            result = runner.invoke(app, ["run", "wf-123"])

            assert result.exit_code == 0, f"Command failed: {result.stdout}"
            mock_client.start_workflow.assert_called_once_with("wf-123")

    def test_run_all_pending(self, runner) -> None:
        """Run all pending workflows with --all flag."""
        with patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.start_batch = AsyncMock(
                return_value=MagicMock(started=["wf-1", "wf-2"], errors={})
            )

            result = runner.invoke(app, ["run", "--all"])

            assert result.exit_code == 0, f"Command failed: {result.stdout}"
            mock_client.start_batch.assert_called_once()

    def test_run_all_with_worktree_filter(self, runner) -> None:
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

    def test_run_requires_id_or_all(self, runner) -> None:
        """run command requires either workflow ID or --all flag."""
        result = runner.invoke(app, ["run"])

        assert result.exit_code != 0
        # Check error message
        output = result.stdout.lower()
        assert "error" in output or "provide" in output or "missing" in output

    def test_run_displays_started_message(self, runner) -> None:
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

    def test_run_all_displays_batch_results(self, runner) -> None:
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
            # Should mention number of started workflows
            assert "3" in result.stdout
            # Should mention errors
            assert "wf-4" in result.stdout or "1" in result.stdout

    def test_run_handles_server_unreachable(self, runner) -> None:
        """run command handles server connection errors gracefully."""
        from amelia.client.api import ServerUnreachableError

        with patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.start_workflow = AsyncMock(
                side_effect=ServerUnreachableError("Cannot connect")
            )

            result = runner.invoke(app, ["run", "wf-123"])

            assert result.exit_code != 0
            # Should suggest starting the server
            output = result.stdout.lower()
            assert "server" in output or "connect" in output
