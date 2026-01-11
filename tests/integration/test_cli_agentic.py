"""Integration tests for CLI commands in agentic execution mode.

Tests the Amelia CLI commands: plan, start, approve, reject, status, cancel.

For CLI tests, the proper mock boundaries are:
- AmeliaClient: HTTP client to Amelia API server (for start/approve/reject/status/cancel)
- create_tracker: External issue tracker API (Jira, GitHub)
- pydantic_ai.Agent: LLM API boundary (for plan command which runs locally)
- get_worktree_context: Git context detection (needed for test isolation)

Internal components like DriverFactory and Architect should NOT be mocked.
"""
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from amelia.agents.architect import MarkdownPlanOutput
from amelia.client.models import (
    CreateWorkflowResponse,
    WorkflowListResponse,
    WorkflowSummary,
)
from amelia.core.types import Issue, Profile, Settings
from amelia.main import app


runner = CliRunner()


@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set API key env var to allow driver construction."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-for-integration-tests")


@pytest.fixture
def mock_worktree_context(tmp_path: Path) -> Generator[MagicMock, None, None]:
    """Mock git worktree context."""
    with patch("amelia.client.cli.get_worktree_context") as mock:
        mock.return_value = (str(tmp_path), "test-worktree")
        yield mock


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    """Create mock settings for CLI tests."""
    profile = Profile(
        name="test",
        driver="api:openrouter",
        model="openrouter:anthropic/claude-sonnet-4",
        tracker="noop",
        working_dir=str(tmp_path),
        plan_output_dir=str(tmp_path / "plans"),
    )
    return Settings(active_profile="test", profiles={"test": profile})


@pytest.mark.integration
class TestPlanCommand:
    """Test the `amelia plan` command with real components.

    Real components: DriverFactory, ApiDriver, Architect
    Mock boundaries:
    - get_worktree_context (git detection)
    - load_settings (config file)
    - create_tracker (external issue tracker API)
    - pydantic_ai.Agent.run (LLM HTTP boundary)
    """

    def test_plan_command_generates_markdown(
        self, tmp_path: Path, mock_worktree_context: MagicMock, mock_settings: Settings
    ) -> None:
        """amelia plan should generate markdown plan file."""
        # Create plans directory
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        # Mock LLM response - this is the HTTP boundary
        mock_llm_response = MarkdownPlanOutput(
            goal="Implement feature X",
            plan_markdown="# Implementation Plan\n\n1. Step one\n2. Step two",
            key_files=["src/app.py", "tests/test_app.py"],
        )

        mock_result = MagicMock()
        mock_result.output = mock_llm_response

        mock_issue = Issue(
            id="TEST-123",
            title="Test Issue",
            description="Test description",
            status="open",
        )

        with patch("amelia.client.cli.load_settings") as mock_load_settings, \
             patch("amelia.client.cli.create_tracker") as mock_create_tracker, \
             patch("pydantic_ai.Agent.run", new_callable=AsyncMock) as mock_agent_run:

            mock_load_settings.return_value = mock_settings
            mock_create_tracker.return_value.get_issue.return_value = mock_issue
            mock_agent_run.return_value = mock_result

            # Run through typer
            result = runner.invoke(app, ["plan", "TEST-123"])

        assert result.exit_code == 0, f"CLI failed with: {result.stdout}"
        assert "Plan generated successfully" in result.stdout or "✓" in result.stdout

    def test_plan_command_with_profile(
        self, tmp_path: Path, mock_worktree_context: MagicMock
    ) -> None:
        """amelia plan --profile work should use specified profile."""
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        # Create settings with multiple profiles
        test_profile = Profile(
            name="test",
            driver="cli:claude",
            model="sonnet",
            tracker="noop",
        )
        work_profile = Profile(
            name="work",
            driver="api:openrouter",
            model="openrouter:anthropic/claude-sonnet-4",
            tracker="jira",
            working_dir=str(tmp_path),
            plan_output_dir=str(plans_dir),
        )
        settings = Settings(
            active_profile="test",
            profiles={"test": test_profile, "work": work_profile},
        )

        mock_llm_response = MarkdownPlanOutput(
            goal="Complete work task",
            plan_markdown="# Work Plan\n\n1. Do work",
            key_files=["src/work.py"],
        )

        mock_result = MagicMock()
        mock_result.output = mock_llm_response

        mock_issue = Issue(
            id="WORK-456",
            title="Work Issue",
            description="Work description",
            status="open",
        )

        with patch("amelia.client.cli.load_settings") as mock_load_settings, \
             patch("amelia.client.cli.create_tracker") as mock_create_tracker, \
             patch("pydantic_ai.Agent.run", new_callable=AsyncMock) as mock_agent_run:

            mock_load_settings.return_value = settings
            mock_create_tracker.return_value.get_issue.return_value = mock_issue
            mock_agent_run.return_value = mock_result

            result = runner.invoke(app, ["plan", "WORK-456", "--profile", "work"])

        assert result.exit_code == 0, f"CLI failed with: {result.stdout}"
        # Verify tracker was created (would have been called with work profile's tracker=jira)
        mock_create_tracker.assert_called_once()


