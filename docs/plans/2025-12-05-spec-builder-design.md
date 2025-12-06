# Spec Builder Design

**Date:** 2025-12-05
**Status:** Draft
**Issue:** TBD

## Overview

**Spec Builder** is a document-assisted technical design tool integrated into Amelia's web dashboard. It helps engineers synthesize reference materials (existing specs, RFCs, competitor docs, research) into structured design specifications that feed into Amelia's planning workflow.

### Core Workflow

```
1. Create session linked to issue (e.g., PROJ-123)
2. Upload reference documents (docx, md, pdf, etc.)
3. Documents parsed via Docling → chunked → embedded in SQLite
4. Chat with AI about the sources (Q&A, exploration)
   - AI offers multiple choice suggestions to guide discussion
5. Select template, generate design spec
6. Spec auto-attaches to issue
7. Run `amelia start PROJ-123` → Architect sees issue + spec
```

### Key Characteristics

- **Local-first**: All data in SQLite (documents, vectors, chat history)
- **Template-driven**: Output structure defined by markdown templates with frontmatter
- **Conversation-guided**: Chat interface with multiple choice suggestions
- **Issue-linked**: Sessions tied to tracker issue IDs, enabling seamless handoff to Architect
- **Driver-agnostic**: Uses Amelia's existing LLM drivers (`api:openai`, `cli:claude`)

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        Amelia Dashboard                         │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌─────────────┐  │
│  │ Workflows │  │  Issues   │  │Spec Builder│  │  Settings   │  │
│  └───────────┘  └───────────┘  └─────┬─────┘  └─────────────┘  │
└────────────────────────────────────────┼────────────────────────┘
                                         │
┌────────────────────────────────────────┼────────────────────────┐
│                     Amelia Server      │                        │
│  ┌─────────────────────────────────────▼──────────────────────┐ │
│  │                  Spec Builder Service                      │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │ │
│  │  │ Document     │  │ Conversation │  │ Spec Generation  │  │ │
│  │  │ Processor    │  │ Manager      │  │ Engine           │  │ │
│  │  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │ │
│  └─────────┼─────────────────┼───────────────────┼────────────┘ │
│            │                 │                   │              │
│  ┌─────────▼─────────────────▼───────────────────▼────────────┐ │
│  │                      SQLite Database                       │ │
│  │  [sessions] [documents] [chunks] [vectors] [messages]      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                  │
│  ┌───────────────────────────▼────────────────────────────────┐ │
│  │                    Existing Amelia Core                    │ │
│  │         [Drivers]  [Trackers]  [Workflows]                 │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Purpose |
|-----------|---------|
| **Document Processor** | Accepts uploads, calls Docling, chunks text, generates embeddings, stores in SQLite+sqlite-vec |
| **Conversation Manager** | Handles chat messages, generates multiple choice suggestions, retrieves relevant chunks via semantic search |
| **Spec Generation Engine** | Loads templates, orchestrates section-by-section generation, validates output |

### External Dependencies

- **Docling** - Document parsing (PDF, DOCX, MD, HTML, images)
- **sqlite-vec** - Vector similarity search extension for SQLite
- **Embedding model** - Sentence transformers or API-based (configurable)

---

## Data Models

### Database Schema

