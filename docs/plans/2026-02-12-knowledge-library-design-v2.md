# Knowledge Library Design (v2)

**Goal:** Provide a RAG backend that stores, chunks, embeds, and retrieves documentation for Amelia's agents via tool calls.

**Related Issues:**
- #203 - Knowledge Library
- #280 - Oracle Consulting System
- #290 - RLM Integration

**Supersedes:** `2026-01-27-knowledge-library-design.md`

---

## Background

Amelia's agents need authoritative documentation when planning, coding, and reviewing. The Architect must reference framework APIs. The Reviewer must validate library usage patterns. The Oracle must synthesize large documents. Today, agents rely on training data or web search — both unreliable for specific framework versions and internal standards.

The Knowledge Library solves this by letting users upload PDF and Markdown documentation, which Amelia parses, chunks, embeds, and stores in PostgreSQL with pg_vector. Agents retrieve relevant chunks through semantic search.

This is **not** a chat interface. It is infrastructure that agents access through tool calls.

---

## Changes from v1

| Decision | v1 | v2 | Rationale |
|----------|----|----|-----------|
| PostgreSQL | 16 | **17** | Current stable release |
| Vector index | IVFFlat (lists=100) | **HNSW** | Better recall, no tuning parameters, community default |
| Docling | >=2.70.0 | **>=2.73.0** | Latest stable |

All other decisions from v1 are unchanged.

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Document formats | PDF, Markdown | Covers framework docs and internal standards |
| Parser | Docling v2.73+ | MIT license, Pydantic data model, structural parsing, built-in chunking |
| Chunking | Docling HierarchicalChunker | Preserves heading hierarchy and semantic boundaries |
| Embeddings | OpenRouter API (`openai/text-embedding-3-small`, 1536 dims) | OpenAI-compatible API, centralized key management, low cost; direct OpenAI driver will inherit this when it lands |
| Vector storage | PostgreSQL 17 + pg_vector (HNSW) | Aligns with PostgreSQL stack; no separate vector DB; HNSW needs no tuning |
| Document organization | Flat with tags | Simple, no hierarchy to manage; agents filter by tag |
| Agent access | Two-tier: direct tool + Oracle deep processing | Simple search for all agents; Oracle adds full-document synthesis for complex queries |
| Dashboard MVP | Upload + list + status + error surfacing | Full CRUD with real-time status; errors accessible via tooltip on failed status badge |
| Web scraping | Post-MVP | Deferred; manual upload sufficient for MVP |

---

## Architecture

```
┌───────────────────────────────────────────────────┐
│                    Agents                          │
│  (Architect, Developer, Reviewer)                 │
│                                                    │
│  Tier 1: knowledge_search(query, top_k, tags?)    │
│          → returns ranked chunks                   │
└──────────────────────┬────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
         ▼                           ▼
┌─────────────────┐       ┌──────────────────────┐
│  Knowledge      │       │  Oracle              │
│  Search         │       │                      │
│                 │       │  Tier 2: calls       │
│  • Embed query  │       │  knowledge_search +  │
│  • pg_vector    │       │  fetches raw_text +  │
│    HNSW search  │       │  full-document       │
│  • Tag filter   │       │  processing          │
│  • Return top_k │       │                      │
└────────┬────────┘       └──────────┬───────────┘
         │                           │
         └─────────────┬─────────────┘
                       ▼
┌───────────────────────────────────────────────────┐
│              PostgreSQL 17 + pg_vector             │
│                                                    │
│  documents        │  document_chunks              │
│  ─────────        │  ───────────────              │
│  id, name, tags   │  id, document_id              │
│  status, raw_text │  content, heading_path        │
│  metadata         │  embedding vector(1536)       │
│                   │  token_count, metadata        │
└───────────────────────────────────────────────────┘
```

---

## Data Model

New PostgreSQL migration (003):

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL,
    tags         TEXT[] NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending',
    error        TEXT,
    chunk_count  INT NOT NULL DEFAULT 0,
    token_count  INT NOT NULL DEFAULT 0,
    raw_text     TEXT,
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE document_chunks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INT NOT NULL,
    content      TEXT NOT NULL,
    heading_path TEXT[],
    token_count  INT NOT NULL,
    embedding    vector(1536),
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chunks_embedding ON document_chunks
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_document ON document_chunks(document_id);
CREATE INDEX idx_documents_tags ON documents USING GIN(tags);
CREATE INDEX idx_documents_status ON documents(status);
```

---

## Backend Modules

```
amelia/knowledge/
    __init__.py
    models.py          -- Pydantic models (Document, Chunk, SearchResult)
    repository.py      -- PostgreSQL queries for documents + chunks
    ingestion.py       -- Docling parsing, chunking, embedding pipeline
    search.py          -- Semantic search + tag filtering
    embeddings.py      -- OpenRouter embedding client
```

### Ingestion Pipeline

Triggered on upload, runs async in background:

```
Upload (PDF/MD)
    │
    ▼
Store metadata → documents row (status='pending')
    │
    ▼
status='processing'
    │
    ▼
Docling DocumentConverter.convert()
    → DoclingDocument with structural parsing
    → Extract raw_text for Oracle/Tier 2 use
    │
    ▼
HierarchicalChunker.chunk()
    → Chunks with heading_path metadata
    → Token counts per chunk
    │
    ▼
