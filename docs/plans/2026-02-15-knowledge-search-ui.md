# Knowledge Library: Search, API & Dashboard UI

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire the existing Knowledge Library backend (models, repository, embeddings, ingestion, service) to API endpoints and a dashboard UI with search, document management, and real-time ingestion progress.

**Architecture:** FastAPI routes expose document CRUD and semantic search. A Zustand store + React Router loader powers the dashboard page with two tabs (Search and Documents). WebSocket events from the existing KnowledgeService drive real-time ingestion progress. The search function embeds queries via OpenRouter and runs pgvector cosine similarity.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, pgvector, React 19, React Router v7, Zustand, shadcn/ui, ai-elements, Tailwind CSS v4, Vitest

---

## Existing Code (from merged PRs #437, #439, #441)

These modules are **already implemented and tested** — do not recreate:

| Module | Key exports |
|--------|-------------|
| `amelia/knowledge/models.py` | `Document`, `DocumentChunk`, `SearchResult`, `DocumentStatus` |
| `amelia/knowledge/repository.py` | `KnowledgeRepository` (CRUD + `search_chunks`) |
| `amelia/knowledge/embeddings.py` | `EmbeddingClient` (`embed`, `embed_batch`) |
| `amelia/knowledge/ingestion.py` | `IngestionPipeline` (`ingest_document`) |
| `amelia/knowledge/service.py` | `KnowledgeService` (`queue_ingestion`, `cleanup`) |
| `amelia/server/models/events.py` | `DOCUMENT_INGESTION_*` event types, `EventDomain.KNOWLEDGE` |

---

## Task 1: Search Function

**Files:**
- Create: `amelia/knowledge/search.py`
- Create: `tests/unit/knowledge/test_search.py`

**Step 1: Write failing test**

Create `tests/unit/knowledge/test_search.py`:

```python
"""Test knowledge search function."""

from unittest.mock import AsyncMock

import pytest

from amelia.knowledge.models import SearchResult
from amelia.knowledge.search import knowledge_search


@pytest.fixture
def mock_embedding_client():
    """Mock embedding client."""
    client = AsyncMock()
    client.embed = AsyncMock(return_value=[0.1] * 1536)
    return client


@pytest.fixture
def mock_repository():
    """Mock repository."""
    repo = AsyncMock()
    repo.search_chunks = AsyncMock(return_value=[])
    return repo


async def test_knowledge_search_embeds_query(mock_embedding_client, mock_repository):
    """Should embed query text and pass to repository."""
    await knowledge_search(
        query="How do React hooks work?",
        embedding_client=mock_embedding_client,
        repository=mock_repository,
    )

    mock_embedding_client.embed.assert_called_once_with("How do React hooks work?")
    mock_repository.search_chunks.assert_called_once()


async def test_knowledge_search_passes_tags(mock_embedding_client, mock_repository):
    """Should forward tags to repository search."""
    await knowledge_search(
        query="useState example",
        tags=["react", "hooks"],
        embedding_client=mock_embedding_client,
        repository=mock_repository,
    )

    call_kwargs = mock_repository.search_chunks.call_args[1]
    assert call_kwargs["tags"] == ["react", "hooks"]


async def test_knowledge_search_passes_top_k(mock_embedding_client, mock_repository):
    """Should forward top_k to repository search."""
    await knowledge_search(
        query="test",
        top_k=10,
        embedding_client=mock_embedding_client,
        repository=mock_repository,
    )

    call_kwargs = mock_repository.search_chunks.call_args[1]
    assert call_kwargs["top_k"] == 10


async def test_knowledge_search_returns_results(mock_embedding_client, mock_repository):
    """Should return search results from repository."""
    expected = [
        SearchResult(
            chunk_id="c1",
            document_id="d1",
            document_name="React Docs",
            tags=["react"],
            content="Hook content",
            heading_path=["Hooks"],
            similarity=0.92,
            token_count=50,
        )
    ]
    mock_repository.search_chunks = AsyncMock(return_value=expected)

    results = await knowledge_search(
        query="hooks",
        embedding_client=mock_embedding_client,
        repository=mock_repository,
    )

    assert results == expected
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/knowledge/test_search.py -v
```

