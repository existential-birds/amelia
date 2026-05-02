"""Test knowledge ingestion pipeline."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest
from loguru import logger

from amelia.knowledge.embeddings import EmbeddingClient, EmbeddingError
from amelia.knowledge.ingestion import IngestionError, IngestionPipeline
from amelia.knowledge.models import Document, DocumentStatus
from amelia.knowledge.repository import ChunkData, KnowledgeRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


# A long, realistic chunk body that comfortably exceeds the 64-token floor
# enforced by `MIN_CHUNK_TOKENS`. Tests use this so chunks are not silently
# dropped by the new tiny-chunk filter.
LONG_CHUNK_TEXT = (
    "Knowledge ingestion in Amelia parses uploaded documents, splits them into "
    "semantically coherent chunks, embeds each chunk for vector search, and "
    "stores the results alongside heading metadata. The hybrid chunker walks "
    "the Docling document tree, merges peer sections that fit within the "
    "embedding model's token budget, and contextualizes each chunk with the "
    "headings under which it appears. This guarantees that retrieval surfaces "
    "passages that retain enough surrounding context to be answerable on their "
    "own without forcing the agent to fetch additional sibling chunks first."
)


@pytest.fixture
def mock_repo() -> AsyncMock:
    """Provide a mocked KnowledgeRepository."""
    repo = AsyncMock(spec=KnowledgeRepository)
    repo.update_document_status.return_value = Document(
        id=uuid4(),
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


def _make_chunker_pair(
    *,
    chunks: list[MagicMock] | None = None,
    contextualize_side_effect: Callable[[MagicMock], str] | None = None,
    count_tokens_side_effect: Callable[[str], int] | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Build (chunker, tokenizer) mocks suitable for `_build_chunker` patching.

    Defaults produce a single chunk whose contextualized text is `LONG_CHUNK_TEXT`
    and whose token count is 100 — well above `MIN_CHUNK_TOKENS = 64`.
    """
    if chunks is None:
        mock_chunk = MagicMock()
        mock_chunk.text = LONG_CHUNK_TEXT
        mock_chunk.meta.headings = ["Heading 1"]
        chunks = [mock_chunk]

    chunker = MagicMock()
    chunker.chunk.return_value = chunks

    if contextualize_side_effect is None:
        chunker.contextualize.side_effect = lambda chunk: chunk.text
    else:
        chunker.contextualize.side_effect = contextualize_side_effect

    tokenizer = MagicMock()
    if count_tokens_side_effect is None:
        tokenizer.count_tokens.return_value = 100
    else:
        tokenizer.count_tokens.side_effect = count_tokens_side_effect

    return chunker, tokenizer


@pytest.fixture
def mock_chunker_pair() -> tuple[MagicMock, MagicMock]:
    """Provide a default (chunker, tokenizer) tuple for `_build_chunker` patching."""
    return _make_chunker_pair()


