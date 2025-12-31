"""Tests for server CLI commands."""
import os
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from amelia.main import app


class TestServerCLI:
    """Tests for 'amelia server' command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_server_command_exists(self, runner):
        """'amelia server' command is registered."""
        result = runner.invoke(app, ["server", "--help"])
        assert result.exit_code == 0
        assert "Amelia API server commands" in result.stdout

    def test_server_default_port(self, runner):
        """Server uses default port 8420."""
        with patch("uvicorn.run") as mock_run:
            # Exit immediately to avoid blocking
            mock_run.side_effect = KeyboardInterrupt()
            runner.invoke(app, ["server"])

            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["port"] == 8420

    def test_server_custom_port(self, runner):
        """Server respects --port flag."""
        with patch("uvicorn.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            runner.invoke(app, ["server", "--port", "9000"])

            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["port"] == 9000

    def test_server_bind_all_flag(self, runner):
        """--bind-all binds to 0.0.0.0."""
        with patch("uvicorn.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            runner.invoke(app, ["server", "--bind-all"])

            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["host"] == "0.0.0.0"

    def test_server_bind_all_shows_warning(self, runner):
        """--bind-all shows security warning."""
        with patch("uvicorn.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            result = runner.invoke(app, ["server", "--bind-all"])

            assert "Warning" in result.stdout or "warning" in result.stdout.lower()

    def test_server_default_localhost(self, runner):
        """Server defaults to localhost binding."""
        with patch("uvicorn.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            runner.invoke(app, ["server"])

            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["host"] == "127.0.0.1"

    def test_server_respects_env_port(self, runner):
        """Server respects AMELIA_PORT environment variable."""
        with patch.dict(os.environ, {"AMELIA_PORT": "9999"}), patch("uvicorn.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            runner.invoke(app, ["server"])

            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["port"] == 9999

    def test_cli_port_overrides_env(self, runner):
        """CLI --port flag overrides AMELIA_PORT env var."""
        with patch.dict(os.environ, {"AMELIA_PORT": "9999"}), patch("uvicorn.run") as mock_run:
            mock_run.side_effect = KeyboardInterrupt()
            runner.invoke(app, ["server", "--port", "8000"])

            call_kwargs = mock_run.call_args.kwargs
            assert call_kwargs["port"] == 8000
