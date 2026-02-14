"""Test OpenRouter embedding client."""

from collections.abc import AsyncGenerator
from unittest.mock import patch

import httpx
import pytest

from amelia.knowledge.embeddings import EmbeddingClient, EmbeddingError


@pytest.fixture
async def embedding_client() -> AsyncGenerator[EmbeddingClient, None]:
    """Provide embedding client with test API key."""
    client = EmbeddingClient(api_key="test-key", model="openai/text-embedding-3-small")
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_embed_single_text(embedding_client: EmbeddingClient) -> None:
    """Should embed single text and return 1536-dim vector."""
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = httpx.Response(
            200,
            json={
                "data": [{"embedding": [0.1] * 1536}],
                "model": "openai/text-embedding-3-small",
            },
        )

        embedding = await embedding_client.embed("Test text")

        assert len(embedding) == 1536
        assert isinstance(embedding[0], float)
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_embed_batch(embedding_client: EmbeddingClient) -> None:
    """Should embed multiple texts in parallel batches."""
    texts = [f"Text {i}" for i in range(250)]  # Requires 3 batches (100, 100, 50)

    def make_response(*args: object, **kwargs: object) -> httpx.Response:
        """Return embeddings matching the input count."""
        json_data = kwargs.get("json", {})
        input_texts = json_data.get("input", []) if isinstance(json_data, dict) else []
        return httpx.Response(
            200,
            json={
                "data": [{"embedding": [0.1] * 1536} for _ in range(len(input_texts))],
                "model": "openai/text-embedding-3-small",
            },
        )

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.side_effect = make_response

        embeddings = await embedding_client.embed_batch(texts)

        assert len(embeddings) == 250
        assert len(embeddings[0]) == 1536
        # Should make 3 API calls (100 + 100 + 50 texts)
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_embed_error_handling(embedding_client: EmbeddingClient) -> None:
    """Should raise EmbeddingError on API failure."""
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = httpx.Response(
            429,
            json={"error": "Rate limit exceeded"},
        )

        with pytest.raises(EmbeddingError, match="Rate limit"):
            await embedding_client.embed("Test text")


@pytest.mark.asyncio
async def test_embed_error_handling_non_json_response(
    embedding_client: EmbeddingClient,
) -> None:
    """Should handle non-JSON error responses gracefully."""
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = httpx.Response(
            502,
            text="<html>Bad Gateway</html>",
        )

        with pytest.raises(EmbeddingError, match=r"API returned 502.*Bad Gateway"):
            await embedding_client.embed("Test text")


@pytest.mark.asyncio
async def test_embed_retry_on_failure(embedding_client: EmbeddingClient) -> None:
    """Should retry failed batches with exponential backoff."""
    with (
        patch("httpx.AsyncClient.post") as mock_post,
        patch("asyncio.sleep") as mock_sleep,
    ):
        # First call fails, second succeeds
        mock_post.side_effect = [
            httpx.Response(500, json={"error": "Server error"}),
            httpx.Response(
                200,
                json={
                    "data": [{"embedding": [0.1] * 1536}],
                    "model": "openai/text-embedding-3-small",
                },
            ),
        ]

        embedding = await embedding_client.embed("Test text")

        assert len(embedding) == 1536
        assert mock_post.call_count == 2  # Retry after first failure
        # Verify exponential backoff: 2^0 = 1 second for first retry
        mock_sleep.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_async_context_manager() -> None:
    """Should support async context manager protocol."""
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = httpx.Response(
            200,
            json={
                "data": [{"embedding": [0.1] * 1536}],
                "model": "openai/text-embedding-3-small",
            },
        )

        async with EmbeddingClient(
            api_key="test-key", model="openai/text-embedding-3-small"
        ) as client:
            embedding = await client.embed("Test text")
            assert len(embedding) == 1536

        # Client should be closed after exiting context
        assert client.client.is_closed
