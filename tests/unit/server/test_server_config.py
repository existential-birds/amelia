"""Tests for server configuration."""

import os
from unittest.mock import patch

import pytest

import amelia.server.dependencies as deps_module
from amelia.server.config import ServerConfig
from amelia.server.dependencies import get_config


@pytest.fixture(autouse=True)
def _clean_amelia_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all AMELIA_-prefixed env vars to isolate tests from the shell."""
    for key in list(os.environ):
        if key.startswith("AMELIA_"):
            monkeypatch.delenv(key)


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
        assert config.database_url == "postgresql://amelia:amelia@localhost:5434/amelia"
        assert config.db_pool_min_size == 2
        assert config.db_pool_max_size == 10

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

    def test_database_url_default(self) -> None:
        """Database URL defaults to local PostgreSQL."""
        config = ServerConfig()
        assert "postgresql://" in config.database_url

    def test_database_url_override(self) -> None:
        """Database URL can be overridden."""
        with patch.dict(
            os.environ, {"AMELIA_DATABASE_URL": "postgresql://user:pass@db:5432/mydb"}
        ):
            config = ServerConfig()
            assert config.database_url == "postgresql://user:pass@db:5432/mydb"

    def test_pool_settings(self) -> None:
        """Pool size settings have valid defaults."""
        config = ServerConfig()
        assert config.db_pool_min_size >= 1
        assert config.db_pool_max_size >= config.db_pool_min_size


class TestBootstrapServerConfig:
    """Tests for bootstrap-only ServerConfig."""

    def test_only_bootstrap_fields(self):
        """Verify ServerConfig only has bootstrap fields."""
        config = ServerConfig()
        # These should exist
        assert hasattr(config, "host")
        assert hasattr(config, "port")
        assert hasattr(config, "database_url")
        assert hasattr(config, "db_pool_min_size")
        assert hasattr(config, "db_pool_max_size")

        # These should NOT exist (moved to database)
        assert not hasattr(config, "log_retention_days")
        assert not hasattr(config, "max_concurrent")
        assert not hasattr(config, "database_path")

    def test_defaults(self):
        """Verify default values."""
        config = ServerConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8420
        assert "postgresql://" in config.database_url


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
