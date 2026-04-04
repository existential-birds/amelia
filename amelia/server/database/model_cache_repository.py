"""Repository for cached OpenRouter model metadata."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg

from amelia.server.database.connection import Database
from amelia.server.models.model_cache import (
    ModelCacheCapabilities,
    ModelCacheEntry,
    ModelCacheModalities,
)


class ModelCacheRepository:
    """CRUD access for the model_cache table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_model(self, model_id: str) -> ModelCacheEntry | None:
        """Return a cached model entry by id."""
        row = await self._db.fetch_one(
            "SELECT * FROM model_cache WHERE id = $1",
            model_id,
        )
        return self._row_to_entry(row) if row else None

    async def upsert_model(self, entry: ModelCacheEntry) -> None:
        """Insert or update cached model metadata."""
        await self._db.execute(
            """
            INSERT INTO model_cache (
                id, name, provider, context_length, max_output_tokens,
                input_cost_per_m, output_cost_per_m, capabilities, modalities,
                raw_response, fetched_at, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9,
                $10, $11, $12, NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                provider = EXCLUDED.provider,
                context_length = EXCLUDED.context_length,
                max_output_tokens = EXCLUDED.max_output_tokens,
                input_cost_per_m = EXCLUDED.input_cost_per_m,
                output_cost_per_m = EXCLUDED.output_cost_per_m,
                capabilities = EXCLUDED.capabilities,
                modalities = EXCLUDED.modalities,
                raw_response = EXCLUDED.raw_response,
                fetched_at = EXCLUDED.fetched_at,
                updated_at = NOW()
            """,
            entry.id,
            entry.name,
            entry.provider,
            entry.context_length,
            entry.max_output_tokens,
            entry.input_cost_per_m,
            entry.output_cost_per_m,
            entry.capabilities.model_dump(),
            entry.modalities.model_dump(),
            entry.raw_response,
            entry.fetched_at,
            entry.created_at,
        )

    async def list_models(self) -> list[ModelCacheEntry]:
        """List cached model entries ordered by id."""
        rows = await self._db.fetch_all("SELECT * FROM model_cache ORDER BY id")
        return [self._row_to_entry(row) for row in rows]

    async def is_stale(self, model_id: str, max_age_hours: int = 24) -> bool:
        """Return whether a cached row is missing or older than the max age."""
        row = await self._db.fetch_one(
            "SELECT fetched_at FROM model_cache WHERE id = $1",
            model_id,
        )
        if row is None:
            return True

        fetched_at = row["fetched_at"]
        if not isinstance(fetched_at, datetime):
            return True

        return fetched_at < datetime.now(UTC) - timedelta(hours=max_age_hours)

    def _row_to_entry(self, row: asyncpg.Record) -> ModelCacheEntry:
        """Convert a database row into a typed cache entry."""
        return ModelCacheEntry(
            id=row["id"],
            name=row["name"],
            provider=row["provider"],
            context_length=row["context_length"],
            max_output_tokens=row["max_output_tokens"],
            input_cost_per_m=row["input_cost_per_m"],
            output_cost_per_m=row["output_cost_per_m"],
            capabilities=ModelCacheCapabilities(**(row["capabilities"] or {})),
            modalities=ModelCacheModalities(**(row["modalities"] or {})),
            raw_response=row["raw_response"],
            fetched_at=row["fetched_at"],
            created_at=row["created_at"],
        )
