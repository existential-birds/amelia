"""Tests for server configuration."""
import os
from unittest.mock import patch


class TestServerConfig:
    """Tests for ServerConfig."""

    def test_default_values(self):
        """ServerConfig has sensible defaults."""
        from amelia.server.config import ServerConfig

        config = ServerConfig()

        assert config.host == "127.0.0.1"
        assert config.port == 8420
        assert config.log_retention_days == 30
        assert config.log_retention_max_events == 100_000
        assert config.max_concurrent_workflows == 5
        assert config.request_timeout_seconds == 30.0
        assert config.websocket_idle_timeout_seconds == 300.0

    def test_env_override_port(self):
        """Port can be overridden via environment variable."""
        from amelia.server.config import ServerConfig

        with patch.dict(os.environ, {"AMELIA_PORT": "9000"}):
            config = ServerConfig()
            assert config.port == 9000

    def test_env_override_host(self):
        """Host can be overridden via environment variable."""
        from amelia.server.config import ServerConfig

        with patch.dict(os.environ, {"AMELIA_HOST": "0.0.0.0"}):
            config = ServerConfig()
            assert config.host == "0.0.0.0"

    def test_env_override_max_concurrent(self):
        """Max concurrent workflows can be overridden."""
        from amelia.server.config import ServerConfig

        with patch.dict(os.environ, {"AMELIA_MAX_CONCURRENT_WORKFLOWS": "10"}):
            config = ServerConfig()
            assert config.max_concurrent_workflows == 10

    def test_env_override_retention_days(self):
        """Log retention days can be overridden."""
        from amelia.server.config import ServerConfig

        with patch.dict(os.environ, {"AMELIA_LOG_RETENTION_DAYS": "90"}):
            config = ServerConfig()
            assert config.log_retention_days == 90

    def test_database_path_default(self):
        """Database path defaults to ~/.amelia/amelia.db."""
        from pathlib import Path

        from amelia.server.config import ServerConfig

        config = ServerConfig()
        expected = Path.home() / ".amelia" / "amelia.db"
        assert config.database_path == expected

    def test_database_path_override(self):
        """Database path can be overridden."""
        from pathlib import Path

        from amelia.server.config import ServerConfig

        with patch.dict(os.environ, {"AMELIA_DATABASE_PATH": "/tmp/test.db"}):
            config = ServerConfig()
            assert config.database_path == Path("/tmp/test.db")
