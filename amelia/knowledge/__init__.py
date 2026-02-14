"""Knowledge Library: RAG backend for documentation retrieval."""

from amelia.knowledge.embeddings import EmbeddingClient, EmbeddingError
from amelia.knowledge.ingestion import IngestionError, IngestionPipeline
from amelia.knowledge.models import Document, DocumentChunk, DocumentStatus, SearchResult
from amelia.knowledge.service import KnowledgeService


__all__ = [
    "Document",
    "DocumentChunk",
    "DocumentStatus",
    "EmbeddingClient",
    "EmbeddingError",
    "IngestionError",
    "IngestionPipeline",
    "KnowledgeService",
    "SearchResult",
]