Expected: `ModuleNotFoundError: No module named 'amelia.knowledge.search'`

**Step 3: Implement search function**

Create `amelia/knowledge/search.py`:

```python
"""Semantic search for Knowledge Library."""

from loguru import logger

from amelia.knowledge.embeddings import EmbeddingClient
from amelia.knowledge.models import SearchResult
from amelia.knowledge.repository import KnowledgeRepository


async def knowledge_search(
    query: str,
    embedding_client: EmbeddingClient,
    repository: KnowledgeRepository,
    top_k: int = 5,
    tags: list[str] | None = None,
    similarity_threshold: float = 0.7,
) -> list[SearchResult]:
    """Search documentation chunks by semantic similarity.

    Embeds the query text, then searches the vector index for matching chunks.

    Args:
        query: Natural language search query.
        embedding_client: Client for embedding the query.
        repository: Knowledge repository for vector search.
        top_k: Maximum results to return.
        tags: Optional tags to filter documents before search.
        similarity_threshold: Minimum cosine similarity (0.0–1.0).

    Returns:
        Ranked search results above the similarity threshold.
    """
    query_embedding = await embedding_client.embed(query)

    results = await repository.search_chunks(
        query_embedding=query_embedding,
        top_k=top_k,
        tags=tags,
        similarity_threshold=similarity_threshold,
    )

    logger.info(
        "Knowledge search completed",
        query=query,
        result_count=len(results),
        tags=tags,
    )

    return results
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/knowledge/test_search.py -v
```

Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add amelia/knowledge/search.py tests/unit/knowledge/test_search.py
git commit -m "feat(knowledge): add semantic search function"
```

---

## Task 2: Agent Tool + Constants

**Files:**
- Create: `amelia/tools/knowledge.py`
- Modify: `amelia/core/constants.py:8-61`
- Create: `tests/unit/tools/test_knowledge_tool.py`

**Step 1: Write failing test**

Create `tests/unit/tools/test_knowledge_tool.py`:

```python
"""Test knowledge_search agent tool."""

from unittest.mock import AsyncMock

import pytest

from amelia.tools.knowledge import create_knowledge_tool


async def test_knowledge_tool_calls_search(mock_embedding_client, mock_repository):
    """Tool should delegate to knowledge_search."""
    mock_embedding_client = AsyncMock()
    mock_embedding_client.embed = AsyncMock(return_value=[0.1] * 1536)
    mock_repository = AsyncMock()
    mock_repository.search_chunks = AsyncMock(return_value=[])

    tool = create_knowledge_tool(
        embedding_client=mock_embedding_client,
        repository=mock_repository,
    )

    results = await tool(query="test query", top_k=3)

    assert results == []
    mock_embedding_client.embed.assert_called_once()
    mock_repository.search_chunks.assert_called_once()


async def test_knowledge_tool_has_name():
    """Tool should have a descriptive name."""
    tool = create_knowledge_tool(
        embedding_client=AsyncMock(),
        repository=AsyncMock(),
    )

    assert "knowledge" in tool.__name__.lower()
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/tools/test_knowledge_tool.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: Add tool name to constants**

In `amelia/core/constants.py`, add to `ToolName` enum after line 37 (`WEB_SEARCH`):

```python
    # Knowledge
    KNOWLEDGE_SEARCH = "knowledge_search"
```

Add to `TOOL_NAME_ALIASES` dict after line 60 (`"WebSearch"`):

```python
    "KnowledgeSearch": ToolName.KNOWLEDGE_SEARCH,
```

**Step 4: Implement tool**

Create `amelia/tools/knowledge.py`:

