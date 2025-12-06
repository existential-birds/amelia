# tests/unit/client/test_cli.py
"""Tests for refactored CLI commands."""
from unittest.mock import AsyncMock, MagicMock, patch


class TestStartCommand:
    """Tests for 'amelia start' command."""

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_detects_worktree(self, mock_client_class, mock_worktree, cli_runner):
        """start command auto-detects worktree context."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            issue_id="ISSUE-123",
            status="planning",
            worktree_path="/home/user/repo",
            worktree_name="main",
        )
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 0
        mock_worktree.assert_called_once()
        mock_client.create_workflow.assert_called_once()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_with_profile(self, mock_client_class, mock_worktree, cli_runner):
        """start command passes profile to API."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            issue_id="ISSUE-123",
            status="planning",
        )
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["start", "ISSUE-123", "--profile", "work"])

        assert result.exit_code == 0
        call_kwargs = mock_client.create_workflow.call_args.kwargs
        assert call_kwargs["profile"] == "work"

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_handles_server_unreachable(self, mock_client_class, mock_worktree, cli_runner):
        """start command shows helpful error when server unreachable."""
        from amelia.client.api import ServerUnreachableError
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.side_effect = ServerUnreachableError(
            "Cannot connect to server"
        )
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 1
        assert "Cannot connect" in result.stdout or "server" in result.stdout.lower()
        assert "amelia server" in result.stdout

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_handles_workflow_conflict(self, mock_client_class, mock_worktree, cli_runner):
        """start command shows active workflow details on conflict."""
        from amelia.client.api import WorkflowConflictError
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.side_effect = WorkflowConflictError(
            "Workflow already active",
            active_workflow={
                "id": "wf-existing",
                "issue_id": "ISSUE-99",
                "status": "in_progress",
            },
        )
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 1
        assert "already active" in result.stdout.lower()
        assert "ISSUE-99" in result.stdout
        assert "amelia cancel" in result.stdout

    @patch("amelia.client.cli.get_worktree_context")
    def test_start_handles_not_in_git_repo(self, mock_worktree, cli_runner):
        """start command shows error when not in git repo."""
        from amelia.main import app

        mock_worktree.side_effect = ValueError("Not inside a git repository")

        result = cli_runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 1
        assert "git repository" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    def test_start_handles_bare_repo(self, mock_worktree, cli_runner):
        """start command shows error for bare repository."""
        from amelia.main import app

        mock_worktree.side_effect = ValueError("Cannot run workflows in a bare repository")

        result = cli_runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 1
        assert "bare repository" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_shows_success_message(self, mock_client_class, mock_worktree, cli_runner):
        """start command shows success with workflow ID."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            issue_id="ISSUE-123",
            status="planning",
            worktree_path="/home/user/repo",
            worktree_name="main",
        )
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 0
        assert "wf-123" in result.stdout
        assert "ISSUE-123" in result.stdout
        assert "planning" in result.stdout.lower()


class TestApproveCommand:
    """Tests for 'amelia approve' command."""

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_approve_finds_workflow_by_worktree(self, mock_client_class, mock_worktree, cli_runner):
        """approve command finds workflow ID from current worktree."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="blocked",
                    worktree_path="/home/user/repo",
                )
            ],
            total=1,
        )
        mock_client.approve_workflow.return_value = None
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["approve"])

        assert result.exit_code == 0
        mock_client.get_active_workflows.assert_called_once_with(worktree_path="/home/user/repo")
        mock_client.approve_workflow.assert_called_once_with(workflow_id="wf-123")

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_approve_shows_error_when_no_workflow(self, mock_client_class, mock_worktree, cli_runner):
        """approve command shows error when no workflow active."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(workflows=[], total=0)
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["approve"])

        assert result.exit_code == 1
        assert "no workflow" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_approve_shows_error_when_not_blocked(self, mock_client_class, mock_worktree, cli_runner):
        """approve command shows error when workflow not awaiting approval."""
        from amelia.client.api import InvalidRequestError
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="in_progress",
                    worktree_path="/home/user/repo",
                )
            ],
            total=1,
        )
        mock_client.approve_workflow.side_effect = InvalidRequestError(
            "Workflow is not awaiting approval"
        )
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["approve"])

        assert result.exit_code == 1
        assert "not awaiting approval" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_approve_shows_success(self, mock_client_class, mock_worktree, cli_runner):
        """approve command shows success message."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="blocked",
                )
            ]
        )
        mock_client.approve_workflow.return_value = None
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["approve"])

        assert result.exit_code == 0
        assert "approved" in result.stdout.lower()
        assert "wf-123" in result.stdout


