"""Tests for server configuration."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import amelia.server.dependencies as deps_module
from amelia.server.config import ServerConfig
from amelia.server.dependencies import get_config


class TestServerConfig:
    """Tests for ServerConfig (bootstrap-only fields).

    Note: Most settings have moved to the database (server_settings table).
    See tests/unit/server/test_settings_repository.py for those tests.
    """

    def test_default_values(self) -> None:
        """ServerConfig has sensible defaults for bootstrap fields."""
        config = ServerConfig()

        assert config.host == "127.0.0.1"
        assert config.port == 8420
        assert config.database_path == Path.home() / ".amelia" / "amelia.db"

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


class TestBootstrapServerConfig:
    """Tests for bootstrap-only ServerConfig."""

    def test_only_bootstrap_fields(self):
        """Verify ServerConfig only has bootstrap fields."""
        config = ServerConfig()
        # These should exist
        assert hasattr(config, "host")
        assert hasattr(config, "port")
        assert hasattr(config, "database_path")

        # These should NOT exist (moved to database)
        assert not hasattr(config, "log_retention_days")
        assert not hasattr(config, "max_concurrent")
        assert not hasattr(config, "stream_tool_results")

    def test_defaults(self):
        """Verify default values."""
        config = ServerConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8420
        assert config.database_path == Path.home() / ".amelia" / "amelia.db"


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