```python
"""Knowledge Library tool for agent access."""

from collections.abc import Callable, Coroutine
from typing import Any

from amelia.knowledge.embeddings import EmbeddingClient
from amelia.knowledge.models import SearchResult
from amelia.knowledge.repository import KnowledgeRepository
from amelia.knowledge.search import knowledge_search as _search


def create_knowledge_tool(
    embedding_client: EmbeddingClient,
    repository: KnowledgeRepository,
) -> Callable[..., Coroutine[Any, Any, list[SearchResult]]]:
    """Create a knowledge_search tool for agent use.

    Args:
        embedding_client: Embedding client instance.
        repository: Knowledge repository instance.

    Returns:
        Async callable that agents invoke for semantic search.
    """

    async def knowledge_search(
        query: str,
        top_k: int = 5,
        tags: list[str] | None = None,
    ) -> list[SearchResult]:
        """Search uploaded documentation for relevant information.

        Use this tool to find information from the knowledge library.
        Useful for looking up framework APIs, library patterns, or internal docs.

        Args:
            query: Natural language search query.
            top_k: Maximum number of results (default 5).
            tags: Optional tags to filter documents.

        Returns:
            Ranked documentation chunks with similarity scores.
        """
        return await _search(
            query=query,
            embedding_client=embedding_client,
            repository=repository,
            top_k=top_k,
            tags=tags,
        )

    return knowledge_search
```

**Step 5: Run tests**

```bash
uv run pytest tests/unit/tools/test_knowledge_tool.py -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add amelia/tools/knowledge.py amelia/core/constants.py tests/unit/tools/test_knowledge_tool.py
git commit -m "feat(knowledge): add knowledge_search agent tool and constant"
```

---

## Task 3: Server Dependencies

**Files:**
- Modify: `amelia/server/dependencies.py`

**Step 1: Add knowledge service dependency**

Append to `amelia/server/dependencies.py` after `get_config()` (after line 160):

```python
from amelia.knowledge.repository import KnowledgeRepository
from amelia.knowledge.service import KnowledgeService


# Module-level knowledge service instance
_knowledge_service: KnowledgeService | None = None


def set_knowledge_service(service: KnowledgeService) -> None:
    """Set the global knowledge service instance.

    Args:
        service: KnowledgeService instance to set.
    """
    global _knowledge_service
    _knowledge_service = service


def clear_knowledge_service() -> None:
    """Clear the global knowledge service instance."""
    global _knowledge_service
    _knowledge_service = None


def get_knowledge_service() -> KnowledgeService:
    """Get the knowledge service instance.

    Returns:
        The current KnowledgeService instance.

    Raises:
        RuntimeError: If knowledge service not initialized.
    """
    if _knowledge_service is None:
        raise RuntimeError("Knowledge service not initialized. Is the server running?")
    return _knowledge_service


def get_knowledge_repository() -> KnowledgeRepository:
    """Get a knowledge repository instance.

    Returns:
        KnowledgeRepository using the current database pool.

    Raises:
        RuntimeError: If database not initialized.
    """
    db = get_database()
    return KnowledgeRepository(db.pool)
```

**Step 2: Verify import works**

```bash
uv run python -c "from amelia.server.dependencies import get_knowledge_service, get_knowledge_repository; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add amelia/server/dependencies.py
git commit -m "feat(knowledge): add knowledge service and repository dependencies"
```

---

## Task 4: API Routes

**Files:**
- Create: `amelia/server/routes/knowledge.py`
- Modify: `amelia/server/routes/__init__.py`
- Modify: `amelia/server/main.py` (router registration)

**Step 1: Create knowledge routes**

Create `amelia/server/routes/knowledge.py`:

