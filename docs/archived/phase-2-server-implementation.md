# Phase 2: Server Architecture Implementation

> **Historical Reference Document**
>
> This document consolidates the implementation plans for Phase 2.1 (Server Foundation) and Phase 2.2 (Real-time Events & CLI). These plans were completed in December 2025.

---

## Overview

Phase 2 transformed Amelia from a CLI-only tool to a client-server architecture with:
- FastAPI-based REST API server
- SQLite database with event sourcing
- WebSocket real-time event streaming
- Thin CLI client delegating to server

### Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Client                               │
│  (amelia start, approve, reject, status, cancel)                │
└─────────────────────┬───────────────────────────────────────────┘
                      │ HTTP/REST + WebSocket
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Server                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ REST Routes  │  │  WebSocket   │  │   Health Endpoints   │   │
│  │ /api/workflows│  │  /ws/events  │  │   /api/health/*     │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────┘   │
│         │                 │                                      │
│         ▼                 ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   OrchestratorService                     │   │
│  │  - Concurrent workflow execution                          │   │
│  │  - Approval gates (human-in-the-loop)                     │   │
│  │  - State machine validation                               │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                             │                                    │
│         ┌───────────────────┼───────────────────┐               │
│         ▼                   ▼                   ▼               │
│  ┌────────────┐    ┌────────────────┐   ┌────────────────┐      │
│  │  EventBus  │    │ WorkflowRepo   │   │   Database     │      │
│  │  (Pub/Sub) │    │  (Repository)  │   │   (SQLite)     │      │
│  └────────────┘    └────────────────┘   └────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 2.1: Server Foundation

### Plan 1: Server Foundation

**Goal:** Create FastAPI server skeleton with configuration and health endpoints.

**Components Created:**
| Component | Location | Purpose |
|-----------|----------|---------|
| ServerConfig | `amelia/server/config.py` | pydantic-settings configuration with env var support |
| FastAPI App | `amelia/server/main.py` | Application factory with lifespan management |
| Health Routes | `amelia/server/routes/health.py` | Liveness/readiness probes, system metrics |
| Server CLI | `amelia/server/cli.py` | `amelia server` command to start server |
| Logging | `amelia/server/logging.py` | Structured JSON logging with structlog |

**Key Decisions:**
- Port 8420 as default (configurable via `AMELIA_PORT`)
- Localhost-only binding by default (security)
- `/api/` prefix for all routes
- Swagger docs at `/api/docs`

---

### Plan 2: Database Foundation

**Goal:** Implement SQLite database with migrations, connection management, and initial schema.

**Components Created:**
| Component | Location | Purpose |
|-----------|----------|---------|
| Database | `amelia/server/database/connection.py` | Async SQLite connection with WAL mode |
| Schema | `amelia/server/database/schema.py` | `CREATE TABLE IF NOT EXISTS` for idempotent setup |

**Key Decisions:**
- SQLite with WAL mode for concurrent read/write
- aiosqlite for async operations
- Simplified schema creation (no Alembic migrations)
- Database path: `~/.amelia/amelia.db`

**Schema Tables:**
- `workflows` - Workflow metadata and status
- `events` - Event sourcing log
- `token_usage` - Token consumption tracking

---

### Plan 3: Workflow Models & Repository

**Goal:** Implement workflow domain models and repository with state machine validation.

**Components Created:**
| Component | Location | Purpose |
|-----------|----------|---------|
| EventType | `amelia/server/models/events.py` | Enum of all workflow event types |
| WorkflowEvent | `amelia/server/models/events.py` | Event sourcing events |
| TokenUsage | `amelia/server/models/tokens.py` | Token tracking per stage |
| ServerExecutionState | `amelia/server/models/state.py` | Workflow state with transitions |
| WorkflowRepository | `amelia/server/database/repository.py` | CRUD operations with state machine |

**Workflow Status Transitions:**
```
pending → in_progress → blocked → in_progress → completed
                    ↘           ↗            ↘
                      cancelled              failed
```

**Key Decisions:**
- Event sourcing lite (append-only events, computed state)
- State machine validation on all transitions
- Sequence numbers for ordering
- Pydantic models for all data structures

---

### Plan 4: REST API Endpoints

**Goal:** Implement REST API endpoints for workflow lifecycle management.

**Endpoints Created:**
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/workflows` | Create new workflow |
| GET | `/api/workflows/{id}` | Get workflow details |
| GET | `/api/workflows/active` | List active workflows |
| POST | `/api/workflows/{id}/approve` | Approve blocked workflow |
| POST | `/api/workflows/{id}/reject` | Reject with feedback |
| POST | `/api/workflows/{id}/cancel` | Cancel active workflow |

**Components Created:**
| Component | Location | Purpose |
|-----------|----------|---------|
| Request Models | `amelia/server/models/requests.py` | Validated request payloads |
| Response Models | `amelia/server/models/responses.py` | Typed response schemas |
| Exceptions | `amelia/server/exceptions.py` | Custom HTTP exception classes |
| Workflows Router | `amelia/server/routes/workflows.py` | REST endpoint handlers |

**Key Decisions:**
- Cursor-based pagination for workflow lists
- 409 Conflict for duplicate worktree workflows
- 429 Too Many Requests for concurrency limit
- 422 Unprocessable Entity for invalid state transitions

---

## Phase 2.2: Real-time Events & CLI

### Plan 5: Event Bus & Orchestrator Service

**Goal:** Implement event bus for real-time broadcasting and orchestrator for workflow execution.

**Components Created:**
| Component | Location | Purpose |
|-----------|----------|---------|
| EventBus | `amelia/server/events/bus.py` | Pub/sub for event broadcasting |
| OrchestratorService | `amelia/server/orchestrator.py` | Concurrent workflow execution |
| ServerLifecycle | `amelia/server/lifecycle.py` | Graceful startup/shutdown |
| LogRetentionService | `amelia/server/retention.py` | Event log cleanup |
| WorktreeHealthChecker | `amelia/server/health_checker.py` | Periodic worktree validation |

**Key Decisions:**
- Max 5 concurrent workflows (configurable)
- Sequence locking for thread-safe event emission
- Approval gates pause execution until human approval
- Background tasks for cleanup and health checks

---

### Plan 6: WebSocket Events

**Goal:** Implement WebSocket endpoint for real-time event streaming.

**Components Created:**
| Component | Location | Purpose |
|-----------|----------|---------|
| WebSocket Messages | `amelia/server/models/websocket.py` | Protocol message types |
| ConnectionManager | `amelia/server/routes/websocket.py` | Subscription management |
| WebSocket Route | `amelia/server/routes/websocket.py` | `/ws/events` endpoint |

**Protocol Messages:**
- Client → Server: `subscribe`, `unsubscribe`, `ping`
- Server → Client: `event`, `subscribed`, `unsubscribed`, `error`, `pong`

**Key Decisions:**
- Subscription filtering by workflow_id
- Reconnection backfill with `?since=` parameter
- Heartbeat ping/pong for connection health
- Graceful disconnect on server shutdown

---

### Plan 7: CLI Thin Client

**Goal:** Refactor CLI to delegate to server via REST API calls.

**Components Created:**
| Component | Location | Purpose |
|-----------|----------|---------|
| Git Utils | `amelia/client/git.py` | Worktree context detection |
| API Client | `amelia/client/api.py` | httpx REST client |
| Client Models | `amelia/client/models.py` | Server-aligned request/response |
| CLI Commands | `amelia/client/cli.py` | Thin client command implementations |

**CLI Commands:**
| Command | Purpose |
|---------|---------|
| `amelia start ISSUE-123` | Create workflow via server (new) |
| `amelia start-direct ISSUE-123` | Legacy direct orchestrator (renamed) |
| `amelia approve` | Approve blocked workflow |
| `amelia reject "feedback"` | Reject with feedback |
| `amelia status` | Show active workflows |
| `amelia status --all` | Show all worktree workflows |
| `amelia cancel` | Cancel active workflow |

**Key Decisions:**
- Auto-detect worktree from current directory
- Server error codes mapped to descriptive exceptions
- Legacy `start` renamed to `start-direct` (breaking change)

---

## Tech Stack Summary

| Category | Technology |
|----------|------------|
| Web Framework | FastAPI |
| Database | SQLite (WAL mode) + aiosqlite |
| Configuration | pydantic-settings |
| HTTP Client | httpx |
| CLI | typer + rich |
| Logging | structlog (JSON) + loguru |
| Validation | Pydantic v2 |
| Testing | pytest + pytest-asyncio + httpx |

---

## Files Created

### Server Package (`amelia/server/`)
```
amelia/server/
├── __init__.py
├── config.py              # ServerConfig with env vars
├── main.py                # FastAPI app factory
├── cli.py                 # Server CLI commands
├── logging.py             # Structured logging
├── exceptions.py          # Custom exceptions
├── lifecycle.py           # Startup/shutdown
├── orchestrator.py        # Workflow execution
├── retention.py           # Log cleanup
├── health_checker.py      # Worktree validation
├── database/
│   ├── __init__.py
│   ├── connection.py      # Database class
│   ├── schema.py          # Table definitions
│   └── repository.py      # WorkflowRepository
├── events/
│   ├── __init__.py
│   └── bus.py             # EventBus pub/sub
├── models/
│   ├── __init__.py
│   ├── events.py          # EventType, WorkflowEvent
│   ├── state.py           # ServerExecutionState
│   ├── tokens.py          # TokenUsage
│   ├── requests.py        # API request models
│   ├── responses.py       # API response models
│   └── websocket.py       # WebSocket messages
└── routes/
    ├── __init__.py
    ├── health.py          # Health endpoints
    ├── workflows.py       # Workflow REST API
    └── websocket.py       # WebSocket endpoint
```

### Client Package (`amelia/client/`)
```
amelia/client/
├── __init__.py
├── git.py                 # Worktree detection
├── api.py                 # REST API client
├── models.py              # Request/response models
└── cli.py                 # Thin client commands
```

---

## Implementation Notes

1. **Migration System Simplified:** Originally planned Alembic migrations were replaced with `CREATE TABLE IF NOT EXISTS` for simpler idempotent schema setup.

2. **Lifespan Pattern:** Used FastAPI's lifespan context manager instead of deprecated `on_event` handlers for startup/shutdown.

3. **DI Pattern:** Dependency injection via FastAPI's `Depends()` with `get_repository()`, `get_orchestrator()`, `get_connection_manager()`.

4. **Breaking Change:** `amelia start` now delegates to server. Use `amelia start-direct` for legacy direct execution without server.

5. **Error Codes:** Server returns structured error responses with `code`, `error`, and optional `details` fields.

---

## Related Documents

- `docs/architecture.md` - Current system architecture
- `docs/configuration.md` - Configuration reference
- `docs/archived/001-agentic-orchestrator/` - Original MVP specification

---

*Archived: December 2025*
