"""Tests for dev command."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from amelia.main import app
from amelia.server.banner import CREAM, GOLD, MOSS, RUST
from amelia.server.dev import (
    _get_log_level_style,
    check_node_installed,
    check_node_modules_exist,
    check_pnpm_installed,
    check_port_available,
    is_amelia_dev_repo,
)


def _close_coroutine(coro):
    """Close coroutine to prevent RuntimeWarning."""
    coro.close()
    return 0


class TestModeDetection:
    """Tests for dev/user mode detection."""

    @pytest.mark.parametrize("create_amelia,create_dashboard,create_git,expected", [
        (True, True, True, True),
        (False, True, True, False),
        (True, False, True, False),
        (True, True, False, False),
    ], ids=["all_present", "missing_amelia", "missing_dashboard", "missing_git"])
    def test_is_amelia_dev_repo(self, tmp_path: Path, create_amelia, create_dashboard, create_git, expected):
        """Test repo detection with various directory configurations."""
        if create_amelia:
            (tmp_path / "amelia").mkdir()
        if create_dashboard:
            (tmp_path / "dashboard").mkdir()
            (tmp_path / "dashboard" / "package.json").write_text("{}")
        if create_git:
            (tmp_path / ".git").mkdir()

        with patch("amelia.server.dev.Path.cwd", return_value=tmp_path):
            assert is_amelia_dev_repo() is expected


class TestDependencyChecks:
    """Tests for pnpm/node dependency checks."""

    @pytest.mark.parametrize("check_func,which_return,expected", [
        (check_pnpm_installed, "/usr/bin/pnpm", True),
        (check_pnpm_installed, None, False),
        (check_node_installed, "/usr/bin/node", True),
        (check_node_installed, None, False),
    ], ids=["pnpm_installed", "pnpm_missing", "node_installed", "node_missing"])
    def test_binary_checks(self, check_func, which_return, expected):
        """Test binary presence detection."""
        with patch("amelia.server.dev.shutil.which", return_value=which_return):
            assert check_func() is expected

    @pytest.mark.parametrize("create_node_modules,expected", [
        (True, True),
        (False, False),
    ], ids=["exists", "missing"])
    def test_check_node_modules_exist(self, tmp_path: Path, create_node_modules, expected):
        """Test node_modules detection."""
        (tmp_path / "dashboard").mkdir(parents=True)
        if create_node_modules:
            (tmp_path / "dashboard" / "node_modules").mkdir()

        with patch("amelia.server.dev.Path.cwd", return_value=tmp_path):
            assert check_node_modules_exist() is expected


class TestPortCheck:
    """Tests for port availability checking."""

    def test_check_port_available_free_port(self):
        """Returns True for available ports."""
        import socket

        # Find a guaranteed-free port by binding to 0, then closing
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            _, port = sock.getsockname()

        # The port should now be available (small race window, but reliable)
        assert check_port_available("127.0.0.1", port) is True

    def test_check_port_available_bound_port(self):
        """Returns False when port is already bound."""
        import socket

        # Bind a socket to a port, then check availability
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))  # Bind to random available port
            _, port = sock.getsockname()
            assert check_port_available("127.0.0.1", port) is False


class TestDevCLI:
    """Tests for 'amelia dev' command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_dev_fails_without_node_in_dev_mode(self, runner: CliRunner):
        """Dev command fails with clear error when node is not installed."""
        with (
            patch("amelia.server.dev.run_first_time_setup", return_value=True),
            patch("amelia.server.dev.is_amelia_dev_repo", return_value=True),
            patch("amelia.server.dev.check_node_installed", return_value=False),
        ):
            result = runner.invoke(app, ["dev"])
            assert result.exit_code == 1
            assert "Node.js" in result.stdout

    def test_dev_fails_without_pnpm_in_dev_mode(self, runner: CliRunner):
        """Dev command fails with clear error when pnpm is not installed."""
        with (
            patch("amelia.server.dev.run_first_time_setup", return_value=True),
            patch("amelia.server.dev.is_amelia_dev_repo", return_value=True),
            patch("amelia.server.dev.check_node_installed", return_value=True),
            patch("amelia.server.dev.check_pnpm_installed", return_value=False),
        ):
            result = runner.invoke(app, ["dev"])
            assert result.exit_code == 1
            assert "pnpm" in result.stdout

    def test_dev_user_mode_skips_node_check(self, runner: CliRunner):
        """In user mode, node/pnpm checks are skipped."""
        with (
            patch("amelia.server.dev.run_first_time_setup", return_value=True),
            patch("amelia.server.dev.is_amelia_dev_repo", return_value=False),
            patch("amelia.server.dev.check_node_installed", return_value=False),
            patch("amelia.server.dev.check_pnpm_installed", return_value=False),
            patch("amelia.server.dev.check_port_available", return_value=True),
            patch("amelia.server.dev.asyncio.run", side_effect=_close_coroutine) as mock_run,
        ):
            runner.invoke(app, ["dev"])
            # Should not fail due to missing node/pnpm
            mock_run.assert_called_once()

    def test_dev_no_dashboard_skips_node_check(self, runner: CliRunner):
        """--no-dashboard skips node/pnpm checks even in dev mode."""
        with (
            patch("amelia.server.dev.run_first_time_setup", return_value=True),
            patch("amelia.server.dev.is_amelia_dev_repo", return_value=True),
            patch("amelia.server.dev.check_node_installed", return_value=False),
            patch("amelia.server.dev.check_pnpm_installed", return_value=False),
            patch("amelia.server.dev.check_port_available", return_value=True),
            patch("amelia.server.dev.asyncio.run", side_effect=_close_coroutine) as mock_run,
        ):
            runner.invoke(app, ["dev", "--no-dashboard"])
            # Should not fail due to missing node/pnpm
            mock_run.assert_called_once()

    def test_dev_fails_when_port_in_use(self, runner: CliRunner):
        """Dev command fails with clear error when port is in use."""
        with (
            patch("amelia.server.dev.run_first_time_setup", return_value=True),
            patch("amelia.server.dev.is_amelia_dev_repo", return_value=False),
            patch("amelia.server.dev.check_port_available", return_value=False),
        ):
            result = runner.invoke(app, ["dev", "--port", "8420"])
            assert result.exit_code == 1
            assert "8420" in result.stdout
            assert "already in use" in result.stdout
            assert "--port" in result.stdout