```python
"""Knowledge Library API routes."""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from loguru import logger
from pydantic import BaseModel

from amelia.knowledge.models import Document, SearchResult
from amelia.knowledge.repository import KnowledgeRepository
from amelia.knowledge.search import knowledge_search
from amelia.knowledge.service import KnowledgeService
from amelia.server.dependencies import get_knowledge_repository, get_knowledge_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

ALLOWED_CONTENT_TYPES = {"application/pdf", "text/markdown"}


class SearchRequest(BaseModel):
    """Semantic search request body.

    Attributes:
        query: Natural language search query.
        top_k: Maximum results (default 5).
        tags: Optional tags to filter documents.
    """

    query: str
    top_k: int = 5
    tags: list[str] | None = None


class DocumentListResponse(BaseModel):
    """Response for document list endpoint.

    Attributes:
        documents: List of documents.
    """

    documents: list[Document]


@router.post("/documents", response_model=Document)
async def upload_document(
    file: UploadFile = File(...),
    name: str = Form(...),
    tags: str = Form(""),
    repository: KnowledgeRepository = Depends(get_knowledge_repository),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> Document:
    """Upload a document for ingestion.

    Accepts PDF or Markdown files. Creates a document record and queues
    background ingestion (parsing, chunking, embedding).

    Args:
        file: Uploaded file (PDF or Markdown).
        name: User-provided document name.
        tags: Comma-separated tags for filtering.
        repository: Knowledge repository.
        service: Knowledge service for background ingestion.

    Returns:
        Created document with pending status.

    Raises:
        HTTPException: 400 if file type is unsupported.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, Markdown.",
        )

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    doc = await repository.create_document(
        name=name,
        filename=file.filename or "unknown",
        content_type=file.content_type,
        tags=tag_list,
    )

    # Save uploaded file to temp location for background ingestion
    suffix = Path(file.filename or "").suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    service.queue_ingestion(
        document_id=doc.id,
        file_path=tmp_path,
        content_type=file.content_type,
    )

    logger.info("Document uploaded", document_id=doc.id, name=name)
    return doc


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    repository: KnowledgeRepository = Depends(get_knowledge_repository),
) -> DocumentListResponse:
    """List all documents.

    Args:
        repository: Knowledge repository.

    Returns:
        All documents ordered by creation date (newest first).
    """
    documents = await repository.list_documents()
    return DocumentListResponse(documents=documents)


@router.get("/documents/{document_id}", response_model=Document)
async def get_document(
    document_id: str,
    repository: KnowledgeRepository = Depends(get_knowledge_repository),
) -> Document:
    """Get document by ID.

    Args:
        document_id: Document UUID.
        repository: Knowledge repository.

    Returns:
        Document details.

    Raises:
        HTTPException: 404 if document not found.
    """
    doc = await repository.get_document(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    return doc


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    repository: KnowledgeRepository = Depends(get_knowledge_repository),
) -> None:
    """Delete document and all associated chunks.

    Args:
        document_id: Document UUID.
        repository: Knowledge repository.

    Raises:
        HTTPException: 404 if document not found.
    """
    doc = await repository.get_document(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    await repository.delete_document(document_id)
    logger.info("Document deleted via API", document_id=document_id)


@router.post("/search", response_model=list[SearchResult])
async def search_documents(
    request: SearchRequest,
    repository: KnowledgeRepository = Depends(get_knowledge_repository),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> list[SearchResult]:
    """Semantic search across documents.

    Embeds the query and searches the vector index for matching chunks.

    Args:
        request: Search parameters (query, top_k, tags).
        repository: Knowledge repository.
        service: Knowledge service (provides embedding client).

    Returns:
        Ranked search results above similarity threshold.
    """
    results = await knowledge_search(
        query=request.query,
        embedding_client=service._pipeline.embedding_client,
        repository=repository,
        top_k=request.top_k,
        tags=request.tags,
    )
    return results
```

**Step 2: Register route in `__init__.py`**

Add to `amelia/server/routes/__init__.py` after line 22 (websocket import):

```python
from amelia.server.routes.knowledge import router as knowledge_router
```

Add `"knowledge_router"` to the `__all__` list.

**Step 3: Register route in `main.py`**

Add import in `amelia/server/main.py` around line 82 (with other route imports):

```python
from amelia.server.routes import knowledge_router
```

Add router registration after line 293 (after `settings_router`):

```python
    application.include_router(knowledge_router, prefix="/api")
```

**Step 4: Wire up KnowledgeService in lifespan**

In `amelia/server/main.py`, in the `lifespan()` function:
- Import `set_knowledge_service` and `clear_knowledge_service` from dependencies (line 68-76)
- After the EventBus and Database are initialized, create and set the KnowledgeService
- In shutdown, call `cleanup()` and `clear_knowledge_service()`

