# Knowledge Ingestion Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the end-to-end ingestion pipeline that parses PDF/Markdown files with Docling, chunks by document structure, embeds via OpenRouter, stores in PostgreSQL, and emits real-time progress events.

**Architecture:** Two new modules — `IngestionPipeline` handles pure data transformation (parse, chunk, embed, store) with a progress callback, while `KnowledgeService` wraps it as a background task with event emission via EventBus. Four new event types under a new `KNOWLEDGE` domain.

**Tech Stack:** Docling (DocumentConverter, HierarchicalChunker), tiktoken (cl100k_base), existing EmbeddingClient, KnowledgeRepository, EventBus.

**Design doc:** `docs/plans/2026-02-14-knowledge-ingestion-pipeline-design.md`

---

### Task 1: Add Event Types to events.py

**Files:**
- Modify: `amelia/server/models/events.py`
- Test: `tests/unit/knowledge/test_ingestion.py` (created in Task 2, validates events exist)

**Step 1: Add KNOWLEDGE to EventDomain enum**

In `amelia/server/models/events.py`, add to `EventDomain`:

```python
class EventDomain(StrEnum):
    """Domain of event origin.

    Attributes:
        WORKFLOW: Standard workflow events (orchestrator, agents).
        BRAINSTORM: Brainstorming session events (chat streaming).
        ORACLE: Oracle consultation events.
        KNOWLEDGE: Knowledge library events (document ingestion).
    """

    WORKFLOW = "workflow"
    BRAINSTORM = "brainstorm"
    ORACLE = "oracle"
    KNOWLEDGE = "knowledge"
```

**Step 2: Add 4 document ingestion event types to EventType enum**

Add after the Oracle section:

```python
    # Knowledge library (document ingestion)
    DOCUMENT_INGESTION_STARTED = "document_ingestion_started"
    DOCUMENT_INGESTION_PROGRESS = "document_ingestion_progress"
    DOCUMENT_INGESTION_COMPLETED = "document_ingestion_completed"
    DOCUMENT_INGESTION_FAILED = "document_ingestion_failed"
```

**Step 3: Add to level classification sets**

Add `EventType.DOCUMENT_INGESTION_FAILED` to `_ERROR_TYPES`.
Add `EventType.DOCUMENT_INGESTION_STARTED` and `EventType.DOCUMENT_INGESTION_COMPLETED` to `_INFO_TYPES`.
(`DOCUMENT_INGESTION_PROGRESS` falls through to DEBUG — correct for frequent updates.)

**Step 4: Run existing tests to verify no regressions**

Run: `uv run pytest tests/unit/server/ -v -q`
Expected: All pass, no regressions.

**Step 5: Commit**

```bash
git add amelia/server/models/events.py
git commit -m "feat(knowledge): add KNOWLEDGE event domain and ingestion event types"
```

---

### Task 2: Create IngestionError and IngestionPipeline skeleton with first test

**Files:**
- Create: `amelia/knowledge/ingestion.py`
- Create: `tests/unit/knowledge/test_ingestion.py`
- Modify: `amelia/knowledge/__init__.py`

**Step 1: Write the first failing test — unsupported content type**

Create `tests/unit/knowledge/test_ingestion.py`:

```python
"""Test knowledge ingestion pipeline."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from amelia.knowledge.ingestion import IngestionError, IngestionPipeline


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Mock KnowledgeRepository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_embedding_client() -> AsyncMock:
    """Mock EmbeddingClient."""
    client = AsyncMock()
    return client


@pytest.fixture
def pipeline(
    mock_repository: AsyncMock, mock_embedding_client: AsyncMock
) -> IngestionPipeline:
    """Create pipeline with mocked dependencies."""
    return IngestionPipeline(
        repository=mock_repository,
        embedding_client=mock_embedding_client,
    )


@pytest.mark.asyncio
async def test_ingest_unsupported_content_type(pipeline: IngestionPipeline) -> None:
    """Should raise IngestionError for unsupported content type."""
    with pytest.raises(IngestionError, match="Unsupported file type"):
        await pipeline.ingest_document(
            document_id="doc-1",
            file_path=Path("/tmp/test.xlsx"),
            content_type="application/vnd.ms-excel",
        )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py::test_ingest_unsupported_content_type -v`
