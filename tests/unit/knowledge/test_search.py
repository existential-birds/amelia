"""Test knowledge search function."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from amelia.knowledge.models import SearchResult
from amelia.knowledge.search import knowledge_search


@pytest.fixture
def mock_embedding_client():
    """Mock embedding client."""
    client = AsyncMock()
    client.embed = AsyncMock(return_value=[0.1] * 1536)
    return client


@pytest.fixture
def mock_repository():
    """Mock repository."""
    repo = AsyncMock()
    repo.search_chunks = AsyncMock(return_value=[])
    return repo


async def test_knowledge_search_embeds_query(mock_embedding_client, mock_repository):
    """Should embed query text and pass to repository."""
    await knowledge_search(
        query="How do React hooks work?",
        embedding_client=mock_embedding_client,
        repository=mock_repository,
    )

    mock_embedding_client.embed.assert_called_once_with("How do React hooks work?")
    mock_repository.search_chunks.assert_called_once()


async def test_knowledge_search_passes_tags(mock_embedding_client, mock_repository):
    """Should forward tags to repository search."""
    await knowledge_search(
        query="useState example",
        tags=["react", "hooks"],
        embedding_client=mock_embedding_client,
        repository=mock_repository,
    )

    call_kwargs = mock_repository.search_chunks.call_args[1]
    assert call_kwargs["tags"] == ["react", "hooks"]


async def test_knowledge_search_passes_top_k(mock_embedding_client, mock_repository):
    """Should forward top_k to repository search."""
    await knowledge_search(
        query="test",
        top_k=10,
        embedding_client=mock_embedding_client,
        repository=mock_repository,
    )

    call_kwargs = mock_repository.search_chunks.call_args[1]
    assert call_kwargs["top_k"] == 10


async def test_knowledge_search_returns_results(mock_embedding_client, mock_repository):
    """Should return search results from repository."""
    expected = [
        SearchResult(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_name="React Docs",
            tags=["react"],
            content="Hook content",
            heading_path=["Hooks"],
            similarity=0.92,
            token_count=50,
        )
    ]
    mock_repository.search_chunks = AsyncMock(return_value=expected)

    results = await knowledge_search(
        query="hooks",
        embedding_client=mock_embedding_client,
        repository=mock_repository,
    )

    assert results == expected