@pytest.mark.integration
class TestStartCommand:
    """Test the `amelia start` command.

    Mock boundary: AmeliaClient (HTTP client to Amelia API server)
    """

    def test_start_command_creates_workflow(
        self, tmp_path: Path, mock_worktree_context: MagicMock
    ) -> None:
        """amelia start should create workflow via API."""
        mock_response = CreateWorkflowResponse(
            id="wf-123",
            status="running",
            message="Workflow created successfully",
        )

        with patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.create_workflow = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = runner.invoke(app, ["start", "TEST-456"])

        assert result.exit_code == 0
        assert "Workflow started" in result.stdout or "wf-123" in result.stdout

    def test_start_command_handles_server_unreachable(
        self, tmp_path: Path, mock_worktree_context: MagicMock
    ) -> None:
        """amelia start should handle server unreachable error gracefully."""
        from amelia.client.api import ServerUnreachableError

        with patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.create_workflow = AsyncMock(
                side_effect=ServerUnreachableError("Cannot connect to server")
            )
            mock_client_class.return_value = mock_client

            result = runner.invoke(app, ["start", "TEST-456"])

        assert result.exit_code == 1
        assert "Error" in result.stdout


@pytest.mark.integration
class TestApproveCommand:
    """Test the `amelia approve` command.

    Mock boundary: AmeliaClient (HTTP client to Amelia API server)
    """

    def test_approve_command_approves_workflow(
        self, tmp_path: Path, mock_worktree_context: MagicMock
    ) -> None:
        """amelia approve should approve the pending workflow."""
        mock_workflows = WorkflowListResponse(
            workflows=[
                WorkflowSummary(
                    id="wf-789",
                    issue_id="TEST-789",
                    status="awaiting_approval",
                    worktree_path="/tmp/test-worktree",
                    started_at=datetime.now(UTC),
                )
            ],
            total=1,
        )

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(tmp_path), "test-worktree")

            mock_client = MagicMock()
            mock_client.get_active_workflows = AsyncMock(return_value=mock_workflows)
            mock_client.approve_workflow = AsyncMock()
            mock_client_class.return_value = mock_client

            result = runner.invoke(app, ["approve"])

        assert result.exit_code == 0
        assert "approved" in result.stdout.lower() or "wf-789" in result.stdout

    def test_approve_command_no_active_workflow(
        self, tmp_path: Path, mock_worktree_context: MagicMock
    ) -> None:
        """amelia approve should error when no workflow is active."""
        mock_workflows = WorkflowListResponse(workflows=[], total=0)

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(tmp_path), "test-worktree")

            mock_client = MagicMock()
            mock_client.get_active_workflows = AsyncMock(return_value=mock_workflows)
            mock_client_class.return_value = mock_client

            result = runner.invoke(app, ["approve"])

        assert result.exit_code == 1
        assert "No workflow active" in result.stdout


