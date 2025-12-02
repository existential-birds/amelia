# Web Dashboard Design

**Date:** 2025-12-01
**Status:** Draft
**Issue:** #4 - Web UI

## Overview

This document describes the design for Amelia's web dashboard - a real-time observability and control interface for the agentic orchestrator. The dashboard achieves feature parity with the CLI, allowing users to start workflows, approve plans, and monitor agent activity from the browser.

## Goals

- Real-time workflow monitoring with live activity log
- Full control: start workflows, approve/reject plans, cancel runs
- Feature parity between CLI and browser interfaces
- Foundation for future multi-workflow queue and platform integrations

## Non-Goals (MVP)

- Multi-workflow concurrent execution (single workflow only)
- Time estimates (show "--:--" until historical data available)
- Platform integrations (Telegram/Slack) - deferred to Phase 2.4
- Views beyond "Active Jobs" (show "Coming soon" placeholders)

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          User's Machine                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐                            ┌──────────────────┐   │
│  │   Browser    │◄────── WebSocket ────────► │                  │   │
│  │  (Vite/React)│        /ws/events          │  FastAPI Server  │   │
│  └──────────────┘                            │                  │   │
│                                              │  - Orchestrator  │   │
│  ┌──────────────┐                            │  - REST API      │   │
│  │  Amelia CLI  │◄──────── REST ───────────► │  - WebSocket     │   │
│  │ (thin client)│        /api/*              │  - Event Bus     │   │
│  └──────────────┘                            └────────┬─────────┘   │
│                                                       │             │
│                                                       ▼             │
│                                              ┌──────────────────┐   │
│                                              │   amelia.db      │   │
│                                              │    (SQLite)      │   │
│                                              └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Architectural Decision: Server-Centric

The FastAPI server owns the LangGraph orchestrator. Both browser and CLI are clients calling the same REST API. This enables:

- True feature parity between interfaces
- Single source of truth for workflow state
- Foundation for future platform adapters (Telegram, Slack)
- Clean separation of concerns

### Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| **FastAPI Server** | Python, FastAPI, SQLAlchemy | Runs orchestrator, REST API, WebSocket |
| **React Dashboard** | Vite, React, TypeScript | Real-time UI for monitoring and control |
| **CLI Client** | Python, Typer, httpx | Thin client calling server APIs |
| **Database** | SQLite | Persists workflows, events, token usage |
| **Event Bus** | Python asyncio | Pub/sub for real-time WebSocket broadcast |

---

## Data Models

### New Models

```python
class WorkflowEvent(BaseModel):
    """Event for activity log and real-time updates."""
    id: str                          # UUID
    workflow_id: str                 # Links to ExecutionState
    timestamp: datetime              # When event occurred
    agent: str                       # "architect", "developer", "reviewer", "system"
    event_type: str                  # "stage_started", "file_created", "review_requested"
    message: str                     # Human-readable summary
    data: dict | None = None         # Structured payload

class TokenUsage(BaseModel):
    """Token consumption tracking per agent."""
    workflow_id: str
    agent: str
    input_tokens: int
    output_tokens: int
    timestamp: datetime
```

### Extended ExecutionState

```python
class ExecutionState(BaseModel):
    # ... existing fields ...
    id: str                                    # NEW: UUID for persistence
    started_at: datetime | None                # NEW: Workflow start time
    stage_timestamps: dict[str, datetime]      # NEW: When each stage started
    workflow_status: WorkflowStatus            # UPDATED: Added "blocked"

WorkflowStatus = Literal["pending", "in_progress", "blocked", "completed", "failed"]
# "blocked" = awaiting human approval
```

### Database Tables

| Table | Purpose |
|-------|---------|
| `workflows` | ExecutionState records (JSON blob + indexed fields) |
| `events` | WorkflowEvent records for activity log |
| `token_usage` | Token counts per agent per workflow |

---

## REST API

**Base URL:** `http://localhost:8420/api`

### Workflow Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/workflows` | Start new workflow `{issue_id, profile?}` |
| `GET` | `/workflows` | List all workflows (with filters) |
| `GET` | `/workflows/active` | Get currently running workflow |
| `GET` | `/workflows/{id}` | Get workflow details + plan |
| `POST` | `/workflows/{id}/approve` | Approve plan (unblocks workflow) |
| `POST` | `/workflows/{id}/reject` | Reject plan with feedback |
| `POST` | `/workflows/{id}/cancel` | Cancel running workflow |

### Event Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/workflows/{id}/events` | Get events (activity log) |
| `GET` | `/workflows/{id}/tokens` | Get token usage breakdown |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `WS /ws/events` | Real-time event stream, broadcasts all WorkflowEvents |

### CLI Mapping

```bash
amelia server              # Start the server
amelia start ISSUE-123     # POST /api/workflows {issue_id: "ISSUE-123"}
amelia approve             # POST /api/workflows/{id}/approve
amelia reject "reason"     # POST /api/workflows/{id}/reject
amelia status              # GET /api/workflows/active
amelia cancel              # POST /api/workflows/{id}/cancel
```

---

## Frontend Structure

### Project Layout

```
dashboard/
├── src/
│   ├── main.tsx              # Entry point
│   ├── App.tsx               # Router + layout
│   ├── api/
│   │   ├── client.ts         # REST API client
│   │   └── websocket.ts      # WebSocket connection manager
│   ├── components/
│   │   ├── Sidebar.tsx       # Navigation
│   │   ├── Header.tsx        # Workflow title, ETA, status
│   │   ├── WorkflowGraph.tsx # Pipeline visualization
│   │   ├── JobQueue.tsx      # Workflow list panel
│   │   ├── ActivityLog.tsx   # Event stream panel
│   │   ├── StatusBadge.tsx   # Status indicators
│   │   └── ComingSoon.tsx    # Placeholder for future views
│   ├── hooks/
│   │   ├── useWorkflow.ts    # Fetch + subscribe to workflow
│   │   └── useWebSocket.ts   # WebSocket connection hook
│   ├── types/
│   │   └── index.ts          # TypeScript types
│   └── styles/
│       └── theme.ts          # Dark theme colors
├── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```

### Design Theme

Based on the Amelia Earhart aviation aesthetic from the design mock:

```typescript
const theme = {
  bg: {
    dark: '#0D1A12',      // Sidebar, panels
    main: '#1F332E'       // Main background
  },
  text: {
    primary: '#EFF8E2',   // Headers, main text
    secondary: '#88A896', // Labels, timestamps
    muted: '#5B8A72'      // Disabled, hints
  },
  accent: {
    gold: '#FFC857',      // Logo, active states
    blue: '#5B9BD5'       // Links, IDs
  },
  status: {
    running: '#FFC857',   // Amber - in progress
    completed: '#5B8A72', # Green - done
    pending: '#4A5C54',   // Gray - queued
    blocked: '#D4A53D',   // Orange - awaiting approval
    failed: '#C94A3A'     // Red - error
  }
};
```

### Navigation Structure

| Section | View | MVP Status |
|---------|------|------------|
| **WORKFLOWS** | Active Jobs | Functional |
| | Agents | Coming soon |
| | Outputs | Coming soon |
| **HISTORY** | Past Runs | Coming soon |
| | Milestones | Coming soon |
| | Deployments | Coming soon |
| **MONITORING** | Logs | Coming soon |
| | Notifications | Coming soon |

---

## Server Structure

### Package Layout

```
amelia/
├── server/                    # NEW: FastAPI server package
│   ├── __init__.py
│   ├── main.py               # FastAPI app, mounts routes
│   ├── routes/
│   │   ├── workflows.py      # /api/workflows/* endpoints
│   │   └── websocket.py      # /ws/events handler
│   ├── services/
│   │   ├── orchestrator.py   # Wraps LangGraph, emits events
│   │   └── event_bus.py      # Pub/sub for WebSocket broadcast
│   └── database/
│       ├── models.py         # SQLAlchemy/SQLModel tables
│       └── repository.py     # CRUD operations
├── core/
│   └── orchestrator.py       # Existing LangGraph (logic unchanged)
├── main.py                   # CLI (refactored to thin client)
```

### Event Emission

Orchestrator nodes wrapped to emit events on state transitions:

```python
async def call_architect_node(state: ExecutionState) -> ExecutionState:
    event_bus.emit(WorkflowEvent(
        agent="architect",
        event_type="stage_started",
        message="Parsing issue and creating task DAG"
    ))
    result = await original_architect_logic(state)
    event_bus.emit(WorkflowEvent(
        agent="architect",
        event_type="stage_completed",
        message=f"Plan created with {len(result.plan.tasks)} tasks"
    ))
    return result
```

### Human Approval Flow

Refactored from CLI input blocking to REST-based:

1. Orchestrator reaches approval gate
2. Sets `workflow_status = "blocked"`
3. Persists state to SQLite
4. Emits `WorkflowEvent(event_type="approval_required")`
5. Waits for `POST /api/workflows/{id}/approve`
6. On approval, sets `workflow_status = "in_progress"` and continues

---

## Token Tracking

### Driver-Level Implementation

Modify `BaseDriver` to capture and return token counts:

```python
class DriverResponse(BaseModel):
    content: str
    token_usage: TokenUsage | None = None

class BaseDriver(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> DriverResponse:
        """Generate response with token tracking."""
```

### Research Required

> **Action Item:** Verify Claude CLI exposes token usage in output. If not, implement estimation via tiktoken as fallback.

---

## Implementation Phases

### Phase 2.1: Foundation (Server + Database)

- FastAPI server skeleton with health endpoint
- SQLite setup with SQLAlchemy/SQLModel
- `WorkflowEvent` and `TokenUsage` models
- Basic REST endpoints (CRUD for workflows)
- `amelia server` command to start it
- Unit tests for API endpoints

### Phase 2.2: Orchestrator Migration

- Move orchestrator execution into server
- Event bus for broadcasting state changes
- Human approval via REST (replace CLI input)
- WebSocket endpoint for real-time events
- Refactor CLI to thin client
- Token tracking in drivers
- Integration tests for orchestrator

### Phase 2.3: Dashboard UI

- Vite + React + TypeScript project setup
- WebSocket connection hook
- Port mock components to proper React
- Active Jobs view (fully functional)
- Placeholder views for other nav items
- Serve dashboard from FastAPI (static files)
- E2E tests with Playwright

### Phase 2.4: Platform Adapters (Future)

Enable Telegram, Slack, and other messaging platform integrations using adapter pattern:

```python
class PlatformAdapter(Protocol):
    """Common interface for messaging platforms."""
    async def send_message(self, conversation_id: str, message: str) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

class TelegramAdapter(PlatformAdapter):
    """Telegraf-based, polling transport."""

class SlackAdapter(PlatformAdapter):
    """Socket Mode or Events API webhooks."""
```

Architecture supports this via event bus subscription:

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Telegram   │  │    Slack    │  │   Browser   │
│   Adapter   │  │   Adapter   │  │  WebSocket  │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       └────────────────┼────────────────┘
                        ▼
              ┌─────────────────┐
              │    Event Bus    │
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │   Orchestrator  │
              └─────────────────┘
```

Platform adapters subscribe to same events as WebSocket, format messages for their platform. Human approval could come from any connected platform.

---

## Testing Strategy

Following TDD - tests first, then implementation.

### Test Structure

```
tests/
├── unit/
│   ├── server/
│   │   ├── test_routes_workflows.py
│   │   ├── test_routes_websocket.py
│   │   ├── test_services_orchestrator.py
│   │   ├── test_services_event_bus.py
│   │   └── test_database_repository.py
│   └── drivers/
│       └── test_token_tracking.py
├── integration/
│   ├── test_server_orchestrator.py
│   └── test_cli_thin_client.py
└── e2e/
    └── test_dashboard.py
```

### TDD Approach Per Phase

| Phase | Write tests for... | Then implement... |
|-------|-------------------|-------------------|
| 2.1 | API routes, DB persistence | FastAPI routes, SQLite repository |
| 2.2 | Event emission, approval flow | Event bus, orchestrator wrapper |
| 2.3 | Component rendering, WebSocket updates | React components, hooks |

### Key Fixtures

```python
@pytest.fixture
def test_client():
    """FastAPI TestClient for API tests."""

@pytest.fixture
def mock_event_bus():
    """Captures emitted events for assertion."""

@pytest.fixture
def sample_workflow_events():
    """Realistic event sequence for UI tests."""
```

---

## Open Questions

### Research Required

| Topic | Question | Action |
|-------|----------|--------|
| Claude CLI tokens | Does CLI output token usage? | Search web, test CLI output |
| AI Elements library | README mentions it - ready to use? | Check repo status |

### Deferred Decisions

| Topic | Current Approach | Revisit When |
|-------|-----------------|--------------|
| Time estimates | Show "--:--" | Have historical data |
| Multi-workflow queue | Single workflow | Phase 3 or user demand |
| Notifications | "Coming soon" | Core dashboard stable |

### Assumptions

1. SQLite sufficient for single-user local use
2. Server port 8420 available (make configurable)
3. Dashboard served from same origin (no CORS)
4. Token tracking addable without breaking driver interface

---

## References

- [Design Mock (HTML)](./amelia-dashboard-dark.html)
- [Design Mock (Image)](./design_mock.jpg)
- [README Phase 2 Description](../../README.md#phase-2-web-ui)
- [remote-agentic-coding-system](https://github.com/ka/remote-agentic-coding-system) - Platform adapter pattern reference