```sql
-- Spec Builder sessions linked to issues
CREATE TABLE spec_sessions (
    id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,           -- e.g., "PROJ-123"
    title TEXT,
    status TEXT DEFAULT 'active',     -- active, completed, archived
    repo_paths JSON,                  -- Local git repos AI can reference
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Uploaded source documents
CREATE TABLE spec_documents (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES spec_sessions(id),
    filename TEXT NOT NULL,
    mime_type TEXT,
    raw_content BLOB,                 -- Original file
    parsed_content TEXT,              -- Docling output (markdown)
    metadata JSON,                    -- Title, author, page count, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Document chunks for semantic search
CREATE TABLE spec_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES spec_documents(id),
    session_id TEXT NOT NULL REFERENCES spec_sessions(id),
    content TEXT NOT NULL,
    chunk_index INTEGER,
    start_offset INTEGER,
    end_offset INTEGER,
    embedding BLOB                    -- Vector via sqlite-vec
);

-- Chat messages with full persistence
CREATE TABLE spec_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES spec_sessions(id),
    role TEXT NOT NULL,               -- user, assistant, system
    content TEXT NOT NULL,
    suggestions JSON,                 -- Multiple choice options (if assistant)
    referenced_chunks JSON,           -- Chunk IDs used for this response
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Generated specs (versioned)
CREATE TABLE spec_outputs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES spec_sessions(id),
    issue_id TEXT NOT NULL,           -- Denormalized for quick lookup
    template_name TEXT NOT NULL,
    content TEXT NOT NULL,            -- Generated markdown
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Pydantic Models

```python
class SpecSession(BaseModel):
    id: str
    issue_id: str
    title: str | None
    status: Literal["active", "completed", "archived"]
    repo_paths: list[Path]
    documents: list[SpecDocument]
    created_at: datetime

class SpecDocument(BaseModel):
    id: str
    filename: str
    mime_type: str | None
    parsed_content: str  # Markdown from Docling
    metadata: dict

class SpecMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    suggestions: list[Suggestion] | None

class Suggestion(BaseModel):
    label: str       # "A", "B", "C"
    text: str        # Short option text
    description: str # Longer explanation

class SpecOutput(BaseModel):
    id: str
    session_id: str
    issue_id: str
    template_name: str
    content: str
    version: int
    created_at: datetime