@pytest.mark.integration
class TestRejectCommand:
    """Test the `amelia reject` command.

    Mock boundary: AmeliaClient (HTTP client to Amelia API server)
    """

    def test_reject_command_rejects_workflow(
        self, tmp_path: Path, mock_worktree_context: MagicMock
    ) -> None:
        """amelia reject should reject with feedback."""
        mock_workflows = WorkflowListResponse(
            workflows=[
                WorkflowSummary(
                    id="wf-reject",
                    issue_id="TEST-REJECT",
                    status="awaiting_approval",
                    worktree_path="/tmp/test-worktree",
                    started_at=datetime.now(UTC),
                )
            ],
            total=1,
        )

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(tmp_path), "test-worktree")

            mock_client = MagicMock()
            mock_client.get_active_workflows = AsyncMock(return_value=mock_workflows)
            mock_client.reject_workflow = AsyncMock()
            mock_client_class.return_value = mock_client

            result = runner.invoke(app, ["reject", "Please add more tests"])

        assert result.exit_code == 0
        assert "rejected" in result.stdout.lower() or "replan" in result.stdout.lower()


@pytest.mark.integration
class TestStatusCommand:
    """Test the `amelia status` command.

    Mock boundary: AmeliaClient (HTTP client to Amelia API server)
    """

    def test_status_command_shows_current_workflow(
        self, tmp_path: Path, mock_worktree_context: MagicMock
    ) -> None:
        """amelia status should show workflow for current worktree."""
        mock_workflows = WorkflowListResponse(
            workflows=[
                WorkflowSummary(
                    id="wf-status",
                    issue_id="TEST-STATUS",
                    status="running",
                    worktree_path="/tmp/test-worktree",
                    started_at=datetime.now(UTC),
                )
            ],
            total=1,
        )

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(tmp_path), "test-worktree")

            mock_client = MagicMock()
            mock_client.get_active_workflows = AsyncMock(return_value=mock_workflows)
            mock_client_class.return_value = mock_client

            result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "wf-status" in result.stdout or "TEST-STATUS" in result.stdout

    def test_status_command_all_worktrees(self, tmp_path: Path) -> None:
        """amelia status --all should show all workflows."""
        mock_workflows = WorkflowListResponse(
            workflows=[
                WorkflowSummary(
                    id="wf-1",
                    issue_id="TEST-1",
                    status="running",
                    worktree_path="/tmp/worktree-1",
                    started_at=datetime.now(UTC),
                ),
                WorkflowSummary(
                    id="wf-2",
                    issue_id="TEST-2",
                    status="awaiting_approval",
                    worktree_path="/tmp/worktree-2",
                    started_at=datetime.now(UTC),
                ),
            ],
            total=2,
        )

        with patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.get_active_workflows = AsyncMock(return_value=mock_workflows)
            mock_client_class.return_value = mock_client

            result = runner.invoke(app, ["status", "--all"])

        assert result.exit_code == 0
        assert "2" in result.stdout  # Total count
        # Verify both worktrees appear
        assert "worktree-1" in result.stdout or "wf-1" in result.stdout
        assert "worktree-2" in result.stdout or "wf-2" in result.stdout

    def test_status_command_no_workflows(
        self, tmp_path: Path, mock_worktree_context: MagicMock
    ) -> None:
        """amelia status should show message when no workflows active."""
        mock_workflows = WorkflowListResponse(workflows=[], total=0)

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(tmp_path), "test-worktree")

            mock_client = MagicMock()
            mock_client.get_active_workflows = AsyncMock(return_value=mock_workflows)
            mock_client_class.return_value = mock_client

            result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "No active workflow" in result.stdout or "no active" in result.stdout.lower()