This requires reading the lifespan function to find exact insertion points. The implementer should:
1. Read `lifespan()` fully
2. After `set_orchestrator(orchestrator)`, add KnowledgeService initialization
3. Before `clear_orchestrator()` in shutdown, add `knowledge_service.cleanup()` and `clear_knowledge_service()`

**Step 5: Commit**

```bash
git add amelia/server/routes/knowledge.py amelia/server/routes/__init__.py amelia/server/main.py
git commit -m "feat(knowledge): add API routes for document CRUD and search"
```

---

## Task 5: API Route Unit Tests

**Files:**
- Create: `tests/unit/server/routes/test_knowledge_routes.py`

**Step 1: Write tests**

Create `tests/unit/server/routes/test_knowledge_routes.py`:

```python
"""Unit tests for knowledge API routes."""

from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from amelia.knowledge.models import Document, DocumentStatus


@pytest.fixture
def mock_knowledge_deps():
    """Mock knowledge dependencies."""
    mock_repo = AsyncMock()
    mock_service = AsyncMock()
    mock_service._pipeline = AsyncMock()
    mock_service._pipeline.embedding_client = AsyncMock()
    return mock_repo, mock_service


@pytest.fixture
def client(mock_knowledge_deps):
    """Test client with mocked dependencies."""
    from amelia.server.routes.knowledge import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/api")

    mock_repo, mock_service = mock_knowledge_deps

    app.dependency_overrides[
        __import__(
            "amelia.server.dependencies", fromlist=["get_knowledge_repository"]
        ).get_knowledge_repository
    ] = lambda: mock_repo
    app.dependency_overrides[
        __import__(
            "amelia.server.dependencies", fromlist=["get_knowledge_service"]
        ).get_knowledge_service
    ] = lambda: mock_service

    return TestClient(app), mock_repo, mock_service


def test_list_documents(client):
    """Should return document list."""
    test_client, mock_repo, _ = client

    mock_repo.list_documents = AsyncMock(return_value=[])

    response = test_client.get("/api/knowledge/documents")

    assert response.status_code == 200
    assert response.json() == {"documents": []}


def test_get_document_not_found(client):
    """Should return 404 for missing document."""
    test_client, mock_repo, _ = client

    mock_repo.get_document = AsyncMock(return_value=None)

    response = test_client.get("/api/knowledge/documents/nonexistent")

    assert response.status_code == 404


def test_delete_document_not_found(client):
    """Should return 404 when deleting missing document."""
    test_client, mock_repo, _ = client

    mock_repo.get_document = AsyncMock(return_value=None)

    response = test_client.delete("/api/knowledge/documents/nonexistent")

    assert response.status_code == 404
```

**Step 2: Run tests**

```bash
uv run pytest tests/unit/server/routes/test_knowledge_routes.py -v
```

Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/unit/server/routes/test_knowledge_routes.py
git commit -m "test(knowledge): add unit tests for API routes"
```

---

## Task 6: Dashboard Types + API Client

**Files:**
- Create: `dashboard/src/types/knowledge.ts`
- Modify: `dashboard/src/api/client.ts`

**Step 1: Create types**

Create `dashboard/src/types/knowledge.ts`:

```typescript
/**
 * Knowledge Library types mirroring Python Pydantic models.
 */

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed';

export interface KnowledgeDocument {
  id: string;
  name: string;
  filename: string;
  content_type: string;
  tags: string[];
  status: DocumentStatus;
  error: string | null;
  chunk_count: number;
  token_count: number;
  raw_text: string | null;
  metadata: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  document_name: string;
  tags: string[];
  content: string;
  heading_path: string[];
  similarity: number;
  token_count: number;
}

export interface KnowledgeDocumentListResponse {
  documents: KnowledgeDocument[];
}