Expected: FAIL (ImportError — module doesn't exist yet)

**Step 3: Create minimal ingestion.py**

Create `amelia/knowledge/ingestion.py`:

```python
"""Knowledge ingestion pipeline: parse, chunk, embed, store."""

import asyncio
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from amelia.knowledge.embeddings import EmbeddingClient
from amelia.knowledge.models import Document, DocumentStatus
from amelia.knowledge.repository import KnowledgeRepository

SUPPORTED_CONTENT_TYPES = {
    "application/pdf": "pdf",
    "text/markdown": "markdown",
}


class IngestionError(Exception):
    """Error during document ingestion with user-friendly message."""

    def __init__(self, user_message: str, detail: str | None = None) -> None:
        self.user_message = user_message
        super().__init__(detail or user_message)


class IngestionPipeline:
    """End-to-end document ingestion: parse, chunk, embed, store.

    Args:
        repository: Knowledge repository for database operations.
        embedding_client: OpenRouter embedding client.
        concurrency_limit: Max concurrent document ingestions.
    """

    def __init__(
        self,
        repository: KnowledgeRepository,
        embedding_client: EmbeddingClient,
        concurrency_limit: int = 2,
    ) -> None:
        self._repository = repository
        self._embedding_client = embedding_client
        self._semaphore = asyncio.Semaphore(concurrency_limit)

    async def ingest_document(
        self,
        document_id: str,
        file_path: Path,
        content_type: str,
        progress_callback: Callable[[str, float, int, int], None] | None = None,
    ) -> Document:
        """Ingest a document end-to-end: parse, chunk, embed, store.

        Args:
            document_id: Document UUID (must already exist in DB).
            file_path: Path to the file on disk.
            content_type: MIME type (application/pdf or text/markdown).
            progress_callback: Optional (stage, progress, chunks_done, total_chunks).

        Returns:
            Updated Document with status READY.

        Raises:
            IngestionError: If any stage fails.
        """
        if content_type not in SUPPORTED_CONTENT_TYPES:
            raise IngestionError(
                f"Unsupported file type: {content_type}. Supported: PDF, Markdown."
            )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py::test_ingest_unsupported_content_type -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/knowledge/ingestion.py tests/unit/knowledge/test_ingestion.py
git commit -m "feat(knowledge): add IngestionError and pipeline skeleton with content type validation"
```

---

### Task 3: Implement _parse stage

**Files:**
- Modify: `amelia/knowledge/ingestion.py`
- Modify: `tests/unit/knowledge/test_ingestion.py`

**Step 1: Write failing test — successful PDF parse**

Add to `tests/unit/knowledge/test_ingestion.py`:

```python
from unittest.mock import MagicMock, patch

from docling.datamodel.base_models import ConversionStatus


def _make_conversion_result(text: str = "Hello world") -> MagicMock:
    """Create a mock Docling ConversionResult."""
    doc = MagicMock()
    doc.export_to_markdown.return_value = text

    result = MagicMock()
    result.status = ConversionStatus.SUCCESS
    result.document = doc
    return result


@pytest.mark.asyncio
async def test_parse_pdf_document(pipeline: IngestionPipeline) -> None:
    """Should parse PDF and return raw text + docling document."""
    mock_result = _make_conversion_result("Parsed PDF content")

    with patch(
        "amelia.knowledge.ingestion.DocumentConverter"
    ) as mock_converter_cls:
        mock_converter_cls.return_value.convert.return_value = mock_result

        raw_text, dl_doc = await pipeline._parse(
            Path("/tmp/test.pdf"), "application/pdf"
        )

    assert raw_text == "Parsed PDF content"
    assert dl_doc is mock_result.document
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py::test_parse_pdf_document -v`
Expected: FAIL (AttributeError — `_parse` doesn't exist)

**Step 3: Implement _parse**

Add imports to `amelia/knowledge/ingestion.py`:

```python
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter
from docling_core.types.doc.document import DoclingDocument
```

Add method to `IngestionPipeline`:

```python
    async def _parse(
        self, file_path: Path, content_type: str
    ) -> tuple[str, DoclingDocument]:
        """Parse document with Docling.

        Args:
            file_path: Path to the file.
            content_type: MIME type.

        Returns:
            Tuple of (raw_text, DoclingDocument).

        Raises:
            IngestionError: If parsing fails.
        """
        format_map = {
            "application/pdf": [InputFormat.PDF],
            "text/markdown": [InputFormat.MD],
        }
        allowed_formats = format_map[content_type]

        def _do_parse() -> tuple[str, DoclingDocument]:
            converter = DocumentConverter(allowed_formats=allowed_formats)
            result = converter.convert(file_path)

            if result.status == ConversionStatus.FAILURE:
                raise IngestionError(
                    "The file could not be parsed. It may be corrupted or in an unsupported format.",
                    detail=f"Docling conversion failed for {file_path}",
                )

            raw_text = result.document.export_to_markdown()
            if not raw_text.strip():
                raise IngestionError("No text content found in this document.")

            return raw_text, result.document

        try:
            return await asyncio.to_thread(_do_parse)
        except IngestionError:
            raise
        except Exception as e:
            error_str = str(e).lower()
            if "password" in error_str or "encrypted" in error_str:
                raise IngestionError(
                    "This PDF is password-protected. Please provide an unlocked version.",
                    detail=str(e),
                ) from e
            raise IngestionError(
                "The file could not be parsed. It may be corrupted or in an unsupported format.",
                detail=str(e),
            ) from e
```

Also add `ConversionStatus` to the imports:

```python
from docling.datamodel.base_models import ConversionStatus, InputFormat
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py::test_parse_pdf_document -v`
Expected: PASS

**Step 5: Write and run test for parse failure**

Add to test file:

```python
@pytest.mark.asyncio
async def test_parse_failure_returns_ingestion_error(
    pipeline: IngestionPipeline,
) -> None:
    """Should raise IngestionError when Docling parsing fails."""
    mock_result = MagicMock()
    mock_result.status = ConversionStatus.FAILURE

    with patch(
        "amelia.knowledge.ingestion.DocumentConverter"
    ) as mock_converter_cls:
        mock_converter_cls.return_value.convert.return_value = mock_result

        with pytest.raises(IngestionError, match="could not be parsed"):
            await pipeline._parse(Path("/tmp/bad.pdf"), "application/pdf")


@pytest.mark.asyncio
async def test_parse_empty_document(pipeline: IngestionPipeline) -> None:
    """Should raise IngestionError when document has no text content."""
    mock_result = _make_conversion_result("   ")

    with patch(
        "amelia.knowledge.ingestion.DocumentConverter"
    ) as mock_converter_cls:
        mock_converter_cls.return_value.convert.return_value = mock_result

        with pytest.raises(IngestionError, match="No text content"):
            await pipeline._parse(Path("/tmp/empty.pdf"), "application/pdf")
```

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py -v -q`
Expected: All pass.

**Step 6: Commit**

```bash
git add amelia/knowledge/ingestion.py tests/unit/knowledge/test_ingestion.py
git commit -m "feat(knowledge): implement _parse stage with Docling DocumentConverter"
```

---

### Task 4: Implement _chunk stage

**Files:**
- Modify: `amelia/knowledge/ingestion.py`
- Modify: `tests/unit/knowledge/test_ingestion.py`

**Step 1: Write failing test — chunk document**

Add to test file:

```python
def _make_doc_chunk(text: str, headings: list[str] | None = None) -> MagicMock:
    """Create a mock DocChunk."""
    chunk = MagicMock()
    chunk.text = text
    chunk.meta = MagicMock()
    chunk.meta.headings = headings
    return chunk


@pytest.mark.asyncio
async def test_chunk_document(pipeline: IngestionPipeline) -> None:
    """Should chunk document and return list with heading paths."""
    mock_chunks = [
        _make_doc_chunk("First chunk", ["Introduction"]),
        _make_doc_chunk("Second chunk", ["Introduction", "Details"]),
        _make_doc_chunk("Third chunk", None),
    ]

    mock_dl_doc = MagicMock()

    with patch(
        "amelia.knowledge.ingestion.HierarchicalChunker"
    ) as mock_chunker_cls:
        mock_chunker_cls.return_value.chunk.return_value = iter(mock_chunks)

        chunks = await pipeline._chunk(mock_dl_doc)

    assert len(chunks) == 3
    assert chunks[0].text == "First chunk"
    assert chunks[1].meta.headings == ["Introduction", "Details"]
    assert chunks[2].meta.headings is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py::test_chunk_document -v`
Expected: FAIL

**Step 3: Implement _chunk**

Add import to `amelia/knowledge/ingestion.py`:

```python
from docling.chunking import HierarchicalChunker
from docling_core.transforms.chunker.hierarchical_chunker import DocChunk
```

Add method to `IngestionPipeline`:

```python
    async def _chunk(self, dl_doc: DoclingDocument) -> list[DocChunk]:
        """Chunk document using Docling HierarchicalChunker.

        Args:
            dl_doc: Docling document from parsing stage.

        Returns:
            List of DocChunk objects with text and heading metadata.

        Raises:
            IngestionError: If chunking fails.
        """

        def _do_chunk() -> list[DocChunk]:
            chunker = HierarchicalChunker()
            return list(chunker.chunk(dl_doc))

        try:
            chunks = await asyncio.to_thread(_do_chunk)
        except Exception as e:
            raise IngestionError(
                "The file could not be parsed. It may be corrupted or in an unsupported format.",
                detail=f"Chunking failed: {e}",
            ) from e

        if not chunks:
            raise IngestionError("No text content found in this document.")

        logger.debug("Chunked document", chunk_count=len(chunks))
        return chunks
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py::test_chunk_document -v`
Expected: PASS

**Step 5: Write and run test for empty chunks**

```python
@pytest.mark.asyncio
async def test_chunk_empty_result(pipeline: IngestionPipeline) -> None:
    """Should raise IngestionError when chunker produces no chunks."""
    mock_dl_doc = MagicMock()

    with patch(
        "amelia.knowledge.ingestion.HierarchicalChunker"
    ) as mock_chunker_cls:
        mock_chunker_cls.return_value.chunk.return_value = iter([])

        with pytest.raises(IngestionError, match="No text content"):
            await pipeline._chunk(mock_dl_doc)
```

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py -v -q`
Expected: All pass.

**Step 6: Commit**

```bash
git add amelia/knowledge/ingestion.py tests/unit/knowledge/test_ingestion.py
git commit -m "feat(knowledge): implement _chunk stage with HierarchicalChunker"
```

---

### Task 5: Implement _embed stage

**Files:**
- Modify: `amelia/knowledge/ingestion.py`
- Modify: `tests/unit/knowledge/test_ingestion.py`

**Step 1: Write failing test — embed chunks**

Add to test file:

```python
from amelia.knowledge.repository import ChunkData


@pytest.mark.asyncio
async def test_embed_chunks(
    pipeline: IngestionPipeline, mock_embedding_client: AsyncMock
) -> None:
    """Should embed chunk texts and return ChunkData with token counts."""
    chunks = [
        _make_doc_chunk("First chunk text", ["Intro"]),
        _make_doc_chunk("Second chunk text", ["Intro", "Details"]),
    ]

    mock_embedding_client.embed_batch.return_value = [
        [0.1] * 1536,
        [0.2] * 1536,
    ]

    chunk_data = await pipeline._embed(chunks)

    assert len(chunk_data) == 2
    assert chunk_data[0]["chunk_index"] == 0
    assert chunk_data[0]["content"] == "First chunk text"
    assert chunk_data[0]["heading_path"] == ["Intro"]
    assert len(chunk_data[0]["embedding"]) == 1536
    assert chunk_data[0]["token_count"] > 0
    assert chunk_data[1]["chunk_index"] == 1
    assert chunk_data[1]["heading_path"] == ["Intro", "Details"]
    mock_embedding_client.embed_batch.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py::test_embed_chunks -v`
Expected: FAIL

**Step 3: Implement _embed**

Add import to `amelia/knowledge/ingestion.py`:

```python
import tiktoken

from amelia.knowledge.repository import ChunkData
```

Add module-level encoder:

```python
_TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")
```

Add method to `IngestionPipeline`:

```python
    async def _embed(
        self,
        chunks: list[DocChunk],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[ChunkData]:
        """Embed chunks and build ChunkData for storage.

        Args:
            chunks: DocChunk objects from chunking stage.
            progress_callback: Optional (processed, total) for embedding progress.

        Returns:
            List of ChunkData dicts ready for repository.insert_chunks.

        Raises:
            IngestionError: If embedding fails.
        """
        texts = [chunk.text for chunk in chunks]

        try:
            embeddings = await self._embedding_client.embed_batch(
                texts, progress_callback=progress_callback
            )
        except Exception as e:
            raise IngestionError(
                "Failed to generate embeddings. Please try again later.",
                detail=str(e),
            ) from e

        chunk_data: list[ChunkData] = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            headings = chunk.meta.headings if chunk.meta.headings else []
            token_count = len(_TIKTOKEN_ENCODING.encode(chunk.text))
            chunk_data.append(
                ChunkData(
                    chunk_index=i,
                    content=chunk.text,
                    heading_path=headings,
                    token_count=token_count,
                    embedding=embedding,
                )
            )

        return chunk_data
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py::test_embed_chunks -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/knowledge/ingestion.py tests/unit/knowledge/test_ingestion.py
git commit -m "feat(knowledge): implement _embed stage with tiktoken token counting"
```

---

### Task 6: Wire up full ingest_document flow

**Files:**
- Modify: `amelia/knowledge/ingestion.py`
- Modify: `tests/unit/knowledge/test_ingestion.py`

**Step 1: Write failing test — full PDF ingestion**

Add to test file:

```python
from amelia.knowledge.models import Document, DocumentStatus


def _make_mock_document(document_id: str = "doc-1", **kwargs: object) -> Document:
    """Create a mock Document for repository returns."""
    return Document(
        id=document_id,
        name="test.pdf",
        filename="test.pdf",
        content_type="application/pdf",
        tags=[],
        status=kwargs.get("status", DocumentStatus.READY),
        chunk_count=kwargs.get("chunk_count", 2),
        token_count=kwargs.get("token_count", 10),
    )


@pytest.mark.asyncio
async def test_ingest_pdf_end_to_end(
    pipeline: IngestionPipeline,
    mock_repository: AsyncMock,
    mock_embedding_client: AsyncMock,
) -> None:
    """Should run full pipeline: parse, chunk, embed, store."""
    mock_result = _make_conversion_result("PDF content here")
    mock_chunks = [
        _make_doc_chunk("Chunk one", ["Heading"]),
        _make_doc_chunk("Chunk two", ["Heading", "Sub"]),
    ]

    mock_embedding_client.embed_batch.return_value = [
        [0.1] * 1536,
        [0.2] * 1536,
    ]
    mock_repository.update_document_status.return_value = _make_mock_document()

    with (
        patch(
            "amelia.knowledge.ingestion.DocumentConverter"
        ) as mock_converter_cls,
        patch(
            "amelia.knowledge.ingestion.HierarchicalChunker"
        ) as mock_chunker_cls,
    ):
        mock_converter_cls.return_value.convert.return_value = mock_result
        mock_chunker_cls.return_value.chunk.return_value = iter(mock_chunks)

        doc = await pipeline.ingest_document(
            document_id="doc-1",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
        )

    # Verify status set to PROCESSING first
    mock_repository.update_document_status.assert_any_call(
        "doc-1", DocumentStatus.PROCESSING
    )
    # Verify chunks inserted
    mock_repository.insert_chunks.assert_called_once()
    args = mock_repository.insert_chunks.call_args
    assert args[0][0] == "doc-1"
    assert len(args[0][1]) == 2
    # Verify final status update to READY
    mock_repository.update_document_status.assert_called_with(
        "doc-1",
        DocumentStatus.READY,
        chunk_count=2,
        token_count=pytest.approx(doc.token_count, abs=5),
        raw_text="PDF content here",
    )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py::test_ingest_pdf_end_to_end -v`
Expected: FAIL (ingest_document only validates content type, doesn't run pipeline)

**Step 3: Complete ingest_document implementation**

Replace the body of `ingest_document` after the content type check:

```python
        async with self._semaphore:
            try:
                # Set status to PROCESSING
                await self._repository.update_document_status(
                    document_id, DocumentStatus.PROCESSING
                )

                # Stage 1: Parse
                if progress_callback:
                    progress_callback("parsing", 0.0, 0, 0)

                raw_text, dl_doc = await self._parse(file_path, content_type)

                if progress_callback:
                    progress_callback("parsing", 0.1, 0, 0)

                # Stage 2: Chunk
                if progress_callback:
                    progress_callback("chunking", 0.1, 0, 0)

                chunks = await self._chunk(dl_doc)
                total_chunks = len(chunks)

                if progress_callback:
                    progress_callback("chunking", 0.2, 0, total_chunks)

                # Stage 3: Embed
                def _embed_progress(processed: int, total: int) -> None:
                    if progress_callback:
                        embed_frac = processed / total if total > 0 else 1.0
                        overall = 0.2 + embed_frac * 0.7  # 0.2 to 0.9
                        progress_callback(
                            "embedding", overall, processed, total_chunks
                        )

                chunk_data = await self._embed(chunks, progress_callback=_embed_progress)

                # Stage 4: Store
                if progress_callback:
                    progress_callback("storing", 0.9, total_chunks, total_chunks)

                await self._repository.insert_chunks(document_id, chunk_data)

                total_tokens = sum(c["token_count"] for c in chunk_data)
                doc = await self._repository.update_document_status(
                    document_id,
                    DocumentStatus.READY,
                    chunk_count=total_chunks,
                    token_count=total_tokens,
                    raw_text=raw_text,
                )

                if progress_callback:
                    progress_callback("storing", 1.0, total_chunks, total_chunks)

                logger.info(
                    "Document ingestion complete",
                    document_id=document_id,
                    chunk_count=total_chunks,
                    token_count=total_tokens,
                )

                return doc

            except IngestionError as e:
                await self._repository.update_document_status(
                    document_id, DocumentStatus.FAILED, error=e.user_message
                )
                raise
            except Exception as e:
                user_msg = "Failed to save document. Please try again."
                await self._repository.update_document_status(
                    document_id, DocumentStatus.FAILED, error=user_msg
                )
                raise IngestionError(user_msg, detail=str(e)) from e
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py::test_ingest_pdf_end_to_end -v`
Expected: PASS

**Step 5: Write and run test for failure setting FAILED status**

Add to test file:

```python
@pytest.mark.asyncio
async def test_ingest_failure_sets_document_failed(
    pipeline: IngestionPipeline,
    mock_repository: AsyncMock,
) -> None:
    """Should set document status to FAILED when pipeline errors."""
    mock_repository.update_document_status.return_value = _make_mock_document(
        status=DocumentStatus.FAILED
    )

    with patch(
        "amelia.knowledge.ingestion.DocumentConverter"
    ) as mock_converter_cls:
        mock_converter_cls.return_value.convert.side_effect = RuntimeError("boom")

        with pytest.raises(IngestionError):
            await pipeline.ingest_document(
                document_id="doc-1",
                file_path=Path("/tmp/test.pdf"),
                content_type="application/pdf",
            )

    # Verify FAILED status was set
    calls = mock_repository.update_document_status.call_args_list
    final_call = calls[-1]
    assert final_call[0][1] == DocumentStatus.FAILED


@pytest.mark.asyncio
async def test_ingest_progress_callback(
    pipeline: IngestionPipeline,
    mock_repository: AsyncMock,
    mock_embedding_client: AsyncMock,
) -> None:
    """Should call progress callback for all stages."""
    mock_result = _make_conversion_result("Content")
    mock_chunks = [_make_doc_chunk("Chunk", ["H"])]
    mock_embedding_client.embed_batch.return_value = [[0.1] * 1536]
    mock_repository.update_document_status.return_value = _make_mock_document()

    stages_seen: list[str] = []

    def on_progress(stage: str, progress: float, done: int, total: int) -> None:
        if stage not in stages_seen:
            stages_seen.append(stage)

    with (
        patch(
            "amelia.knowledge.ingestion.DocumentConverter"
        ) as mock_converter_cls,
        patch(
            "amelia.knowledge.ingestion.HierarchicalChunker"
        ) as mock_chunker_cls,
    ):
        mock_converter_cls.return_value.convert.return_value = mock_result
        mock_chunker_cls.return_value.chunk.return_value = iter(mock_chunks)

        await pipeline.ingest_document(
            document_id="doc-1",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
            progress_callback=on_progress,
        )

    assert stages_seen == ["parsing", "chunking", "storing"]
```

Note: "embedding" stage won't appear in stages_seen because the embed_batch mock returns immediately without calling the inner progress callback. That's expected — the embed progress is tested via the _embed_progress bridge.

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py -v -q`
Expected: All pass.

**Step 6: Commit**

```bash
git add amelia/knowledge/ingestion.py tests/unit/knowledge/test_ingestion.py
git commit -m "feat(knowledge): wire up full ingest_document pipeline with error handling"
```

---

### Task 7: Implement concurrency semaphore test

**Files:**
- Modify: `tests/unit/knowledge/test_ingestion.py`

**Step 1: Write test for concurrency limiting**

```python
@pytest.mark.asyncio
async def test_concurrency_semaphore(
    mock_repository: AsyncMock,
    mock_embedding_client: AsyncMock,
) -> None:
    """Should limit concurrent ingestions via semaphore."""
    pipeline = IngestionPipeline(
        repository=mock_repository,
        embedding_client=mock_embedding_client,
        concurrency_limit=1,
    )

    mock_result = _make_conversion_result("Content")
    mock_chunks = [_make_doc_chunk("Chunk", ["H"])]
    mock_embedding_client.embed_batch.return_value = [[0.1] * 1536]
    mock_repository.update_document_status.return_value = _make_mock_document()

    # Track concurrent executions
    max_concurrent = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    original_parse = pipeline._parse

    async def slow_parse(*args: object, **kwargs: object) -> object:
        nonlocal max_concurrent, current_concurrent
        async with lock:
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
        await asyncio.sleep(0.05)
        result = await original_parse(*args, **kwargs)
        async with lock:
            current_concurrent -= 1
        return result

    with (
        patch.object(pipeline, "_parse", side_effect=slow_parse),
        patch(
            "amelia.knowledge.ingestion.HierarchicalChunker"
        ) as mock_chunker_cls,
    ):
        mock_chunker_cls.return_value.chunk.return_value = iter(mock_chunks)

        tasks = [
            pipeline.ingest_document(
                document_id=f"doc-{i}",
                file_path=Path("/tmp/test.pdf"),
                content_type="application/pdf",
            )
            for i in range(3)
        ]
        await asyncio.gather(*tasks)

    assert max_concurrent == 1
```

Add `import asyncio` to the top of the test file if not already there.

**Step 2: Run test**

Run: `uv run pytest tests/unit/knowledge/test_ingestion.py::test_concurrency_semaphore -v`
Expected: PASS (semaphore already implemented in Task 6)

**Step 3: Commit**

```bash
git add tests/unit/knowledge/test_ingestion.py
git commit -m "test(knowledge): add concurrency semaphore test for ingestion pipeline"
```

---

### Task 8: Implement KnowledgeService

**Files:**
- Create: `amelia/knowledge/service.py`
- Create: `tests/unit/knowledge/test_service.py`

**Step 1: Write failing test — started event**

Create `tests/unit/knowledge/test_service.py`:

```python
"""Test knowledge background ingestion service."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.knowledge.models import Document, DocumentStatus
from amelia.knowledge.service import KnowledgeService
from amelia.server.models.events import EventDomain, EventType


def _make_mock_document(**kwargs: object) -> Document:
    """Create a mock Document."""
    return Document(
        id=kwargs.get("id", "doc-1"),
        name="test.pdf",
        filename="test.pdf",
        content_type="application/pdf",
        tags=[],
        status=kwargs.get("status", DocumentStatus.READY),
        chunk_count=kwargs.get("chunk_count", 5),
        token_count=kwargs.get("token_count", 100),
    )


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Mock EventBus."""
    return MagicMock()


@pytest.fixture
def mock_pipeline() -> AsyncMock:
    """Mock IngestionPipeline."""
    pipeline = AsyncMock()
    pipeline.ingest_document.return_value = _make_mock_document()
    return pipeline


@pytest.fixture
def service(mock_event_bus: MagicMock, mock_pipeline: AsyncMock) -> KnowledgeService:
    """Create service with mocked dependencies."""
    return KnowledgeService(
        event_bus=mock_event_bus,
        ingestion_pipeline=mock_pipeline,
    )


@pytest.mark.asyncio
async def test_queue_ingestion_emits_started_event(
    service: KnowledgeService,
    mock_event_bus: MagicMock,
    mock_pipeline: AsyncMock,
) -> None:
    """Should emit DOCUMENT_INGESTION_STARTED when task begins."""
    service.queue_ingestion(
        document_id="doc-1",
        file_path=Path("/tmp/test.pdf"),
        content_type="application/pdf",
    )

    # Wait for background task to complete
    await service.cleanup()

    # Find STARTED event
    events = [
        call.args[0]
        for call in mock_event_bus.emit.call_args_list
    ]
    started_events = [
        e for e in events if e.event_type == EventType.DOCUMENT_INGESTION_STARTED
    ]
    assert len(started_events) == 1
    assert started_events[0].domain == EventDomain.KNOWLEDGE
    assert started_events[0].agent == "knowledge"
    assert started_events[0].data["document_id"] == "doc-1"
    assert started_events[0].data["status"] == "processing"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/knowledge/test_service.py::test_queue_ingestion_emits_started_event -v`
Expected: FAIL (ImportError)

**Step 3: Create service.py**

Create `amelia/knowledge/service.py`:

```python
"""Background ingestion service with event emission."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from loguru import logger

from amelia.knowledge.ingestion import IngestionError, IngestionPipeline
from amelia.server.events.bus import EventBus
from amelia.server.models.events import (
    EventDomain,
    EventLevel,
    EventType,
    WorkflowEvent,
)


class KnowledgeService:
    """Background service for document ingestion with event emission.

    Args:
        event_bus: EventBus for broadcasting progress events.
        ingestion_pipeline: Pipeline for document processing.
    """

    def __init__(
        self,
        event_bus: EventBus,
        ingestion_pipeline: IngestionPipeline,
    ) -> None:
        self._event_bus = event_bus
        self._pipeline = ingestion_pipeline
        self._tasks: set[asyncio.Task[None]] = set()

    def queue_ingestion(
        self,
        document_id: str,
        file_path: Path,
        content_type: str,
    ) -> None:
        """Queue a document for background ingestion.

        Args:
            document_id: Document UUID (must already exist in DB).
            file_path: Path to the uploaded file.
            content_type: MIME type of the file.
        """
        task = asyncio.create_task(
            self._ingest_with_events(document_id, file_path, content_type)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        logger.info(
            "Queued document ingestion",
            document_id=document_id,
            content_type=content_type,
        )

    async def cleanup(self) -> None:
        """Wait for all pending ingestion tasks to complete."""
        if self._tasks:
            logger.info("Waiting for ingestion tasks", count=len(self._tasks))
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _ingest_with_events(
        self,
        document_id: str,
        file_path: Path,
        content_type: str,
    ) -> None:
        """Run ingestion pipeline and emit lifecycle events."""
        self._emit_event(
            document_id=document_id,
            event_type=EventType.DOCUMENT_INGESTION_STARTED,
            message=f"Starting ingestion for document {document_id}",
            data={"document_id": document_id, "status": "processing"},
        )

        def on_progress(
            stage: str, progress: float, chunks_done: int, total_chunks: int
        ) -> None:
            self._emit_event(
                document_id=document_id,
                event_type=EventType.DOCUMENT_INGESTION_PROGRESS,
                message=f"Ingestion {stage}: {progress:.0%}",
                data={
                    "document_id": document_id,
                    "stage": stage,
                    "progress": progress,
                    "chunks_processed": chunks_done,
                    "total_chunks": total_chunks,
                },
            )

        try:
            doc = await self._pipeline.ingest_document(
                document_id=document_id,
                file_path=file_path,
                content_type=content_type,
                progress_callback=on_progress,
            )

            self._emit_event(
                document_id=document_id,
                event_type=EventType.DOCUMENT_INGESTION_COMPLETED,
                message=f"Ingestion complete: {doc.chunk_count} chunks, {doc.token_count} tokens",
                data={
                    "document_id": document_id,
                    "status": "ready",
                    "chunk_count": doc.chunk_count,
                    "token_count": doc.token_count,
                },
            )

        except (IngestionError, Exception) as e:
            error_msg = e.user_message if isinstance(e, IngestionError) else str(e)
            logger.error(
                "Document ingestion failed",
                document_id=document_id,
                error=error_msg,
            )
            self._emit_event(
                document_id=document_id,
                event_type=EventType.DOCUMENT_INGESTION_FAILED,
                message=f"Ingestion failed: {error_msg}",
                level=EventLevel.ERROR,
                data={
                    "document_id": document_id,
                    "status": "failed",
                    "error": error_msg,
                },
            )

    def _emit_event(
        self,
        document_id: str,
        event_type: EventType,
        message: str,
        data: dict[str, object],
        level: EventLevel | None = None,
    ) -> None:
        """Emit a knowledge event via EventBus."""
        event = WorkflowEvent(
            id=str(uuid4()),
            domain=EventDomain.KNOWLEDGE,
            workflow_id=document_id,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="knowledge",
            event_type=event_type,
            level=level,
            message=message,
            data=data,
        )
        self._event_bus.emit(event)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/knowledge/test_service.py::test_queue_ingestion_emits_started_event -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/knowledge/service.py tests/unit/knowledge/test_service.py
git commit -m "feat(knowledge): add KnowledgeService with background ingestion and started event"
```

---

### Task 9: Add remaining service tests

**Files:**
- Modify: `tests/unit/knowledge/test_service.py`

**Step 1: Write completed event test**

```python
@pytest.mark.asyncio
async def test_queue_ingestion_emits_completed_event(
    service: KnowledgeService,
    mock_event_bus: MagicMock,
    mock_pipeline: AsyncMock,
) -> None:
    """Should emit DOCUMENT_INGESTION_COMPLETED on success."""
    mock_pipeline.ingest_document.return_value = _make_mock_document(
        chunk_count=5, token_count=100
    )

    service.queue_ingestion(
        document_id="doc-1",
        file_path=Path("/tmp/test.pdf"),
        content_type="application/pdf",
    )
    await service.cleanup()

    events = [call.args[0] for call in mock_event_bus.emit.call_args_list]
    completed = [
        e for e in events if e.event_type == EventType.DOCUMENT_INGESTION_COMPLETED
    ]
    assert len(completed) == 1
    assert completed[0].data["status"] == "ready"
    assert completed[0].data["chunk_count"] == 5
    assert completed[0].data["token_count"] == 100
```

**Step 2: Write failed event test**

```python
@pytest.mark.asyncio
async def test_queue_ingestion_emits_failed_event(
    service: KnowledgeService,
    mock_event_bus: MagicMock,
    mock_pipeline: AsyncMock,
) -> None:
    """Should emit DOCUMENT_INGESTION_FAILED on pipeline error."""
    from amelia.knowledge.ingestion import IngestionError

    mock_pipeline.ingest_document.side_effect = IngestionError(
        "This PDF is password-protected. Please provide an unlocked version."
    )

    service.queue_ingestion(
        document_id="doc-1",
        file_path=Path("/tmp/test.pdf"),
        content_type="application/pdf",
    )
    await service.cleanup()

    events = [call.args[0] for call in mock_event_bus.emit.call_args_list]
    failed = [
        e for e in events if e.event_type == EventType.DOCUMENT_INGESTION_FAILED
    ]
    assert len(failed) == 1
    assert failed[0].data["status"] == "failed"
    assert "password-protected" in failed[0].data["error"]
    assert failed[0].level.value == "error"
```

**Step 3: Write task cleanup test**

```python
@pytest.mark.asyncio
async def test_task_auto_removed_on_completion(
    service: KnowledgeService,
    mock_pipeline: AsyncMock,
) -> None:
    """Should remove task from tracking set after completion."""
    service.queue_ingestion(
        document_id="doc-1",
        file_path=Path("/tmp/test.pdf"),
        content_type="application/pdf",
    )

    assert len(service._tasks) == 1
    await service.cleanup()
    assert len(service._tasks) == 0
```

**Step 4: Write progress event test**

```python
@pytest.mark.asyncio
async def test_queue_ingestion_emits_progress_events(
    service: KnowledgeService,
    mock_event_bus: MagicMock,
    mock_pipeline: AsyncMock,
) -> None:
    """Should emit progress events when pipeline reports progress."""
    progress_callbacks: list[object] = []

    async def capture_callback(**kwargs: object) -> Document:
        cb = kwargs.get("progress_callback")
        if cb:
            # Simulate pipeline calling progress
            cb("parsing", 0.0, 0, 0)
            cb("embedding", 0.5, 3, 10)
        return _make_mock_document()

    mock_pipeline.ingest_document.side_effect = capture_callback

    service.queue_ingestion(
        document_id="doc-1",
        file_path=Path("/tmp/test.pdf"),
        content_type="application/pdf",
    )
    await service.cleanup()

    events = [call.args[0] for call in mock_event_bus.emit.call_args_list]
    progress = [
        e for e in events if e.event_type == EventType.DOCUMENT_INGESTION_PROGRESS
    ]
    assert len(progress) == 2
    assert progress[0].data["stage"] == "parsing"
    assert progress[1].data["stage"] == "embedding"
```

**Step 5: Run all service tests**

Run: `uv run pytest tests/unit/knowledge/test_service.py -v`
Expected: All 5 tests pass.

**Step 6: Commit**

```bash
git add tests/unit/knowledge/test_service.py
git commit -m "test(knowledge): add service tests for completed, failed, progress events and cleanup"
```

---

### Task 10: Update __init__.py exports and run full suite

**Files:**
- Modify: `amelia/knowledge/__init__.py`

**Step 1: Update exports**

```python
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
```

**Step 2: Run full test suite**

Run: `uv run pytest -v -q`
Expected: All tests pass.

**Step 3: Run type checker**

Run: `uv run mypy amelia/knowledge/ingestion.py amelia/knowledge/service.py`
Expected: No errors.

**Step 4: Run linter**

Run: `uv run ruff check amelia/knowledge/ tests/unit/knowledge/`
Expected: No issues.

**Step 5: Commit**

```bash
git add amelia/knowledge/__init__.py
git commit -m "feat(knowledge): export IngestionPipeline, IngestionError, KnowledgeService"
```
