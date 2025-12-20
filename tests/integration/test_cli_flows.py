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

from amelia.core.types import Settings


@pytest.fixture
def mock_workflow_client(git_repo_with_changes: Path) -> AsyncMock:
    """Common mock client setup for workflow tests."""
    mock_client = AsyncMock()
    mock_client.create_workflow.return_value = MagicMock(
        id="wf-123",
        issue_id="ISSUE-123",
        status="planning",
        worktree_path=str(git_repo_with_changes),
        worktree_name="main",
        started_at=datetime(2025, 12, 1, 10, 0, 0),
    )
    return mock_client


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
        mock_workflow_client: AsyncMock,
    ) -> None:
        """Test start -> approve flow."""
        from amelia.main import app

        mock_worktree.return_value = (str(git_repo_with_changes), "main")

        mock_client = mock_workflow_client

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
        mock_workflow_client: AsyncMock,
    ) -> None:
        """Test start -> reject flow."""
        from amelia.main import app

        mock_worktree.return_value = (str(git_repo_with_changes), "main")

        mock_client = mock_workflow_client

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
        mock_workflow_client: AsyncMock,
    ) -> None:
        """Test start -> status flow."""
        from amelia.main import app

        mock_worktree.return_value = (str(git_repo_with_changes), "main")

        mock_client = mock_workflow_client

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

    @pytest.mark.parametrize("cmd,issue_id,plan_only_expected", [
        (["start", "ISSUE-123"], "ISSUE-123", False),
        (["plan", "ISSUE-456"], "ISSUE-456", True),
    ])
    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_workflow_creation_commands(
        self,
        mock_client_class: MagicMock,
        mock_worktree: MagicMock,
        cli_runner: CliRunner,
        git_repo_with_changes: Path,
        cmd: list[str],
        issue_id: str,
        plan_only_expected: bool,
    ) -> None:
        """Test start and plan commands create workflows correctly."""
        from amelia.main import app

        mock_worktree.return_value = (str(git_repo_with_changes), "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            issue_id=issue_id,
            status="planning",
            worktree_path=str(git_repo_with_changes),
            worktree_name="main",
            started_at=datetime(2025, 12, 1, 10, 0, 0),
        )
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, cmd)

        assert result.exit_code == 0
        assert "wf-123" in result.stdout
        mock_client.create_workflow.assert_called_once()
        call_kwargs = mock_client.create_workflow.call_args.kwargs
        assert call_kwargs["issue_id"] == issue_id
        assert call_kwargs.get("plan_only", False) is plan_only_expected

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
        mock_workflow_client: AsyncMock,
    ) -> None:
        """Test start -> cancel flow."""
        from amelia.main import app

        mock_worktree.return_value = (str(git_repo_with_changes), "main")

        mock_client = mock_workflow_client

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

    @pytest.mark.parametrize("extra_args,expected_profile", [
        ([], None),
        (["--profile", "work"], "work"),
    ])
    @patch("amelia.main.stream_workflow_events")
    @patch("amelia.main.run_shell_command")
    @patch("amelia.main.load_settings")
    @patch("amelia.main.AmeliaClient")
    def test_review_local_creates_workflow(
        self,
        mock_client_class: MagicMock,
        mock_load_settings: MagicMock,
        mock_run_shell: MagicMock,
        mock_stream: MagicMock,
        cli_runner: CliRunner,
        mock_settings: Settings,
        extra_args: list[str],
        expected_profile: str | None,
    ) -> None:
        """Test review --local creates review workflow with diff content."""
        from amelia.main import app

        mock_load_settings.return_value = mock_settings
        mock_run_shell.return_value = "diff --git a/file.txt\n+new line"

        mock_client = AsyncMock()
        mock_client.create_review_workflow.return_value = MagicMock(
            id="wf-review-123",
        )
        mock_client_class.return_value = mock_client
        mock_stream.return_value = None

        result = cli_runner.invoke(app, ["review", "--local"] + extra_args)

        assert result.exit_code == 0
        assert "wf-review-123" in result.stdout
        mock_client.create_review_workflow.assert_called_once()
        call_kwargs = mock_client.create_review_workflow.call_args.kwargs
        assert "diff_content" in call_kwargs
        assert "+new line" in call_kwargs["diff_content"]
        if expected_profile:
            assert call_kwargs["profile"] == expected_profile

    @patch("amelia.main.run_shell_command")
    @patch("amelia.main.load_settings")
    def test_review_local_no_changes(
        self,
        mock_load_settings: MagicMock,
        mock_run_shell: MagicMock,
        cli_runner: CliRunner,
        mock_settings: Settings,
    ) -> None:
        """Test review --local exits gracefully when no changes exist."""
        from amelia.main import app

        mock_load_settings.return_value = mock_settings
        mock_run_shell.return_value = ""

        result = cli_runner.invoke(app, ["review", "--local"])

        assert result.exit_code == 0
        assert "no local uncommitted changes" in result.stdout.lower()

    @pytest.mark.parametrize("cmd", [
        ["start", "ISSUE-123"],
        ["plan", "ISSUE-123"],
    ])
    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_profile_flag_passed_to_client(
        self,
        mock_client_class: MagicMock,
        mock_worktree: MagicMock,
        cli_runner: CliRunner,
        git_repo_with_changes: Path,
        cmd: list[str],
    ) -> None:
        """Verify --profile flag is consistently passed across start and plan commands."""
        from amelia.main import app

        mock_worktree.return_value = (str(git_repo_with_changes), "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            issue_id="ISSUE-123",
            status="planning",
            worktree_path=str(git_repo_with_changes),
            worktree_name="main",
            started_at=datetime(2025, 12, 1, 10, 0, 0),
        )
        mock_client_class.return_value = mock_client

        result = cli_runner.invoke(app, cmd + ["--profile", "work"])

        assert result.exit_code == 0
        call_kwargs = mock_client.create_workflow.call_args.kwargs
        assert call_kwargs["profile"] == "work"

    @patch("amelia.main.validate_profile")
    @patch("amelia.main.load_settings")
    def test_review_without_local_flag_fails(
        self,
        mock_load_settings: MagicMock,
        mock_validate_profile: MagicMock,
        cli_runner: CliRunner,
        mock_settings: Settings,
    ) -> None:
        """Test review command without --local shows usage message."""
        from amelia.main import app

        mock_load_settings.return_value = mock_settings
        mock_validate_profile.return_value = None

        result = cli_runner.invoke(app, ["review"])

        assert result.exit_code == 1
        # Error message is written to stderr (err=True)
        combined_output = result.stdout + result.stderr
        assert "use --local to review local uncommitted changes" in combined_output.lower()
