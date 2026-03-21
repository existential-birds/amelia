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


def _mock_start_container() -> tuple[AsyncMock, AsyncMock]:
    """Create mock restart (fail) and mock run (succeed) for _start_container tests."""
    mock_restart = AsyncMock()
    mock_restart.returncode = 1  # No existing container to restart
    mock_restart.wait = AsyncMock()

    mock_run = AsyncMock()
    mock_run.communicate.return_value = (b"container-id", b"")
    mock_run.returncode = 0

    return mock_restart, mock_run


@pytest.fixture
def mocked_provider(monkeypatch: pytest.MonkeyPatch) -> DockerSandboxProvider:
    """DockerSandboxProvider with all async methods monkeypatched for ensure_running tests."""
    provider = DockerSandboxProvider(profile_name="test")
    monkeypatch.setattr(provider, "health_check", AsyncMock(return_value=False))
    monkeypatch.setattr(provider, "_image_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(provider, "_build_image", AsyncMock())
    monkeypatch.setattr(provider, "_start_container", AsyncMock())
    monkeypatch.setattr(provider, "_wait_for_ready", AsyncMock())
    monkeypatch.setattr(provider, "_apply_network_allowlist", AsyncMock())
    return provider


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

    def test_allowlist_enabled_by_default(self) -> None:
        provider = DockerSandboxProvider(profile_name="test")
        assert provider.network_allowlist_enabled is True


class TestHealthCheck:
    """Tests for health_check() — inspects container state."""

    @pytest.fixture
    def provider(self) -> DockerSandboxProvider:
        return DockerSandboxProvider(profile_name="test")

    @pytest.mark.parametrize(
        "stdout,returncode,expected",
        [
            pytest.param(b"true\n", 0, True, id="healthy"),
            pytest.param(b"false\n", 0, False, id="unhealthy"),
            pytest.param(b"", 1, False, id="missing"),
        ],
    )
    async def test_health_check(
        self, provider: DockerSandboxProvider, stdout: bytes, returncode: int, expected: bool,
    ) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (stdout, b"")
        mock_proc.returncode = returncode

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await provider.health_check()

        assert result is expected


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

    async def test_noop_when_healthy(self, mocked_provider: DockerSandboxProvider) -> None:
        mocked_provider.health_check.return_value = True  # type: ignore[attr-defined]
        await mocked_provider.ensure_running()

        mocked_provider.health_check.assert_awaited_once()  # type: ignore[attr-defined]
        mocked_provider._build_image.assert_not_awaited()  # type: ignore[attr-defined]
        mocked_provider._start_container.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_builds_and_starts_when_not_healthy(self, mocked_provider: DockerSandboxProvider) -> None:
        await mocked_provider.ensure_running()

        mocked_provider._build_image.assert_awaited_once()  # type: ignore[attr-defined]
        mocked_provider._start_container.assert_awaited_once()  # type: ignore[attr-defined]

    async def test_skips_build_when_image_exists(self, mocked_provider: DockerSandboxProvider) -> None:
        mocked_provider._image_exists.return_value = True  # type: ignore[attr-defined]
        await mocked_provider.ensure_running()

        mocked_provider._build_image.assert_not_awaited()  # type: ignore[attr-defined]
        mocked_provider._start_container.assert_awaited_once()  # type: ignore[attr-defined]


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

        monkeypatch.setattr(provider, "health_check", AsyncMock(return_value=False))
        monkeypatch.setattr(provider, "_image_exists", AsyncMock(return_value=True))
        monkeypatch.setattr(provider, "_build_image", AsyncMock())
        monkeypatch.setattr(provider, "_start_container", AsyncMock())

        async def mock_wait() -> None:
            call_order.append("wait_for_ready")

        async def mock_allowlist() -> None:
            call_order.append("apply_network_allowlist")

        monkeypatch.setattr(provider, "_wait_for_ready", mock_wait)
        monkeypatch.setattr(provider, "_apply_network_allowlist", mock_allowlist)

        await provider.ensure_running()

        assert call_order == ["wait_for_ready", "apply_network_allowlist"]

    async def test_allowlist_skipped_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When network_allowlist_enabled=False, no docker exec is invoked."""
        provider = DockerSandboxProvider(profile_name="test", network_allowlist_enabled=False)
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
            "docker", "exec", "-i", "--user", "root", "amelia-sandbox-test",
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


class TestProxyTokenGeneration:
    """Docker provider generates a unique proxy token per container."""

    def test_proxy_token_generated_on_init(self) -> None:
        provider = DockerSandboxProvider(profile_name="test")
        assert provider.proxy_token is not None
        assert len(provider.proxy_token) > 20  # secrets.token_urlsafe(32) is 43 chars

    def test_proxy_token_unique_per_instance(self) -> None:
        p1 = DockerSandboxProvider(profile_name="test")
        p2 = DockerSandboxProvider(profile_name="test")
        assert p1.proxy_token != p2.proxy_token

    async def test_token_passed_as_env_var(self) -> None:
        provider = DockerSandboxProvider(
            profile_name="test", network_allowlist_enabled=False,
        )
        mock_restart, mock_run = _mock_start_container()

        with patch("asyncio.create_subprocess_exec", side_effect=[mock_restart, mock_run]) as mock_exec:
            await provider._start_container()

        run_args = mock_exec.call_args_list[1][0]
        # Find the AMELIA_PROXY_TOKEN env var
        env_pairs = list(zip(run_args, run_args[1:], strict=False))
        token_envs = [v for k, v in env_pairs if k == "-e" and v.startswith("AMELIA_PROXY_TOKEN=")]
        assert len(token_envs) == 1
        assert token_envs[0] == f"AMELIA_PROXY_TOKEN={provider.proxy_token}"


class TestContainerCapabilities:
    """NET_ADMIN/NET_RAW should only be added when allowlist is enabled."""

    @pytest.mark.parametrize(
        "allowlist_enabled,cap_present",
        [
            pytest.param(True, True, id="enabled"),
            pytest.param(False, False, id="disabled"),
        ],
    )
    async def test_capabilities_match_allowlist_setting(
        self, allowlist_enabled: bool, cap_present: bool,
    ) -> None:
        provider = DockerSandboxProvider(
            profile_name="test", network_allowlist_enabled=allowlist_enabled,
        )
        mock_restart, mock_run = _mock_start_container()

        with patch("asyncio.create_subprocess_exec", side_effect=[mock_restart, mock_run]) as mock_exec:
            await provider._start_container()

        run_args = mock_exec.call_args_list[1][0]
        assert ("--cap-add" in run_args) is cap_present
        assert ("NET_ADMIN" in run_args) is cap_present
        assert ("NET_RAW" in run_args) is cap_present


class TestProxyTokenSyncOnRestart:
    """Restarted containers must sync the existing AMELIA_PROXY_TOKEN."""

    async def test_restarted_container_reads_existing_token(self) -> None:
        """When a stopped container is restarted, the provider reads the token from it."""
        provider = DockerSandboxProvider(profile_name="test")
        original_token = provider.proxy_token

        # Mock: docker start succeeds (existing container)
        mock_restart = AsyncMock()
        mock_restart.returncode = 0
        mock_restart.wait = AsyncMock()

        # Mock: docker inspect returns env with a different token
        container_token = "container-baked-token-xyz"
        env_output = (
            f"LLM_PROXY_URL=http://host.docker.internal:8430/proxy/v1\n"
            f"AMELIA_PROFILE=test\n"
            f"AMELIA_PROXY_TOKEN={container_token}\n"
        )
        mock_inspect = AsyncMock()
        mock_inspect.communicate.return_value = (env_output.encode(), b"")
        mock_inspect.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=[mock_restart, mock_inspect],
        ):
            await provider._start_container()

        assert provider.proxy_token == container_token
        assert provider.proxy_token != original_token

    async def test_restarted_container_keeps_token_on_inspect_failure(self) -> None:
        """If docker inspect fails, the provider keeps its current token."""
        provider = DockerSandboxProvider(profile_name="test")
        original_token = provider.proxy_token

        mock_restart = AsyncMock()
        mock_restart.returncode = 0
        mock_restart.wait = AsyncMock()

        mock_inspect = AsyncMock()
        mock_inspect.communicate.return_value = (b"", b"inspect error")
        mock_inspect.returncode = 1

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=[mock_restart, mock_inspect],
        ):
            await provider._start_container()

        assert provider.proxy_token == original_token

    async def test_restarted_container_keeps_token_when_env_var_missing(self) -> None:
        """If AMELIA_PROXY_TOKEN isn't in the container env, keep current token."""
        provider = DockerSandboxProvider(profile_name="test")
        original_token = provider.proxy_token

        mock_restart = AsyncMock()
        mock_restart.returncode = 0
        mock_restart.wait = AsyncMock()

        env_output = "SOME_OTHER_VAR=value\n"
        mock_inspect = AsyncMock()
        mock_inspect.communicate.return_value = (env_output.encode(), b"")
        mock_inspect.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=[mock_restart, mock_inspect],
        ):
            await provider._start_container()

        assert provider.proxy_token == original_token
