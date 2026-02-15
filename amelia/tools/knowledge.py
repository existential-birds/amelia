"""Knowledge Library tool for agent access."""

from collections.abc import Callable, Coroutine
from typing import Any

from amelia.knowledge.embeddings import EmbeddingClient
from amelia.knowledge.models import SearchResult
from amelia.knowledge.repository import KnowledgeRepository
from amelia.knowledge.search import knowledge_search as _search


def create_knowledge_tool(
    embedding_client: EmbeddingClient,
    repository: KnowledgeRepository,
) -> Callable[..., Coroutine[Any, Any, list[SearchResult]]]:
    """Create a knowledge_search tool for agent use.

    Args:
        embedding_client: Embedding client instance.
        repository: Knowledge repository instance.

    Returns:
        Async callable that agents invoke for semantic search.
    """

    async def knowledge_search(
        query: str,
        top_k: int = 5,
        tags: list[str] | None = None,
    ) -> list[SearchResult]:
        """Search uploaded documentation for relevant information.

        Use this tool to find information from the knowledge library.
        Useful for looking up framework APIs, library patterns, or internal docs.

        Args:
            query: Natural language search query.
            top_k: Maximum number of results (default 5).
            tags: Optional tags to filter documents.

        Returns:
            Ranked documentation chunks with similarity scores.
        """
        return await _search(
            query=query,
            embedding_client=embedding_client,
            repository=repository,
            top_k=top_k,
            tags=tags,
        )

    return knowledge_search
