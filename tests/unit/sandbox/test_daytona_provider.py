"""Unit tests for DaytonaSandboxProvider."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import DaytonaResources, RetryConfig


def _mock_sandbox_with_install() -> AsyncMock:
    """Create a mock sandbox that passes the post-clone pip install check."""
    mock = AsyncMock()
    mock.process.exec.return_value = MagicMock(exit_code=0, result="")
    return mock


class TestDaytonaSandboxProviderInit:
    """Provider initialization."""

    def test_creates_client_with_config(self) -> None:
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
    async def test_creates_sandbox_and_clones_repo(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
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
                branch="main",
            )

    @pytest.mark.asyncio
    async def test_clones_specified_branch(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
                branch="develop",
            )
            await provider.ensure_running()

            mock_sandbox.git.clone.assert_called_once_with(
                "https://github.com/org/repo.git",
                "/workspace/repo",
                branch="develop",
            )

    @pytest.mark.asyncio
    async def test_noop_if_already_healthy(self) -> None:
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
    async def test_uses_custom_image(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
                image="ubuntu:22.04",
            )
            await provider.ensure_running()

            params = mock_client.create.call_args[0][0]
            # Non-debian-slim image should be passed as Image(name)
            assert params.image is not None

    @pytest.mark.asyncio
    async def test_uses_debian_slim_image_with_version(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
                image="debian-slim:3.11",
            )
            await provider.ensure_running()

            params = mock_client.create.call_args[0][0]
            assert params.image is not None

    @pytest.mark.asyncio
    async def test_ensure_running_times_out(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()

            async def hang(*args: object, **kwargs: object) -> None:
                await asyncio.sleep(999)

            mock_client.create.side_effect = hang
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
                timeout=0.1,
            )

            with pytest.raises(TimeoutError, match="timed out after 0.1s"):
                await provider.ensure_running()

    @pytest.mark.asyncio
    async def test_passes_resources_when_configured(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
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

            params = mock_client.create.call_args[0][0]
            assert params.resources.cpu == 4
            assert params.resources.memory == 8
            assert params.resources.disk == 20


    @pytest.mark.asyncio
    async def test_retries_on_transient_failure(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.side_effect = [
                ConnectionError("connection reset"),
                mock_sandbox,
            ]
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
                retry_config=RetryConfig(max_retries=2, base_delay=0.1, max_delay=1.0),
            )
            await provider.ensure_running()

            assert mock_client.create.call_count == 2
            mock_sandbox.git.clone.assert_called_once()


class TestDaytonaSandboxProviderWorkerInstall:
    """Post-clone amelia package installation."""

    @pytest.mark.asyncio
    async def test_installs_amelia_after_clone(self) -> None:
        """ensure_running should pip install amelia from repo after clone."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.process.exec.return_value = MagicMock(
                exit_code=0, result="",
            )
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            assert mock_sandbox.process.exec.call_count == 3
            # First call: check for pyproject.toml / setup.py
            mock_sandbox.process.exec.assert_any_call(
                "test -f /workspace/repo/pyproject.toml || test -f /workspace/repo/setup.py"
            )
            # Second call: pip install
            mock_sandbox.process.exec.assert_any_call(
                "pip install --no-cache-dir --no-deps /workspace/repo"
            )
            # Third call: mkdir for worker upload
            mock_sandbox.process.exec.assert_any_call("mkdir -p /opt/amelia")

    @pytest.mark.asyncio
    async def test_skips_install_when_no_repo_url(self) -> None:
        """No repo = no clone = no pip install."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="",
            )
            await provider.ensure_running()

            mock_sandbox.git.clone.assert_not_called()
            # Only call should be mkdir for worker upload (no pip install)
            mock_sandbox.process.exec.assert_called_once_with("mkdir -p /opt/amelia")

    @pytest.mark.asyncio
    async def test_raises_on_install_failure(self) -> None:
        """Failed pip install should raise RuntimeError and clean up."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.process.exec.side_effect = [
                MagicMock(exit_code=0, result=""),  # test -f check passes
                MagicMock(exit_code=1, result="pip error"),  # pip install fails
            ]
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            with pytest.raises(RuntimeError, match="Failed to install package from cloned repo"):
                await provider.ensure_running()
            assert provider._sandbox is None


