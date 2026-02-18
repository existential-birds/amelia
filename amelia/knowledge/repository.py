"""PostgreSQL repository for Knowledge Library."""

import uuid
from typing import NotRequired, TypedDict
from uuid import uuid4

import asyncpg
from loguru import logger

from amelia.knowledge.models import Document, DocumentStatus, SearchResult
from amelia.server.database.connection import Database


class ChunkData(TypedDict):
    """Type for chunk data passed to insert_chunks."""

    chunk_index: int
    content: str
    heading_path: list[str]
    token_count: int
    embedding: list[float]
    metadata: NotRequired[dict[str, str]]


class KnowledgeRepository:
    """Repository for Knowledge Library database operations.

    Args:
        db: Database connection.
    """

    def __init__(self, db: Database):
        self.db = db

    async def create_document(
        self,
        name: str,
        filename: str,
        content_type: str,
        tags: list[str] | None = None,
    ) -> Document:
        """Create a new document record.

        Args:
            name: User-provided document name.
            filename: Original uploaded filename.
            content_type: MIME type.
            tags: Optional tags for filtering.

        Returns:
            Created document with generated ID.
        """
        doc_id = uuid4()
        tags = tags or []

        row = await self.db.fetch_one(
            """
            INSERT INTO documents (id, name, filename, content_type, tags, status)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            doc_id,
            name,
            filename,
            content_type,
            tags,
            DocumentStatus.PENDING,
        )

        logger.info("Created document", document_id=doc_id, name=name)
        return self._row_to_document(row)

    async def get_document(self, document_id: uuid.UUID) -> Document | None:
        """Retrieve document by ID.

        Args:
            document_id: Document UUID.

        Returns:
            Document if found, None otherwise.
        """
        row = await self.db.fetch_one(
            "SELECT * FROM documents WHERE id = $1",
            document_id,
        )

        if not row:
            return None

        return self._row_to_document(row)

    async def list_documents(self) -> list[Document]:
        """List all documents.

        Returns:
            List of all documents, ordered by creation date (newest first).
        """
        rows = await self.db.fetch_all(
            "SELECT * FROM documents ORDER BY created_at DESC"
        )

        return [self._row_to_document(row) for row in rows]

    async def update_document_status(
        self,
        document_id: uuid.UUID,
        status: DocumentStatus,
        error: str | None = None,
        chunk_count: int | None = None,
        token_count: int | None = None,
        raw_text: str | None = None,
    ) -> Document:
        """Update document status and metadata.

        Args:
            document_id: Document UUID.
            status: New processing status.
            error: Optional error message (for failed status).
            chunk_count: Optional chunk count (for ready status).
            token_count: Optional total token count (for ready status).
            raw_text: Optional full document text (for ready status).

        Returns:
            Updated document.

        Raises:
            ValueError: If document not found.
        """
        row = await self.db.fetch_one(
            """
            UPDATE documents
            SET status = $2,
                error = $3,
                chunk_count = COALESCE($4, chunk_count),
                token_count = COALESCE($5, token_count),
                raw_text = COALESCE($6, raw_text),
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            document_id,
            status,
            error,
            chunk_count,
            token_count,
            raw_text,
        )

        if not row:
            raise ValueError(f"Document not found: {document_id}")

        logger.info(
            "Updated document status",
            document_id=document_id,
            status=status,
            error=error,
        )
        return self._row_to_document(row)

    async def update_document_tags(
        self,
        document_id: uuid.UUID,
        tags: list[str],
    ) -> Document:
        """Update document tags.

        Args:
            document_id: Document UUID.
            tags: New tags to set (replaces existing tags).

        Returns:
            Updated document.

        Raises:
            ValueError: If document not found.
        """
        row = await self.db.fetch_one(
            """
            UPDATE documents
            SET tags = $2,
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            document_id,
            tags,
        )

        if not row:
            raise ValueError(f"Document not found: {document_id}")

        logger.info(
            "Updated document tags",
            document_id=document_id,
            tag_count=len(tags),
        )
        return self._row_to_document(row)

    async def delete_document(self, document_id: uuid.UUID) -> None:
        """Delete document and all associated chunks.

        Args:
            document_id: Document UUID.
        """
        await self.db.execute(
            "DELETE FROM documents WHERE id = $1",
            document_id,
        )

        logger.info("Deleted document", document_id=document_id)

    async def insert_chunks(
        self,
        document_id: uuid.UUID,
        chunks: list[ChunkData],
    ) -> None:
        """Insert document chunks in batch.

        Args:
            document_id: Parent document UUID.
            chunks: List of chunk dictionaries with fields:
                - chunk_index: int
                - content: str
                - heading_path: list[str]
                - token_count: int
                - embedding: list[float] (1536 dims)
                - metadata: dict
        """
        if not chunks:
            return

        async with self.db.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO document_chunks
                    (id, document_id, chunk_index, content, heading_path,
                     token_count, embedding, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                [
                    (
                        uuid4(),
                        document_id,
                        chunk["chunk_index"],
                        chunk["content"],
                        chunk["heading_path"],
                        chunk["token_count"],
                        chunk["embedding"],
                        chunk.get("metadata", {}),
                    )
                    for chunk in chunks
                ],
            )

        logger.info(
            "Inserted chunks",
            document_id=document_id,
            chunk_count=len(chunks),
        )

    async def search_chunks(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        tags: list[str] | None = None,
        similarity_threshold: float = 0.7,
    ) -> list[SearchResult]:
        """Semantic search for document chunks.

        Uses filter-then-search strategy: filter by tags first, then vector search.

        Args:
            query_embedding: Query vector (1536 dims).
            top_k: Maximum results to return.
            tags: Optional tags to filter documents.
            similarity_threshold: Minimum cosine similarity (0.0-1.0).

        Returns:
            Ranked search results above threshold.
        """
        async with self.db.pool.acquire() as conn:
            if tags:
                # Filter-then-search: constrain to tagged documents
                rows = await conn.fetch(
                    """
                    WITH tagged_docs AS (
                        SELECT id FROM documents
                        WHERE tags && $1
                    )
                    SELECT
                        dc.id AS chunk_id,
                        dc.document_id,
                        d.name AS document_name,
                        d.tags,
                        dc.content,
                        dc.heading_path,
                        dc.token_count,
                        1 - (dc.embedding <=> $2) AS similarity
                    FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.id
                    JOIN tagged_docs td ON dc.document_id = td.id
                    WHERE d.status = 'ready'
                      AND 1 - (dc.embedding <=> $2) >= $3
                    ORDER BY dc.embedding <=> $2
                    LIMIT $4
                    """,
                    tags,
                    query_embedding,
                    similarity_threshold,
                    top_k,
                )
            else:
                # Search all ready documents
                rows = await conn.fetch(
                    """
                    SELECT
                        dc.id AS chunk_id,
                        dc.document_id,
                        d.name AS document_name,
                        d.tags,
                        dc.content,
                        dc.heading_path,
                        dc.token_count,
                        1 - (dc.embedding <=> $1) AS similarity
                    FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.id
                    WHERE d.status = 'ready'
                      AND 1 - (dc.embedding <=> $1) >= $2
                    ORDER BY dc.embedding <=> $1
                    LIMIT $3
                    """,
                    query_embedding,
                    similarity_threshold,
                    top_k,
                )

        results = [
            SearchResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                document_name=row["document_name"],
                tags=row["tags"],
                content=row["content"],
                heading_path=row["heading_path"],
                similarity=row["similarity"],
                token_count=row["token_count"],
            )
            for row in rows
        ]

        logger.debug(
            "Search completed",
            result_count=len(results),
            tags=tags,
            top_k=top_k,
        )
        return results

    def _row_to_document(self, row: asyncpg.Record) -> Document:
        """Convert database row to Document model."""
        return Document(
            id=row["id"],
            name=row["name"],
            filename=row["filename"],
            content_type=row["content_type"],
            tags=row["tags"],
            status=DocumentStatus(row["status"]),
            error=row["error"],
            chunk_count=row["chunk_count"],
            token_count=row["token_count"],
            raw_text=row["raw_text"],
            metadata=row["metadata"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
