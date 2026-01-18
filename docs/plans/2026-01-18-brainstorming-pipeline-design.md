# Brainstorming Pipeline Design

**Goal:** Enable collaborative design exploration through a chat interface, producing design documents that can hand off to the implementation pipeline.

**Architecture:** Direct chat sessions with Claude driver session continuity, NOT a LangGraph workflow. Reuses existing WebSocket infrastructure for streaming. Dedicated database tables for sessions, messages, and artifacts.

**Tech Stack:** FastAPI (endpoints), WebSocket (streaming via existing `/ws/events`), Claude CLI driver (session continuity + Oracle tool), ai-elements (React chat UI), SQLite (persistence).

---

## Overview

The Brainstorming Pipeline is a chat-based system where users collaborate with an AI agent to explore ideas and produce design documents. Unlike the Implementation Pipeline, it does not use LangGraph's interrupt/resume pattern — the Claude driver maintains conversation context via `session_id`.

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   Dashboard     │  WS     │    FastAPI      │         │  Claude Driver  │
│   ai-elements   │ ──────► │   /brainstorm   │ ──────► │  session_id     │
│   components    │ stream  │   endpoints     │         │  + Oracle tool  │
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

---

## Data Models

### BrainstormingSession

```python
class BrainstormingSession(BaseModel):
    """Tracks a brainstorming chat session."""

    id: str                           # UUID
    profile_id: str                   # Which profile/project
    driver_session_id: str | None     # Claude driver session for continuity

    status: Literal["active", "ready_for_handoff", "completed", "failed"]
    topic: str | None                 # Optional initial topic

    created_at: datetime
    updated_at: datetime
```

### Message (AI SDK UIMessage compatible)

```python
class Message(BaseModel):
    """Single message in Vercel AI SDK format."""

    id: str
    role: Literal["user", "assistant"]
    content: str
    parts: list[MessagePart] | None = None

class MessagePart(BaseModel):
    """Tool calls, results, reasoning, etc."""

    type: Literal["text", "tool-call", "tool-result", "reasoning"]
    # Type-specific fields per AI SDK spec
```

### Artifact

```python
class Artifact(BaseModel):
    """Document produced by a brainstorming session."""

    id: str
    session_id: str
    type: str                         # "design", "adr", "spec", "readme", etc.
    path: Path
    title: str | None
    created_at: datetime
```

---

## Database Schema

```sql
CREATE TABLE brainstorm_sessions (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    driver_session_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    topic TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_brainstorm_sessions_profile ON brainstorm_sessions(profile_id);
CREATE INDEX idx_brainstorm_sessions_status ON brainstorm_sessions(status);

CREATE TABLE brainstorm_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES brainstorm_sessions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    parts_json TEXT,
    created_at TIMESTAMP NOT NULL,
    UNIQUE(session_id, sequence)
);

CREATE INDEX idx_brainstorm_messages_session ON brainstorm_messages(session_id, sequence);

CREATE TABLE brainstorm_artifacts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES brainstorm_sessions(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_brainstorm_artifacts_session ON brainstorm_artifacts(session_id);
```

---

## API Endpoints

### Session Lifecycle

```
POST   /api/brainstorm/sessions              → Create new session
GET    /api/brainstorm/sessions              → List sessions
GET    /api/brainstorm/sessions/{id}         → Get session with messages
DELETE /api/brainstorm/sessions/{id}         → Delete session
```

### Chat

```
POST   /api/brainstorm/sessions/{id}/message → Send message
```

Request:
```json
{ "content": "Let's design a caching layer" }
```

Response:
```json
{ "message_id": "msg-123" }
```

Streaming happens via existing WebSocket (`/ws/events`), tagged with `session_id`.

### Handoff

```
POST   /api/brainstorm/sessions/{id}/handoff → Create implementation workflow
```

Request:
```json
{
  "artifact_path": "docs/plans/2026-01-18-caching-design.md",
  "issue": { "title": "Implement caching layer", "description": "..." }
}
```

Response:
```json
{ "workflow_id": "impl-123", "status": "created" }
```

---

## WebSocket Events