class TestAutoInstall:
    """Tests for auto-install behavior."""

    @pytest.mark.parametrize("return_code,expected", [
        (0, True),
        (1, False),
    ], ids=["success", "failure"])
    async def test_run_pnpm_install(self, return_code, expected) -> None:
        """Test pnpm install handles exit codes correctly."""
        from amelia.server.dev import run_pnpm_install

        mock_process = AsyncMock()
        mock_process.returncode = return_code
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=[b"", None])
        mock_process.wait = AsyncMock(return_value=return_code)

        with patch("amelia.server.dev.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_pnpm_install()
            assert result is expected


class TestProcessManager:
    """Tests for ProcessManager class."""

    @pytest.fixture
    def mock_process(self):
        """Create a mock asyncio subprocess."""
        process = AsyncMock()
        process.returncode = None
        process.stdout = AsyncMock()
        process.stderr = AsyncMock()
        process.wait = AsyncMock(return_value=0)
        process.terminate = MagicMock()
        process.kill = MagicMock()
        return process

    async def test_process_manager_shutdown_terminates_processes(self, mock_process: AsyncMock) -> None:
        """Shutdown terminates running processes."""
        from amelia.server.dev import ProcessManager

        manager = ProcessManager()
        manager.server_process = mock_process
        manager.dashboard_process = mock_process

        await manager.shutdown()

        # terminate should be called for both
        assert mock_process.terminate.call_count == 2


class TestGetLogLevelStyle:
    """Tests for _get_log_level_style() log level parsing."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("INFO:     Starting server", MOSS),
            ("INFO: message", MOSS),
            ("info:     lowercase", MOSS),
            ("DEBUG:    Some debug info", CREAM),
            ("debug: lowercase", CREAM),
            ("WARNING:  Something concerning", GOLD),
            ("warning: lowercase", GOLD),
            ("WARN:     Short form", GOLD),
            ("warn: lowercase short", GOLD),
            ("ERROR:    Something failed", RUST),
            ("error: lowercase", RUST),
            ("CRITICAL: System down", RUST),
            ("critical: lowercase", RUST),
            ("Random text without level", CREAM),
            ("", CREAM),
            ("   Leading whitespace", CREAM),
        ],
        ids=[
            "INFO-uppercase",
            "INFO-short",
            "info-lowercase",
            "DEBUG-uppercase",
            "debug-lowercase",
            "WARNING-uppercase",
            "warning-lowercase",
            "WARN-uppercase",
            "warn-lowercase",
            "ERROR-uppercase",
            "error-lowercase",
            "CRITICAL-uppercase",
            "critical-lowercase",
            "no-level",
            "empty-string",
            "leading-whitespace",
        ],
    )
    def test_log_level_detection(self, text: str, expected: str) -> None:
        """Correctly identifies log level and returns appropriate color."""
        assert _get_log_level_style(text) == expected
