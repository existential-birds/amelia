from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from amelia.knowledge.embeddings import EmbeddingClient
from amelia.knowledge.ingestion import IngestionPipeline
from amelia.knowledge.repository import KnowledgeRepository
from amelia.server.database.connection import Database


@pytest.fixture
async def knowledge_repo(test_db: Database) -> KnowledgeRepository:
    return KnowledgeRepository(test_db)


@pytest.fixture
def mock_embedding_client() -> AsyncMock:
    mock = AsyncMock(spec=EmbeddingClient)
    mock.embed_batch.side_effect = lambda texts, **kw: [[0.1] * 1536] * len(texts)
    return mock


@pytest.fixture
def pipeline_factory(
    knowledge_repo: KnowledgeRepository,
    mock_embedding_client: AsyncMock,
) -> Callable[..., IngestionPipeline]:
    def _create(
        tag_derivation_model: str | None = "minimax/minimax-m2.5",
        tag_derivation_driver: str = "api",
    ) -> IngestionPipeline:
        return IngestionPipeline(
            repository=knowledge_repo,
            embedding_client=mock_embedding_client,
            tag_derivation_model=tag_derivation_model,
            tag_derivation_driver=tag_derivation_driver,
        )
    return _create
