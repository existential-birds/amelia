"""OpenRouter embedding client for Knowledge Library."""

import asyncio
from collections.abc import Callable

import httpx
from loguru import logger


# Constants
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/embeddings"
EMBEDDING_BATCH_SIZE = 100
EMBEDDING_MAX_PARALLEL = 3
EMBEDDING_MAX_RETRIES = 3
EMBEDDING_TIMEOUT_SECONDS = 30


class EmbeddingError(Exception):
    """Raised when embedding API request fails."""


class EmbeddingClient:
    """OpenRouter API client for text embeddings.

    Args:
        api_key: OpenRouter API key.
        model: Embedding model ID (default: openai/text-embedding-3-small).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "openai/text-embedding-3-small",
    ):
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(EMBEDDING_TIMEOUT_SECONDS)
        )

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()

    async def __aenter__(self) -> "EmbeddingClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Exit async context manager and close client."""
        await self.close()

    async def embed(self, text: str) -> list[float]:
        """Embed single text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector (1536 dims for text-embedding-3-small).

        Raises:
            EmbeddingError: If API request fails after retries.
        """
        embeddings = await self.embed_batch([text])
        return embeddings[0]

    async def embed_batch(
        self,
        texts: list[str],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        """Embed multiple texts in parallel batches.

        Args:
            texts: List of texts to embed.
            progress_callback: Optional callback(processed, total) for progress.

        Returns:
            List of embedding vectors in same order as input.

        Raises:
            EmbeddingError: If any batch fails after retries.
        """
        if not texts:
            return []

        # Split into batches
        batches = [
            texts[i : i + EMBEDDING_BATCH_SIZE]
            for i in range(0, len(texts), EMBEDDING_BATCH_SIZE)
        ]

        logger.debug(
            "Embedding texts",
            total_texts=len(texts),
            batch_count=len(batches),
            batch_size=EMBEDDING_BATCH_SIZE,
        )

        # Process batches in parallel with concurrency limit
        semaphore = asyncio.Semaphore(EMBEDDING_MAX_PARALLEL)
        tasks = [
            self._embed_batch_with_retry(batch, semaphore, progress_callback, len(texts))
            for batch in batches
        ]

        batch_results = await asyncio.gather(*tasks)

        # Flatten results while preserving order
        embeddings = [emb for batch in batch_results for emb in batch]

        return embeddings

    async def _embed_batch_with_retry(
        self,
        texts: list[str],
        semaphore: asyncio.Semaphore,
        progress_callback: Callable[[int, int], None] | None,
        total: int,
    ) -> list[list[float]]:
        """Embed batch with retry logic and progress reporting.

        Args:
            texts: Batch of texts to embed.
            semaphore: Concurrency limiter.
            progress_callback: Optional callback(processed, total).
            total: Total number of texts being embedded.

        Returns:
            Embeddings for this batch.

        Raises:
            EmbeddingError: If batch fails after max retries.
        """
        async with semaphore:
            for attempt in range(EMBEDDING_MAX_RETRIES):
                try:
                    embeddings = await self._call_api(texts)

                    # Report progress
                    if progress_callback:
                        progress_callback(len(texts), total)

                    return embeddings

                except EmbeddingError as e:
                    if attempt == EMBEDDING_MAX_RETRIES - 1:
                        logger.error(
                            "Embedding batch failed after retries",
                            batch_size=len(texts),
                            error=str(e),
                        )
                        raise

                    # Exponential backoff
                    wait = 2**attempt
                    logger.warning(
                        "Embedding batch failed, retrying",
                        attempt=attempt + 1,
                        wait_seconds=wait,
                        error=str(e),
                    )
                    await asyncio.sleep(wait)

        raise EmbeddingError("Unreachable")

    async def _call_api(self, texts: list[str]) -> list[list[float]]:
        """Call OpenRouter embeddings API.

        Args:
            texts: Texts to embed in this request.

        Returns:
            Embeddings from API response.

        Raises:
            EmbeddingError: If API returns error or invalid response.
        """
        try:
            response = await self.client.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": texts,
                },
            )

            if response.status_code != 200:
                error_msg = response.json().get("error", "Unknown error")
                raise EmbeddingError(
                    f"API returned {response.status_code}: {error_msg}"
                )

            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]

            return embeddings

        except httpx.HTTPError as e:
            raise EmbeddingError(f"HTTP request failed: {e}") from e
        except (KeyError, ValueError) as e:
            raise EmbeddingError(f"Invalid API response: {e}") from e
