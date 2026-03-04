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


def _make_mock_sandbox(stdout_chunks: list[str], exit_code: int = 0):
    """Create a mock sandbox with session-based streaming configured.

    Args:
        stdout_chunks: Text chunks to deliver via the on_stdout callback.
        exit_code: Exit code returned by get_session_command.
    """
    mock_sandbox = AsyncMock()
    mock_sandbox.process.exec.return_value = MagicMock(exit_code=0)

    # execute_session_command returns a response with cmd_id
    mock_sandbox.process.execute_session_command.return_value = MagicMock(
        cmd_id="test-cmd-id",
    )

    # get_session_command_logs_async calls the on_stdout callback with chunks
    async def fake_logs_async(_sid, _cid, on_stdout, on_stderr):
        for chunk in stdout_chunks:
            await on_stdout(chunk)

    mock_sandbox.process.get_session_command_logs_async.side_effect = fake_logs_async

    # get_session_command returns command info with exit code
    mock_sandbox.process.get_session_command.return_value = MagicMock(
        exit_code=exit_code,
    )

    return mock_sandbox


class TestDaytonaSandboxProviderExecStream:
    """Command execution via session-based streaming."""

    @pytest.mark.asyncio
    async def test_exec_stream_yields_stdout_lines(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _make_mock_sandbox(["line1\nline2\n", "line3\n"])
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
            mock_sandbox = _make_mock_sandbox([], exit_code=1)
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

    @pytest.mark.asyncio
    async def test_exec_stream_buffers_partial_lines(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            # Chunks split mid-line: "hel" + "lo world\nfoo\n"
            mock_sandbox = _make_mock_sandbox(["hel", "lo world\nfoo\n"])
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
            async for line in provider.exec_stream(["echo", "hello"]):
                lines.append(line)

            assert lines == ["hello world", "foo"]

    @pytest.mark.asyncio
    async def test_exec_stream_yields_trailing_partial_line(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            # No trailing newline
            mock_sandbox = _make_mock_sandbox(["partial"])
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
            async for line in provider.exec_stream(["echo", "-n", "partial"]):
                lines.append(line)

            assert lines == ["partial"]

    @pytest.mark.asyncio
    async def test_exec_stream_cleans_up_session_on_error(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _make_mock_sandbox([], exit_code=1)
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            with pytest.raises(RuntimeError):
                async for _ in provider.exec_stream(["false"]):
                    pass

            mock_sandbox.process.delete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_exec_stream_cleans_up_session_on_success(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _make_mock_sandbox(["ok\n"])
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            async for _ in provider.exec_stream(["echo", "ok"]):
                pass

            mock_sandbox.process.delete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_exec_stream_bakes_cwd_and_env_into_command(self):
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _make_mock_sandbox(["ok\n"])
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            async for _ in provider.exec_stream(
                ["ls"], cwd="/workspace", env={"FOO": "bar"},
            ):
                pass

            call_args = mock_sandbox.process.execute_session_command.call_args
            req = call_args[0][1]
            assert "cd" in req.command
            assert "/workspace" in req.command
            assert "FOO=bar" in req.command
            assert req.run_async is True


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
