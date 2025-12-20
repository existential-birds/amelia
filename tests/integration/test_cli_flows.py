# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# tests/integration/test_cli_flows.py
"""Integration tests for CLI command flows."""
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner


class TestCLIFlows:
    """Integration tests for full CLI workflows."""

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_approve_flow(
        self,
        mock_client_class: MagicMock,
        mock_worktree: MagicMock,
        cli_runner: CliRunner,
        git_repo_with_changes: Path,
    ) -> None:
        """Test start -> approve flow."""
        from amelia.main import app

        mock_worktree.return_value = (str(git_repo_with_changes), "main")

        mock_client = AsyncMock()

        # Mock start workflow response
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            issue_id="ISSUE-123",
            status="planning",
            worktree_path=str(git_repo_with_changes),
            worktree_name="main",
            started_at=datetime(2025, 12, 1, 10, 0, 0),
        )

        # Mock get workflows for approve
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="blocked",
                    worktree_path=str(git_repo_with_changes),
                )
            ]
        )
        mock_client.approve_workflow.return_value = None

        mock_client_class.return_value = mock_client

        # Start workflow
        result = cli_runner.invoke(app, ["start", "ISSUE-123"])
        assert result.exit_code == 0
        assert "wf-123" in result.stdout

        # Approve workflow
        result = cli_runner.invoke(app, ["approve"])
        assert result.exit_code == 0
        assert "approved" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_reject_flow(
        self,
        mock_client_class: MagicMock,
        mock_worktree: MagicMock,
        cli_runner: CliRunner,
        git_repo_with_changes: Path,
    ) -> None:
        """Test start -> reject flow."""
        from amelia.main import app

        mock_worktree.return_value = (str(git_repo_with_changes), "main")

        mock_client = AsyncMock()

        # Mock start workflow response
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            issue_id="ISSUE-123",
            status="planning",
            worktree_path=str(git_repo_with_changes),
            worktree_name="main",
            started_at=datetime(2025, 12, 1, 10, 0, 0),
        )

        # Mock get workflows for reject
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="blocked",
                )
            ]
        )
        mock_client.reject_workflow.return_value = None

        mock_client_class.return_value = mock_client

        # Start workflow
        result = cli_runner.invoke(app, ["start", "ISSUE-123"])
        assert result.exit_code == 0

        # Reject workflow
        result = cli_runner.invoke(app, ["reject", "Not ready"])
        assert result.exit_code == 0
        assert "rejected" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_status_flow(
        self,
        mock_client_class: MagicMock,
        mock_worktree: MagicMock,
        cli_runner: CliRunner,
        git_repo_with_changes: Path,
    ) -> None:
        """Test start -> status flow."""
        from amelia.main import app

        mock_worktree.return_value = (str(git_repo_with_changes), "main")

        mock_client = AsyncMock()

        # Mock start workflow response
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            issue_id="ISSUE-123",
            status="planning",
            worktree_path=str(git_repo_with_changes),
            worktree_name="main",
            started_at=datetime(2025, 12, 1, 10, 0, 0),
        )

        # Mock get workflows for status
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="in_progress",
                    worktree_path=str(git_repo_with_changes),
                    worktree_name="main",
                    started_at=datetime(2025, 12, 1, 10, 0, 0),
                )
            ],
            total=1,
        )

        mock_client_class.return_value = mock_client

        # Start workflow
        result = cli_runner.invoke(app, ["start", "ISSUE-123"])
        assert result.exit_code == 0
        assert "wf-123" in result.stdout

        # Check status
        result = cli_runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "wf-123" in result.stdout

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_plan_command_creates_workflow(
        self,
        mock_client_class: MagicMock,
        mock_worktree: MagicMock,
        cli_runner: CliRunner,
        git_repo_with_changes: Path,
    ) -> None:
        """Test plan command creates workflow with plan_only=True."""
        from amelia.main import app

        mock_worktree.return_value = (str(git_repo_with_changes), "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-plan-123",
            issue_id="ISSUE-456",
            status="planning",
            worktree_path=str(git_repo_with_changes),
            worktree_name="main",
            started_at=datetime(2025, 12, 1, 10, 0, 0),
        )
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["plan", "ISSUE-456"])

        assert result.exit_code == 0
        assert "wf-plan-123" in result.stdout
        mock_client.create_workflow.assert_called_once()
        call_kwargs = mock_client.create_workflow.call_args.kwargs
        assert call_kwargs["issue_id"] == "ISSUE-456"
        assert call_kwargs["plan_only"] is True

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_plan_command_with_profile(
        self,
        mock_client_class: MagicMock,
        mock_worktree: MagicMock,
        cli_runner: CliRunner,
        git_repo_with_changes: Path,
    ) -> None:
        """Test plan command passes profile to API."""
        from amelia.main import app

        mock_worktree.return_value = (str(git_repo_with_changes), "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-plan-123",
            issue_id="ISSUE-456",
            status="planning",
            worktree_path=str(git_repo_with_changes),
            worktree_name="main",
            started_at=datetime(2025, 12, 1, 10, 0, 0),
        )
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, ["plan", "ISSUE-456", "--profile", "work"])

        assert result.exit_code == 0
        call_kwargs = mock_client.create_workflow.call_args.kwargs
        assert call_kwargs["profile"] == "work"

    @pytest.mark.parametrize("cmd", [
        ["start", "ISSUE-123"],
        ["plan", "ISSUE-123"],
        ["approve"],
        ["reject", "reason"],
        ["cancel", "--force"],
    ])
    @patch("amelia.client.cli.get_worktree_context")
    def test_error_when_not_in_git_repo(
        self,
        mock_worktree: MagicMock,
        cli_runner: CliRunner,
        cmd: list[str],
    ) -> None:
        """All commands fail gracefully when not in git repo."""
        from amelia.main import app

        mock_worktree.side_effect = ValueError("Not inside a git repository")
        result = cli_runner.invoke(app, cmd)
        assert result.exit_code == 1
        assert "git repository" in result.stdout.lower() or "error" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_cancel_flow(
        self,
        mock_client_class: MagicMock,
        mock_worktree: MagicMock,
        cli_runner: CliRunner,
        git_repo_with_changes: Path,
    ) -> None:
        """Test start -> cancel flow."""
        from amelia.main import app

        mock_worktree.return_value = (str(git_repo_with_changes), "main")

        mock_client = AsyncMock()

        # Mock start workflow response
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            issue_id="ISSUE-123",
            status="planning",
            worktree_path=str(git_repo_with_changes),
            worktree_name="main",
            started_at=datetime(2025, 12, 1, 10, 0, 0),
        )

        # Mock get workflows for cancel
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="in_progress",
                )
            ]
        )
        mock_client.cancel_workflow.return_value = None

        mock_client_class.return_value = mock_client

        # Start workflow
        result = cli_runner.invoke(app, ["start", "ISSUE-123"])
        assert result.exit_code == 0
        assert "wf-123" in result.stdout

        # Cancel workflow (with --force to skip confirmation)
        result = cli_runner.invoke(app, ["cancel", "--force"])
        assert result.exit_code == 0
        assert "cancelled" in result.stdout.lower()