@pytest.fixture
def pipeline(mock_repo: AsyncMock, mock_embedding: AsyncMock) -> IngestionPipeline:
    """Provide an IngestionPipeline with mocked dependencies."""
    return IngestionPipeline(
        repository=mock_repo,
        embedding_client=mock_embedding,
        concurrency_limit=2,
        tag_derivation_model=None,
        tag_derivation_driver="api",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_initialization_stores_tag_config(
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
) -> None:
    """Should store tag derivation configuration parameters as instance variables."""
    pipeline_enabled = IngestionPipeline(
        repository=mock_repo,
        embedding_client=mock_embedding,
        concurrency_limit=3,
        tag_derivation_model="openai/gpt-4o-mini",
        tag_derivation_driver="claude",
    )
    assert pipeline_enabled.tag_derivation_model == "openai/gpt-4o-mini"
    assert pipeline_enabled.tag_derivation_driver == "claude"

    pipeline_disabled = IngestionPipeline(
        repository=mock_repo,
        embedding_client=mock_embedding,
        concurrency_limit=2,
        tag_derivation_model=None,
        tag_derivation_driver="api",
    )
    assert pipeline_disabled.tag_derivation_model is None
    assert pipeline_disabled.tag_derivation_driver == "api"

    pipeline_defaults = IngestionPipeline(
        repository=mock_repo,
        embedding_client=mock_embedding,
    )
    assert pipeline_defaults.tag_derivation_model is None
    assert pipeline_defaults.tag_derivation_driver == "api"


@pytest.mark.asyncio
async def test_ingest_pdf_document(
    pipeline: IngestionPipeline,
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
    mock_chunker_pair: tuple[MagicMock, MagicMock],
) -> None:
    """Should ingest PDF: parse, chunk, embed, store, and update status."""
    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch.object(
            IngestionPipeline,
            "_build_chunker",
            return_value=mock_chunker_pair,
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
    assert chunks[0]["content"] == LONG_CHUNK_TEXT
    assert chunks[0]["heading_path"] == ["Heading 1"]
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["embedding"] == [0.1] * 1536
    # Token count comes from the real tokenizer's count_tokens, not len/4.
    assert chunks[0]["token_count"] == 100

    # Returns a Document
    assert isinstance(result, Document)


@pytest.mark.asyncio
async def test_ingest_markdown_document(
    pipeline: IngestionPipeline,
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
    mock_chunker_pair: tuple[MagicMock, MagicMock],
) -> None:
    """Should ingest markdown documents the same as PDF."""
    mock_repo.update_document_status.return_value = Document(
        id=uuid4(),
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
        patch.object(
            IngestionPipeline,
            "_build_chunker",
            return_value=mock_chunker_pair,
        ),
    ):
        result = await pipeline.ingest_document(
            document_id="doc-2",
            file_path=Path("/tmp/readme.md"),
            content_type="text/markdown",
        )

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
        pytest.raises(IngestionError),
    ):
        await pipeline.ingest_document(
            document_id="doc-5",
            file_path=Path("/tmp/corrupt.pdf"),
            content_type="application/pdf",
        )

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
    mock_chunker_pair: tuple[MagicMock, MagicMock],
) -> None:
    """Should set document status to FAILED when embedding raises EmbeddingError."""
    mock_embedding.embed_batch.side_effect = EmbeddingError("Rate limit exceeded")

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch.object(
            IngestionPipeline,
            "_build_chunker",
            return_value=mock_chunker_pair,
        ),
        pytest.raises(IngestionError),
    ):
        await pipeline.ingest_document(
            document_id="doc-6",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
        )

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
    mock_chunker_pair: tuple[MagicMock, MagicMock],
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
        patch.object(
            IngestionPipeline,
            "_build_chunker",
            return_value=mock_chunker_pair,
        ),
    ):
        await pipeline.ingest_document(
            document_id="doc-7",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
            progress_callback=progress_callback,
        )

    stages_seen = [c[0] for c in progress_calls]
    assert "parsing" in stages_seen
    assert "chunking" in stages_seen
    assert "embedding" in stages_seen
    assert "storing" in stages_seen

    progress_values = [c[1] for c in progress_calls]
    for i in range(1, len(progress_values)):
        assert progress_values[i] >= progress_values[i - 1], (
            f"Progress should be non-decreasing: {progress_values}"
        )

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
            id=uuid4(),
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

    chunker_pair = _make_chunker_pair()

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch.object(
            IngestionPipeline,
            "_build_chunker",
            return_value=chunker_pair,
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


# ---------------------------------------------------------------------------
# New chunker contract: contextualize + min-token filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drops_chunks_below_min_tokens(
    pipeline: IngestionPipeline,
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
) -> None:
    """Tiny chunks (<MIN_CHUNK_TOKENS) are filtered out before embedding."""
    big_chunk = MagicMock()
    big_chunk.text = LONG_CHUNK_TEXT
    big_chunk.meta.headings = ["Big Section"]

    tiny_chunk = MagicMock()
    tiny_chunk.text = "Tiny."
    tiny_chunk.meta.headings = ["Tiny Section"]

    chunker = MagicMock()
    chunker.chunk.return_value = [big_chunk, tiny_chunk]
    chunker.contextualize.side_effect = lambda chunk: chunk.text

    tokenizer = MagicMock()

    def count_tokens(text: str) -> int:
        return 30 if text == "Tiny." else 100

    tokenizer.count_tokens.side_effect = count_tokens

    # Adjust embed_batch to return one embedding (only the big chunk survives)
    mock_embedding.embed_batch.return_value = [[0.1] * 1536]

    captured_logs: list[str] = []
    sink_id = logger.add(
        lambda msg: captured_logs.append(msg.record["message"]),
        level="WARNING",
    )

    try:
        with (
            patch(
                "docling.document_converter.DocumentConverter",
                return_value=mock_converter,
            ),
            patch.object(
                IngestionPipeline,
                "_build_chunker",
                return_value=(chunker, tokenizer),
            ),
        ):
            await pipeline.ingest_document(
                document_id="doc-tiny",
                file_path=Path("/tmp/test.pdf"),
                content_type="application/pdf",
            )
    finally:
        logger.remove(sink_id)

    # Only the big chunk's text was embedded; tiny chunk was dropped.
    mock_embedding.embed_batch.assert_called_once()
    embed_args = mock_embedding.embed_batch.call_args
    embedded_texts = embed_args.args[0]
    assert embedded_texts == [LONG_CHUNK_TEXT]
    assert "Tiny." not in embedded_texts

    # Repository received a single chunk (the big one).
    mock_repo.insert_chunks.assert_called_once()
    inserted = mock_repo.insert_chunks.call_args.args[1]
    assert len(inserted) == 1
    assert inserted[0]["content"] == LONG_CHUNK_TEXT

    # A warning was logged about the dropped chunk.
    assert any("dropped tiny chunks" in line for line in captured_logs), (
        f"Expected 'dropped tiny chunks' warning, captured: {captured_logs}"
    )


