"""Integration test for Daytona sandbox stack.

Tests DaytonaSandboxProvider + ContainerDriver + WorktreeManager
working together, mocking at the Daytona SDK boundary.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import SandboxConfig
from amelia.drivers.base import AgenticMessage, AgenticMessageType


class TestDaytonaFullStack:
    """DaytonaSandboxProvider + ContainerDriver end-to-end."""

    @pytest.fixture
    def mock_daytona(self):
        """Mock Daytona SDK returning realistic process.exec responses."""
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

        # exec_stream is called multiple times:
        # 1. ensure_running -> health_check (process.exec "true")
        # 2. _write_prompt -> exec_stream(["tee", ...], stdin=...)
        # 3. worker command -> exec_stream(["python", "-m", ...])
        # 4. _cleanup_prompt -> exec_stream(["rm", "-f", ...])
        #
        # We configure process.exec to return the worker JSON only when the
        # command contains the worker module name; otherwise return empty.
        def exec_side_effect(cmd, **kwargs):
            if "amelia.sandbox.worker" in cmd:
                return MagicMock(
                    result=result_msg.model_dump_json(),
                    exit_code=0,
                )
            return MagicMock(result="", exit_code=0)

        mock_daytona.process.exec.side_effect = exec_side_effect

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

        # WorktreeManager uses exec_stream for git worktree commands
        wt = WorktreeManager(
            provider=provider,
            repo_url="https://github.com/org/repo.git",
        )

        mock_daytona.process.exec.return_value = MagicMock(
            result="", exit_code=0,
        )

        # create_worktree calls setup_repo (git clone --bare) then
        # git worktree add, both via exec_stream
        worktree_path = await wt.create_worktree("wf-123", base_branch="main")
        assert worktree_path == "/workspace/worktrees/wf-123"

    @pytest.mark.asyncio
    async def test_factory_creates_daytona_stack(self, mock_daytona):
        """get_driver with daytona mode should produce working ContainerDriver."""
        import os

        from amelia.drivers.factory import get_driver

        sandbox = SandboxConfig(
            mode="daytona",
            repo_url="https://github.com/org/repo.git",
        )
        with patch.dict(os.environ, {"DAYTONA_API_KEY": "test-key"}):
            driver = get_driver(
                "api", model="test-model",
                sandbox_config=sandbox, profile_name="work",
            )

        assert driver is not None
        assert hasattr(driver, "execute_agentic")
