"""Background service for knowledge ingestion with event emission."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from loguru import logger

from amelia.knowledge.ingestion import IngestionError, IngestionPipeline
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventDomain, EventType, WorkflowEvent


class KnowledgeService:
    """Background ingestion service with event emission.

    Args:
        event_bus: Event bus for broadcasting ingestion events.
        ingestion_pipeline: Pipeline for parsing, chunking, and embedding.
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
            document_id: UUID of the document record.
            file_path: Path to the uploaded file.
            content_type: MIME type of the file.
        """
        task = asyncio.create_task(
            self._ingest_with_events(document_id, file_path, content_type)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def cleanup(self) -> None:
        """Cancel and await all pending ingestion tasks."""
        if not self._tasks:
            return

        logger.info("Cleaning up knowledge service", pending_tasks=len(self._tasks))
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _ingest_with_events(
        self,
        document_id: str,
        file_path: Path,
        content_type: str,
    ) -> None:
        """Run ingestion pipeline with event emission.

        Args:
            document_id: UUID of the document record.
            file_path: Path to the uploaded file.
            content_type: MIME type of the file.
        """
        self._emit_event(
            document_id=document_id,
            event_type=EventType.DOCUMENT_INGESTION_STARTED,
            message=f"Ingestion started for document {document_id}",
            data={"document_id": document_id, "status": "processing"},
        )

        def progress_callback(
            stage: str, progress: float, chunks_processed: int, total_chunks: int
        ) -> None:
            self._emit_event(
                document_id=document_id,
                event_type=EventType.DOCUMENT_INGESTION_PROGRESS,
                message=f"Ingestion progress: {stage} ({progress:.0%})",
                data={
                    "document_id": document_id,
                    "stage": stage,
                    "progress": progress,
                    "chunks_processed": chunks_processed,
                    "total_chunks": total_chunks,
                },
            )

        try:
            doc = await self._pipeline.ingest_document(
                document_id=document_id,
                file_path=file_path,
                content_type=content_type,
                progress_callback=progress_callback,
            )
            self._emit_event(
                document_id=document_id,
                event_type=EventType.DOCUMENT_INGESTION_COMPLETED,
                message=f"Ingestion completed for document {document_id}",
                data={
                    "document_id": document_id,
                    "status": "ready",
                    "chunk_count": doc.chunk_count,
                    "token_count": doc.token_count,
                },
            )
        except IngestionError as exc:
            self._emit_event(
                document_id=document_id,
                event_type=EventType.DOCUMENT_INGESTION_FAILED,
                message=f"Ingestion failed for document {document_id}: {exc.user_message}",
                data={
                    "document_id": document_id,
                    "status": "failed",
                    "error": exc.user_message,
                },
            )
        except Exception as exc:
            logger.exception(
                "Unexpected ingestion error",
                document_id=document_id,
            )
            self._emit_event(
                document_id=document_id,
                event_type=EventType.DOCUMENT_INGESTION_FAILED,
                message=f"Ingestion failed for document {document_id}",
                data={
                    "document_id": document_id,
                    "status": "failed",
                    "error": str(exc),
                },
            )

    def _emit_event(
        self,
        document_id: str,
        event_type: EventType,
        message: str,
        data: dict[str, object],
    ) -> None:
        """Emit a knowledge ingestion event.

        Args:
            document_id: Document ID used as workflow_id.
            event_type: The event type to emit.
            message: Human-readable event message.
            data: Event data payload.
        """
        self._event_bus.emit(
            WorkflowEvent(
                id=str(uuid4()),
                domain=EventDomain.KNOWLEDGE,
                workflow_id=document_id,
                sequence=0,
                timestamp=datetime.now(UTC),
                agent="knowledge",
                event_type=event_type,
                message=message,
                data=data,
            )
        )
