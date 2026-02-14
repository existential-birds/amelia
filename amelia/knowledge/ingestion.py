"""Knowledge ingestion pipeline for parsing, chunking, and embedding documents."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

from amelia.knowledge.embeddings import EmbeddingClient, EmbeddingError
from amelia.knowledge.models import Document, DocumentStatus
from amelia.knowledge.repository import ChunkData, KnowledgeRepository


class IngestionError(Exception):
    """Pipeline error with user-friendly message."""

    def __init__(self, user_message: str, *args: object) -> None:
        self.user_message = user_message
        super().__init__(user_message, *args)


# Supported MIME types
_SUPPORTED_TYPES = {"application/pdf", "text/markdown"}


class IngestionPipeline:
    """Parse, chunk, embed, and store documents.

    Args:
        repository: Data layer for documents and chunks.
        embedding_client: OpenRouter embedding client.
        concurrency_limit: Max simultaneous document ingestions.
    """

    def __init__(
        self,
        repository: KnowledgeRepository,
        embedding_client: EmbeddingClient,
        concurrency_limit: int = 2,
    ) -> None:
        self.repository = repository
        self.embedding_client = embedding_client
        self._semaphore = asyncio.Semaphore(concurrency_limit)

    async def ingest_document(
        self,
        document_id: str,
        file_path: Path,
        content_type: str,
        progress_callback: Callable[[str, float, int, int], None] | None = None,
    ) -> Document:
        """Run full ingestion pipeline for a document.

        Args:
            document_id: UUID of the document record.
            file_path: Path to the uploaded file.
            content_type: MIME type of the file.
            progress_callback: Optional (stage, progress, chunks_processed, total_chunks).

        Returns:
            Updated Document with status=READY.

        Raises:
            IngestionError: On any pipeline failure.
        """
        async with self._semaphore:
            try:
                await self.repository.update_document_status(
                    document_id, DocumentStatus.PROCESSING
                )

                # Stage 1: Parse
                if progress_callback:
                    progress_callback("parsing", 0.0, 0, 0)
                raw_text, docling_doc = await self._parse(file_path, content_type)
                if progress_callback:
                    progress_callback("parsing", 0.1, 0, 0)

                # Stage 2: Chunk
                if progress_callback:
                    progress_callback("chunking", 0.1, 0, 0)
                chunks = await self._chunk(docling_doc)
                total_chunks = len(chunks)
                if progress_callback:
                    progress_callback("chunking", 0.2, 0, total_chunks)

                # Stage 3: Embed
                if progress_callback:
                    progress_callback("embedding", 0.2, 0, total_chunks)
                chunk_texts = [c.text for c in chunks]

                def embed_progress(processed: int, total: int) -> None:
                    if progress_callback:
                        frac = processed / total if total > 0 else 1.0
                        progress_callback(
                            "embedding", 0.2 + 0.7 * frac, processed, total_chunks
                        )

                embeddings = await self.embedding_client.embed_batch(
                    chunk_texts, progress_callback=embed_progress
                )

                # Build ChunkData list
                chunk_data: list[ChunkData] = []
                total_tokens = 0
                for i, (chunk, embedding) in enumerate(
                    zip(chunks, embeddings, strict=True)
                ):
                    # Estimate token count (~4 chars per token)
                    token_count = max(1, len(chunk.text) // 4)
                    total_tokens += token_count
                    chunk_data.append(
                        ChunkData(
                            chunk_index=i,
                            content=chunk.text,
                            heading_path=list(chunk.meta.headings)
                            if chunk.meta.headings
                            else [],
                            token_count=token_count,
                            embedding=embedding,
                        )
                    )

                # Stage 4: Store
                if progress_callback:
                    progress_callback("storing", 0.9, total_chunks, total_chunks)
                await self.repository.insert_chunks(document_id, chunk_data)
                doc = await self.repository.update_document_status(
                    document_id,
                    DocumentStatus.READY,
                    chunk_count=total_chunks,
                    token_count=total_tokens,
                    raw_text=raw_text,
                )
                if progress_callback:
                    progress_callback("storing", 1.0, total_chunks, total_chunks)

                logger.info(
                    "Document ingested",
                    document_id=document_id,
                    chunk_count=total_chunks,
                    token_count=total_tokens,
                )
                return doc

            except IngestionError as exc:
                await self._fail_document(document_id, exc.user_message)
                raise
            except EmbeddingError as exc:
                user_msg = "Failed to generate embeddings. Please try again later."
                await self._fail_document(document_id, user_msg)
                raise IngestionError(user_msg) from exc
            except Exception as exc:
                user_msg = "Failed to save document. Please try again."
                await self._fail_document(document_id, user_msg)
                raise IngestionError(user_msg) from exc

    async def _parse(
        self, file_path: Path, content_type: str
    ) -> tuple[str, object]:
        """Parse document with Docling.

        Args:
            file_path: Path to file.
            content_type: MIME type.

        Returns:
            Tuple of (raw_text, docling_document).

        Raises:
            IngestionError: If unsupported type, corrupt file, or empty.
        """
        if content_type not in _SUPPORTED_TYPES:
            raise IngestionError(
                f"Unsupported file type: {content_type}. Supported: PDF, Markdown."
            )

        try:
            from docling.document_converter import DocumentConverter  # noqa: PLC0415

            converter = DocumentConverter()
            result = await asyncio.to_thread(converter.convert, str(file_path))
            raw_text = result.document.export_to_text()
        except IngestionError:
            raise
        except Exception as exc:
            user_msg = "The file could not be parsed. It may be corrupted or in an unsupported format."
            raise IngestionError(user_msg) from exc

        if not raw_text or not raw_text.strip():
            raise IngestionError("No text content found in this document.")

        return raw_text, result.document

    async def _chunk(self, docling_doc: object) -> list[Any]:
        """Chunk document using Docling's hierarchical chunker.

        Args:
            docling_doc: Docling document object.

        Returns:
            List of Docling chunk objects.
        """
        from docling.chunking import (  # type: ignore[attr-defined]  # noqa: PLC0415
            HierarchicalChunker,
        )

        chunker = HierarchicalChunker()
        chunks = await asyncio.to_thread(chunker.chunk, docling_doc)  # type: ignore[arg-type]
        return list(chunks)

    async def _fail_document(self, document_id: str, error_message: str) -> None:
        """Set document status to FAILED."""
        try:
            await self.repository.update_document_status(
                document_id, DocumentStatus.FAILED, error=error_message
            )
        except Exception:
            logger.exception(
                "Failed to update document status",
                document_id=document_id,
            )