@pytest.mark.asyncio
async def test_embeds_contextualized_text(
    pipeline: IngestionPipeline,
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
) -> None:
    """Embedding input is `chunker.contextualize(...)` output, not raw chunk.text."""
    chunk = MagicMock()
    chunk.text = LONG_CHUNK_TEXT
    chunk.meta.headings = ["Heading 1"]

    contextualized = f"# Heading 1\n{LONG_CHUNK_TEXT}"

    chunker = MagicMock()
    chunker.chunk.return_value = [chunk]
    chunker.contextualize.side_effect = lambda chunk: contextualized

    tokenizer = MagicMock()
    tokenizer.count_tokens.return_value = 120

    mock_embedding.embed_batch.return_value = [[0.1] * 1536]

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch.object(
            IngestionPipeline,
            "_build_chunker",
            return_value=(chunker, tokenizer),
        ),
    ):
        await pipeline.ingest_document(
            document_id="doc-ctx",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
        )

    # embed_batch must have been called with the heading-prepended text,
    # NOT the raw chunk.text.
    mock_embedding.embed_batch.assert_called_once()
    embedded_texts = mock_embedding.embed_batch.call_args.args[0]
    assert embedded_texts == [contextualized]
    assert chunk.text not in embedded_texts  # Raw chunk text was not embedded.

    # The stored chunk content is also the contextualized text.
    inserted = mock_repo.insert_chunks.call_args.args[1]
    assert inserted[0]["content"] == contextualized
    assert inserted[0]["token_count"] == 120


# ---------------------------------------------------------------------------
# Tag Extraction Helper Tests
# ---------------------------------------------------------------------------


def test_prepare_tag_extraction_input_truncates_long_text(
    pipeline: IngestionPipeline,
) -> None:
    """Should truncate text to MAX_RAW_TEXT_FOR_TAGS (8000 chars) and add note."""
    long_text = "a" * 10000
    chunks: list[ChunkData] = [
        ChunkData(
            chunk_index=0,
            content="chunk1",
            heading_path=["Heading 1"],
            token_count=10,
            embedding=[0.1] * 1536,
        )
    ]

    excerpt, headings = pipeline._prepare_tag_extraction_input(
        raw_text=long_text,
        chunk_data=chunks,
        document_name="test.pdf",
    )

    assert len(excerpt) > 8000
    assert excerpt[:8000] == "a" * 8000
    assert "[... content truncated for tag extraction ...]" in excerpt
    assert headings == [["Heading 1"]]


