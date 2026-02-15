"""Test KnowledgeService event emission and task lifecycle."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.knowledge.embeddings import EmbeddingClient, EmbeddingError
from amelia.knowledge.ingestion import IngestionPipeline
from amelia.knowledge.models import Document, DocumentStatus
from amelia.knowledge.repository import KnowledgeRepository
from amelia.knowledge.service import KnowledgeService
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventDomain, EventType, WorkflowEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Provide a mocked EventBus."""
    bus = MagicMock(spec=EventBus)
    return bus


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
def service(
    mock_event_bus: MagicMock,
    mock_repo: AsyncMock,
    mock_embedding: AsyncMock,
) -> KnowledgeService:
    """Provide a KnowledgeService with real pipeline and mocked dependencies."""
    pipeline = IngestionPipeline(
        repository=mock_repo, embedding_client=mock_embedding,
    )
    return KnowledgeService(
        event_bus=mock_event_bus, ingestion_pipeline=pipeline,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_events(
    bus: MagicMock, event_type: EventType,
) -> list[WorkflowEvent]:
    """Extract emitted events of a given type from the mock EventBus."""
    return [
        call_args.args[0]
        for call_args in bus.emit.call_args_list
        if isinstance(call_args.args[0], WorkflowEvent)
        and call_args.args[0].event_type == event_type
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_ingestion_emits_started_event(
    service: KnowledgeService,
    mock_event_bus: MagicMock,
    mock_converter: MagicMock,
    mock_chunker: MagicMock,
) -> None:
    """Should emit DOCUMENT_INGESTION_STARTED when ingestion is queued."""
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
        service.queue_ingestion("doc-1", Path("/tmp/test.pdf"), "application/pdf")
        await asyncio.sleep(0.1)

    started = _find_events(mock_event_bus, EventType.DOCUMENT_INGESTION_STARTED)
    assert len(started) >= 1
    event = started[0]
    assert event.data is not None
    assert event.data["document_id"] == "doc-1"
    assert event.data["status"] == "processing"
    assert event.domain == EventDomain.KNOWLEDGE
    assert event.agent == "knowledge"
    assert event.workflow_id == "doc-1"


@pytest.mark.asyncio
async def test_queue_ingestion_emits_progress_events(
    service: KnowledgeService,
    mock_event_bus: MagicMock,
    mock_converter: MagicMock,
    mock_chunker: MagicMock,
) -> None:
    """Should emit DOCUMENT_INGESTION_PROGRESS events during pipeline stages."""
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
        service.queue_ingestion("doc-1", Path("/tmp/test.pdf"), "application/pdf")
        # Wait for task to complete naturally (don't cancel via cleanup)
        await asyncio.gather(*service._tasks, return_exceptions=True)

    progress = _find_events(mock_event_bus, EventType.DOCUMENT_INGESTION_PROGRESS)
    assert len(progress) >= 1

    event = progress[0]
    assert event.data is not None
    assert "stage" in event.data
    assert "progress" in event.data
    assert "chunks_processed" in event.data
    assert "total_chunks" in event.data


@pytest.mark.asyncio
async def test_queue_ingestion_emits_completed_event(
    service: KnowledgeService,
    mock_event_bus: MagicMock,
    mock_converter: MagicMock,
    mock_chunker: MagicMock,
) -> None:
    """Should emit DOCUMENT_INGESTION_COMPLETED on successful ingestion."""
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
        service.queue_ingestion("doc-1", Path("/tmp/test.pdf"), "application/pdf")
        await asyncio.gather(*service._tasks, return_exceptions=True)

    completed = _find_events(mock_event_bus, EventType.DOCUMENT_INGESTION_COMPLETED)
    assert len(completed) == 1
    event = completed[0]
    assert event.data is not None
    assert event.data["status"] == "ready"
    assert "chunk_count" in event.data
    assert "token_count" in event.data


@pytest.mark.asyncio
async def test_queue_ingestion_emits_failed_event(
    service: KnowledgeService,
    mock_event_bus: MagicMock,
    mock_embedding: AsyncMock,
    mock_converter: MagicMock,
    mock_chunker: MagicMock,
) -> None:
    """Should emit DOCUMENT_INGESTION_FAILED when pipeline raises an error."""
    mock_embedding.embed_batch.side_effect = EmbeddingError("fail")

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
        service.queue_ingestion("doc-1", Path("/tmp/test.pdf"), "application/pdf")
        await asyncio.gather(*service._tasks, return_exceptions=True)

    failed = _find_events(mock_event_bus, EventType.DOCUMENT_INGESTION_FAILED)
    assert len(failed) == 1
    event = failed[0]
    assert event.data is not None
    assert event.data["status"] == "failed"
    assert "error" in event.data


@pytest.mark.asyncio
async def test_cleanup_awaits_pending_tasks(
    service: KnowledgeService,
    mock_converter: MagicMock,
    mock_chunker: MagicMock,
) -> None:
    """Should cancel and await all pending tasks on cleanup."""
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
        service.queue_ingestion("doc-1", Path("/tmp/test.pdf"), "application/pdf")
        await service.cleanup()

    assert len(service._tasks) == 0


@pytest.mark.asyncio
async def test_task_auto_removed_on_completion(
    service: KnowledgeService,
    mock_converter: MagicMock,
    mock_chunker: MagicMock,
) -> None:
    """Should auto-remove task from tracked set when it completes."""
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
        service.queue_ingestion("doc-1", Path("/tmp/test.pdf"), "application/pdf")
        # Wait long enough for the task to complete and callback to fire
        await asyncio.sleep(0.5)

    assert len(service._tasks) == 0