export interface IngestionProgressEvent {
  document_id: string;
  stage: 'parsing' | 'chunking' | 'embedding' | 'storing';
  progress: number;
  chunks_processed: number;
  total_chunks: number;
}
```

**Step 2: Add API methods**

Add to the `api` object in `dashboard/src/api/client.ts`, before the closing `};`:

```typescript
  // ==========================================================================
  // Knowledge API
  // ==========================================================================

  /**
   * List all knowledge documents.
   *
   * @returns Array of knowledge documents.
   * @throws {ApiError} When the API request fails.
   */
  async getKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/knowledge/documents`);
    const data = await handleResponse<KnowledgeDocumentListResponse>(response);
    return data.documents;
  },

  /**
   * Upload a document for ingestion.
   *
   * @param file - File to upload (PDF or Markdown).
   * @param name - Document display name.
   * @param tags - Tags for filtering.
   * @returns Created document with pending status.
   * @throws {ApiError} When upload fails or file type unsupported.
   */
  async uploadKnowledgeDocument(
    file: File,
    name: string,
    tags: string[]
  ): Promise<KnowledgeDocument> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    formData.append('tags', tags.join(','));

    const response = await fetchWithTimeout(`${API_BASE_URL}/knowledge/documents`, {
      method: 'POST',
      body: formData,
    });
    return handleResponse<KnowledgeDocument>(response);
  },

  /**
   * Delete a knowledge document.
   *
   * @param documentId - Document UUID.
   * @throws {ApiError} When document not found or API request fails.
   */
  async deleteKnowledgeDocument(documentId: string): Promise<void> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/knowledge/documents/${documentId}`,
      { method: 'DELETE' }
    );
    if (!response.ok) {
      await handleResponse(response);
    }
  },

  /**
   * Search knowledge documents.
   *
   * @param query - Natural language search query.
   * @param topK - Maximum results (default 5).
   * @param tags - Optional tags to filter.
   * @returns Ranked search results.
   * @throws {ApiError} When search fails.
   */
  async searchKnowledge(
    query: string,
    topK: number = 5,
    tags?: string[]
  ): Promise<SearchResult[]> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/knowledge/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, top_k: topK, tags }),
    });
    return handleResponse<SearchResult[]>(response);
  },
```

Also add the knowledge types to the import at the top of `client.ts`:

```typescript
import type { KnowledgeDocument, KnowledgeDocumentListResponse, SearchResult } from '../types/knowledge';
```

**Step 3: Verify build**

```bash
cd dashboard && pnpm type-check
```

Expected: No type errors

**Step 4: Commit**

```bash
git add dashboard/src/types/knowledge.ts dashboard/src/api/client.ts
git commit -m "feat(knowledge): add dashboard types and API client methods"
```

---

## Task 7: Dashboard Loader

**Files:**
- Create: `dashboard/src/loaders/knowledge.ts`
- Modify: `dashboard/src/loaders/index.ts`

**Step 1: Create loader**

Create `dashboard/src/loaders/knowledge.ts`:

```typescript
/**
 * @fileoverview Loader for the Knowledge Library page.
 */
import { api } from '@/api/client';
import type { KnowledgeDocument } from '@/types/knowledge';

/**
 * Loader data type for KnowledgePage.
 */
export interface KnowledgeLoaderData {
  /** All knowledge documents. */
  documents: KnowledgeDocument[];
}

/**
 * Loader for the Knowledge Library page.
 * Fetches all documents on navigation.
 *
 * @returns KnowledgeLoaderData with documents.
 */