def test_prepare_tag_extraction_input_extracts_unique_headings(
    pipeline: IngestionPipeline,
) -> None:
    """Should extract unique heading paths and deduplicate them."""
    raw_text = "Short document"
    chunks: list[ChunkData] = [
        ChunkData(
            chunk_index=0,
            content="chunk1",
            heading_path=["Heading 1"],
            token_count=10,
            embedding=[0.1] * 1536,
        ),
        ChunkData(
            chunk_index=1,
            content="chunk2",
            heading_path=["Heading 1"],  # Duplicate
            token_count=10,
            embedding=[0.1] * 1536,
        ),
        ChunkData(
            chunk_index=2,
            content="chunk3",
            heading_path=["Heading 2", "Subheading"],
            token_count=10,
            embedding=[0.1] * 1536,
        ),
        ChunkData(
            chunk_index=3,
            content="chunk4",
            heading_path=[],  # Empty heading path
            token_count=10,
            embedding=[0.1] * 1536,
        ),
    ]

    excerpt, headings = pipeline._prepare_tag_extraction_input(
        raw_text=raw_text,
        chunk_data=chunks,
        document_name="test.pdf",
    )

    assert len(headings) == 2
    assert ["Heading 1"] in headings
    assert ["Heading 2", "Subheading"] in headings
    assert excerpt == raw_text


def test_validate_tags_deduplicates_and_cleans(
    pipeline: IngestionPipeline,
) -> None:
    """Should clean tags: lowercase, strip, deduplicate, filter empty and long."""
    raw_tags = [
        "Python",
        "  Django  ",
        "PYTHON",
        "kubernetes",
        "",
        "   ",
        "a" * 60,
        "React",
        "react",
    ]

    cleaned = pipeline._validate_tags(raw_tags)

    assert cleaned == ["python", "django", "kubernetes", "react"]
    assert len(cleaned) == 4


def test_build_tag_extraction_prompt(
    pipeline: IngestionPipeline,
) -> None:
    """Should build prompt with document name, heading tree, and content."""
    raw_text_excerpt = "This is sample content from the document."
    heading_paths = [
        ["Introduction"],
        ["Chapter 1", "Section 1.1"],
        ["Chapter 1", "Section 1.2"],
    ]
    document_name = "technical_guide.pdf"

    prompt = pipeline._build_tag_extraction_prompt(
        raw_text_excerpt=raw_text_excerpt,
        heading_paths=heading_paths,
        document_name=document_name,
    )

    assert document_name in prompt
    assert "- Introduction" in prompt
    assert "  - Section 1.1" in prompt
    assert "  - Section 1.2" in prompt
    assert raw_text_excerpt in prompt
    assert "5-10 relevant tags" in prompt
    assert "lowercase" in prompt


# ---------------------------------------------------------------------------
# Tag Derivation Method Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_derive_tags_success(
    pipeline: IngestionPipeline,
) -> None:
    """Should derive tags using LLM extraction and return validated tags."""
    from amelia.knowledge.models import TagExtractionOutput

    raw_text = "This is a Python Django tutorial document."
    chunk_data: list[ChunkData] = [
        ChunkData(
            chunk_index=0,
            content="chunk1",
            heading_path=["Introduction"],
            token_count=10,
            embedding=[0.1] * 1536,
        )
    ]
    document_name = "django_tutorial.pdf"
    model = "openai/gpt-4o-mini"
    driver_type = "api"

    mock_output = TagExtractionOutput(
        tags=["Python", "  Django  ", "PYTHON", "web-framework", "tutorial"],
        reasoning="Document focuses on Django web framework tutorial using Python",
    )

    with patch("amelia.core.extraction.extract_structured") as mock_extract:
        mock_extract.return_value = mock_output

        result = await pipeline._derive_tags(
            document_name=document_name,
            raw_text=raw_text,
            chunk_data=chunk_data,
            model=model,
            driver_type=driver_type,
        )

    assert result == ["python", "django", "web-framework", "tutorial"]

    mock_extract.assert_called_once()
    call_kwargs = mock_extract.call_args.kwargs
    assert call_kwargs["model"] == model
    assert call_kwargs["driver_type"] == driver_type
    assert call_kwargs["schema"] == TagExtractionOutput
    assert document_name in call_kwargs["prompt"]


