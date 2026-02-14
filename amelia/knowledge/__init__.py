"""Knowledge Library: RAG backend for documentation retrieval."""

from amelia.knowledge.embeddings import EmbeddingClient, EmbeddingError
from amelia.knowledge.models import Document, DocumentChunk, DocumentStatus, SearchResult


__all__ = [
    "Document",
    "DocumentChunk",
    "DocumentStatus",
    "EmbeddingClient",
    "EmbeddingError",
    "SearchResult",
]
