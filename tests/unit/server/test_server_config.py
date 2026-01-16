"""Tests for server configuration."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import amelia.server.dependencies as deps_module
from amelia.server.config import ServerConfig
from amelia.server.dependencies import get_config


class TestServerConfig:
    """Tests for ServerConfig."""

    def test_default_values(self) -> None:
        """ServerConfig has sensible defaults."""
        config = ServerConfig()

        assert config.host == "127.0.0.1"
        assert config.port == 8420
        assert config.log_retention_days == 30
        assert config.log_retention_max_events == 100_000
        assert config.websocket_idle_timeout_seconds == 300.0

    def test_env_override_port(self) -> None:
        """Port can be overridden via environment variable."""
        with patch.dict(os.environ, {"AMELIA_PORT": "9000"}):
            config = ServerConfig()
            assert config.port == 9000

    def test_env_override_host(self) -> None:
        """Host can be overridden via environment variable."""
        with patch.dict(os.environ, {"AMELIA_HOST": "0.0.0.0"}):
            config = ServerConfig()
            assert config.host == "0.0.0.0"

    def test_env_override_retention_days(self) -> None:
        """Log retention days can be overridden."""
        with patch.dict(os.environ, {"AMELIA_LOG_RETENTION_DAYS": "90"}):
            config = ServerConfig()
            assert config.log_retention_days == 90

    def test_database_path_default(self) -> None:
        """Database path defaults to ~/.amelia/amelia.db."""
        config = ServerConfig()
        expected = Path.home() / ".amelia" / "amelia.db"
        assert config.database_path == expected

    def test_database_path_override(self) -> None:
        """Database path can be overridden."""
        with patch.dict(os.environ, {"AMELIA_DATABASE_PATH": "/tmp/test.db"}):
            config = ServerConfig()
            assert config.database_path == Path("/tmp/test.db")

    def test_trace_retention_days_default(self) -> None:
        """trace_retention_days defaults to 7."""
        config = ServerConfig()
        assert config.trace_retention_days == 7

    def test_trace_retention_days_from_env(self) -> None:
        """trace_retention_days can be set via environment."""
        with patch.dict(os.environ, {"AMELIA_TRACE_RETENTION_DAYS": "3"}):
            config = ServerConfig()
            assert config.trace_retention_days == 3

    def test_trace_retention_days_zero_disables_persistence(self) -> None:
        """trace_retention_days=0 is valid (disables persistence)."""
        config = ServerConfig(trace_retention_days=0)
        assert config.trace_retention_days == 0

    def test_working_dir_defaults_to_cwd(self) -> None:
        """working_dir should default to current working directory."""
        # Explicitly clear env var in case it's set by another test
        env = {k: v for k, v in os.environ.items() if k != "AMELIA_WORKING_DIR"}
        with patch.dict(os.environ, env, clear=True):
            config = ServerConfig()
            assert config.working_dir == Path.cwd()

    def test_working_dir_from_env_var(self) -> None:
        """working_dir should be set from AMELIA_WORKING_DIR env var."""
        with patch.dict(os.environ, {"AMELIA_WORKING_DIR": "/tmp/test-repo"}):
            config = ServerConfig()
            assert config.working_dir == Path("/tmp/test-repo")

    def test_working_dir_expands_user(self) -> None:
        """working_dir should expand ~ to home directory."""
        with patch.dict(os.environ, {"AMELIA_WORKING_DIR": "~/projects/repo"}):
            config = ServerConfig()
            assert config.working_dir == Path.home() / "projects" / "repo"


class TestGetConfig:
    """Tests for get_config dependency."""

    def test_get_config_raises_when_not_initialized(self) -> None:
        """get_config raises RuntimeError before server starts."""
        # Ensure _config is None (it should be by default, but be explicit)
        original = deps_module._config
        deps_module._config = None
        try:
            with pytest.raises(RuntimeError, match="Server config not initialized"):
                get_config()
        finally:
            deps_module._config = original