Reuse existing `/ws/events` endpoint. Client subscribes to `session_id` (treated like `workflow_id`).

### New Event Types

```python
# In amelia/server/models/events.py
BRAINSTORM_SESSION_CREATED = "brainstorm_session_created"
BRAINSTORM_REASONING = "brainstorm_reasoning"
BRAINSTORM_TOOL_CALL = "brainstorm_tool_call"
BRAINSTORM_TOOL_RESULT = "brainstorm_tool_result"
BRAINSTORM_TEXT = "brainstorm_text"
BRAINSTORM_MESSAGE_COMPLETE = "brainstorm_message_complete"
BRAINSTORM_ARTIFACT_CREATED = "brainstorm_artifact_created"
BRAINSTORM_SESSION_COMPLETED = "brainstorm_session_completed"
```

### Event Flow

```
User sends message
    ↓
POST /api/brainstorm/sessions/{id}/message
    ↓
driver.execute_agentic(prompt, session_id, instructions)
    ↓
Stream AgenticMessage → Transform → Emit WebSocket events
    ↓
Dashboard receives events, updates UI in real-time
```

### Driver Message → WebSocket Event Mapping

| `AgenticMessage` Type | WebSocket Event | ai-elements Component |
|-----------------------|-----------------|----------------------|
| `THINKING` | `brainstorm_reasoning` | `<Reasoning>` |
| `TOOL_CALL` | `brainstorm_tool_call` | `<Tool>` |
| `TOOL_RESULT` | `brainstorm_tool_result` | `<Tool>` (output) |
| `RESULT` | `brainstorm_text` | `<MessageContent>` |

---

## Brainstormer System Prompt

```python
BRAINSTORMER_SYSTEM_PROMPT = """You help turn ideas into fully formed designs through collaborative dialogue.

## Your Process

### Phase 1: Understanding
- First, explore the codebase to understand existing patterns (use Oracle if needed)
- Ask questions ONE AT A TIME to clarify the idea
- Prefer multiple choice questions when possible
- Focus on: purpose, constraints, success criteria

### Phase 2: Exploring Approaches
- Propose 2-3 different approaches with trade-offs
- Lead with your recommendation and explain why
- Let the user choose before proceeding

### Phase 3: Presenting the Design
- Present the design in sections (200-300 words each)
- After each section ask: "Does this look right so far?"
- Cover: architecture, components, data flow, error handling, testing
- Be ready to revise based on feedback

### Phase 4: Documentation
- When all sections are validated, ask: "Ready to write the document?"
- If confirmed, write the design doc to `docs/plans/YYYY-MM-DD-<topic>-design.md`
- Use clear, concise prose (active voice, no jargon, omit needless words)

## Tools Available
- **Oracle**: For researching the codebase, exploring patterns, getting expert guidance
- **File tools**: For reading existing code and writing the final document

## Key Principles
- One question at a time — don't overwhelm
- YAGNI ruthlessly — remove unnecessary features
- Validate incrementally — don't present everything at once
- Be flexible — go back and clarify when needed
"""
```

---

## Dashboard UI

### Page Structure