```

---

## Source Types

| Source | Parser | Use Case |
|--------|--------|----------|
| DOCX, PDF, PPTX | Docling | Specs, RFCs, presentations |
| Markdown | Docling | Existing docs, READMEs |
| Web URL | Docling (future) | External references |
| YouTube | Transcript API (future) | Tech talks, tutorials |
| **Git repo** | Filesystem (on-demand) | Existing codebase patterns |

### Git Repo Source

Git repos are referenced, not ingested. AI reads files on-demand from filesystem.

```python
class GitRepoSource:
    """Reference local git repo - no ingestion, just filesystem access."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    async def list_files(
        self,
        patterns: list[str] = ["**/*.py"],
    ) -> list[FileInfo]:
        """List available files for AI to reference."""

    async def read_file(self, relative_path: str) -> str:
        """Read file content on-demand."""

    async def search_code(self, query: str) -> list[SearchResult]:
        """Grep/ripgrep for patterns in repo."""
```

---

## Template System

### Template Format

Templates are markdown files with YAML frontmatter, stored in `templates/specs/`.

```markdown
---
name: api-design
display_name: API Design Specification
description: Template for REST/GraphQL API design documents
sections:
  - id: overview
    title: Overview
    required: true
    prompt: |
      Summarize the API's purpose, target consumers, and key capabilities.
      Draw from any architecture docs or requirements in the sources.
  - id: endpoints
    title: Endpoints
    required: true
    prompt: |
      List all endpoints with methods, paths, request/response schemas.
      Reference any existing API patterns from the sources.
  - id: data-models
    title: Data Models
    required: true
    prompt: |
      Define the core data structures. Include field types, constraints,
      and relationships. Use existing domain models from sources if available.
  - id: error-handling
    title: Error Handling
    required: false
    prompt: |
      Describe error response format, common error codes, and retry guidance.
  - id: security
    title: Security Considerations
    required: true
    prompt: |
      Cover authentication, authorization, rate limiting, and data validation.
---

# {{title}}

## Overview
{{sections.overview}}

## Endpoints
{{sections.endpoints}}

## Data Models
{{sections.data-models}}

## Error Handling
{{sections.error-handling}}

## Security Considerations
{{sections.security}}
```

### Built-in Templates

| Template | Use Case |
|----------|----------|
| `feature-spec` | New feature design with user stories, acceptance criteria |
| `api-design` | REST/GraphQL API specification |
| `architecture-decision` | ADR format for architectural choices |
| `refactoring-plan` | Code refactoring with before/after, migration steps |

---

## Conversation Flow

### Interaction Model

Chat follows a guided exploration pattern with AI-generated multiple choice suggestions.

```
┌─────────────────────────────────────────────────────────────┐
│  Session: PROJ-123 - Auth System Redesign                   │
├─────────────────────────────────────────────────────────────┤
│  📄 Sources: oauth-rfc.pdf, current-auth.md, competitor.docx│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Assistant] I've ingested 3 documents. Based on initial    │
│  analysis, they cover OAuth 2.0 specs, your current auth    │
│  implementation, and a competitor's approach.               │
│                                                             │
│  What would you like to explore first?                      │
│                                                             │
│  ○ A) Gaps in current implementation vs OAuth spec          │
│  ○ B) How competitor handles token refresh                  │
│  ○ C) Security considerations across all sources            │
│  ○ D) Something else...                                     │
│                                                             │
│  [User] A                                                   │
│                                                             │
│  [Assistant] Comparing current-auth.md against oauth-rfc,   │
│  I found 3 gaps: [details with source citations]...         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Suggestion Generation

```python
class ConversationManager:
    async def generate_response(
        self,
        session: SpecSession,
        user_message: str,
    ) -> SpecMessage:
        # 1. Retrieve relevant chunks via semantic search
        relevant_chunks = await self.search_chunks(
            session_id=session.id,
            query=user_message,
            top_k=10,
        )

        # 2. Build context with conversation history + chunks
        context = self.build_context(
            history=session.messages[-20:],
            chunks=relevant_chunks,
        )

        # 3. Generate response with suggestions
        response = await self.driver.generate(
            system_prompt=CONVERSATION_SYSTEM_PROMPT,
            context=context,
            user_message=user_message,
            response_model=ConversationResponse,
        )

        return SpecMessage(
            role="assistant",
            content=response.message,
            suggestions=response.suggestions,
            referenced_chunks=[c.id for c in relevant_chunks],
        )
```

### System Prompt

```
You are a technical design assistant helping synthesize reference
documents into specifications.

Guidelines:
- Ground all responses in the provided source documents
- Cite sources when making claims: [source: filename.pdf, p.12]
- After each response, offer 2-4 multiple choice suggestions
- Suggestions should be concrete next steps, not generic options
- One suggestion should always be "Generate spec" when enough
  context has been gathered
- Keep responses focused and concise (under 300 words)
```

---

## Spec Generation

### Generation Flow

```python
class SpecGenerationEngine:
    async def generate_spec(
        self,
        session: SpecSession,
        template: SpecTemplate,
    ) -> SpecOutput:
        sections = {}

        for section in template.sections:
            # 1. Gather relevant context for this section
            relevant_chunks = await self.search_chunks(
                session_id=session.id,
                query=section.prompt,
                top_k=15,
            )

            # 2. Include conversation insights
            conversation_context = self.extract_insights(
                messages=session.messages,
                section_topic=section.title,
            )

            # 3. Generate section content
            content = await self.driver.generate(
                system_prompt=SECTION_GENERATION_PROMPT,
                context={
                    "chunks": relevant_chunks,
                    "conversation": conversation_context,
                    "section": section,
                    "previous_sections": sections,
                },
                response_model=SectionContent,
            )

            sections[section.id] = content

        # 4. Assemble final document from template
        final_content = template.render(sections)

        # 5. Store versioned output
        return await self.store_output(session, template, final_content)
```

### Architect Integration

```python
class ArchitectAgent:
    async def plan(self, issue: Issue) -> TaskDAG:
        # Check for attached spec
        spec = await self.spec_repository.get_latest_for_issue(issue.id)

        if spec:
            context = f"{issue.description}\n\n## Design Spec\n{spec.content}"
        else:
            context = issue.description

        # Continue with planning...
```

---

## API Endpoints

### REST API

```python
# Session management
POST   /api/spec-builder/sessions
       Body: { issue_id: str, title?: str, repo_paths?: list[str] }
       Returns: SpecSession

GET    /api/spec-builder/sessions
       Query: ?issue_id=PROJ-123&status=active
       Returns: list[SpecSession]

GET    /api/spec-builder/sessions/{session_id}
       Returns: SpecSession with documents and message count

DELETE /api/spec-builder/sessions/{session_id}
       Returns: 204 No Content

# Document upload
POST   /api/spec-builder/sessions/{session_id}/documents
       Body: multipart/form-data with file(s)
       Returns: list[SpecDocument]

DELETE /api/spec-builder/sessions/{session_id}/documents/{doc_id}
       Returns: 204 No Content

# Conversation
GET    /api/spec-builder/sessions/{session_id}/messages
       Query: ?limit=50&before={message_id}
       Returns: list[SpecMessage]

POST   /api/spec-builder/sessions/{session_id}/messages
       Body: { content: str }
       Returns: SpecMessage (assistant response with suggestions)

# Templates
GET    /api/spec-builder/templates
       Returns: list[TemplateMeta]

GET    /api/spec-builder/templates/{name}
       Returns: SpecTemplate (full template with sections)

# Spec generation
POST   /api/spec-builder/sessions/{session_id}/generate
       Body: { template_name: str }
       Returns: SpecOutput

GET    /api/spec-builder/sessions/{session_id}/outputs
       Returns: list[SpecOutput] (all versions)

GET    /api/spec-builder/outputs/by-issue/{issue_id}
       Returns: SpecOutput | null (latest for Architect integration)
```

### WebSocket Streaming

```typescript
// Client connects to existing WebSocket
ws.send(JSON.stringify({
  type: "spec_builder.message",
  session_id: "sess_123",
  content: "What are the security gaps?"
}));

// Server streams response
{ type: "spec_builder.chunk", content: "Based on..." }
{ type: "spec_builder.chunk", content: " the OAuth RFC..." }
{ type: "spec_builder.suggestions", suggestions: [...] }
{ type: "spec_builder.done", message_id: "msg_456" }
```

---

## Frontend Components

### AI SDK Integration

Use Vercel AI SDK `useChat` pattern for streaming chat.

```typescript
export function useSpecChat(sessionId: string) {
  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
    api: `/api/spec-builder/sessions/${sessionId}/messages`,
    streamProtocol: 'text',
  });

  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);

  const selectSuggestion = (label: string) => {
    handleSubmit(new Event('submit'), { data: { content: label } });
  };

  return {
    messages,
    input,
    handleInputChange,
    handleSubmit,
    isLoading,
    suggestions,
    selectSuggestion,
  };
}
```

### Component Structure

```
src/components/spec-builder/
├── SpecBuilderPage.tsx        # Main page with session management
├── SessionSidebar.tsx         # List sessions, create new
├── ChatPanel.tsx              # Main chat interface
│   ├── MessageList.tsx        # Scrollable message history
│   ├── Message.tsx            # Single message bubble
│   ├── SuggestionPills.tsx    # Multiple choice options (A, B, C, D)
│   ├── ChatInput.tsx          # Text input with submit
│   └── StreamingIndicator.tsx # Typing/loading state
├── SourcesPanel.tsx           # Uploaded docs + repo references
│   ├── DocumentList.tsx       # List uploaded files
│   ├── UploadDropzone.tsx     # Drag-and-drop upload
│   └── RepoSelector.tsx       # Add local git repo paths
├── SpecOutputPanel.tsx        # Generated specs
│   ├── TemplateSelector.tsx   # Choose template
│   ├── SpecPreview.tsx        # Rendered markdown preview
│   └── VersionHistory.tsx     # Previous spec versions
└── hooks/
    ├── useSpecChat.ts         # Chat state management
    ├── useSpecSession.ts      # Session CRUD
    └── useDocuments.ts        # Document upload/delete
```

### SuggestionPills Component

```tsx
export function SuggestionPills({
  suggestions,
  onSelect,
  disabled,
}: {
  suggestions: Suggestion[];
  onSelect: (label: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2 p-3 border-t">
      {suggestions.map((s) => (
        <button
          key={s.label}
          onClick={() => onSelect(s.label)}
          disabled={disabled}
          className="px-3 py-2 rounded-lg border hover:bg-accent text-left"
        >
          <span className="font-mono font-bold mr-2">{s.label})</span>
          <span>{s.text}</span>
        </button>
      ))}
    </div>
  );
}
```

---

## Error Handling

### Error Categories

| Category | Examples | Handling |
|----------|----------|----------|
| **Upload errors** | File too large, unsupported format, Docling parse failure | Show toast with specific error, allow retry |
| **LLM errors** | Rate limit, context too long, driver unavailable | Retry with backoff, fallback message, surface to user |
| **Session errors** | Session not found, issue ID invalid | Redirect to session list, show error state |
| **Generation errors** | Template not found, section generation failed | Partial output with failed sections marked, allow retry per-section |

### Backend Errors

```python
class SpecBuilderError(Exception):
    """Base error for Spec Builder operations."""
    def __init__(self, code: str, message: str, details: dict | None = None):
        self.code = code
        self.message = message
        self.details = details or {}

class DocumentParseError(SpecBuilderError):
    """Docling failed to parse document."""

class ContextTooLongError(SpecBuilderError):
    """Conversation + sources exceed model context limit."""

class GenerationError(SpecBuilderError):
    """Spec section generation failed."""
```

---

## Testing Strategy

### Unit Tests

```python
tests/unit/spec_builder/test_document_processor.py
- test_parse_docx_extracts_content
- test_parse_pdf_with_images
- test_chunk_text_respects_boundaries
- test_unsupported_format_raises_error

tests/unit/spec_builder/test_conversation_manager.py
- test_search_chunks_returns_relevant_results
- test_build_context_includes_history
- test_suggestions_generated_with_response

tests/unit/spec_builder/test_spec_generation.py
- test_load_template_parses_frontmatter
- test_generate_section_uses_relevant_chunks
- test_render_template_fills_sections
```

### Integration Tests

```python
tests/integration/spec_builder/test_api.py
- test_create_session_linked_to_issue
- test_upload_document_triggers_processing
- test_post_message_returns_streaming_response
- test_generate_spec_produces_valid_output

tests/integration/test_architect_with_spec.py
- test_architect_includes_attached_spec_in_context
- test_architect_works_without_spec
```

### E2E Tests

```typescript
tests/e2e/spec-builder.spec.ts
- test_create_session_upload_doc_chat_generate
- test_suggestion_pills_submit_on_click
- test_spec_output_renders_markdown
- test_session_persists_across_page_reload
```

---

## Implementation Phases

### Phase 1: Core Backend (Foundation)

- Database schema + migrations
- Pydantic models
- Repository layer (CRUD)
- Docling integration for document parsing
- Chunking and embedding generation
- REST endpoints for sessions and documents

### Phase 2: Conversation Engine

- sqlite-vec query implementation
- Conversation manager with context building
- Driver integration for LLM calls
- Chat API endpoints (non-streaming first)
- WebSocket streaming integration

### Phase 3: Spec Generation

- Template loader (markdown + frontmatter)
- Built-in templates
- Section-by-section generation engine
- Architect integration (auto-attach specs)
- Generation API endpoints

### Phase 4: Frontend

- Session management UI
- Sources panel (upload, repo selector)
- Chat panel with AI SDK integration
- Suggestion pills component
- Spec output panel with preview

### Phase 5: Polish & Extensions

- Git repo file reading tools
- Keyboard shortcuts
- Export functionality
- Future source type interfaces (web, YouTube)

### Dependency Graph

```
Phase 1 ─────► Phase 2 ─────► Phase 3
    │              │              │
    └──────────────┴──────────────┴─────► Phase 4
                                              │
                                              ▼
                                         Phase 5
```

---

## Design Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary use case | Pre-planning phase | Feeds into existing Architect workflow |
| Output format | Template-based (markdown + frontmatter) | Version-controllable, human-readable |
| Interaction model | Chat with multiple choice suggestions | Reduces cognitive load, guides exploration |
| Document processing | Full ingestion with Docling | Deep semantic search capability |
| Vector storage | SQLite + sqlite-vec | Local-first, single database |
| LLM integration | Existing Amelia drivers | Consistent architecture, enterprise compliance |
| UI location | New tab in dashboard | Shared components, unified experience |
| Session organization | Linked to issues | Seamless Architect handoff |
| Conversation persistence | Full persistence | Resume sessions, review decision history |
| Git repo handling | On-demand filesystem access | No duplication, always current |
