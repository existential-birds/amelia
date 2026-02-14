"""Test knowledge ingestion pipeline."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from amelia.knowledge.embeddings import EmbeddingClient, EmbeddingError
from amelia.knowledge.ingestion import IngestionError, IngestionPipeline
from amelia.knowledge.models import Document, DocumentStatus
from amelia.knowledge.repository import ChunkData, KnowledgeRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_repo() -> AsyncMock:
    """Provide a mocked KnowledgeRepository."""
    repo = AsyncMock(spec=KnowledgeRepository)
    repo.update_document_status.return_value = Document(
        id="doc-1",
        name="test.pdf",
        filename="test.pdf",
        content_type="application/pdf",
        status=DocumentStatus.READY,
        chunk_count=1,
        token_count=10,
    )
    repo.insert_chunks = AsyncMock()
    return repo


@pytest.fixture
def mock_embedding() -> AsyncMock:
    """Provide a mocked EmbeddingClient."""
    client = AsyncMock(spec=EmbeddingClient)
    client.embed_batch.return_value = [[0.1] * 1536]
    return client


@pytest.fixture
def mock_converter() -> MagicMock:
    """Provide a mocked Docling DocumentConverter."""
    converter = MagicMock()
    mock_result = MagicMock()
    mock_result.document.export_to_text.return_value = "Sample text content"
    converter.convert.return_value = mock_result
    return converter


@pytest.fixture
def mock_chunker() -> MagicMock:
    """Provide a mocked Docling HierarchicalChunker."""
    chunker = MagicMock()
    mock_chunk = MagicMock()
    mock_chunk.text = "Chunk text"
    mock_chunk.meta.headings = ["Heading 1"]
    chunker.chunk.return_value = [mock_chunk]
    return chunker


@pytest.fixture
def pipeline(mock_repo: AsyncMock, mock_embedding: AsyncMock) -> IngestionPipeline:
    """Provide an IngestionPipeline with mocked dependencies."""
    return IngestionPipeline(repository=mock_repo, embedding_client=mock_embedding)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_pdf_document(
    pipeline: IngestionPipeline,
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
    mock_chunker: MagicMock,
) -> None:
    """Should ingest PDF: parse, chunk, embed, store, and update status."""
    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch(
            "docling.chunking.HierarchicalChunker",
            return_value=mock_chunker,
        ),
    ):
        result = await pipeline.ingest_document(
            document_id="doc-1",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
        )

    # Status transitions: PROCESSING first, then READY on success
    status_calls = mock_repo.update_document_status.call_args_list
    assert len(status_calls) >= 2
    assert status_calls[0] == call(
        "doc-1", DocumentStatus.PROCESSING,
    )
    last_call = status_calls[-1]
    assert last_call.args[0] == "doc-1"
    assert last_call.args[1] == DocumentStatus.READY

    # Chunks inserted with correct structure
    mock_repo.insert_chunks.assert_called_once()
    insert_args = mock_repo.insert_chunks.call_args
    assert insert_args.args[0] == "doc-1"
    chunks: list[ChunkData] = insert_args.args[1]
    assert len(chunks) == 1
    assert chunks[0]["content"] == "Chunk text"
    assert chunks[0]["heading_path"] == ["Heading 1"]
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["embedding"] == [0.1] * 1536

    # Returns a Document
    assert isinstance(result, Document)


@pytest.mark.asyncio
async def test_ingest_markdown_document(
    pipeline: IngestionPipeline,
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
    mock_chunker: MagicMock,
) -> None:
    """Should ingest markdown documents the same as PDF."""
    mock_repo.update_document_status.return_value = Document(
        id="doc-2",
        name="readme.md",
        filename="readme.md",
        content_type="text/markdown",
        status=DocumentStatus.READY,
        chunk_count=1,
        token_count=10,
    )

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch(
            "docling.chunking.HierarchicalChunker",
            return_value=mock_chunker,
        ),
    ):
        result = await pipeline.ingest_document(
            document_id="doc-2",
            file_path=Path("/tmp/readme.md"),
            content_type="text/markdown",
        )

    # Verify status transitions for markdown
    status_calls = mock_repo.update_document_status.call_args_list
    assert len(status_calls) >= 2
    assert status_calls[0] == call(
        "doc-2", DocumentStatus.PROCESSING,
    )
    last_call = status_calls[-1]
    assert last_call.args[1] == DocumentStatus.READY

    mock_repo.insert_chunks.assert_called_once()
    assert isinstance(result, Document)


@pytest.mark.asyncio
async def test_parse_unsupported_content_type(
    pipeline: IngestionPipeline,
) -> None:
    """Should raise IngestionError for unsupported content types."""
    with pytest.raises(IngestionError) as exc_info:
        await pipeline.ingest_document(
            document_id="doc-3",
            file_path=Path("/tmp/archive.zip"),
            content_type="application/zip",
        )

    assert "Unsupported file type" in exc_info.value.user_message


@pytest.mark.asyncio
async def test_parse_empty_document(
    pipeline: IngestionPipeline,
    mock_repo: AsyncMock,
) -> None:
    """Should raise IngestionError when document has no text content."""
    mock_converter = MagicMock()
    mock_result = MagicMock()
    mock_result.document.export_to_text.return_value = ""
    mock_converter.convert.return_value = mock_result

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch(
            "docling.chunking.HierarchicalChunker",
        ),
        pytest.raises(IngestionError) as exc_info,
    ):
        await pipeline.ingest_document(
            document_id="doc-4",
            file_path=Path("/tmp/empty.pdf"),
            content_type="application/pdf",
        )

    assert "No text content found" in exc_info.value.user_message


@pytest.mark.asyncio
async def test_parse_failure_sets_document_failed(
    pipeline: IngestionPipeline,
    mock_repo: AsyncMock,
) -> None:
    """Should set document status to FAILED when parsing raises an exception."""
    mock_converter = MagicMock()
    mock_converter.convert.side_effect = RuntimeError("PDF parse error")

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch(
            "docling.chunking.HierarchicalChunker",
        ),
        pytest.raises(IngestionError),
    ):
        await pipeline.ingest_document(
            document_id="doc-5",
            file_path=Path("/tmp/corrupt.pdf"),
            content_type="application/pdf",
        )

    # Verify document marked as FAILED with error message
    failed_call = mock_repo.update_document_status.call_args_list[-1]
    assert failed_call.args[0] == "doc-5"
    assert failed_call.args[1] == DocumentStatus.FAILED
    assert failed_call.kwargs.get("error") or (
        len(failed_call.args) > 2 and failed_call.args[2]
    )


@pytest.mark.asyncio
async def test_embed_failure_sets_document_failed(
    pipeline: IngestionPipeline,
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
    mock_chunker: MagicMock,
) -> None:
    """Should set document status to FAILED when embedding raises EmbeddingError."""
    mock_embedding.embed_batch.side_effect = EmbeddingError("Rate limit exceeded")

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch(
            "docling.chunking.HierarchicalChunker",
            return_value=mock_chunker,
        ),
        pytest.raises(IngestionError),
    ):
        await pipeline.ingest_document(
            document_id="doc-6",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
        )

    # Verify document marked as FAILED
    failed_call = mock_repo.update_document_status.call_args_list[-1]
    assert failed_call.args[0] == "doc-6"
    assert failed_call.args[1] == DocumentStatus.FAILED
    assert failed_call.kwargs.get("error") or (
        len(failed_call.args) > 2 and failed_call.args[2]
    )


@pytest.mark.asyncio
async def test_progress_callback_called(
    pipeline: IngestionPipeline,
    mock_converter: MagicMock,
    mock_chunker: MagicMock,
) -> None:
    """Should call progress callback for all 4 stages with increasing progress."""
    progress_calls: list[tuple[str, float, int, int]] = []

    def progress_callback(
        stage: str, progress: float, chunks_processed: int, total_chunks: int
    ) -> None:
        progress_calls.append((stage, progress, chunks_processed, total_chunks))

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch(
            "docling.chunking.HierarchicalChunker",
            return_value=mock_chunker,
        ),
    ):
        await pipeline.ingest_document(
            document_id="doc-7",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
            progress_callback=progress_callback,
        )

    # All 4 stages should appear
    stages_seen = [c[0] for c in progress_calls]
    assert "parsing" in stages_seen
    assert "chunking" in stages_seen
    assert "embedding" in stages_seen
    assert "storing" in stages_seen

    # Progress values should be monotonically non-decreasing
    progress_values = [c[1] for c in progress_calls]
    for i in range(1, len(progress_values)):
        assert progress_values[i] >= progress_values[i - 1], (
            f"Progress should be non-decreasing: {progress_values}"
        )

    # Final progress should be 1.0
    assert progress_values[-1] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_concurrency_semaphore(
    mock_embedding: AsyncMock,
) -> None:
    """Should limit concurrent ingestions to concurrency_limit (2)."""
    max_concurrent = 0
    current_concurrent = 0
    barrier = asyncio.Event()
    release = asyncio.Event()

    mock_repo = AsyncMock(spec=KnowledgeRepository)

    async def slow_status_update(
        *args: object, **kwargs: object
    ) -> Document:
        nonlocal max_concurrent, current_concurrent
        # Only block on the PROCESSING call (first per ingestion)
        if len(args) >= 2 and args[1] == DocumentStatus.PROCESSING:
            current_concurrent += 1
            if current_concurrent > max_concurrent:
                max_concurrent = current_concurrent
            if current_concurrent >= 2:
                barrier.set()
            await release.wait()
            current_concurrent -= 1
        return Document(
            id=str(args[0]) if args else "doc-x",
            name="test.pdf",
            filename="test.pdf",
            content_type="application/pdf",
            status=DocumentStatus.READY,
            chunk_count=1,
            token_count=10,
        )

    mock_repo.update_document_status.side_effect = slow_status_update
    mock_repo.insert_chunks = AsyncMock()

    pipeline = IngestionPipeline(
        repository=mock_repo,
        embedding_client=mock_embedding,
        concurrency_limit=2,
    )

    mock_converter = MagicMock()
    mock_result = MagicMock()
    mock_result.document.export_to_text.return_value = "Sample text"
    mock_converter.convert.return_value = mock_result

    mock_chunker = MagicMock()
    mock_chunk = MagicMock()
    mock_chunk.text = "Chunk"
    mock_chunk.meta.headings = ["H1"]
    mock_chunker.chunk.return_value = [mock_chunk]

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch(
            "docling.chunking.HierarchicalChunker",
            return_value=mock_chunker,
        ),
    ):
        tasks = [
            asyncio.create_task(
                pipeline.ingest_document(
                    document_id=f"doc-{i}",
                    file_path=Path(f"/tmp/test{i}.pdf"),
                    content_type="application/pdf",
                )
            )
            for i in range(3)
        ]

        await asyncio.wait_for(barrier.wait(), timeout=5.0)
        await asyncio.sleep(0.05)

        snapshot = max_concurrent

        release.set()
        await asyncio.gather(*tasks)

    assert snapshot <= 2, f"Expected at most 2 concurrent, got {snapshot}"
