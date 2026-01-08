"""Integration tests for CLI task option (--title/--description)."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from amelia.main import app


class TestCliTaskOptionIntegration:
    """Integration tests for --title/--description CLI flow."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def noop_worktree(self, tmp_path: Path) -> Path:
        """Create a worktree with noop tracker settings."""
        worktree = tmp_path / "noop-repo"
        worktree.mkdir()
        (worktree / ".git").touch()
        settings_content = """
active_profile: noop
profiles:
  noop:
    name: noop
    driver: cli:claude
    model: sonnet
    tracker: noop
    strategy: single
"""
        (worktree / "settings.amelia.yaml").write_text(settings_content)
        return worktree

    @pytest.fixture
    def github_worktree(self, tmp_path: Path) -> Path:
        """Create a worktree with github tracker settings."""
        worktree = tmp_path / "github-repo"
        worktree.mkdir()
        (worktree / ".git").touch()
        settings_content = """
active_profile: github
profiles:
  github:
    name: github
    driver: cli:claude
    model: sonnet
    tracker: github
    strategy: single
"""
        (worktree / "settings.amelia.yaml").write_text(settings_content)
        return worktree

    def test_start_with_title_noop_tracker_succeeds(
        self,
        runner: CliRunner,
        noop_worktree: Path,
    ) -> None:
        """start with --title and noop tracker should succeed."""
        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(noop_worktree), "noop-repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(return_value=MagicMock(
                id="wf-123", status="pending"
            ))

            result = runner.invoke(
                app,
                [
                    "start", "TASK-1",
                    "-p", "noop",
                    "--title", "Add logout button",
                    "--description", "Add to navbar",
                ],
            )

            assert result.exit_code == 0
            assert "wf-123" in result.stdout

            # Verify task fields were passed
            call_kwargs = mock_client.create_workflow.call_args.kwargs
            assert call_kwargs["task_title"] == "Add logout button"
            assert call_kwargs["task_description"] == "Add to navbar"

    def test_start_with_title_non_noop_tracker_returns_400(
        self,
        runner: CliRunner,
        github_worktree: Path,
    ) -> None:
        """start with --title and github tracker should return 400 error."""
        from amelia.client.api import InvalidRequestError

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(github_worktree), "github-repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(
                side_effect=InvalidRequestError("--title requires noop tracker")
            )

            result = runner.invoke(
                app,
                [
                    "start", "TASK-1",
                    "-p", "github",
                    "--title", "Add logout button",
                ],
            )

            assert result.exit_code == 1
            assert "noop" in result.stdout.lower() or "error" in result.stdout.lower()
