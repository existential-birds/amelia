"""Tests for DockerSandboxProvider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest

from amelia.sandbox.docker import DockerSandboxProvider
from amelia.sandbox.provider import SandboxProvider


async def _async_iter[T](items: list[T]) -> AsyncIterator[T]:
    """Convert a list to an async iterator."""
    for item in items:
        yield item


class TestDockerProviderProtocol:
    """DockerSandboxProvider satisfies SandboxProvider protocol."""

    def test_satisfies_protocol(self):
        provider = DockerSandboxProvider(profile_name="test")
        assert isinstance(provider, SandboxProvider)

    def test_container_name(self):
        provider = DockerSandboxProvider(profile_name="work")
        assert provider.container_name == "amelia-sandbox-work"

    def test_default_image(self):
        provider = DockerSandboxProvider(profile_name="test")
        assert provider.image == "amelia-sandbox:latest"

    def test_custom_image(self):
        provider = DockerSandboxProvider(profile_name="test", image="custom:v1")
        assert provider.image == "custom:v1"


class TestHealthCheck:
    """Tests for health_check() — inspects container state."""

    @pytest.fixture
    def provider(self):
        return DockerSandboxProvider(profile_name="test")

    async def test_healthy_container(self, provider):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"true\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await provider.health_check()

        assert result is True
        args = mock_exec.call_args[0]
        assert "docker" in args
        assert "inspect" in args

    async def test_unhealthy_container(self, provider):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"false\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await provider.health_check()

        assert result is False

    async def test_missing_container(self, provider):
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"No such object")
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await provider.health_check()

        assert result is False


class TestExecStream:
    """Tests for exec_stream() — runs commands via docker exec."""

    @pytest.fixture
    def provider(self):
        return DockerSandboxProvider(profile_name="test")

    async def test_streams_stdout_lines(self, provider):
        lines = [b"line1\n", b"line2\n", b"line3\n"]

        mock_proc = AsyncMock()
        mock_proc.stdout.__aiter__ = lambda self: _async_iter(lines)
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = [line async for line in provider.exec_stream(["echo", "hello"])]

        assert result == ["line1", "line2", "line3"]

    async def test_passes_cwd(self, provider):
        mock_proc = AsyncMock()
        mock_proc.stdout.__aiter__ = lambda self: _async_iter([])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            _ = [line async for line in provider.exec_stream(
                ["ls"], cwd="/workspace/worktrees/issue-1"
            )]

        args = mock_exec.call_args[0]
        assert "--workdir" in args
        assert "/workspace/worktrees/issue-1" in args

    async def test_nonzero_exit_raises(self, provider):
        mock_proc = AsyncMock()
        mock_proc.stdout.__aiter__ = lambda self: _async_iter([b"output\n"])
        mock_proc.wait = AsyncMock(return_value=1)
        mock_proc.returncode = 1
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"error details")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc), pytest.raises(RuntimeError, match="exited with code 1"):
            _ = [line async for line in provider.exec_stream(["false"])]


class TestTeardown:
    """Tests for teardown() — removes the container."""

    async def test_removes_container(self):
        provider = DockerSandboxProvider(profile_name="test")
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await provider.teardown()

        args = mock_exec.call_args[0]
        assert "docker" in args
        assert "rm" in args
        assert "-f" in args
        assert "amelia-sandbox-test" in args


class TestEnsureRunning:
    """Tests for ensure_running() — starts container if not healthy."""

    async def test_noop_when_healthy(self):
        provider = DockerSandboxProvider(profile_name="test")
        provider.health_check = AsyncMock(return_value=True)
        provider._build_image = AsyncMock()
        provider._start_container = AsyncMock()

        await provider.ensure_running()

        provider.health_check.assert_awaited_once()
        provider._build_image.assert_not_awaited()
        provider._start_container.assert_not_awaited()

    async def test_builds_and_starts_when_not_healthy(self):
        provider = DockerSandboxProvider(profile_name="test")
        provider.health_check = AsyncMock(return_value=False)
        provider._image_exists = AsyncMock(return_value=False)
        provider._build_image = AsyncMock()
        provider._start_container = AsyncMock()
        provider._wait_for_ready = AsyncMock()

        await provider.ensure_running()

        provider._build_image.assert_awaited_once()
        provider._start_container.assert_awaited_once()

    async def test_skips_build_when_image_exists(self):
        provider = DockerSandboxProvider(profile_name="test")
        provider.health_check = AsyncMock(return_value=False)
        provider._image_exists = AsyncMock(return_value=True)
        provider._build_image = AsyncMock()
        provider._start_container = AsyncMock()
        provider._wait_for_ready = AsyncMock()

        await provider.ensure_running()

        provider._build_image.assert_not_awaited()
        provider._start_container.assert_awaited_once()
