# Knowledge Ingestion Pipeline Design

**Issue:** #435 (PR Checkpoint #3)
**Branch:** `feat/knowledge-ingestion`
**Depends on:** #433 (models/repository), #434 (embeddings) — both merged

## Overview

End-to-end ingestion pipeline that takes uploaded files (PDF, Markdown), parses them with Docling, chunks by document structure, embeds via OpenRouter, and stores in PostgreSQL with pg_vector. A background service wraps the pipeline with event emission for real-time dashboard updates.

## Components

```
                          amelia/knowledge/ingestion.py
                         +----------------------------------+
file_path, content_type  |  IngestionPipeline                |
------------------------>|                                    |
                         |  _parse()  --> _chunk() -->        |
                         |  _embed()  --> _store()            |
                         |                                    |
                         |  Dependencies:                     |
                         |   - KnowledgeRepository            |
                         |   - EmbeddingClient                |
                         +----------------+-------------------+
                                          |
                          amelia/knowledge/service.py
                         +----------------+-------------------+
                         |  KnowledgeService (singleton)      |
                         |                                    |
                         |  queue_ingestion() -> asyncio task  |
                         |  _ingest_with_events()             |
                         |  _emit_event()                     |
                         |                                    |
                         |  Dependencies:                     |
                         |   - EventBus                       |
                         |   - IngestionPipeline              |
                         +------------------------------------+
```

**Separation of concerns:**
- `IngestionPipeline` — pure data transformation, no events, no background tasks. Accepts a progress callback.
- `KnowledgeService` — background task management, event emission, progress translation. Wraps the pipeline.

## IngestionPipeline

```python
class IngestionPipeline:
    def __init__(
        self,
        repository: KnowledgeRepository,
        embedding_client: EmbeddingClient,
        concurrency_limit: int = 2,
    ): ...

    async def ingest_document(
        self,
        document_id: str,
        file_path: Path,
        content_type: str,
        progress_callback: Callable[[str, float, int, int], None] | None = None,
    ) -> Document: ...
```

### Stages

| Stage | Method | Execution | Input | Output |
|-------|--------|-----------|-------|--------|
| Parse | `_parse(file_path, content_type)` | Thread pool (`asyncio.to_thread`) | file path + MIME type | `(raw_text, DoclingDocument)` |
| Chunk | `_chunk(docling_doc)` | Thread pool | DoclingDocument | `list[DoclingChunk]` |
| Embed | `_embed(chunks)` | Async (EmbeddingClient) | chunk texts | `list[ChunkData]` with embeddings + token counts |
| Store | Inline in `ingest_document` | Async (repository) | ChunkData list | — |

### Progress Callback

Signature: `(stage: str, progress: float, chunks_processed: int, total_chunks: int)`

- Stages: `"parsing"`, `"chunking"`, `"embedding"`, `"storing"`
- Progress: 0.0-1.0 cumulative, weighted toward embedding (the slow part)
  - parsing: 0.0-0.1
  - chunking: 0.1-0.2
  - embedding: 0.2-0.9
  - storing: 0.9-1.0

### Concurrency

A semaphore limits simultaneous document ingestions (default 2). Acquired in `ingest_document` so the entire pipeline for one document runs under the semaphore.

### Error Handling

`IngestionError` exception with a `user_message` field. Each stage catches known exceptions and wraps them. The pipeline sets document status to `FAILED` with `error.user_message` before re-raising.

| Error Condition | User Message |
|----------------|-------------|
| Password-protected PDF | "This PDF is password-protected. Please provide an unlocked version." |
| Corrupt/invalid file | "The file could not be parsed. It may be corrupted or in an unsupported format." |
| Unsupported content type | "Unsupported file type: {content_type}. Supported: PDF, Markdown." |
| Empty document | "No text content found in this document." |
| Embedding API failure | "Failed to generate embeddings. Please try again later." |
| Database error | "Failed to save document. Please try again." |

## KnowledgeService

```python
class KnowledgeService:
    def __init__(
        self,
        event_bus: EventBus,
        ingestion_pipeline: IngestionPipeline,
    ): ...

    def queue_ingestion(
        self,
        document_id: str,
        file_path: Path,
        content_type: str,
    ) -> None: ...

    async def cleanup(self) -> None: ...
```

