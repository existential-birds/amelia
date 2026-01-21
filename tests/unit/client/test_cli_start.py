"""Tests for CLI start command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from amelia.main import app


class TestStartCommandTaskFlags:
    """Tests for --title and --description flags on start command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_description_without_title_errors(self, runner):
        """--description without --title should error at client side."""
        result = runner.invoke(
            app,
            ["start", "TASK-1", "--description", "Some description"],
        )
        assert result.exit_code != 0
        # Check output includes the validation error message
        output = result.stdout.lower() + (result.output.lower() if hasattr(result, 'output') else '')
        assert "requires" in output or "title" in output

    def test_title_flag_passed_to_client(self, runner, tmp_path):
        """--title should be passed to API client."""
        # Create mock git worktree
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").touch()

        with patch("amelia.client.cli._get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(worktree), "repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(return_value=MagicMock(
                id="wf-123", status="pending"
            ))

            result = runner.invoke(
                app,
                ["start", "TASK-1", "-p", "noop", "--title", "Add logout button"],
            )

            assert result.exit_code == 0, f"Command failed: {result.stdout}"

            # Verify create_workflow was called with task_title
            mock_client.create_workflow.assert_called_once()
            call_kwargs = mock_client.create_workflow.call_args.kwargs
            assert call_kwargs.get("task_title") == "Add logout button"

    def test_title_and_description_flags_passed_to_client(self, runner, tmp_path):
        """--title and --description should both be passed to API client."""
        # Create mock git worktree
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").touch()

        with patch("amelia.client.cli._get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(worktree), "repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(return_value=MagicMock(
                id="wf-123", status="pending"
            ))

            runner.invoke(
                app,
                [
                    "start", "TASK-1", "-p", "noop",
                    "--title", "Add logout button",
                    "--description", "Implement logout functionality in the navbar",
                ],
            )

            # Verify create_workflow was called with both parameters
            mock_client.create_workflow.assert_called_once()
            call_kwargs = mock_client.create_workflow.call_args.kwargs
            assert call_kwargs.get("task_title") == "Add logout button"
            assert call_kwargs.get("task_description") == "Implement logout functionality in the navbar"


class TestPlanCommandTaskFlags:
    """Tests for --title and --description flags on plan command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_description_without_title_errors(self, runner):
        """--description without --title should error at client side."""
        result = runner.invoke(
            app,
            ["plan", "TASK-1", "--description", "Some description"],
        )
        assert result.exit_code != 0
        # Check both stdout and output (typer uses different attributes)
        output = (result.stdout + result.output).lower()
        assert "requires" in output or "title" in output

    def test_title_flag_constructs_issue_directly(self, runner, tmp_path):
        """--title should construct Issue directly, bypassing tracker."""
        # Create mock git worktree
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").touch()

        # Mock profile data returned from server API
        mock_profile_response = {
            "id": "noop",
            "driver": "cli:claude",
            "model": "sonnet",
            "validator_model": "sonnet",
            "tracker": "noop",
            "working_dir": str(worktree),
            "plan_output_dir": "docs/plans",
            "plan_path_pattern": "docs/plans/{date}-{issue_key}.md",
            "max_review_iterations": 3,
            "max_task_review_iterations": 5,
            "auto_approve_reviews": False,
            "is_active": True,
        }

        with patch("amelia.client.cli._get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.Architect") as mock_architect_class, \
             patch("amelia.client.cli.DriverFactory"), \
             patch("amelia.client.cli.create_tracker") as mock_create_tracker, \
             patch("httpx.AsyncClient") as mock_http_client_class:
            mock_ctx.return_value = (str(worktree), "repo")

            # Mock the HTTP client for profile fetching
            mock_http_client = MagicMock()
            mock_http_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_http_client_class.return_value.__aexit__ = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=MagicMock(
                status_code=200,
                json=MagicMock(return_value=mock_profile_response),
            ))

            # Mock architect to capture the state
            mock_architect = mock_architect_class.return_value
            captured_state = None

            async def capture_plan(*args, **kwargs):
                nonlocal captured_state
                captured_state = kwargs.get("state") or args[0]
                # Yield a final state
                final_state = captured_state.model_copy(update={"plan_path": "/tmp/plan.md"})
                yield final_state, None

            mock_architect.plan = capture_plan

            runner.invoke(
                app,
                ["plan", "TASK-1", "-p", "noop", "--title", "Fix typo", "--description", "Fix README"],
            )

            # Tracker should NOT be called when --title is provided with noop
            mock_create_tracker.assert_not_called()

            # State should have our custom issue
            assert captured_state is not None
            assert captured_state.issue.title == "Fix typo"
            assert captured_state.issue.description == "Fix README"
