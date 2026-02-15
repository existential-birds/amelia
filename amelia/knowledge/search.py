"""Semantic search for Knowledge Library."""

from loguru import logger

from amelia.knowledge.embeddings import EmbeddingClient
from amelia.knowledge.models import SearchResult
from amelia.knowledge.repository import KnowledgeRepository


async def knowledge_search(
    query: str,
    embedding_client: EmbeddingClient,
    repository: KnowledgeRepository,
    top_k: int = 5,
    tags: list[str] | None = None,
    similarity_threshold: float = 0.7,
) -> list[SearchResult]:
    """Search documentation chunks by semantic similarity.

    Embeds the query text, then searches the vector index for matching chunks.

    Args:
        query: Natural language search query.
        embedding_client: Client for embedding the query.
        repository: Knowledge repository for vector search.
        top_k: Maximum results to return.
        tags: Optional tags to filter documents before search.
        similarity_threshold: Minimum cosine similarity (0.0–1.0).

    Returns:
        Ranked search results above the similarity threshold.
    """
    query_embedding = await embedding_client.embed(query)

    results = await repository.search_chunks(
        query_embedding=query_embedding,
        top_k=top_k,
        tags=tags,
        similarity_threshold=similarity_threshold,
    )

    logger.info(
        "Knowledge search completed",
        query=query,
        result_count=len(results),
        tags=tags,
    )

    return results