@pytest.mark.asyncio
async def test_derive_tags_handles_llm_failure(
    pipeline: IngestionPipeline,
) -> None:
    """Should return empty list when LLM extraction fails."""
    raw_text = "Sample document text"
    chunk_data: list[ChunkData] = [
        ChunkData(
            chunk_index=0,
            content="chunk1",
            heading_path=["Heading 1"],
            token_count=10,
            embedding=[0.1] * 1536,
        )
    ]
    document_name = "test.pdf"
    model = "openai/gpt-4o-mini"
    driver_type = "api"

    with patch("amelia.core.extraction.extract_structured") as mock_extract:
        mock_extract.side_effect = RuntimeError("LLM API unavailable")

        result = await pipeline._derive_tags(
            document_name=document_name,
            raw_text=raw_text,
            chunk_data=chunk_data,
            model=model,
            driver_type=driver_type,
        )

    assert result == []
    mock_extract.assert_called_once()


# ---------------------------------------------------------------------------
# Tag Derivation Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_with_tag_derivation_enabled(
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
    mock_chunker_pair: tuple[MagicMock, MagicMock],
) -> None:
    """Should derive tags and update document when tag derivation is enabled."""
    from amelia.knowledge.models import TagExtractionOutput

    pipeline = IngestionPipeline(
        repository=mock_repo,
        embedding_client=mock_embedding,
        concurrency_limit=2,
        tag_derivation_model="openai/gpt-4o-mini",
        tag_derivation_driver="api",
    )

    mock_output = TagExtractionOutput(
        tags=["python", "django", "tutorial"],
        reasoning="Document is a Python Django tutorial",
    )

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch.object(
            IngestionPipeline,
            "_build_chunker",
            return_value=mock_chunker_pair,
        ),
        patch("amelia.core.extraction.extract_structured") as mock_extract,
    ):
        mock_extract.return_value = mock_output

        result = await pipeline.ingest_document(
            document_id="doc-1",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
        )

    mock_extract.assert_called_once()
    mock_repo.update_document_tags.assert_called_once_with(
        "doc-1", ["python", "django", "tutorial"]
    )
    assert isinstance(result, Document)
    assert result.status == DocumentStatus.READY


@pytest.mark.asyncio
async def test_ingest_with_tag_derivation_disabled(
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
    mock_chunker_pair: tuple[MagicMock, MagicMock],
) -> None:
    """Should skip tag derivation when tag_derivation_model is None."""
    pipeline = IngestionPipeline(
        repository=mock_repo,
        embedding_client=mock_embedding,
        concurrency_limit=2,
        tag_derivation_model=None,
        tag_derivation_driver="api",
    )

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch.object(
            IngestionPipeline,
            "_build_chunker",
            return_value=mock_chunker_pair,
        ),
        patch("amelia.core.extraction.extract_structured") as mock_extract,
    ):
        result = await pipeline.ingest_document(
            document_id="doc-1",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
        )

    mock_extract.assert_not_called()
    mock_repo.update_document_tags.assert_not_called()
    assert isinstance(result, Document)
    assert result.status == DocumentStatus.READY


