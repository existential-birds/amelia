# Oracle Phase 1 Design — Foundation

**Goal:** Build the Oracle consultation system foundation: a standalone agent that accepts a problem + codebase context and returns expert advice using agentic LLM execution.

**Related Issues:**
- #290 — RLM Integration (this is Phase 1 of that plan)
- #203 — Knowledge Library (future Phase 2 dependency)

**References:**
- `docs/plans/2026-01-17-rlm-integration-design.md` — Full RLM integration design

---

## Scope

Phase 1 delivers:
- **FileBundler** — standalone codebase file gathering utility
- **Oracle agent** — agentic consultation using `execute_agentic()`
- **OracleConsultation model** — state tracking and persistence
- **API endpoint** — `POST /api/oracle/consult` with WebSocket event streaming

Phase 1 does **not** include:
- Knowledge Library / RAG integration (Phase 2)
- RLM structured tools / recursive processing (Phase 3)
- Agent integration (Architect/Reviewer calling Oracle) (Phase 4)
- Token budgeting or context truncation

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Oracle location | `amelia/agents/oracle.py` | Alongside other agents; Oracle is conceptually an agent |
| LLM execution | `driver.execute_agentic()` | Agentic from day one; Oracle can use shell/file tools while reasoning. Natural upgrade path to RLM tools in Phase 3 |
| Integration point | API endpoint only | Phase 1 is standalone. Agent tool registration comes in Phase 4 |
| FileBundler location | `amelia/tools/file_bundler.py` | Standalone, reusable utility |
| Token budgeting | Deferred | No max_tokens enforcement in Phase 1. Token counts tracked for metrics only |
| .gitignore | Respected by default | FileBundler uses `git ls-files` to exclude gitignored files |

---

## Component 1: FileBundler

**File:** `amelia/tools/file_bundler.py`

Gathers codebase files by glob patterns, estimates token counts, and returns structured bundles.

### Types

```python
class BundledFile(BaseModel):
    """A single file with its content and metadata."""
    path: str              # Relative to working_dir
    content: str
    token_estimate: int

class FileBundle(BaseModel):
    """Collection of gathered files with aggregate metrics."""
    files: list[BundledFile]
    total_tokens: int
    working_dir: str
```

### Interface

```python
async def bundle_files(
    working_dir: str,
    patterns: list[str],                    # Glob patterns: ["src/**/*.py", "*.md"]
    exclude_patterns: list[str] | None = None,  # Additional exclusions
) -> FileBundle:
```

### Behavior

- Resolves globs relative to `working_dir`
- Respects `.gitignore` via `git ls-files` when in a git repo; falls back to hardcoded exclusions (`node_modules`, `__pycache__`, `.venv`, `.git`, `dist`, `build`) outside git repos
- Reads file contents asynchronously via `asyncio.to_thread`
- Estimates tokens using tiktoken (`cl100k_base` encoding); counts are approximate for non-OpenAI models
- Skips binary files (detected by null bytes in first 512 bytes)
- Path traversal prevention: all resolved paths must be within `working_dir`
- `working_dir` itself is validated at the API layer — must be within the profile's configured working directory

---

## Component 2: Oracle Agent

**File:** `amelia/agents/oracle.py`

Accepts a problem and codebase context, reasons about it using an agentic LLM session with tool access.

### Class

```python
class Oracle:
    def __init__(
        self,
        config: AgentConfig,
        event_bus: EventBus | None = None,
    ):
        self._driver = get_driver(
            driver_key=config.driver,
            model=config.model,
            cwd=".",
        )
        self._event_bus = event_bus
        self._config = config

    async def consult(
        self,
        problem: str,
        working_dir: str,
        files: list[str] | None = None,
        workflow_id: str | None = None,
    ) -> OracleConsultResult:
```

### Flow

1. Emit `ORACLE_CONSULTATION_STARTED` via EventBus
2. Use FileBundler to gather codebase context from `working_dir` + `files` patterns
3. Build a system prompt: "You are a consulting expert. Analyze the codebase context and provide advice on the given problem."
4. Assemble prompt with problem statement + bundled file contents
5. Call `self._driver.execute_agentic()` with `cwd=working_dir`
6. Stream `AgenticMessage` events, emitting `ORACLE_CONSULTATION_THINKING` events via EventBus
7. Collect the final result text
8. Build `OracleConsultResult` with consultation metadata
9. Emit `ORACLE_CONSULTATION_COMPLETED` or `ORACLE_CONSULTATION_FAILED`

### Return Type

```python
class OracleConsultResult(BaseModel):
    """Result from an Oracle consultation."""
    advice: str
    consultation: OracleConsultation  # Full record for persistence
```

### Design Notes

