"""Repository for server settings management."""
from datetime import datetime
from typing import Any

import asyncpg
from pydantic import BaseModel

from amelia.server.database.connection import Database


class ServerSettings(BaseModel):
    """Server settings data class."""

    log_retention_days: int
    checkpoint_retention_days: int
    websocket_idle_timeout_seconds: float
    workflow_start_timeout_seconds: float
    max_concurrent: int
    stream_tool_results: bool
    created_at: datetime
    updated_at: datetime


class SettingsRepository:
    """Repository for server settings CRUD operations."""

    def __init__(self, db: Database) -> None:
        """Initialize repository with database connection.

        Args:
            db: Database connection instance.
        """
        self._db = db

    async def ensure_defaults(self) -> None:
        """Create server_settings singleton row if it doesn't exist.

        Idempotent - safe to call multiple times.
        """
        await self._db.execute(
            """INSERT INTO server_settings (id) VALUES (1) ON CONFLICT DO NOTHING"""
        )

    async def get_server_settings(self) -> ServerSettings:
        """Get current server settings.

        Returns:
            ServerSettings with current values.

        Raises:
            ValueError: If settings not initialized (call ensure_defaults first).
        """
        row = await self._db.fetch_one(
            "SELECT * FROM server_settings WHERE id = 1"
        )
        if row is None:
            raise ValueError("Server settings not initialized. Call ensure_defaults() first.")
        return self._row_to_settings(row)

    async def update_server_settings(self, updates: dict[str, Any]) -> ServerSettings:
        """Update server settings.

        Args:
            updates: Dictionary of field names to new values.

        Returns:
            Updated ServerSettings.

        Raises:
            ValueError: If invalid field names provided.
        """
        valid_fields = {
            "log_retention_days",
            "checkpoint_retention_days",
            "websocket_idle_timeout_seconds",
            "workflow_start_timeout_seconds",
            "max_concurrent",
            "stream_tool_results",
        }
        invalid = set(updates.keys()) - valid_fields
        if invalid:
            raise ValueError(f"Invalid settings fields: {invalid}")

        if not updates:
            return await self.get_server_settings()

        # Build UPDATE statement
        set_clauses = []
        values = []
        for i, (k, v) in enumerate(updates.items(), start=1):
            set_clauses.append(f"{k} = ${i}")
            values.append(v)
        set_clauses.append("updated_at = NOW()")

        await self._db.execute(
            f"UPDATE server_settings SET {', '.join(set_clauses)} WHERE id = 1",
            *values,
        )
        return await self.get_server_settings()

    def _row_to_settings(self, row: asyncpg.Record) -> ServerSettings:
        """Convert database row to ServerSettings.

        Args:
            row: Database row from server_settings table.

        Returns:
            ServerSettings instance.
        """
        return ServerSettings(
            log_retention_days=row["log_retention_days"],
            checkpoint_retention_days=row["checkpoint_retention_days"],
            websocket_idle_timeout_seconds=row["websocket_idle_timeout_seconds"],
            workflow_start_timeout_seconds=row["workflow_start_timeout_seconds"],
            max_concurrent=row["max_concurrent"],
            stream_tool_results=row["stream_tool_results"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
