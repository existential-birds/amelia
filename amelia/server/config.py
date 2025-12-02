"""Server configuration with environment variable support."""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    """Server configuration with environment variable support.

    All settings can be overridden via environment variables with AMELIA_ prefix.
    Example: AMELIA_PORT=9000 overrides the port setting.
    """

    model_config = SettingsConfigDict(
        env_prefix="AMELIA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server binding
    host: str = Field(
        default="127.0.0.1",
        description="Host to bind the server to",
    )
    port: int = Field(
        default=8420,
        ge=1,
        le=65535,
        description="Port to bind the server to",
    )

    # Concurrency
    max_concurrent_workflows: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Maximum concurrent workflows",
    )

    # Log retention
    log_retention_days: int = Field(
        default=30,
        ge=1,
        description="Days to retain event logs",
    )
    log_retention_max_events: int = Field(
        default=100_000,
        ge=1000,
        description="Maximum events per workflow",
    )

    # Timeouts
    request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="HTTP request timeout",
    )
    websocket_idle_timeout_seconds: float = Field(
        default=300.0,
        gt=0,
        description="WebSocket idle timeout (5 min default)",
    )
    workflow_start_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        description="Max time to start a workflow",
    )

    # Rate limiting
    rate_limit_requests_per_minute: int = Field(
        default=60,
        ge=1,
        description="Rate limit: requests per minute",
    )
    rate_limit_burst_size: int = Field(
        default=10,
        ge=1,
        description="Rate limit: burst size",
    )

    # Database
    database_path: Path = Field(
        default_factory=lambda: Path.home() / ".amelia" / "amelia.db",
        description="Path to SQLite database file",
    )