- Oracle uses `execute_agentic()` so it can read additional files, run shell commands, and reason interactively — not just process a static context dump
- The FileBundler output provides initial context; the agentic loop lets Oracle go deeper
- `workflow_id` is optional: consultations work standalone (API) or within workflows (Phase 4)

---

## Component 3: OracleConsultation Model

### Data Model

Added to `amelia/core/types.py`:

```python
class OracleConsultation(BaseModel):
    """Record of an Oracle consultation for persistence and analytics."""
    timestamp: datetime
    problem: str
    advice: str | None = None
    model: str
    session_id: str              # UUIDv4, generated per-consultation by Oracle.consult()
    tokens: dict[str, int] = Field(default_factory=dict)
    cost_usd: float | None = None
    files_consulted: list[str] = Field(default_factory=list)
    outcome: Literal["success", "error"] = "success"
    error_message: str | None = None
```

`session_id` is a UUIDv4 generated by `Oracle.consult()` at the start of each consultation. It uniquely identifies a single consultation for logging, event correlation, and analytics. When Oracle is called within a workflow (Phase 4), the `workflow_id` is passed separately for cross-referencing but `session_id` remains consultation-scoped.

### State Integration

Added to `amelia/pipelines/base.py`:

```python
class BasePipelineState(BaseModel):
    # ... existing fields ...

    # Oracle consultations (append-only)
    oracle_consultations: Annotated[
        list[OracleConsultation], operator.add
    ] = Field(default_factory=list)
```

Uses LangGraph's append-only reducer, matching the existing `history` pattern.

### Event Types

Added to `amelia/server/models/events.py`:

```python
class EventType(StrEnum):
    # ... existing events ...

    # Oracle events
    ORACLE_CONSULTATION_STARTED = "oracle_consultation_started"
    ORACLE_CONSULTATION_THINKING = "oracle_consultation_thinking"
    ORACLE_CONSULTATION_COMPLETED = "oracle_consultation_completed"
    ORACLE_CONSULTATION_FAILED = "oracle_consultation_failed"
```

---

## Component 4: API Endpoint

**File:** `amelia/server/routes/oracle.py`

### Endpoint

`POST /api/oracle/consult`

### Request

```python
class OracleConsultRequest(BaseModel):
    problem: str
    working_dir: str
    files: list[str] | None = None
    model: str | None = None
    profile_id: str | None = None
```

### Response

```python
class OracleConsultResponse(BaseModel):
    advice: str
    consultation: OracleConsultation
```

### Behavior

1. Resolve profile from `profile_id` or active profile
2. Validate `working_dir`: must resolve to a path within the profile's configured `working_dir` (reject requests with paths outside the profile root)
3. Get `oracle` agent config from profile via `profile.get_agent_config("oracle")` — returns `400` if the profile has no `agents.oracle` section (consistent with how missing architect/developer/reviewer configs are handled)
4. Override model if provided in request
5. Instantiate `Oracle(config=agent_config, event_bus=event_bus)`
6. Call `oracle.consult(problem, working_dir, files)`
7. Events stream via WebSocket in real-time (same pattern as brainstorm streaming)
8. Return `OracleConsultResponse`

### Profile Config

Oracle gets its own agent config section:

```yaml
agents:
  oracle:
    driver: api
    model: claude-sonnet-4-20250514
```

Follows the same pattern as `architect`, `developer`, `reviewer` configs.

### Route Registration

Registered in `amelia/server/app.py` via `app.include_router(oracle_router)`.

---

## File Layout

### New Files

| File | Purpose |
|------|---------|
| `amelia/tools/file_bundler.py` | FileBundler utility |
| `amelia/agents/oracle.py` | Oracle agent |
| `amelia/server/routes/oracle.py` | API endpoint |
| `tests/unit/test_file_bundler.py` | FileBundler tests |
| `tests/unit/test_oracle.py` | Oracle agent tests |
| `tests/unit/test_oracle_routes.py` | API endpoint tests |

### Modified Files

| File | Change |
|------|--------|
| `amelia/core/types.py` | Add `OracleConsultation` model |
| `amelia/pipelines/base.py` | Add `oracle_consultations` to `BasePipelineState` |
| `amelia/server/models/events.py` | Add Oracle event types |
| `amelia/server/app.py` | Register Oracle router |
| Profile schema | Add `oracle` agent config |

---

## Future Phases

This foundation enables:

- **Phase 2:** Knowledge Library adds `doc_ids` parameter to Oracle, FileBundler gains doc retrieval
- **Phase 3:** RLM tools (search_pattern, get_section, chunk_by_structure, query_subset, summarize, request_capability) added to Oracle's agentic loop
- **Phase 4:** `oracle_consult` registered as a tool for Architect/Developer/Reviewer agents
- **Phase 5:** Spec Builder integration