export async function knowledgeLoader(): Promise<KnowledgeLoaderData> {
  const documents = await api.getKnowledgeDocuments();
  return { documents };
}
```

**Step 2: Export from index**

Add to `dashboard/src/loaders/index.ts`:

```typescript
export { knowledgeLoader } from './knowledge';
export type { KnowledgeLoaderData } from './knowledge';
```

**Step 3: Verify build**

```bash
cd dashboard && pnpm type-check
```

Expected: No type errors

**Step 4: Commit**

```bash
git add dashboard/src/loaders/knowledge.ts dashboard/src/loaders/index.ts
git commit -m "feat(knowledge): add dashboard data loader"
```

---

## Task 8: Knowledge Library Page

**Files:**
- Create: `dashboard/src/pages/KnowledgePage.tsx`

This is the main page with two tabs: **Search** and **Documents**.

**Step 1: Implement page**

Create `dashboard/src/pages/KnowledgePage.tsx`.

**Design requirements (reference the UI proposal from this conversation):**

1. **PageHeader** with:
   - Left: Label "KNOWLEDGE" + Title "Library"
   - Center: Label "DOCUMENTS" + Value showing document count
   - Right: Upload button (opens Dialog)

2. **Tabs** component with two tabs:
   - **Search** (default): `PromptInput` (ai-elements) for search bar, `Suggestions` chips for tag filters, search results as `Card` components with `Badge` for similarity score and tags, `Empty` state when no search performed
   - **Documents**: `DataTable` with columns (Name, Tags, Status, Chunks, Uploaded, Actions), `Empty` state when no documents

3. **Upload Dialog** using shadcn `Dialog`:
   - File input (accept `.pdf,.md`)
   - Name `Input`
   - Tags `Input` (comma-separated)
   - Submit button

4. **Status rendering** in Documents tab:
   - `pending`: `Badge` with muted style
   - `processing`: `Badge` with gold/running style + stage text
   - `ready`: `Badge` with green/completed style
   - `failed`: `Badge` with destructive style + `Tooltip` showing error

5. **Search results** use `Card` with:
   - Heading path shown as breadcrumb text (e.g. "React Docs > Hooks > useState")
   - Similarity score as `Badge` (right-aligned)
   - Content text
   - Source document name + tag `Badge` components
   - Token count in muted text

6. **Real-time updates**: Use `useAutoRevalidation` or subscribe to WebSocket events for `DOCUMENT_INGESTION_*` event types to refresh document list when ingestion completes.

7. **Responsive**: Desktop shows `DataTable`, mobile shows `Card` list.

**Component imports to use** (no custom components):

```typescript
// shadcn/ui
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { DataTable } from '@/components/ui/data-table';
import { DataTableColumnHeader } from '@/components/ui/data-table-column-header';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
  DialogDescription, DialogFooter
} from '@/components/ui/dialog';
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from '@/components/ui/empty';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

// ai-elements (if installed — check dashboard/package.json first)
// If NOT installed, use a plain Input + Button for search instead
import { Suggestions, Suggestion } from '@ai-elements/suggestion';

// Existing dashboard
import { PageHeader } from '@/components/PageHeader';

// Lucide icons
import { Library, Upload, Search, FileText, Trash2, AlertCircle } from 'lucide-react';
```

> **Important:** Check if `ai-elements` is in `dashboard/package.json`. If not installed, use a standard `Input` with a search icon button instead of `PromptInput`. Do not add unnecessary dependencies.

**Step 2: Verify build**

```bash
cd dashboard && pnpm type-check && pnpm build
```

Expected: Build succeeds

**Step 3: Commit**

```bash
git add dashboard/src/pages/KnowledgePage.tsx
git commit -m "feat(knowledge): add Knowledge Library dashboard page"
```

---

## Task 9: Router + Sidebar Integration

**Files:**
- Modify: `dashboard/src/router.tsx`
- Modify: `dashboard/src/components/DashboardSidebar.tsx:262-267`

**Step 1: Add route**

In `dashboard/src/router.tsx`, add import at top:

```typescript
import { knowledgeLoader } from '@/loaders';
```

Add route after the `costs` route (after line 129):

```typescript
      {
        path: 'knowledge',
        loader: knowledgeLoader,
        lazy: async () => {
          const { default: Component } = await import('@/pages/KnowledgePage');
          return { Component };
        },
      },
```

**Step 2: Enable sidebar link**

In `dashboard/src/components/DashboardSidebar.tsx`, remove the `comingSoon` prop from the Knowledge link (line 266):

Change:
```typescript
              <SidebarNavLink
                to="/knowledge"
                icon={Library}
                label="Knowledge"
                comingSoon
              />
```

To:
```typescript
              <SidebarNavLink
                to="/knowledge"
                icon={Library}
                label="Knowledge"
              />
