"""Tests for server configuration."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import amelia.server.main as main_module
from amelia.server.config import ServerConfig
from amelia.server.main import get_config


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


class TestGetConfig:
    """Tests for get_config dependency."""

    def test_get_config_raises_when_not_initialized(self) -> None:
        """get_config raises RuntimeError before server starts."""
        # Ensure _config is None (it should be by default, but be explicit)
        original = main_module._config
        main_module._config = None
        try:
            with pytest.raises(RuntimeError, match="Server config not initialized"):
                get_config()
        finally:
            main_module._config = original