class TestDaytonaSandboxProviderWorkflowBranch:
    """Workflow branch creation after clone."""

    @pytest.mark.asyncio
    async def test_creates_workflow_branch_after_clone(self) -> None:
        """workflow_branch should create a git branch after clone + install."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            # All process.exec calls succeed: test -f check, pip install, git checkout
            mock_sandbox.process.exec.return_value = MagicMock(exit_code=0, result="")
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
                workflow_branch="amelia/wf-123",
            )
            await provider.ensure_running()

            mock_sandbox.process.exec.assert_any_call(
                "git -C /workspace/repo checkout -b amelia/wf-123"
            )

    @pytest.mark.asyncio
    async def test_no_branch_when_workflow_branch_is_none(self) -> None:
        """No git checkout -b when workflow_branch is None."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = AsyncMock()
            mock_sandbox.process.exec.return_value = MagicMock(exit_code=0, result="")
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            # process.exec should only be called for test -f check and pip install
            for call in mock_sandbox.process.exec.call_args_list:
                assert "checkout -b" not in str(call)


class TestDaytonaSandboxProviderImageBuilder:
    """Image construction with worker deps."""

    @pytest.mark.asyncio
    async def test_image_includes_worker_deps(self) -> None:
        """Image should include pip install for worker dependencies."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import _WORKER_DEPS, DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            params = mock_client.create.call_args[0][0]
            dockerfile = params.image._dockerfile
            # Should contain pip install with all worker deps
            for dep in _WORKER_DEPS:
                assert dep in dockerfile, f"Missing worker dep: {dep}"

    @pytest.mark.asyncio
    async def test_image_includes_git(self) -> None:
        """Image should install git."""
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            params = mock_client.create.call_args[0][0]
            dockerfile = params.image._dockerfile
            assert "apt-get" in dockerfile
            assert "git" in dockerfile


class TestDaytonaSandboxProviderGitAuth:
    """Git credential threading."""

    @pytest.mark.asyncio
    async def test_clone_passes_credentials_when_token_set(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
                git_token="ghp_test123",
            )
            await provider.ensure_running()

            mock_sandbox.git.clone.assert_called_once_with(
                "https://github.com/org/repo.git",
                "/workspace/repo",
                branch="main",
                username="x-access-token",
                password="ghp_test123",
            )

    @pytest.mark.asyncio
    async def test_clone_no_credentials_when_token_absent(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            mock_sandbox.git.clone.assert_called_once_with(
                "https://github.com/org/repo.git",
                "/workspace/repo",
                branch="main",
            )

    @pytest.mark.asyncio
    async def test_git_push_passes_credentials(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
                git_token="ghp_test123",
            )
            await provider.ensure_running()
            await provider.git_push("/workspace/repo")

            mock_sandbox.git.push.assert_called_once_with(
                "/workspace/repo",
                username="x-access-token",
                password="ghp_test123",
            )

    @pytest.mark.asyncio
    async def test_git_push_raises_when_not_running(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_cls.return_value = AsyncMock()
            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
                git_token="ghp_test123",
            )
            with pytest.raises(RuntimeError, match="Sandbox not running"):
                await provider.git_push("/workspace/repo")

    @pytest.mark.asyncio
    async def test_git_fetch_passes_credentials(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
                git_token="ghp_test123",
            )
            await provider.ensure_running()
            await provider.git_fetch("/workspace/repo")

            mock_sandbox.git.pull.assert_called_once_with(
                "/workspace/repo",
                username="x-access-token",
                password="ghp_test123",
            )

    @pytest.mark.asyncio
    async def test_git_fetch_raises_when_not_running(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_cls.return_value = AsyncMock()
            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
                git_token="ghp_test123",
            )
            with pytest.raises(RuntimeError, match="Sandbox not running"):
                await provider.git_fetch("/workspace/repo")


def _make_mock_sandbox(stdout_chunks: list[str], exit_code: int = 0) -> AsyncMock:
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


class TestDaytonaSandboxProviderWriteFile:
    """File upload via Daytona FS API."""

    @pytest.mark.asyncio
    async def test_write_file_uploads_content(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()

            # Reset after ensure_running (which uploads worker.py).
            mock_sandbox.fs.upload_file.reset_mock()

            await provider.write_file("/tmp/prompt.txt", b"hello world")

            mock_sandbox.fs.upload_file.assert_called_once_with(
                b"hello world", "/tmp/prompt.txt",
            )

    @pytest.mark.asyncio
    async def test_write_file_raises_when_not_running(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_cls.return_value = AsyncMock()
            provider = DaytonaSandboxProvider(
                api_key="test-key",
                repo_url="https://github.com/org/repo.git",
            )
            with pytest.raises(RuntimeError, match="Sandbox not running"):
                await provider.write_file("/tmp/file.txt", b"content")


class TestDaytonaSandboxProviderExecStream:
    """Command execution via session-based streaming."""

    @pytest.mark.asyncio
    async def test_exec_stream_yields_stdout_lines(self) -> None:
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
    async def test_exec_stream_raises_on_nonzero_exit(self) -> None:
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
    async def test_exec_stream_buffers_partial_lines(self) -> None:
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
    async def test_exec_stream_yields_trailing_partial_line(self) -> None:
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
    async def test_exec_stream_cleans_up_session_on_error(self) -> None:
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
            mock_sandbox.process.delete_session.reset_mock()

            with pytest.raises(RuntimeError):
                async for _ in provider.exec_stream(["false"]):
                    pass

            mock_sandbox.process.delete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_exec_stream_cleans_up_session_on_success(self) -> None:
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
            mock_sandbox.process.delete_session.reset_mock()

            async for _ in provider.exec_stream(["echo", "ok"]):
                pass

            mock_sandbox.process.delete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_exec_stream_cleans_up_on_early_break(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _make_mock_sandbox(["line1\nline2\nline3\n"])
            mock_client.create.return_value = mock_sandbox
            mock_cls.return_value = mock_client

            provider = DaytonaSandboxProvider(
                api_key="test-key",
                api_url="https://test.daytona.io/api",
                target="us",
                repo_url="https://github.com/org/repo.git",
            )
            await provider.ensure_running()
            mock_sandbox.process.delete_session.reset_mock()

            stream = provider.exec_stream(["echo", "hello"])
            async for _ in stream:
                break  # Break after first line
            await stream.aclose()

            mock_sandbox.process.delete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_exec_stream_bakes_cwd_and_env_into_command(self) -> None:
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
    async def test_teardown_deletes_sandbox(self) -> None:
        with patch("amelia.sandbox.daytona.AsyncDaytona") as mock_cls:
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            mock_client = AsyncMock()
            mock_sandbox = _mock_sandbox_with_install()
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
    async def test_teardown_noop_when_no_sandbox(self) -> None:
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


class TestWorkerEnv:
    """Tests for the worker_env property."""

    def test_worker_env_returns_empty_when_no_env_set(self) -> None:
        """Provider with no LLM env returns empty dict."""
        with patch("amelia.sandbox.daytona.AsyncDaytona"):
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            provider = DaytonaSandboxProvider(api_key="test-key")
            assert provider.worker_env == {}

    def test_worker_env_returns_configured_env(self) -> None:
        """Provider with LLM env returns the configured variables."""
        with patch("amelia.sandbox.daytona.AsyncDaytona"):
            from amelia.sandbox.daytona import DaytonaSandboxProvider

            provider = DaytonaSandboxProvider(api_key="test-key")
            provider._worker_env = {"LLM_PROXY_URL": "https://example.com", "OPENAI_API_KEY": "sk-test"}
            assert provider.worker_env == {
                "LLM_PROXY_URL": "https://example.com",
                "OPENAI_API_KEY": "sk-test",
            }


class TestDaytonaSandboxProviderHealthCheck:
    """Health check."""

    @pytest.mark.asyncio
    async def test_healthy_sandbox(self) -> None:
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
    async def test_no_sandbox_returns_false(self) -> None:
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
