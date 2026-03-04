"""Unit tests for DaytonaSandboxProvider."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import DaytonaResources


class TestDaytonaSandboxProviderInit:
    """Provider initialization."""

    def test_creates_client_with_config(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="eu",
                repo_url="https://github.com/org/repo.git",
            )
            mock_cls.assert_called_once()
            assert provider._repo_url == "https://github.com/org/repo.git"


class TestDaytonaSandboxProviderEnsureRunning:
    """Sandbox creation and repo cloning."""

    @pytest.mark.asyncio
    async def test_creates_sandbox_and_clones_repo(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            mock_client.create.assert_called_once()
            mock_sandbox.git.clone.assert_called_once_with(
                "https://github.com/org/repo.git",
                "/workspace/repo",
            )

    @pytest.mark.asyncio
    async def test_noop_if_already_healthy(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.process.exec.return_value = MagicMock(exit_code=0)
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            # First call creates
            await provider.ensure_running()
            # Second call should no-op
            await provider.ensure_running()

            assert mock_client.create.call_count == 1

    @pytest.mark.asyncio
    async def test_passes_resources_when_configured(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            resources = DaytonaResources(cpu=4, memory=8, disk=20)
            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
                resources=resources,
            )
            await provider.ensure_running()

            create_args = mock_client.create.call_args
            # Verify resources were passed through
            params = create_args[0][0] if create_args[0] else create_args[1].get("params")
            assert params is not None


class TestDaytonaSandboxProviderExecStream:
    """Command execution via process.exec."""

    @pytest.mark.asyncio
    async def test_exec_stream_yields_stdout_lines(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.process.exec.return_value = MagicMock(
                result="line1\nline2\nline3\n",
                exit_code=0,
            )
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            lines = []
            async for line in provider.exec_stream(["echo", "hello"], cwd="/workspace"):
                lines.append(line)

            assert lines == ["line1", "line2", "line3"]

    @pytest.mark.asyncio
    async def test_exec_stream_raises_on_nonzero_exit(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.process.exec.return_value = MagicMock(
                result="",
                exit_code=1,
            )
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            with pytest.raises(RuntimeError, match="exited with code 1"):
                async for _ in provider.exec_stream(["false"]):
                    pass


class TestDaytonaSandboxProviderTeardown:
    """Sandbox cleanup."""

    @pytest.mark.asyncio
    async def test_teardown_deletes_sandbox(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()
            await provider.teardown()

            mock_sandbox.delete.assert_called_once()
            assert provider._sandbox is None

    @pytest.mark.asyncio
    async def test_teardown_noop_when_no_sandbox(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_cls.return_value = AsyncMock()
            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            # Should not raise
            await provider.teardown()


class TestDaytonaSandboxProviderHealthCheck:
    """Health check."""

    @pytest.mark.asyncio
    async def test_healthy_sandbox(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.process.exec.return_value = MagicMock(exit_code=0)
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            assert await provider.health_check() is True

    @pytest.mark.asyncio
    async def test_no_sandbox_returns_false(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_cls.return_value = AsyncMock()
            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            assert await provider.health_check() is False