class TestRejectCommand:
    """Tests for 'amelia reject' command."""

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_reject_with_reason(self, mock_client_class, mock_worktree, cli_runner):
        """reject command sends reason to API."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[MagicMock(id="wf-123", issue_id="ISSUE-123")]
        )
        mock_client.reject_workflow.return_value = None
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["reject", "Not ready yet"])

        assert result.exit_code == 0
        mock_client.reject_workflow.assert_called_once_with(
            workflow_id="wf-123", reason="Not ready yet"
        )

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_reject_shows_error_when_no_workflow(self, mock_client_class, mock_worktree, cli_runner):
        """reject command shows error when no workflow active."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(workflows=[], total=0)
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["reject", "reason"])

        assert result.exit_code == 1
        assert "no workflow" in result.stdout.lower()


class TestStatusCommand:
    """Tests for 'amelia status' command."""

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_status_shows_current_worktree(self, mock_client_class, mock_worktree, cli_runner):
        """status command shows workflow for current worktree."""
        from datetime import datetime

        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="in_progress",
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                    started_at=datetime(2025, 12, 1, 10, 0, 0),
                )
            ],
            total=1,
        )
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "wf-123" in result.stdout
        assert "ISSUE-123" in result.stdout
        assert "in_progress" in result.stdout

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_status_all_shows_all_worktrees(self, mock_client_class, mock_worktree, cli_runner):
        """status --all shows workflows from all worktrees."""
        from datetime import datetime

        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="in_progress",
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                    started_at=datetime(2025, 12, 1, 10, 0, 0),
                ),
                MagicMock(
                    id="wf-456",
                    issue_id="ISSUE-456",
                    status="blocked",
                    worktree_path="/home/user/repo2",
                    worktree_name="feature-x",
                    started_at=datetime(2025, 12, 1, 11, 0, 0),
                ),
            ],
            total=2,
        )
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["status", "--all"])

        assert result.exit_code == 0
        mock_client.get_active_workflows.assert_called_once_with(worktree_path=None)
        assert "wf-123" in result.stdout
        assert "wf-456" in result.stdout

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_status_shows_no_workflows_message(self, mock_client_class, mock_worktree, cli_runner):
        """status command shows message when no workflows active."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(workflows=[], total=0)
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "no active" in result.stdout.lower() or "no workflow" in result.stdout.lower()


class TestCancelCommand:
    """Tests for 'amelia cancel' command."""

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_cancel_finds_workflow_by_worktree(self, mock_client_class, mock_worktree, cli_runner):
        """cancel command finds workflow from current worktree."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[MagicMock(id="wf-123", issue_id="ISSUE-123")]
        )
        mock_client.cancel_workflow.return_value = None
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["cancel"], input="y\n")

        assert result.exit_code == 0
        mock_client.cancel_workflow.assert_called_once_with(workflow_id="wf-123")

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_cancel_requires_confirmation(self, mock_client_class, mock_worktree, cli_runner):
        """cancel command requires user confirmation."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[MagicMock(id="wf-123", issue_id="ISSUE-123")]
        )
        mock_client_class.return_value = mock_client

        # User declines - not an error, just aborted
        result = cli_runner.invoke(app, ["cancel"], input="n\n")

        assert result.exit_code == 0
        assert "Aborted" in result.output
        mock_client.cancel_workflow.assert_not_called()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_cancel_force_skips_confirmation(self, mock_client_class, mock_worktree, cli_runner):
        """cancel --force skips confirmation prompt."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[MagicMock(id="wf-123", issue_id="ISSUE-123")]
        )
        mock_client.cancel_workflow.return_value = None
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["cancel", "--force"])

        assert result.exit_code == 0
        mock_client.cancel_workflow.assert_called_once()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_cancel_shows_error_when_no_workflow(self, mock_client_class, mock_worktree, cli_runner):
        """cancel command shows error when no workflow active."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(workflows=[], total=0)
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["cancel"])

        assert result.exit_code == 1
        assert "no workflow" in result.stdout.lower()
