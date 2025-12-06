# Knowledge Library Design

**Date:** 2025-12-06
**Status:** Draft
**Phase:** 13 (before AWS AgentCore)

## Overview

**Knowledge Library** is a co-learning feature where developers and Amelia's agents share a growing knowledge base of framework documentation and best practices.

### The Problem

When Amelia writes code using a framework the developer doesn't know well, two things go wrong:
1. The developer can't effectively review or maintain the code
2. The developer misses an opportunity to learn from Amelia's work

### The Solution

A shared knowledge base that serves both purposes:
- **For developers**: Chat-based Q&A to learn frameworks, plus on-demand explanations of code Amelia writes
- **For agents**: RAG retrieval of pertinent documentation sections while coding

### Core Workflow

```
1. Developer adds a framework (paste docs URL)
2. Docling parses → chunks → embeds into sqlite-vec
3. Developer explores via chat ("How does React Query handle caching?")
4. During workflows, agents retrieve relevant chunks when coding
5. Developer clicks Amelia's code → "Explain this" → grounded explanation
```

### Key Principle: Co-Learning

Amelia isn't a black box. As it codes, the developer can understand *why* decisions were made, grounded in the same documentation Amelia used. Over time, both human and agent operate from a shared, growing knowledge foundation.

---

## Architecture

Knowledge Library shares backend infrastructure with Spec Builder but has its own dedicated UI.

### System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Amelia Dashboard                         │
│  ┌───────────┐  ┌───────────┐  ┌─────────────┐  ┌───────────┐  │
│  │ Workflows │  │Spec Builder│  │Knowledge    │  │ Settings  │  │
│  │           │  │           │  │Library      │  │           │  │
│  └───────────┘  └───────────┘  └──────┬──────┘  └───────────┘  │
└───────────────────────────────────────┼─────────────────────────┘
                                        │
┌───────────────────────────────────────┼─────────────────────────┐
│                     Amelia Server     │                         │
│  ┌────────────────────────────────────▼────────────────────────┐│
│  │              Shared RAG Infrastructure                      ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  ││
│  │  │ Docling      │  │ Chunking &   │  │ Semantic Search  │  ││
│  │  │ Ingestion    │  │ Embedding    │  │ (sqlite-vec)     │  ││
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                  │
│  ┌───────────────────────────▼─────────────────────────────────┐│
│  │                    SQLite Database                          ││
│  │  [frameworks] [framework_docs] [chunks] [vectors]           ││
│  │  [chat_sessions] [messages] [project_frameworks]            ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                  │
│  ┌───────────────────────────▼─────────────────────────────────┐│
│  │                 Agent RAG Integration                       ││
│  │         Developer/Architect query knowledge base            ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Purpose |
|-----------|---------|
| **Framework Manager** | CRUD for frameworks, URL fetching, triggers Docling ingestion |
| **Chat Engine** | Q&A conversations grounded in framework docs |
| **Code Explainer** | Takes code snippet + framework context, generates explanation |
| **Agent RAG Hook** | Provides retrieval interface for Developer/Architect agents |

### Reuse from Spec Builder

- Docling ingestion pipeline
- Chunking and embedding logic
- sqlite-vec storage and query
- Streaming chat infrastructure

---

## Data Models

### Database Schema