### Lifecycle

- Created once at server startup (singleton), lives for the process lifetime
- `queue_ingestion()` is synchronous — creates an `asyncio.Task` and returns immediately
- Tracks pending tasks in `set[asyncio.Task]` with auto-removal via `task.add_done_callback`
- `cleanup()` called during server shutdown — cancels and awaits pending tasks

### Event Emission Flow

1. `queue_ingestion()` spawns `_ingest_with_events()`
2. `_ingest_with_events()`:
   - Emits `DOCUMENT_INGESTION_STARTED`
   - Calls `pipeline.ingest_document()` with a progress callback
   - Progress callback emits `DOCUMENT_INGESTION_PROGRESS` events (EventBus.emit is synchronous)
   - On success: emits `DOCUMENT_INGESTION_COMPLETED`
   - On failure: emits `DOCUMENT_INGESTION_FAILED`

### Event Data Payloads

| Event | Data |
|-------|------|
| `STARTED` | `{"document_id": str, "status": "processing"}` |
| `PROGRESS` | `{"document_id": str, "stage": str, "progress": float, "chunks_processed": int, "total_chunks": int}` |
| `COMPLETED` | `{"document_id": str, "status": "ready", "chunk_count": int, "token_count": int}` |
| `FAILED` | `{"document_id": str, "status": "failed", "error": str}` |

## Event Types

New additions to `amelia/server/models/events.py`:

**New domain:**
```python
class EventDomain(str, Enum):
    WORKFLOW = "workflow"
    BRAINSTORM = "brainstorm"
    ORACLE = "oracle"
    KNOWLEDGE = "knowledge"    # new
```

**New event types:**
```python
DOCUMENT_INGESTION_STARTED = "document_ingestion_started"
DOCUMENT_INGESTION_PROGRESS = "document_ingestion_progress"
DOCUMENT_INGESTION_COMPLETED = "document_ingestion_completed"
DOCUMENT_INGESTION_FAILED = "document_ingestion_failed"
```

**Event construction:** `domain=KNOWLEDGE`, `workflow_id=document_id`, `agent="knowledge"`, `sequence=0` (ephemeral).

## Testing

### Unit: test_ingestion.py

| Test | Verifies |
|------|----------|
| `test_ingest_pdf_document` | Full pipeline with mocked Docling + mocked embedding client |
| `test_ingest_markdown_document` | Markdown content type flow |
| `test_parse_unsupported_content_type` | IngestionError for unknown MIME type |
| `test_parse_empty_document` | IngestionError when no text extracted |
| `test_parse_failure_sets_document_failed` | Document status set to FAILED on parse error |
| `test_embed_failure_sets_document_failed` | Document status set to FAILED on embedding error |
| `test_progress_callback_called` | Callback receives all 4 stages with increasing progress |
| `test_concurrency_semaphore` | Concurrent ingestions limited by semaphore |

### Unit: test_service.py

| Test | Verifies |
|------|----------|
| `test_queue_ingestion_emits_started_event` | STARTED event emitted when task begins |
| `test_queue_ingestion_emits_progress_events` | PROGRESS events emitted during processing |
| `test_queue_ingestion_emits_completed_event` | COMPLETED event with chunk/token counts |
| `test_queue_ingestion_emits_failed_event` | FAILED event with error message |
| `test_cleanup_awaits_pending_tasks` | cleanup() waits for in-flight tasks |
| `test_task_auto_removed_on_completion` | Task set cleaned up after completion |

### Mock boundaries

- Mock Docling (DocumentConverter, HierarchicalChunker) at the library boundary
- Mock EmbeddingClient and KnowledgeRepository (both have their own test suites)
- Mock EventBus in service tests to capture emitted events
- Do NOT mock IngestionPipeline in service tests — let it run with mocked dependencies

## Files

| File | Purpose |
|------|---------|
| `amelia/knowledge/ingestion.py` | IngestionPipeline, IngestionError |
| `amelia/knowledge/service.py` | KnowledgeService |
| `amelia/server/models/events.py` | New KNOWLEDGE domain + 4 event types |
| `amelia/knowledge/__init__.py` | Updated exports |
| `tests/unit/knowledge/test_ingestion.py` | Pipeline tests |
| `tests/unit/knowledge/test_service.py` | Service tests |
