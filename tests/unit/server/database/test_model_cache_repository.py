"""Tests for ModelCacheRepository."""

from datetime import UTC, datetime, timedelta

import pytest

from amelia.server.database.connection import Database
from amelia.server.database.model_cache_repository import ModelCacheRepository
from amelia.server.models.model_cache import (
    ModelCacheCapabilities,
    ModelCacheEntry,
    ModelCacheModalities,
)


pytestmark = pytest.mark.integration


def make_entry(
    model_id: str = "anthropic/claude-sonnet-4",
    *,
    fetched_at: datetime | None = None,
    input_cost_per_m: float | None = 3.0,
    output_cost_per_m: float | None = 15.0,
) -> ModelCacheEntry:
    """Create a model cache entry with sensible defaults."""
    now = fetched_at or datetime.now(UTC)
    return ModelCacheEntry(
        id=model_id,
        name="Claude Sonnet 4",
        provider="anthropic",
        context_length=200_000,
        max_output_tokens=16_000,
        input_cost_per_m=input_cost_per_m,
        output_cost_per_m=output_cost_per_m,
        capabilities=ModelCacheCapabilities(
            tool_call=True,
            reasoning=True,
            structured_output=True,
        ),
        modalities=ModelCacheModalities(input=["text", "image"], output=["text"]),
        raw_response={"id": model_id, "name": "Claude Sonnet 4"},
        fetched_at=now,
        created_at=now,
    )


class TestModelCacheRepository:
    """Tests for model cache persistence behavior."""

    @pytest.fixture
    def repo(self, db_with_schema: Database) -> ModelCacheRepository:
        """Create a repository backed by the test database."""
        return ModelCacheRepository(db_with_schema)

    async def test_round_trip_entry(self, repo: ModelCacheRepository) -> None:
        """Cached model rows round-trip into typed entries."""
        entry = make_entry()

        await repo.upsert_model(entry)

        cached = await repo.get_model(entry.id)

        assert cached is not None
        assert cached.id == entry.id
        assert cached.name == entry.name
        assert cached.provider == entry.provider
        assert cached.context_length == 200_000
        assert cached.max_output_tokens == 16_000
        assert cached.input_cost_per_m == 3.0
        assert cached.output_cost_per_m == 15.0
        assert cached.capabilities.tool_call is True
        assert cached.capabilities.reasoning is True
        assert cached.capabilities.structured_output is True
        assert cached.modalities.input == ["text", "image"]
        assert cached.modalities.output == ["text"]
        assert cached.raw_response == {"id": entry.id, "name": "Claude Sonnet 4"}

    async def test_is_stale_false_for_fresh_and_true_for_missing_or_old(
        self,
        repo: ModelCacheRepository,
    ) -> None:
        """Fresh rows are not stale; missing and expired rows are stale."""
        fresh_entry = make_entry(
            model_id="openai/gpt-4o",
            fetched_at=datetime.now(UTC) - timedelta(hours=2),
        )
        stale_entry = make_entry(
            model_id="meta-llama/llama-4-scout",
            fetched_at=datetime.now(UTC) - timedelta(hours=30),
        )

        await repo.upsert_model(fresh_entry)
        await repo.upsert_model(stale_entry)

        assert await repo.is_stale(fresh_entry.id, max_age_hours=24) is False
        assert await repo.is_stale(stale_entry.id, max_age_hours=24) is True
        assert await repo.is_stale("missing/model", max_age_hours=24) is True

    async def test_upsert_replaces_existing_row_without_duplicates(
        self,
        repo: ModelCacheRepository,
    ) -> None:
        """Upsert updates the existing model row instead of inserting a duplicate."""
        original = make_entry()
        updated = make_entry(
            input_cost_per_m=4.5,
            output_cost_per_m=18.0,
        ).model_copy(update={
            "name": "Claude Sonnet 4.1",
            "context_length": 256_000,
            "capabilities": ModelCacheCapabilities(
                tool_call=True,
                reasoning=False,
                structured_output=True,
            ),
        })

        await repo.upsert_model(original)
        await repo.upsert_model(updated)

        models = await repo.list_models()
        assert len(models) == 1

        cached = models[0]
        assert cached.name == "Claude Sonnet 4.1"
        assert cached.context_length == 256_000
        assert cached.input_cost_per_m == 4.5
        assert cached.output_cost_per_m == 18.0
        assert cached.capabilities.reasoning is False
