"""Repository for server settings management."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from amelia.server.database.connection import Database


class ServerSettings(BaseModel):
    """Server settings data class."""

    log_retention_days: int
    log_retention_max_events: int
    checkpoint_retention_days: int
    checkpoint_path: str
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
            """INSERT OR IGNORE INTO server_settings (id) VALUES (1)"""
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
            "log_retention_max_events",
            "checkpoint_retention_days",
            "checkpoint_path",
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
        set_clauses = [f"{k} = ?" for k in updates]
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values = list(updates.values())

        await self._db.execute(
            f"UPDATE server_settings SET {', '.join(set_clauses)} WHERE id = 1",
            values,
        )
        return await self.get_server_settings()

    def _row_to_settings(self, row: Any) -> ServerSettings:
        """Convert database row to ServerSettings.

        Args:
            row: Database row from server_settings table.

        Returns:
            ServerSettings instance.
        """
        return ServerSettings(
            log_retention_days=row["log_retention_days"],
            log_retention_max_events=row["log_retention_max_events"],
            checkpoint_retention_days=row["checkpoint_retention_days"],
            checkpoint_path=row["checkpoint_path"],
            websocket_idle_timeout_seconds=row["websocket_idle_timeout_seconds"],
            workflow_start_timeout_seconds=row["workflow_start_timeout_seconds"],
            max_concurrent=row["max_concurrent"],
            stream_tool_results=bool(row["stream_tool_results"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