```
┌─────────────────────────────────────────────────────────────────┐
│  Sidebar          │  Spec Builder (full page)                   │
│  ─────────────    │                                             │
│  Dashboard        │  ┌─────────────────────────────────────┐   │
│  Workflows        │  │         Conversation                │   │
│  ► Spec Builder   │  │         (scrollable)                │   │
│  Settings         │  │                                     │   │
│                   │  │  [User message]                     │   │
│                   │  │                                     │   │
│                   │  │  [Assistant message]                │   │
│                   │  │    ├─ Reasoning (collapsible)      │   │
│                   │  │    ├─ Tool: oracle_consult         │   │
│                   │  │    └─ Response text                │   │
│                   │  │                                     │   │
│                   │  └─────────────────────────────────────┘   │
│                   │                                             │
│                   │  ┌─────────────────────────────────────┐   │
│                   │  │ [Type your message...]        [Send]│   │
│                   │  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### ai-elements Component Mapping

| UI Element | Component |
|------------|-----------|
| Chat container | `<Conversation>` + `<ConversationContent>` |
| Auto-scroll | `<ConversationScrollButton>` |
| User message | `<Message from="user">` + `<MessageContent>` |
| Assistant message | `<Message from="assistant">` |
| Thinking/reasoning | `<Reasoning>` |
| Tool calls | `<Tool>` + `<ToolHeader>` + `<ToolInput>` + `<ToolOutput>` |
| Response text | `<MessageResponse>` |
| Input box | `<PromptInput>` + `<PromptInputTextarea>` + `<PromptInputSubmit>` |

---

## Handoff Flow

1. Agent writes document via `write_file` tool
2. Backend detects artifact creation from tool result
3. Creates `brainstorm_artifacts` row
4. Emits `BRAINSTORM_ARTIFACT_CREATED` event
5. Dashboard shows handoff option

### Handoff UI

```
┌─────────────────────────────────────────────────┐
│  ✓ Design document created                      │
│                                                 │
│  docs/plans/2026-01-18-caching-design.md       │
│                                                 │
│  [View Document]  [Hand off to Implementation] │
└─────────────────────────────────────────────────┘
```

### Handoff Logic

```python
async def handoff_to_implementation(
    session_id: str,
    artifact_path: str,
    issue: Issue | None,
) -> str:
    session = await get_session(session_id)

    # Validate artifact exists
    artifact = next((a for a in session.artifacts if a.path == artifact_path), None)
    if not artifact:
        raise ValueError(f"Artifact not found: {artifact_path}")

    # Load design from file
    design = Design.from_file(Path(artifact_path))

    # Create implementation workflow
    pipeline = get_pipeline("implementation")
    workflow_id = str(uuid4())

    initial_state = pipeline.get_initial_state(
        workflow_id=workflow_id,
        profile_id=session.profile_id,
        design=design,
        issue=issue,
    )

    # Update brainstorming session status
    session.status = "completed"
    await save_session(session)

    return workflow_id
```

---

## File Structure

```
amelia/
├── server/
│   ├── models/
│   │   └── brainstorm.py           # Pydantic models
│   ├── routes/
│   │   └── brainstorm.py           # API endpoints
│   ├── services/
│   │   └── brainstorm.py           # Business logic
│   └── database/
│       └── brainstorm_repository.py # DB operations

dashboard/src/
├── pages/
│   └── SpecBuilderPage.tsx         # Main page
├── components/
│   └── brainstorm/
│       ├── BrainstormChat.tsx      # Chat container
│       ├── SessionList.tsx         # Session sidebar/list
│       ├── ArtifactCard.tsx        # Artifact display
│       └── HandoffDialog.tsx       # Handoff confirmation
├── hooks/
│   └── useBrainstormSession.ts     # Session state management
└── api/
    └── brainstorm.ts               # API client
```

---

## Implementation Phases

### Phase 2a: Backend Foundation
- [ ] Add brainstorming event types to `EventType` enum
- [ ] Create database schema and migrations
- [ ] Create Pydantic models (`BrainstormingSession`, `Message`, `Artifact`)
- [ ] Create `BrainstormRepository` for DB operations
- [ ] Create `BrainstormService` with session management

### Phase 2b: Chat Endpoint
- [ ] Implement `POST /sessions/{id}/message` endpoint
- [ ] Integrate with Claude driver (`execute_agentic` with `session_id`)
- [ ] Stream `AgenticMessage` → WebSocket events
- [ ] Detect artifact creation from `write_file` tool calls
- [ ] Store messages in database for UI display

### Phase 2c: Session Lifecycle
- [ ] Implement session CRUD endpoints
- [ ] Implement handoff endpoint
- [ ] Integration with implementation pipeline

### Phase 3: Dashboard UI (separate phase)
- [ ] Install ai-elements as dependency
- [ ] Create `SpecBuilderPage` with session list
- [ ] Create `BrainstormChat` component
- [ ] Wire up WebSocket subscription
- [ ] Implement handoff dialog

---

## Related Documents

- [Multiple Workflow Pipelines Design](./2026-01-10-multiple-workflow-pipelines-design.md) — Parent design doc
- [Oracle Consulting System](./2026-01-12-oracle-consulting-system.md) — Oracle tool integration
