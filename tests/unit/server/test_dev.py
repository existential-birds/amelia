"""Tests for dev command."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from amelia.main import app
from amelia.server.dev import (
    Colors,
    check_node_installed,
    check_node_modules_exist,
    check_pnpm_installed,
    check_port_available,
    is_amelia_dev_repo,
)


class TestModeDetection:
    """Tests for dev/user mode detection."""

    def test_is_amelia_dev_repo_all_present(self, tmp_path: Path):
        """Returns True when all three markers are present."""
        (tmp_path / "amelia").mkdir()
        (tmp_path / "dashboard").mkdir()
        (tmp_path / "dashboard" / "package.json").write_text("{}")
        (tmp_path / ".git").mkdir()

        with patch("amelia.server.dev.Path.cwd", return_value=tmp_path):
            assert is_amelia_dev_repo() is True

    def test_is_amelia_dev_repo_missing_amelia_dir(self, tmp_path: Path):
        """Returns False when amelia/ directory is missing."""
        (tmp_path / "dashboard").mkdir()
        (tmp_path / "dashboard" / "package.json").write_text("{}")
        (tmp_path / ".git").mkdir()

        with patch("amelia.server.dev.Path.cwd", return_value=tmp_path):
            assert is_amelia_dev_repo() is False

    def test_is_amelia_dev_repo_missing_dashboard(self, tmp_path: Path):
        """Returns False when dashboard/package.json is missing."""
        (tmp_path / "amelia").mkdir()
        (tmp_path / ".git").mkdir()

        with patch("amelia.server.dev.Path.cwd", return_value=tmp_path):
            assert is_amelia_dev_repo() is False

    def test_is_amelia_dev_repo_missing_git(self, tmp_path: Path):
        """Returns False when .git/ directory is missing."""
        (tmp_path / "amelia").mkdir()
        (tmp_path / "dashboard").mkdir()
        (tmp_path / "dashboard" / "package.json").write_text("{}")

        with patch("amelia.server.dev.Path.cwd", return_value=tmp_path):
            assert is_amelia_dev_repo() is False


class TestDependencyChecks:
    """Tests for pnpm/node dependency checks."""

    def test_check_pnpm_installed_true(self):
        """Returns True when pnpm is in PATH."""
        with patch("amelia.server.dev.shutil.which", return_value="/usr/bin/pnpm"):
            assert check_pnpm_installed() is True

    def test_check_pnpm_installed_false(self):
        """Returns False when pnpm is not in PATH."""
        with patch("amelia.server.dev.shutil.which", return_value=None):
            assert check_pnpm_installed() is False

    def test_check_node_installed_true(self):
        """Returns True when node is in PATH."""
        with patch("amelia.server.dev.shutil.which", return_value="/usr/bin/node"):
            assert check_node_installed() is True

    def test_check_node_installed_false(self):
        """Returns False when node is not in PATH."""
        with patch("amelia.server.dev.shutil.which", return_value=None):
            assert check_node_installed() is False

    def test_check_node_modules_exist_true(self, tmp_path: Path):
        """Returns True when node_modules exists."""
        (tmp_path / "dashboard" / "node_modules").mkdir(parents=True)

        with patch("amelia.server.dev.Path.cwd", return_value=tmp_path):
            assert check_node_modules_exist() is True

    def test_check_node_modules_exist_false(self, tmp_path: Path):
        """Returns False when node_modules does not exist."""
        (tmp_path / "dashboard").mkdir(parents=True)

        with patch("amelia.server.dev.Path.cwd", return_value=tmp_path):
            assert check_node_modules_exist() is False


class TestPortCheck:
    """Tests for port availability checking."""

    def test_check_port_available_free_port(self):
        """Returns True for available ports."""
        # Use a high port unlikely to be in use
        assert check_port_available("127.0.0.1", 59123) is True

    def test_check_port_available_bound_port(self):
        """Returns False when port is already bound."""
        import socket

        # Bind a socket to a port, then check availability
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))  # Bind to random available port
        _, port = sock.getsockname()

        try:
            assert check_port_available("127.0.0.1", port) is False
        finally:
            sock.close()


class TestColors:
    """Tests for color palette."""

    def test_colors_are_hex_values(self):
        """All colors are valid hex color codes."""
        for color in Colors:
            assert color.value.startswith("#")
            assert len(color.value) == 7  # #RRGGBB

    def test_required_colors_exist(self):
        """All required brand colors are defined."""
        assert Colors.NAVY.value == "#0a2463"
        assert Colors.GOLD.value == "#ffc857"
        assert Colors.CREAM.value == "#eff8e2"
        assert Colors.MOSS.value == "#88976b"
        assert Colors.RUST.value == "#a0311c"
        assert Colors.GRAY.value == "#6d726a"


class TestDevCLI:
    """Tests for 'amelia dev' command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_dev_command_exists(self, runner: CliRunner):
        """'amelia dev' command is registered."""
        result = runner.invoke(app, ["dev", "--help"])
        assert result.exit_code == 0
        assert "Start development server with dashboard" in result.stdout

    def test_dev_shows_port_option(self, runner: CliRunner):
        """--port option is available."""
        result = runner.invoke(app, ["dev", "--help"])
        assert "--port" in result.stdout or "-p" in result.stdout

    def test_dev_shows_no_dashboard_option(self, runner: CliRunner):
        """--no-dashboard option is available."""
        result = runner.invoke(app, ["dev", "--help"])
        assert "--no-dashboard" in result.stdout

    def test_dev_shows_bind_all_option(self, runner: CliRunner):
        """--bind-all option is available."""
        result = runner.invoke(app, ["dev", "--help"])
        assert "--bind-all" in result.stdout

    def test_dev_fails_without_node_in_dev_mode(self, runner: CliRunner):
        """Dev command fails with clear error when node is not installed."""
        with (
            patch("amelia.server.dev.is_amelia_dev_repo", return_value=True),
            patch("amelia.server.dev.check_node_installed", return_value=False),
        ):
            result = runner.invoke(app, ["dev"])
            assert result.exit_code == 1
            assert "Node.js" in result.stdout

    def test_dev_fails_without_pnpm_in_dev_mode(self, runner: CliRunner):
        """Dev command fails with clear error when pnpm is not installed."""
        with (
            patch("amelia.server.dev.is_amelia_dev_repo", return_value=True),
            patch("amelia.server.dev.check_node_installed", return_value=True),
            patch("amelia.server.dev.check_pnpm_installed", return_value=False),
        ):
            result = runner.invoke(app, ["dev"])
            assert result.exit_code == 1
            assert "pnpm" in result.stdout

    def test_dev_user_mode_skips_node_check(self, runner: CliRunner):
        """In user mode, node/pnpm checks are skipped."""

        def close_coroutine(coro):
            """Close coroutine to prevent RuntimeWarning."""
            coro.close()
            return 0

        with (
            patch("amelia.server.dev.is_amelia_dev_repo", return_value=False),
            patch("amelia.server.dev.check_node_installed", return_value=False),
            patch("amelia.server.dev.check_pnpm_installed", return_value=False),
            patch("amelia.server.dev.check_port_available", return_value=True),
            patch("amelia.server.dev.asyncio.run", side_effect=close_coroutine) as mock_run,
        ):
            runner.invoke(app, ["dev"])
            # Should not fail due to missing node/pnpm
            mock_run.assert_called_once()

    def test_dev_no_dashboard_skips_node_check(self, runner: CliRunner):
        """--no-dashboard skips node/pnpm checks even in dev mode."""

        def close_coroutine(coro):
            """Close coroutine to prevent RuntimeWarning."""
            coro.close()
            return 0

        with (
            patch("amelia.server.dev.is_amelia_dev_repo", return_value=True),
            patch("amelia.server.dev.check_node_installed", return_value=False),
            patch("amelia.server.dev.check_pnpm_installed", return_value=False),
            patch("amelia.server.dev.check_port_available", return_value=True),
            patch("amelia.server.dev.asyncio.run", side_effect=close_coroutine) as mock_run,
        ):
            runner.invoke(app, ["dev", "--no-dashboard"])
            # Should not fail due to missing node/pnpm
            mock_run.assert_called_once()

    def test_dev_fails_when_port_in_use(self, runner: CliRunner):
        """Dev command fails with clear error when port is in use."""
        with (
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

    async def test_run_pnpm_install_failure_returns_false(self):
        """run_pnpm_install returns False on non-zero exit code."""
        from amelia.server.dev import run_pnpm_install

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=[b"", None])
        mock_process.wait = AsyncMock(return_value=1)

        with patch("amelia.server.dev.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_pnpm_install()
            assert result is False

    async def test_run_pnpm_install_success_returns_true(self):
        """run_pnpm_install returns True on zero exit code."""
        from amelia.server.dev import run_pnpm_install

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=[b"", None])
        mock_process.wait = AsyncMock(return_value=0)

        with patch("amelia.server.dev.asyncio.create_subprocess_exec", return_value=mock_process):
            result = await run_pnpm_install()
            assert result is True


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

    async def test_process_manager_shutdown_terminates_processes(self, mock_process: AsyncMock):
        """Shutdown terminates running processes."""
        from amelia.server.dev import ProcessManager

        manager = ProcessManager()
        manager.server_process = mock_process
        manager.dashboard_process = mock_process

        await manager.shutdown()

        # terminate should be called for both
        assert mock_process.terminate.call_count == 2