```

**Step 3: Verify build**

```bash
cd dashboard && pnpm type-check && pnpm build
```

Expected: Build succeeds

**Step 4: Commit**

```bash
git add dashboard/src/router.tsx dashboard/src/components/DashboardSidebar.tsx
git commit -m "feat(knowledge): enable Knowledge Library route and sidebar link"
```

---

## Task 10: Dashboard Tests

**Files:**
- Create: `dashboard/src/pages/__tests__/KnowledgePage.test.tsx`

**Step 1: Write tests**

Create `dashboard/src/pages/__tests__/KnowledgePage.test.tsx`:

```typescript
/**
 * Tests for Knowledge Library page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import type { KnowledgeDocument } from '@/types/knowledge';

const mockDocuments: KnowledgeDocument[] = [
  {
    id: 'doc-1',
    name: 'React Docs',
    filename: 'react.pdf',
    content_type: 'application/pdf',
    tags: ['react', 'frontend'],
    status: 'ready',
    error: null,
    chunk_count: 42,
    token_count: 8500,
    raw_text: null,
    metadata: {},
    created_at: '2026-02-15T00:00:00Z',
    updated_at: '2026-02-15T00:00:00Z',
  },
];

function renderWithRouter(documents: KnowledgeDocument[] = []) {
  const router = createMemoryRouter(
    [
      {
        path: '/knowledge',
        loader: () => ({ documents }),
        lazy: async () => {
          const { default: Component } = await import('@/pages/KnowledgePage');
          return { Component };
        },
      },
    ],
    { initialEntries: ['/knowledge'] }
  );

  return render(<RouterProvider router={router} />);
}

describe('KnowledgePage', () => {
  it('renders page header', async () => {
    renderWithRouter();
    expect(await screen.findByText('Library')).toBeInTheDocument();
  });

  it('shows empty state when no documents', async () => {
    renderWithRouter([]);
    expect(await screen.findByText(/no documents/i)).toBeInTheDocument();
  });

  it('shows documents when loaded', async () => {
    renderWithRouter(mockDocuments);
    expect(await screen.findByText('React Docs')).toBeInTheDocument();
  });
});
```

**Step 2: Run tests**

```bash
cd dashboard && pnpm test:run
```

Expected: All tests PASS

**Step 3: Commit**

```bash
git add dashboard/src/pages/__tests__/KnowledgePage.test.tsx
git commit -m "test(knowledge): add dashboard page tests"
```

---

## Task 11: Lint + Type Check + Full Test Suite

**Step 1: Run backend checks**

```bash
uv run ruff check amelia tests
uv run mypy amelia
uv run pytest tests/unit/ -v
```

Fix any issues.

**Step 2: Run frontend checks**

```bash
cd dashboard && pnpm lint && pnpm type-check && pnpm test:run && pnpm build
```

Fix any issues.

**Step 3: Commit fixes if any**

```bash
git add -A
git commit -m "fix(knowledge): resolve lint and type errors"
```

---

## Completion Checklist

- [ ] `amelia/knowledge/search.py` — search function
- [ ] `amelia/tools/knowledge.py` — agent tool
- [ ] `amelia/core/constants.py` — KNOWLEDGE_SEARCH tool name
- [ ] `amelia/server/dependencies.py` — knowledge service + repository deps
- [ ] `amelia/server/routes/knowledge.py` — API endpoints
- [ ] `amelia/server/routes/__init__.py` — export knowledge_router
- [ ] `amelia/server/main.py` — register router + wire KnowledgeService in lifespan
- [ ] `dashboard/src/types/knowledge.ts` — TypeScript types
- [ ] `dashboard/src/api/client.ts` — API methods
- [ ] `dashboard/src/loaders/knowledge.ts` — data loader
- [ ] `dashboard/src/pages/KnowledgePage.tsx` — main page with Search + Documents tabs
- [ ] `dashboard/src/router.tsx` — /knowledge route
- [ ] `dashboard/src/components/DashboardSidebar.tsx` — remove comingSoon
- [ ] All backend tests pass
- [ ] All frontend tests pass
- [ ] Lint + type checks pass
- [ ] Build succeeds
