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

    def test_satisfies_protocol(self) -> None:
        provider = DockerSandboxProvider(profile_name="test")
        assert isinstance(provider, SandboxProvider)

    def test_container_name(self) -> None:
        provider = DockerSandboxProvider(profile_name="work")
        assert provider.container_name == "amelia-sandbox-work"

    def test_default_image(self) -> None:
        provider = DockerSandboxProvider(profile_name="test")
        assert provider.image == "amelia-sandbox:latest"

    def test_custom_image(self) -> None:
        provider = DockerSandboxProvider(profile_name="test", image="custom:v1")
        assert provider.image == "custom:v1"


class TestHealthCheck:
    """Tests for health_check() — inspects container state."""

    @pytest.fixture
    def provider(self) -> DockerSandboxProvider:
        return DockerSandboxProvider(profile_name="test")

    async def test_healthy_container(self, provider: DockerSandboxProvider) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"true\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await provider.health_check()

        assert result is True
        args = mock_exec.call_args[0]
        assert "docker" in args
        assert "inspect" in args

    async def test_unhealthy_container(self, provider: DockerSandboxProvider) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"false\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await provider.health_check()

        assert result is False

    async def test_missing_container(self, provider: DockerSandboxProvider) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"No such object")
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await provider.health_check()

        assert result is False


class TestExecStream:
    """Tests for exec_stream() — runs commands via docker exec."""

    @pytest.fixture
    def provider(self) -> DockerSandboxProvider:
        return DockerSandboxProvider(profile_name="test")

    async def test_streams_stdout_lines(self, provider: DockerSandboxProvider) -> None:
        lines = [b"line1\n", b"line2\n", b"line3\n"]

        mock_proc = AsyncMock()
        mock_proc.stdout.__aiter__ = lambda self: _async_iter(lines)
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = [line async for line in provider.exec_stream(["echo", "hello"])]

        assert result == ["line1", "line2", "line3"]

    async def test_passes_cwd(self, provider: DockerSandboxProvider) -> None:
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

    async def test_nonzero_exit_raises(self, provider: DockerSandboxProvider) -> None:
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

    async def test_removes_container(self) -> None:
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

    async def test_noop_when_healthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = DockerSandboxProvider(profile_name="test")
        mock_health_check = AsyncMock(return_value=True)
        mock_build_image = AsyncMock()
        mock_start_container = AsyncMock()
        monkeypatch.setattr(provider, "health_check", mock_health_check)
        monkeypatch.setattr(provider, "_build_image", mock_build_image)
        monkeypatch.setattr(provider, "_start_container", mock_start_container)

        await provider.ensure_running()

        mock_health_check.assert_awaited_once()
        mock_build_image.assert_not_awaited()
        mock_start_container.assert_not_awaited()

    async def test_builds_and_starts_when_not_healthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = DockerSandboxProvider(profile_name="test")
        mock_health_check = AsyncMock(return_value=False)
        mock_image_exists = AsyncMock(return_value=False)
        mock_build_image = AsyncMock()
        mock_start_container = AsyncMock()
        mock_wait_for_ready = AsyncMock()
        monkeypatch.setattr(provider, "health_check", mock_health_check)
        monkeypatch.setattr(provider, "_image_exists", mock_image_exists)
        monkeypatch.setattr(provider, "_build_image", mock_build_image)
        monkeypatch.setattr(provider, "_start_container", mock_start_container)
        monkeypatch.setattr(provider, "_wait_for_ready", mock_wait_for_ready)

        await provider.ensure_running()

        mock_build_image.assert_awaited_once()
        mock_start_container.assert_awaited_once()

    async def test_skips_build_when_image_exists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = DockerSandboxProvider(profile_name="test")
        mock_health_check = AsyncMock(return_value=False)
        mock_image_exists = AsyncMock(return_value=True)
        mock_build_image = AsyncMock()
        mock_start_container = AsyncMock()
        mock_wait_for_ready = AsyncMock()
        monkeypatch.setattr(provider, "health_check", mock_health_check)
        monkeypatch.setattr(provider, "_image_exists", mock_image_exists)
        monkeypatch.setattr(provider, "_build_image", mock_build_image)
        monkeypatch.setattr(provider, "_start_container", mock_start_container)
        monkeypatch.setattr(provider, "_wait_for_ready", mock_wait_for_ready)

        await provider.ensure_running()

        mock_build_image.assert_not_awaited()
        mock_start_container.assert_awaited_once()


class TestNetworkAllowlist:
    """Tests for _apply_network_allowlist() — applies iptables rules in container."""

    async def test_allowlist_applied_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ensure_running() calls _apply_network_allowlist() after _wait_for_ready()."""
        provider = DockerSandboxProvider(
            profile_name="test",
            network_allowlist_enabled=True,
            network_allowed_hosts=["github.com"],
        )
        call_order: list[str] = []

        mock_health_check = AsyncMock(return_value=False)
        mock_image_exists = AsyncMock(return_value=True)
        mock_start_container = AsyncMock()

        async def mock_wait() -> None:
            call_order.append("wait_for_ready")

        async def mock_allowlist() -> None:
            call_order.append("apply_network_allowlist")

        monkeypatch.setattr(provider, "health_check", mock_health_check)
        monkeypatch.setattr(provider, "_image_exists", mock_image_exists)
        monkeypatch.setattr(provider, "_build_image", AsyncMock())
        monkeypatch.setattr(provider, "_start_container", mock_start_container)
        monkeypatch.setattr(provider, "_wait_for_ready", mock_wait)
        monkeypatch.setattr(provider, "_apply_network_allowlist", mock_allowlist)

        await provider.ensure_running()

        assert call_order == ["wait_for_ready", "apply_network_allowlist"]

    async def test_allowlist_skipped_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When network_allowlist_enabled=False, no docker exec is invoked."""
        provider = DockerSandboxProvider(profile_name="test")
        assert provider.network_allowlist_enabled is False

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            await provider._apply_network_allowlist()

        mock_exec.assert_not_called()

    async def test_allowlist_generates_and_pipes_rules(self) -> None:
        """Verify rules are generated and piped to docker exec as stdin."""
        hosts = ["github.com", "pypi.org"]
        provider = DockerSandboxProvider(
            profile_name="test",
            network_allowlist_enabled=True,
            network_allowed_hosts=hosts,
        )

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec,
            patch(
                "amelia.sandbox.docker.generate_allowlist_rules",
                return_value="#!/bin/sh\nfake-rules\n",
            ) as mock_gen,
        ):
            await provider._apply_network_allowlist()

        mock_gen.assert_called_once_with(allowed_hosts=hosts)

        args = mock_exec.call_args[0]
        assert args == (
            "docker", "exec", "-i", "amelia-sandbox-test",
            "sh", "/opt/amelia/scripts/setup-network.sh",
        )
        # Verify rules were piped via stdin
        mock_proc.communicate.assert_awaited_once()
        call_kwargs = mock_proc.communicate.call_args
        assert call_kwargs[1]["input"] == b"#!/bin/sh\nfake-rules\n"

    async def test_allowlist_failure_raises(self) -> None:
        """Non-zero exit from docker exec raises RuntimeError."""
        provider = DockerSandboxProvider(
            profile_name="test",
            network_allowlist_enabled=True,
            network_allowed_hosts=["github.com"],
        )

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"iptables: Permission denied")
        mock_proc.returncode = 1

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch(
                "amelia.sandbox.docker.generate_allowlist_rules",
                return_value="#!/bin/sh\nfake-rules\n",
            ),
            pytest.raises(RuntimeError, match="Failed to apply network allowlist"),
        ):
            await provider._apply_network_allowlist()