```sql
-- Global framework definitions
CREATE TABLE frameworks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,              -- "React Query"
    slug TEXT UNIQUE NOT NULL,       -- "react-query"
    version TEXT,                    -- "v5.0"
    docs_url TEXT,                   -- Primary docs URL
    status TEXT DEFAULT 'pending',   -- pending, ingesting, ready, failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Source documents for each framework (can have multiple URLs)
CREATE TABLE framework_sources (
    id TEXT PRIMARY KEY,
    framework_id TEXT NOT NULL REFERENCES frameworks(id),
    url TEXT NOT NULL,               -- Specific docs page URL
    title TEXT,                      -- Page title
    parsed_content TEXT,             -- Docling output (markdown)
    metadata JSON,                   -- Crawl depth, last fetched, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Chunks with embeddings (shared structure with Spec Builder)
CREATE TABLE framework_chunks (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES framework_sources(id),
    framework_id TEXT NOT NULL REFERENCES frameworks(id),
    content TEXT NOT NULL,
    chunk_index INTEGER,
    embedding BLOB                   -- Vector via sqlite-vec
);

-- Project-specific framework associations and overrides
CREATE TABLE project_frameworks (
    id TEXT PRIMARY KEY,
    project_path TEXT NOT NULL,      -- "/Users/dev/myproject"
    framework_id TEXT NOT NULL REFERENCES frameworks(id),
    conventions TEXT,                -- Project-specific notes/conventions
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_path, framework_id)
);

-- Chat sessions for learning
CREATE TABLE knowledge_sessions (
    id TEXT PRIMARY KEY,
    framework_id TEXT REFERENCES frameworks(id),  -- NULL = general/multi-framework
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Chat messages
CREATE TABLE knowledge_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES knowledge_sessions(id),
    role TEXT NOT NULL,              -- user, assistant
    content TEXT NOT NULL,
    referenced_chunks JSON,          -- Chunk IDs used for grounding
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Pydantic Models

```python
class Framework(BaseModel):
    id: str
    name: str
    slug: str
    version: str | None
    docs_url: str | None
    status: Literal["pending", "ingesting", "ready", "failed"]

class FrameworkSource(BaseModel):
    id: str
    framework_id: str
    url: str
    title: str | None

class ProjectFramework(BaseModel):
    framework: Framework
    conventions: str | None  # Project-specific overrides

class KnowledgeMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    referenced_chunks: list[str] | None
```

---

## API Endpoints

### Framework Management

```python
# Add a new framework
POST   /api/knowledge/frameworks
       Body: { name: str, docs_url: str, version?: str }
       Returns: Framework
       # Triggers async Docling ingestion

# List all frameworks
GET    /api/knowledge/frameworks
       Query: ?status=ready&search=react
       Returns: list[Framework]

# Get framework details with source count
GET    /api/knowledge/frameworks/{framework_id}
       Returns: Framework with sources summary

# Delete framework and all its data
DELETE /api/knowledge/frameworks/{framework_id}
       Returns: 204 No Content

# Add additional docs URL to existing framework
POST   /api/knowledge/frameworks/{framework_id}/sources
       Body: { url: str }
       Returns: FrameworkSource

# Check ingestion status
GET    /api/knowledge/frameworks/{framework_id}/status
       Returns: { status: str, sources_total: int, sources_ingested: int }
```

### Project Framework Associations

```python
# Link framework to project with optional conventions
POST   /api/knowledge/projects/{project_path}/frameworks
       Body: { framework_id: str, conventions?: str }
       Returns: ProjectFramework

# List frameworks for a project (includes global + project-specific)
GET    /api/knowledge/projects/{project_path}/frameworks
       Returns: list[ProjectFramework]

# Update project-specific conventions
PATCH  /api/knowledge/projects/{project_path}/frameworks/{framework_id}
       Body: { conventions: str }
       Returns: ProjectFramework

# Unlink framework from project
DELETE /api/knowledge/projects/{project_path}/frameworks/{framework_id}
       Returns: 204 No Content
```

### Chat / Q&A

```python
# Create learning session
POST   /api/knowledge/sessions
       Body: { framework_id?: str, title?: str }
       Returns: KnowledgeSession

# List sessions
GET    /api/knowledge/sessions
       Returns: list[KnowledgeSession]

# Send message, get streamed response
POST   /api/knowledge/sessions/{session_id}/messages
       Body: { content: str }
       Returns: streaming KnowledgeMessage

# Get session history
GET    /api/knowledge/sessions/{session_id}/messages
       Query: ?limit=50
       Returns: list[KnowledgeMessage]
```

### Code Explanation (for workflow integration)

```python
# Explain a code snippet in context of project's frameworks
POST   /api/knowledge/explain
       Body: {
         code: str,
         file_path?: str,
         project_path: str
       }
       Returns: streaming explanation with chunk references