@pytest.mark.integration
class TestCancelCommand:
    """Test the `amelia cancel` command.

    Mock boundary: AmeliaClient (HTTP client to Amelia API server)
    """

    def test_cancel_command_cancels_workflow(
        self, tmp_path: Path, mock_worktree_context: MagicMock
    ) -> None:
        """amelia cancel --force should cancel without confirmation."""
        mock_workflows = WorkflowListResponse(
            workflows=[
                WorkflowSummary(
                    id="wf-cancel",
                    issue_id="TEST-CANCEL",
                    status="running",
                    worktree_path="/tmp/test-worktree",
                    started_at=datetime.now(UTC),
                )
            ],
            total=1,
        )

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(tmp_path), "test-worktree")

            mock_client = MagicMock()
            mock_client.get_active_workflows = AsyncMock(return_value=mock_workflows)
            mock_client.cancel_workflow = AsyncMock()
            mock_client_class.return_value = mock_client

            result = runner.invoke(app, ["cancel", "--force"])

        assert result.exit_code == 0
        assert "cancelled" in result.stdout.lower() or "wf-cancel" in result.stdout

    def test_cancel_command_no_workflow(
        self, tmp_path: Path, mock_worktree_context: MagicMock
    ) -> None:
        """amelia cancel should error when no workflow is active."""
        mock_workflows = WorkflowListResponse(workflows=[], total=0)

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(tmp_path), "test-worktree")

            mock_client = MagicMock()
            mock_client.get_active_workflows = AsyncMock(return_value=mock_workflows)
            mock_client_class.return_value = mock_client

            result = runner.invoke(app, ["cancel", "--force"])

        assert result.exit_code == 1
        assert "No workflow active" in result.stdout

    def test_cancel_command_prompts_before_cancelling(
        self, tmp_path: Path, mock_worktree_context: MagicMock
    ) -> None:
        """amelia cancel without --force should prompt and cancel only after user confirms."""
        mock_workflows = WorkflowListResponse(
            workflows=[
                WorkflowSummary(
                    id="wf-confirm",
                    issue_id="TEST-CONFIRM",
                    status="running",
                    worktree_path="/tmp/test-worktree",
                    started_at=datetime.now(UTC),
                )
            ],
            total=1,
        )

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(tmp_path), "test-worktree")

            mock_client = MagicMock()
            mock_client.get_active_workflows = AsyncMock(return_value=mock_workflows)
            mock_client.cancel_workflow = AsyncMock()
            mock_client_class.return_value = mock_client

            # Simulate user typing "y" to confirm
            result = runner.invoke(app, ["cancel"], input="y\n")

        assert result.exit_code == 0
        assert "cancelled" in result.stdout.lower() or "wf-confirm" in result.stdout
        # Verify cancel_workflow was called after confirmation
        mock_client.cancel_workflow.assert_called_once_with(workflow_id="wf-confirm")

    def test_cancel_command_aborts_on_decline(
        self, tmp_path: Path, mock_worktree_context: MagicMock
    ) -> None:
        """amelia cancel should NOT cancel when user declines confirmation."""
        mock_workflows = WorkflowListResponse(
            workflows=[
                WorkflowSummary(
                    id="wf-decline",
                    issue_id="TEST-DECLINE",
                    status="running",
                    worktree_path="/tmp/test-worktree",
                    started_at=datetime.now(UTC),
                )
            ],
            total=1,
        )

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(tmp_path), "test-worktree")

            mock_client = MagicMock()
            mock_client.get_active_workflows = AsyncMock(return_value=mock_workflows)
            mock_client.cancel_workflow = AsyncMock()
            mock_client_class.return_value = mock_client

            # Simulate user typing "n" to decline
            result = runner.invoke(app, ["cancel"], input="n\n")

        assert result.exit_code == 0
        assert "Aborted" in result.stdout
        # CRITICAL: Verify cancel_workflow was NOT called when user declined
        mock_client.cancel_workflow.assert_not_called()


@pytest.mark.integration
class TestCLIErrorHandling:
    """Test CLI error handling."""

    def test_cli_not_in_git_repo(self, tmp_path: Path) -> None:
        """CLI should error gracefully when not in a git repo."""
        with patch("amelia.client.cli.get_worktree_context") as mock_ctx:
            mock_ctx.side_effect = ValueError("Not inside a git repository")

            result = runner.invoke(app, ["status"])

        assert result.exit_code == 1
        assert "git repository" in result.stdout.lower() or "error" in result.stdout.lower()