@pytest.mark.asyncio
async def test_progress_callback_includes_tag_derivation(
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
    mock_chunker_pair: tuple[MagicMock, MagicMock],
) -> None:
    """Should include deriving_tags stage in progress callbacks when enabled."""
    from amelia.knowledge.models import TagExtractionOutput

    pipeline = IngestionPipeline(
        repository=mock_repo,
        embedding_client=mock_embedding,
        concurrency_limit=2,
        tag_derivation_model="openai/gpt-4o-mini",
        tag_derivation_driver="api",
    )

    progress_calls: list[tuple[str, float, int, int]] = []

    def progress_callback(
        stage: str, progress: float, chunks_processed: int, total_chunks: int
    ) -> None:
        progress_calls.append((stage, progress, chunks_processed, total_chunks))

    mock_output = TagExtractionOutput(
        tags=["python", "django", "tutorial"],
        reasoning="Python Django tutorial document",
    )

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch.object(
            IngestionPipeline,
            "_build_chunker",
            return_value=mock_chunker_pair,
        ),
        patch("amelia.core.extraction.extract_structured") as mock_extract,
    ):
        mock_extract.return_value = mock_output

        await pipeline.ingest_document(
            document_id="doc-1",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
            progress_callback=progress_callback,
        )

    stages_seen = [c[0] for c in progress_calls]
    assert "parsing" in stages_seen
    assert "chunking" in stages_seen
    assert "embedding" in stages_seen
    assert "deriving_tags" in stages_seen
    assert "storing" in stages_seen

    progress_values = [c[1] for c in progress_calls]
    for i in range(1, len(progress_values)):
        assert progress_values[i] >= progress_values[i - 1], (
            f"Progress should be non-decreasing: {progress_values}"
        )

    assert progress_values[-1] == pytest.approx(1.0)

    deriving_tags_indices = [
        i for i, (stage, _, _, _) in enumerate(progress_calls) if stage == "deriving_tags"
    ]
    storing_indices = [
        i for i, (stage, _, _, _) in enumerate(progress_calls) if stage == "storing"
    ]
    assert any(dt < s for dt in deriving_tags_indices for s in storing_indices)


@pytest.mark.asyncio
async def test_ingest_continues_when_tag_update_fails(
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
    mock_chunker_pair: tuple[MagicMock, MagicMock],
) -> None:
    """Should continue pipeline when update_document_tags fails (non-blocking error)."""
    from amelia.knowledge.models import TagExtractionOutput

    pipeline = IngestionPipeline(
        repository=mock_repo,
        embedding_client=mock_embedding,
        concurrency_limit=2,
        tag_derivation_model="openai/gpt-4o-mini",
        tag_derivation_driver="api",
    )

    mock_repo.update_document_tags.side_effect = RuntimeError("Database connection lost")

    mock_output = TagExtractionOutput(
        tags=["python", "django", "tutorial"],
        reasoning="Document is a Python Django tutorial",
    )

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch.object(
            IngestionPipeline,
            "_build_chunker",
            return_value=mock_chunker_pair,
        ),
        patch("amelia.core.extraction.extract_structured") as mock_extract,
    ):
        mock_extract.return_value = mock_output

        result = await pipeline.ingest_document(
            document_id="doc-1",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
        )

    mock_repo.update_document_tags.assert_called_once_with(
        "doc-1", ["python", "django", "tutorial"]
    )
    assert isinstance(result, Document)
    assert result.status == DocumentStatus.READY


@pytest.mark.asyncio
async def test_ingest_skips_tag_update_when_no_tags_derived(
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
    mock_chunker_pair: tuple[MagicMock, MagicMock],
) -> None:
    """Should skip update_document_tags call when no tags are derived."""
    from amelia.knowledge.models import TagExtractionOutput

    pipeline = IngestionPipeline(
        repository=mock_repo,
        embedding_client=mock_embedding,
        concurrency_limit=2,
        tag_derivation_model="openai/gpt-4o-mini",
        tag_derivation_driver="api",
    )

    mock_output = TagExtractionOutput(
        tags=["", "  ", "a" * 60],
        reasoning="Could not identify clear tags",
    )

    with (
        patch(
            "docling.document_converter.DocumentConverter",
            return_value=mock_converter,
        ),
        patch.object(
            IngestionPipeline,
            "_build_chunker",
            return_value=mock_chunker_pair,
        ),
        patch("amelia.core.extraction.extract_structured") as mock_extract,
    ):
        mock_extract.return_value = mock_output

        result = await pipeline.ingest_document(
            document_id="doc-1",
            file_path=Path("/tmp/test.pdf"),
            content_type="application/pdf",
        )

    mock_repo.update_document_tags.assert_not_called()
    assert isinstance(result, Document)
    assert result.status == DocumentStatus.READY
