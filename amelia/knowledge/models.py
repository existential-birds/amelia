"""Pydantic models for Knowledge Library."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DocumentStatus(StrEnum):
    """Document processing status.

    Attributes:
        PENDING: Document uploaded, awaiting processing.
        PROCESSING: Currently being parsed, chunked, and embedded.
        READY: Successfully processed and searchable.
        FAILED: Processing failed (error in `error` field).
    """

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(BaseModel):
    """Document metadata and status.

    Attributes:
        id: Unique document identifier.
        name: User-provided document name.
        filename: Original uploaded filename.
        content_type: MIME type (application/pdf, text/markdown).
        tags: User-provided tags for filtering.
        status: Processing status (pending/processing/ready/failed).
        error: Error message if status=failed.
        chunk_count: Number of chunks generated.
        token_count: Total tokens across all chunks.
        raw_text: Full extracted text for Oracle deep processing.
        metadata: Additional metadata (file size, upload source, etc).
        created_at: Upload timestamp.
        updated_at: Last status update timestamp.
    """

    id: str
    name: str
    filename: str
    content_type: str
    tags: list[str] = Field(default_factory=list)
    status: DocumentStatus = DocumentStatus.PENDING
    error: str | None = None
    chunk_count: int = 0
    token_count: int = 0
    raw_text: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DocumentChunk(BaseModel):
    """Text chunk with embedding vector.

    Attributes:
        id: Unique chunk identifier.
        document_id: Parent document reference.
        chunk_index: Sequential index within document.
        content: Chunk text content.
        heading_path: Hierarchical heading context.
        token_count: Token count for this chunk.
        embedding: Dense vector (1536 dims for text-embedding-3-small).
        metadata: Additional chunk metadata.
        created_at: Chunk creation timestamp.
    """

    id: str
    document_id: str
    chunk_index: int
    content: str
    heading_path: list[str] = Field(default_factory=list)
    token_count: int
    embedding: list[float]
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SearchResult(BaseModel):
    """Semantic search result.

    Attributes:
        chunk_id: Matching chunk identifier.
        document_id: Source document identifier.
        document_name: Human-readable document name.
        tags: Document tags.
        content: Chunk text content.
        heading_path: Hierarchical heading context.
        similarity: Cosine similarity score (0.0-1.0).
        token_count: Token count for context window management.
    """

    chunk_id: str
    document_id: str
    document_name: str
    tags: list[str]
    content: str
    heading_path: list[str]
    similarity: float
    token_count: int
