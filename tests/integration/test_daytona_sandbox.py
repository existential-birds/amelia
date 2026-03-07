"""Integration test for Daytona sandbox stack.

Tests DaytonaSandboxProvider + ContainerDriver + WorktreeManager
working together, mocking at the Daytona SDK boundary.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import SandboxConfig, SandboxMode
from amelia.drivers.base import AgenticMessage, AgenticMessageType


def _configure_session_streaming(mock_sandbox, responses: dict[str, str]):
    """Configure mock sandbox with session-based streaming.

    Args:
        mock_sandbox: The mock sandbox object.
        responses: Mapping of command substring -> stdout output.
            If a command contains the key, the corresponding value is
            delivered via the on_stdout callback.
    """
    # Health check still uses process.exec
    mock_sandbox.process.exec.return_value = MagicMock(exit_code=0)

    # execute_session_command returns a response with cmd_id
    mock_sandbox.process.execute_session_command.return_value = MagicMock(
        cmd_id="test-cmd-id",
    )

    # get_session_command returns success exit code
    mock_sandbox.process.get_session_command.return_value = MagicMock(
        exit_code=0,
    )

    # get_session_command_logs_async delivers output via callback
    async def fake_logs_async(session_id, cmd_id, on_stdout, on_stderr):
        # Find which command was executed by checking the execute call
        exec_call = mock_sandbox.process.execute_session_command.call_args
        cmd_str = exec_call[0][1].command if exec_call else ""

        for pattern, output in responses.items():
            if pattern in cmd_str:
                if output:
                    await on_stdout(output)
                return
        # Default: no output

    mock_sandbox.process.get_session_command_logs_async.side_effect = fake_logs_async


class TestDaytonaFullStack:
    """DaytonaSandboxProvider + ContainerDriver end-to-end."""

    @pytest.fixture
    def mock_daytona(self):
        """Mock Daytona SDK returning realistic session-based responses."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.id = "test-sandbox-123"
            mock_sandbox.process.exec.return_value = MagicMock(
                result="", exit_code=0,
            )
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client
            yield mock_sandbox

    @pytest.mark.asyncio
    async def test_container_driver_with_daytona_provider(self, mock_daytona):
        """ContainerDriver should work with DaytonaSandboxProvider."""
        from amelia.sandbox.daytona import DaytonaSandboxProvider
        from amelia.sandbox.driver import ContainerDriver

        provider = DaytonaSandboxProvider(
            api_key="test-key",
            api_url="https://test.daytona.io/api",
            target="us",
            repo_url="https://github.com/org/repo.git",
        )
        driver = ContainerDriver(model="test-model", provider=provider)

        # Build the RESULT message the worker would emit
        result_msg = AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="Generated output",
        )

        # Track which command is being executed for per-call responses.
        call_count = {"n": 0}
        worker_json = result_msg.model_dump_json()

        async def per_call_logs_async(session_id, cmd_id, on_stdout, on_stderr):
            call_count["n"] += 1
            exec_call = mock_daytona.process.execute_session_command.call_args
            cmd_str = exec_call[0][1].command if exec_call else ""
            if "worker" in cmd_str and "generate" in cmd_str:
                await on_stdout(worker_json + "\n")

        mock_daytona.process.execute_session_command.return_value = MagicMock(
            cmd_id="test-cmd-id",
        )
        mock_daytona.process.get_session_command.return_value = MagicMock(
            exit_code=0,
        )
        mock_daytona.process.get_session_command_logs_async.side_effect = (
            per_call_logs_async
        )

        output, session_id = await driver.generate(prompt="Test prompt")
        assert output == "Generated output"
        assert session_id is None

    @pytest.mark.asyncio
    async def test_worktree_manager_with_daytona_provider(self, mock_daytona):
        """WorktreeManager should work via DaytonaSandboxProvider.exec_stream."""
        from amelia.sandbox.daytona import DaytonaSandboxProvider
        from amelia.sandbox.worktree import WorktreeManager

        provider = DaytonaSandboxProvider(
            api_key="test-key",
            api_url="https://test.daytona.io/api",
            target="us",
            repo_url="https://github.com/org/repo.git",
        )
        await provider.ensure_running()

        wt = WorktreeManager(
            provider=provider,
            repo_url="https://github.com/org/repo.git",
        )

        # Session-based streaming returns empty output for git commands
        mock_daytona.process.execute_session_command.return_value = MagicMock(
            cmd_id="test-cmd-id",
        )
        mock_daytona.process.get_session_command.return_value = MagicMock(
            exit_code=0,
        )

        async def noop_logs_async(session_id, cmd_id, on_stdout, on_stderr):
            pass  # No output for git commands

        mock_daytona.process.get_session_command_logs_async.side_effect = (
            noop_logs_async
        )

        worktree_path = await wt.create_worktree("wf-123", base_branch="main")
        assert worktree_path == "/workspace/worktrees/wf-123"

    @pytest.mark.asyncio
    async def test_worktree_manager_detects_existing_clone(self, mock_daytona):
        """setup_repo should fetch (not clone) when the repo already exists."""
        from amelia.sandbox.daytona import DaytonaSandboxProvider
        from amelia.sandbox.worktree import WorktreeManager

        provider = DaytonaSandboxProvider(
            api_key="test-key",
            api_url="https://test.daytona.io/api",
            target="us",
            repo_url="https://github.com/org/repo.git",
        )
        await provider.ensure_running()

        wt = WorktreeManager(
            provider=provider,
            repo_url="https://github.com/org/repo.git",
        )

        # Track commands executed via session streaming
        executed_commands: list[str] = []

        mock_daytona.process.execute_session_command.return_value = MagicMock(
            cmd_id="test-cmd-id",
        )
        mock_daytona.process.get_session_command.return_value = MagicMock(
            exit_code=0,
        )

        async def tracking_logs_async(session_id, cmd_id, on_stdout, on_stderr):
            exec_call = mock_daytona.process.execute_session_command.call_args
            cmd_str = exec_call[0][1].command if exec_call else ""
            executed_commands.append(cmd_str)

            # rev-parse succeeds and returns ".git" (non-bare existing repo)
            if "rev-parse --git-dir" in cmd_str:
                await on_stdout(".git\n")

        mock_daytona.process.get_session_command_logs_async.side_effect = (
            tracking_logs_async
        )

        await wt.setup_repo()

        # Should have called rev-parse (shell) and fetch (SDK), but NOT clone --bare
        assert any("rev-parse --git-dir" in c for c in executed_commands)
        assert not any("clone --bare" in c for c in executed_commands)
        # Fetch dispatches to SDK git.pull since DaytonaSandboxProvider has git_fetch
        mock_daytona.git.pull.assert_awaited_once_with("/workspace/repo")
        assert wt._repo_initialized is True

    @pytest.mark.asyncio
    async def test_factory_creates_daytona_stack(self, mock_daytona):
        """get_driver with daytona mode should produce working ContainerDriver."""
        import os

        from amelia.drivers.factory import get_driver

        sandbox = SandboxConfig(
            mode=SandboxMode.DAYTONA,
            repo_url="https://github.com/org/repo.git",
        )
        with patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key", "OPENROUTER_API_KEY": "test-openrouter-key"}):
            driver = get_driver(
                "api", model="test-model",
                sandbox_config=sandbox, profile_name="work",
            )

        assert driver is not None
        assert hasattr(driver, "execute_agentic")
