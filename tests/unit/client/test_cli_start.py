"""Tests for CLI start command."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from typer.testing import CliRunner

from amelia.main import app


class TestStartCommandTaskFlags:
    """Tests for --title and --description flags on start command."""

    def test_description_without_title_errors(self, runner: CliRunner) -> None:
        """--description without --title should error at client side."""
        result = runner.invoke(
            app,
            ["start", "TASK-1", "--description", "Some description"],
        )
        assert result.exit_code != 0
        output = result.stdout.lower() + (result.output.lower() if hasattr(result, 'output') else '')
        assert "requires" in output or "title" in output

    def test_title_flag_passed_to_client(self, runner: CliRunner, mock_worktree: Path) -> None:
        """--title should be passed to API client."""
        with patch("amelia.client.cli._get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(mock_worktree), "repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(return_value=MagicMock(
                id=str(uuid4()), status="pending"
            ))

            result = runner.invoke(
                app,
                ["start", "TASK-1", "-p", "none", "--title", "Add logout button"],
            )

            assert result.exit_code == 0, f"Command failed: {result.stdout}"
            mock_client.create_workflow.assert_called_once()
            call_kwargs = mock_client.create_workflow.call_args.kwargs
            assert call_kwargs.get("task_title") == "Add logout button"

    def test_title_and_description_flags_passed_to_client(self, runner: CliRunner, mock_worktree: Path) -> None:
        """--title and --description should both be passed to API client."""
        with patch("amelia.client.cli._get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(mock_worktree), "repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(return_value=MagicMock(
                id=str(uuid4()), status="pending"
            ))

            runner.invoke(
                app,
                [
                    "start", "TASK-1", "-p", "none",
                    "--title", "Add logout button",
                    "--description", "Implement logout functionality in the navbar",
                ],
            )

            mock_client.create_workflow.assert_called_once()
            call_kwargs = mock_client.create_workflow.call_args.kwargs
            assert call_kwargs.get("task_title") == "Add logout button"
            assert call_kwargs.get("task_description") == "Implement logout functionality in the navbar"


class TestPlanCommandTaskFlags:
    """Tests for --title and --description flags on plan command."""

    def test_description_without_title_errors(self, runner: CliRunner) -> None:
        """--description without --title should error at client side."""
        result = runner.invoke(
            app,
            ["plan", "TASK-1", "--description", "Some description"],
        )
        assert result.exit_code != 0
        output = (result.stdout + result.output).lower()
        assert "requires" in output or "title" in output

    def test_title_flag_constructs_issue_directly(self, runner: CliRunner, mock_worktree: Path) -> None:
        """--title should construct Issue directly, bypassing tracker."""
        mock_profile_response = {
            "id": "noop",
            "tracker": "noop",
            "repo_root": str(mock_worktree),
            "plan_output_dir": "docs/plans",
            "plan_path_pattern": "docs/plans/{date}-{issue_key}.md",
            "is_active": True,
            "agents": {
                "architect": {"driver": "claude", "model": "sonnet", "options": {}},
                "developer": {"driver": "claude", "model": "sonnet", "options": {}},
                "reviewer": {"driver": "claude", "model": "sonnet", "options": {}},
            },
        }

        with patch("amelia.client.cli._get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.Architect") as mock_architect_class, \
             patch("amelia.client.cli.create_tracker") as mock_create_tracker, \
             patch("httpx.AsyncClient") as mock_http_client_class:
            mock_ctx.return_value = (str(mock_worktree), "repo")

            mock_http_client = MagicMock()
            mock_http_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_http_client_class.return_value.__aexit__ = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=MagicMock(
                status_code=200,
                json=MagicMock(return_value=mock_profile_response),
            ))

            mock_architect = mock_architect_class.return_value
            captured_state = None

            async def capture_plan(*args, **kwargs):
                nonlocal captured_state
                captured_state = kwargs.get("state") or args[0]
                final_state = captured_state.model_copy(update={"plan_path": "/tmp/plan.md"})
                yield final_state, None

            mock_architect.plan = capture_plan

            runner.invoke(
                app,
                ["plan", "TASK-1", "-p", "noop", "--title", "Fix typo", "--description", "Fix README"],
            )

            mock_create_tracker.assert_not_called()

            assert captured_state is not None
            assert captured_state.issue.title == "Fix typo"
            assert captured_state.issue.description == "Fix README"