```

---

## Agent Integration

How Developer and Architect agents use the Knowledge Library during workflows.

### RAG Hook Interface

```python
class KnowledgeRetriever:
    """Retrieval interface for agents."""

    async def query(
        self,
        query: str,
        project_path: str,
        top_k: int = 5,
    ) -> list[KnowledgeChunk]:
        """
        Retrieve relevant chunks from project's frameworks.

        1. Get frameworks linked to project
        2. Semantic search across those frameworks' chunks
        3. Return top_k most relevant chunks
        """

    async def get_context_for_task(
        self,
        task_description: str,
        file_paths: list[str],
        project_path: str,
    ) -> str:
        """
        Build context string for agent prompt.

        Analyzes task + files to determine relevant queries,
        retrieves chunks, formats as markdown context block.
        """
```

### Integration Points

```python
class DeveloperAgent:
    def __init__(self, driver: Driver, knowledge: KnowledgeRetriever):
        self.driver = driver
        self.knowledge = knowledge

    async def execute_task(self, task: Task, context: ExecutionContext) -> TaskResult:
        # 1. Retrieve relevant framework knowledge
        knowledge_context = await self.knowledge.get_context_for_task(
            task_description=task.description,
            file_paths=task.affected_files,
            project_path=context.project_path,
        )

        # 2. Include in agent prompt
        prompt = f"""
        ## Task
        {task.description}

        ## Relevant Framework Documentation
        {knowledge_context}

        ## Instructions
        Implement the task following the framework best practices above.
        """

        # 3. Execute with enriched context
        return await self.driver.generate(...)
```

### Retrieval Strategy

To avoid context bloat, retrieval is **pertinent and sparse**:

| Signal | Action |
|--------|--------|
| Task mentions "query" or "fetch" | Retrieve data-fetching framework docs (React Query, SWR) |
| File imports detected | Retrieve docs for imported packages |
| Error in framework code | Retrieve troubleshooting/FAQ sections |
| New file creation | Retrieve setup/configuration docs |

Chunks are deduplicated and capped (e.g., max 2000 tokens of framework context per task).

---

## Frontend UI

### Dashboard Tab: Knowledge Library

```
┌─────────────────────────────────────────────────────────────────────┐
│  Workflows │ Spec Builder │ Knowledge Library │ Settings            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────┐  ┌──────────────────────────────────────┐ │
│  │ FRAMEWORKS           │  │ Chat: React Query                    │ │
│  │                      │  │                                      │ │
│  │ ┌──────────────────┐ │  │ ┌──────────────────────────────────┐ │ │
│  │ │ 🟢 React Query   │ │  │ │ How does staleTime differ from   │ │ │
│  │ │    v5.0          │ │  │ │ cacheTime?                       │ │ │
│  │ └──────────────────┘ │  │ └──────────────────────────────────┘ │ │
│  │ ┌──────────────────┐ │  │                                      │ │
│  │ │ 🟢 FastAPI       │ │  │ ┌──────────────────────────────────┐ │ │
│  │ │    0.109         │ │  │ │ staleTime controls how long data │ │ │
│  │ └──────────────────┘ │  │ │ is considered fresh. cacheTime   │ │ │
│  │ ┌──────────────────┐ │  │ │ controls how long inactive data  │ │ │
│  │ │ 🟡 Pydantic      │ │  │ │ stays in memory...               │ │ │
│  │ │    ingesting...  │ │  │ │                                  │ │ │
│  │ └──────────────────┘ │  │ │ [Source: caching.md]             │ │ │
│  │                      │  │ └──────────────────────────────────┘ │ │
│  │ [+ Add Framework]    │  │                                      │ │
│  │                      │  │ ┌──────────────────────────────────┐ │ │
│  └──────────────────────┘  │ │ Ask about React Query...     [→] │ │ │
│                            │ └──────────────────────────────────┘ │ │
│                            └──────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Structure

