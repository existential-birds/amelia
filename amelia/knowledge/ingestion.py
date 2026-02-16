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

# Max text length for tag extraction (~2000 tokens)
MAX_RAW_TEXT_FOR_TAGS = 8000


class IngestionPipeline:
    """Parse, chunk, embed, and store documents.

    Args:
        repository: Data layer for documents and chunks.
        embedding_client: OpenRouter embedding client.
        concurrency_limit: Max simultaneous document ingestions.
        tag_derivation_model: LLM model for tag extraction (None = disabled).
        tag_derivation_driver: Driver type for tag extraction ("api" or "cli").
    """

    def __init__(
        self,
        repository: KnowledgeRepository,
        embedding_client: EmbeddingClient,
        concurrency_limit: int = 2,
        tag_derivation_model: str | None = None,
        tag_derivation_driver: str = "api",
    ) -> None:
        self.repository = repository
        self.embedding_client = embedding_client
        self._semaphore = asyncio.Semaphore(concurrency_limit)
        self.tag_derivation_model = tag_derivation_model
        self.tag_derivation_driver = tag_derivation_driver

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

                # Stage 3.5: Derive tags (if enabled)
                if self.tag_derivation_model:
                    if progress_callback:
                        progress_callback("deriving_tags", 0.89, total_chunks, total_chunks)

                    derived_tags = await self._derive_tags(
                        document_name=file_path.name,
                        raw_text=raw_text,
                        chunk_data=chunk_data,
                        model=self.tag_derivation_model,
                        driver_type=self.tag_derivation_driver,
                    )

                    # Update document with derived tags (non-blocking)
                    if derived_tags:
                        try:
                            await self.repository.update_document_tags(document_id, derived_tags)
                        except Exception as exc:
                            logger.warning(
                                "Failed to update document tags",
                                document_id=document_id,
                                error=str(exc),
                            )

                    if progress_callback:
                        progress_callback("deriving_tags", 0.90, total_chunks, total_chunks)

                # Stage 4: Store
                if progress_callback:
                    progress_callback("storing", 0.91, total_chunks, total_chunks)
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

    def _prepare_tag_extraction_input(
        self,
        raw_text: str,
        chunk_data: list[ChunkData],
        document_name: str,
    ) -> tuple[str, list[list[str]]]:
        """Prepare text excerpt and heading structure for tag extraction.

        Args:
            raw_text: Full document text.
            chunk_data: List of chunks with heading paths.
            document_name: Original filename.

        Returns:
            Tuple of (text_excerpt, unique_heading_paths).
        """
        # Extract unique heading paths from chunks
        unique_headings: list[list[str]] = []
        seen_paths = set()
        for chunk in chunk_data:
            path_tuple = tuple(chunk["heading_path"])
            if path_tuple and path_tuple not in seen_paths:
                unique_headings.append(chunk["heading_path"])
                seen_paths.add(path_tuple)

        # Truncate text if needed
        text_excerpt = raw_text[:MAX_RAW_TEXT_FOR_TAGS]
        if len(raw_text) > MAX_RAW_TEXT_FOR_TAGS:
            text_excerpt += "\n\n[... content truncated for tag extraction ...]"

        return text_excerpt, unique_headings

    def _build_tag_extraction_prompt(
        self,
        raw_text_excerpt: str,
        heading_paths: list[list[str]],
        document_name: str,
    ) -> str:
        """Build prompt for tag extraction from document content.

        Args:
            raw_text_excerpt: Truncated document text.
            heading_paths: Unique heading paths from document structure.
            document_name: Original filename.

        Returns:
            Prompt string for LLM tag extraction.
        """
        # Format heading tree
        heading_tree = ""
        if heading_paths:
            for path in heading_paths:
                indent = "  " * (len(path) - 1)
                heading_tree += f"{indent}- {path[-1]}\n"

        return f"""Extract 5-10 relevant tags for the following document to enable effective filtering and discovery.

Document name: {document_name}

Document structure (headings):
{heading_tree if heading_tree else "(No headings found)"}

Document content excerpt (first ~8000 chars):
{raw_text_excerpt}

Guidelines for tag selection:
- Focus on main topics, technologies, concepts, and document purpose
- Use concise tags (1-3 words each)
- Prefer specific over generic tags (e.g., "kubernetes" over "cloud")
- Include both broad categories and specific details
- Use lowercase for consistency
- Avoid overly generic tags like "document" or "information"

Return 5-10 tags that best describe this document's content and purpose."""

    def _validate_tags(self, tags: list[str]) -> list[str]:
        """Validate and clean extracted tags.

        Args:
            tags: Raw tags from LLM.

        Returns:
            Cleaned and deduplicated tags.
        """
        cleaned = []
        seen = set()

        for tag in tags:
            # Strip whitespace and lowercase
            tag = tag.strip().lower()

            # Skip empty or very long tags
            if not tag or len(tag) > 50:
                continue

            # Deduplicate (case-insensitive)
            if tag not in seen:
                cleaned.append(tag)
                seen.add(tag)

        return cleaned

    async def _derive_tags(
        self,
        document_name: str,
        raw_text: str,
        chunk_data: list[ChunkData],
        model: str,
        driver_type: str,
    ) -> list[str]:
        """Derive tags from document content using LLM extraction.

        Args:
            document_name: Original filename for context.
            raw_text: Full document text.
            chunk_data: List of chunks with heading paths.
            model: LLM model identifier for extraction.
            driver_type: Driver type ("api" or "cli").

        Returns:
            List of validated tags (empty list if extraction fails).

        Note:
            Failures are logged but not raised - returns empty list on error.
        """
        try:
            # Prepare input (truncate text, extract headings)
            text_excerpt, heading_paths = self._prepare_tag_extraction_input(
                raw_text, chunk_data, document_name
            )

            # Build prompt
            prompt = self._build_tag_extraction_prompt(
                text_excerpt, heading_paths, document_name
            )

            # Extract structured output using LLM
            from amelia.core.extraction import extract_structured  # noqa: PLC0415
            from amelia.knowledge.models import TagExtractionOutput  # noqa: PLC0415

            result = await extract_structured(
                prompt=prompt,
                schema=TagExtractionOutput,
                model=model,
                driver_type=driver_type,
            )

            # Validate and clean tags
            tags = self._validate_tags(result.tags)

            logger.info(
                "Derived tags from document",
                document_name=document_name,
                tag_count=len(tags),
                tags=tags,
                reasoning=result.reasoning,
            )

            return tags

        except Exception as exc:
            # Non-blocking: log error and return empty list
            logger.warning(
                "Tag derivation failed, continuing without tags",
                document_name=document_name,
                error=str(exc),
            )
            return []