Embed chunks (batched via OpenRouter, openai/text-embedding-3-small)
    → vector(1536) per chunk
    │
    ▼
INSERT chunks → document_chunks rows
    │
    ▼
status='ready', chunk_count=N, token_count=T
```

If any step fails, status becomes `'failed'` with the error stored. The user can delete and re-upload.

### Search

```python
async def knowledge_search(
    query: str,
    top_k: int = 5,
    tags: list[str] | None = None,
    similarity_threshold: float = 0.7,
) -> list[SearchResult]:
```

1. Embed the query via OpenRouter
2. Execute pg_vector HNSW cosine similarity search on `document_chunks`
3. If `tags` provided, filter to chunks from documents matching any tag
4. Return top_k results above threshold

### SearchResult Model

```python
class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    tags: list[str]
    content: str
    heading_path: list[str]
    similarity: float
    token_count: int
```

### Embedding Client

Thin async wrapper calling `POST https://openrouter.ai/api/v1/embeddings` with bearer auth. Uses the user's OpenRouter API key. Default model: `openai/text-embedding-3-small` (1536 dimensions). Embedding model is configurable in server settings.

Batches chunks per request to minimize round trips.

---

## Agent Tool Integration

### Tier 1: Direct Search (All Agents)

Registered as a tool in the driver tool set, added to `ToolName` enum in `amelia/core/constants.py`:

```python
knowledge_search(query: str, top_k: int = 5, tags: list[str] | None = None) -> list[SearchResult]
```

Agents call this like any other tool. The Architect calls it when planning around an unfamiliar framework. The Reviewer calls it to validate library usage patterns.

### Tier 2: Oracle Deep Processing

Oracle calls `knowledge_search` for retrieval, then additionally fetches `raw_text` from `documents` for full-document processing. Oracle decides based on query complexity whether to use chunk results directly or pull the full document.

The Knowledge Library does not know about Oracle. Oracle composes on top — it calls the same `knowledge_search` function and makes a separate repository call for `raw_text`. No changes to the existing Oracle API contract.

---

## API Endpoints

Added to the existing FastAPI server:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/knowledge/documents` | Upload file (multipart form: file + name + tags) |
| `GET` | `/api/knowledge/documents` | List all documents |
| `GET` | `/api/knowledge/documents/{id}` | Get document details |
| `DELETE` | `/api/knowledge/documents/{id}` | Delete document + cascaded chunks |
| `POST` | `/api/knowledge/search` | Semantic search (query, top_k, tags) |

Upload accepts `.pdf` and `.md` files. The ingestion pipeline runs as a background task — the endpoint returns immediately with the document record in `pending` status.

---

## WebSocket Events

```python
class EventType(StrEnum):
    DOCUMENT_INGESTION_STARTED = "document_ingestion_started"
    DOCUMENT_INGESTION_COMPLETED = "document_ingestion_completed"
    DOCUMENT_INGESTION_FAILED = "document_ingestion_failed"
```

Events carry the document ID, status, and (for failures) the error message. Enables real-time dashboard updates.

---

## Dashboard

New route at `/knowledge` — a Knowledge Library tab replacing the current "Coming Soon" sidebar placeholder.

**Document list view:**
- Table: Name, Tags (pill badges), Status (color-coded badge), Chunks, Uploaded
- Upload button opens drag-and-drop zone for `.pdf` and `.md` files
- Name and tags entered during upload (tags as comma-separated input)
- Delete action with confirmation per row
- Status auto-updates via WebSocket (pending → processing → ready/failed)
- Failed status badge shows the error message in a tooltip

**Frontend files:**

```
dashboard/src/
    pages/knowledge/
        index.tsx          -- route component, document list
        upload-dialog.tsx  -- upload modal with drag-drop + name/tags
    api/knowledge.ts       -- fetch wrappers for /api/knowledge/* endpoints
    stores/knowledge.ts    -- Zustand store for document list + WebSocket updates
```

---

## Dependencies

| Package | Purpose | Layer |
|---------|---------|-------|
| `docling>=2.73.0` | PDF/Markdown parsing and structural chunking | Backend |
| `pgvector` | pg_vector Python bindings for asyncpg | Backend |
| `httpx` (existing) | OpenRouter API calls | Backend |

No new frontend dependencies.

**Infrastructure change:** Docker-compose switches from `postgres:16` to `pgvector/pgvector:pg17`.

---

## Implementation Phases

| Phase | What | Depends On |
|-------|------|------------|
| 1 | PostgreSQL 17 upgrade + pg_vector migration | — |
| 2 | Pydantic models + repository layer | Phase 1 |
| 3 | Embedding client (OpenRouter wrapper) | — |
| 4 | Ingestion pipeline (Docling + chunking + embedding + storage) | Phase 2, 3 |
| 5 | Search module + `knowledge_search` agent tool registration | Phase 2, 3 |
| 6 | Oracle integration (Tier 2 deep processing) | Phase 5 |
| 7 | API endpoints + WebSocket events | Phase 4, 5 |
| 8 | Dashboard Knowledge Library tab | Phase 7 |

Phases 2+3 run in parallel. Phases 4+5 run in parallel.

---

## Post-MVP

- Web scraping / URL ingestion
- Auto-detection from package.json / requirements.txt
- Document preview panel in dashboard
- Multi-page crawling
- Embedding model selection in dashboard settings
- Direct OpenAI embedding support (via OpenAI driver)