```
src/components/knowledge-library/
├── KnowledgeLibraryPage.tsx    # Main page layout
├── FrameworkSidebar.tsx        # List frameworks, add new
│   ├── FrameworkCard.tsx       # Single framework with status
│   └── AddFrameworkModal.tsx   # URL input, name, version
├── ChatPanel.tsx               # Q&A interface (reuse from Spec Builder)
│   ├── MessageList.tsx
│   ├── Message.tsx
│   ├── SourceCitation.tsx      # Clickable [Source: file.md] links
│   └── ChatInput.tsx
├── FrameworkDetail.tsx         # View sources, conventions, delete
└── hooks/
    ├── useFrameworks.ts        # Framework CRUD
    ├── useKnowledgeChat.ts     # Chat state
    └── useIngestionStatus.ts   # Poll ingestion progress
```

### Code Explanation UI (Workflow Integration)

In the workflow detail view, code blocks get an "Explain" button:

```
┌─────────────────────────────────────────────────────────┐
│ Task: Add user query hook                               │
├─────────────────────────────────────────────────────────┤
│ File: src/hooks/useUser.ts                    [Explain] │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ export function useUser(id: string) {               │ │
│ │   return useQuery({                                 │ │
│ │     queryKey: ['user', id],                         │ │
│ │     queryFn: () => fetchUser(id),                   │ │
│ │     staleTime: 5 * 60 * 1000,                       │ │
│ │   });                                               │ │
│ │ }                                                   │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

Clicking "Explain" opens a slide-over panel with a grounded explanation.

---

## Implementation Phases

### Phase 1: Core Backend (MVP Foundation)

- Database schema + migrations for framework tables
- `FrameworkManager` service: add framework via URL, trigger ingestion
- Docling integration (reuse Spec Builder pipeline)
- Chunking and embedding into sqlite-vec
- REST endpoints: framework CRUD, ingestion status
- Basic error handling (invalid URL, Docling failures)

### Phase 2: Chat Engine (MVP)

- `KnowledgeChatEngine` with semantic search retrieval
- Chat session persistence
- Streaming responses via existing WebSocket infrastructure
- Source citations in responses (`[Source: filename.md]`)
- REST + WebSocket endpoints for chat

### Phase 3: Frontend - Knowledge Library Tab (MVP)

- Framework sidebar with status indicators
- Add Framework modal (URL input)
- Chat panel (reuse Spec Builder components)
- Source citation rendering
- Ingestion progress indicator

### Phase 4: Code Explanation (MVP)

- `/api/knowledge/explain` endpoint
- "Explain" button on code blocks in workflow detail view
- Slide-over panel with grounded explanation
- Framework detection from file imports

### Phase 5: Agent RAG Integration (MVP)

- `KnowledgeRetriever` class for agents
- Integration into `DeveloperAgent` prompt building
- Pertinent retrieval based on task + file signals
- Context token capping

---

### Future Phases (Post-MVP)

| Phase | Feature |
|-------|---------|
| **6** | Auto-detection from package.json/requirements.txt |
| **7** | Project-specific conventions UI |
| **8** | Post-workflow learning summaries |
| **9** | Multi-page crawling (follow links from docs URL) |
| **10** | Framework version management (upgrade docs) |

### Dependency Graph

```
Phase 1 ──► Phase 2 ──► Phase 3
                │
                └──────► Phase 4
                │
                └──────► Phase 5

(Phases 4 & 5 can parallelize after Phase 2)
```

---

## Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Feature name | Knowledge Library | Clear purpose, distinct from Spec Builder |
| Primary interaction | Chat-based Q&A | Simple, familiar, reuses Spec Builder patterns |
| Doc ingestion | Docling via URL | Handles multiple formats, already planned |
| Storage | Shared RAG infrastructure (sqlite-vec) | One embedding/chunk system, DRY |
| Framework scope | Global library + project overrides | Add once, use everywhere, customize per-project |
| Agent integration | On-demand RAG retrieval | Pertinent chunks only, avoids context bloat |
| Contextual learning | On-demand "Explain" button | Non-intrusive, developer pulls when curious |
| Learning tracking | None | Keep it simple, not an LMS |
| MVP scope | Manual URL add, chat, code explain, agent RAG | Core value without complexity |
| Deferred | Auto-detection, learning summaries, multi-page crawl | Clear path for iteration |
| Builder | Amelia | Dogfooding the orchestrator |
