"""Bootstrap server configuration.

Only settings needed before database is available.
All other settings are stored in the database.
"""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    """Minimal bootstrap configuration.

    Only settings needed before the database is available.
    All other server settings live in the server_settings database table.
    """

    model_config = SettingsConfigDict(
        env_prefix="AMELIA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

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
    database_path: Path = Field(
        default_factory=lambda: Path.home() / ".amelia" / "amelia.db",
        description="Path to SQLite database file",
    )
