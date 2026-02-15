"""Test knowledge_search agent tool."""

from unittest.mock import AsyncMock

import pytest

from amelia.tools.knowledge import create_knowledge_tool


async def test_knowledge_tool_calls_search():
    """Tool should delegate to knowledge_search."""
    mock_embedding_client = AsyncMock()
    mock_embedding_client.embed = AsyncMock(return_value=[0.1] * 1536)
    mock_repository = AsyncMock()
    mock_repository.search_chunks = AsyncMock(return_value=[])

    tool = create_knowledge_tool(
        embedding_client=mock_embedding_client,
        repository=mock_repository,
    )

    results = await tool(query="test query", top_k=3)

    assert results == []
    mock_embedding_client.embed.assert_called_once()
    mock_repository.search_chunks.assert_called_once()


async def test_knowledge_tool_has_name():
    """Tool should have a descriptive name."""
    tool = create_knowledge_tool(
        embedding_client=AsyncMock(),
        repository=AsyncMock(),
    )

    assert "knowledge" in tool.__name__.lower()
