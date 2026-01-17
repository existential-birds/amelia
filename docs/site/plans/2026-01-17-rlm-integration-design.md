# RLM Integration Design

**Goal:** Enhance Amelia's agents (Architect, Reviewer, future Spec Builder) with the ability to deeply process large documents from the Knowledge Library using the Recursive Language Model (RLM) approach.

**Related Issues:**
- #203 - Knowledge Library (shared RAG infrastructure)
- #204 - Spec Builder (document-assisted design tool)
- Oracle Consulting System (existing implementation plan)

**References:**
- `docs/research/recursive_language_models.md` - RLM paper analysis

---

## Background

### The Problem

When Amelia's agents need knowledge about third-party libraries, frameworks, or research papers:

1. **Architect** must query the web or infer from training data — inefficient and potentially outdated
2. **Reviewer** cannot validate library usage patterns against authoritative documentation
3. **Spec Builder** (future) needs to synthesize large white papers and RFCs into specs

### The RLM Insight

From the paper "Recursive Language Models" (Zhang, Khattab, Kraska - MIT CSAIL):

> "The key insight is that long prompts should not be fed into the neural network directly but should instead be treated as part of the environment that the LLM can symbolically interact with."

Instead of stuffing large documents into the prompt (causing context rot and high cost), RLM treats documents as external objects that the LLM manipulates through structured operations and recursive sub-queries.

**Key findings from the paper:**
- Crossover point: ~16K tokens — below this, base LLM often outperforms RLM
- Task complexity matters: complex reasoning benefits from RLM at shorter lengths
- Cost is comparable at median, but high variance due to trajectory lengths

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Agent                                │
│  (Architect, Reviewer, Spec Builder)                        │
│                                                              │
│  1. Queries Knowledge Library (RAG) for relevant docs       │
│  2. Calls Oracle with problem + depth_hint + working_dir    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                        Oracle                                │
│                                                              │
│  • Receives problem + depth_hint + working_dir              │
│  • Queries Knowledge Library for full doc content           │
│  • Accesses codebase via working_dir (FileBundler)          │
│  • Decides: direct injection vs RLM processing              │
│  • If RLM: uses structured tools in a loop                  │
│  • Returns synthesized knowledge + session metrics          │
└────────────┬─────────────────────────────────┬──────────────┘
             │                                 │
             ▼                                 ▼
┌────────────────────────┐       ┌────────────────────────────┐
│   Knowledge Library    │       │        Codebase            │
│                        │       │                            │
│  • Framework docs      │       │  • Current project files   │
│  • White papers        │       │  • Via FileBundler globs   │
│  • Specs, RFCs         │       │  • working_dir from agent  │
└────────────────────────┘       └────────────────────────────┘
```

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| When to use RLM | Hybrid: RAG discovery + RLM for >16K tokens or complex tasks | Paper shows crossover at ~16K; task complexity matters |
| Implementation | Structured tools (not Python REPL) | Cleaner, safer, composable; can add tools via `request_capability` |
| Integration point | Oracle as the RLM agent | Clean separation; agents delegate deep processing |
| Decision-making | Oracle decides with `depth_hint` | Centralizes logic; agents can override when needed |
| Tool set | Full set from paper patterns (7 tools) | Cover known patterns upfront |
| Caching | Session-scoped | Simple, no staleness; good enough for v1 |
| Doc retrieval | Oracle queries Knowledge Library directly | Self-sufficient Oracle; simpler agent code |
| Codebase access | Oracle receives `working_dir`, uses FileBundler | Enables grounded answers with actual code context |
| Gap detection | `request_capability()` → dashboard + analytics | Closes feedback loop for tool evolution |

---

## Oracle Internals

### Decision Flow

```
oracle_consult(problem, depth_hint, working_dir, doc_ids?)
                           │
                           ▼
                ┌─────────────────────┐
                │  Gather context     │
                │  • Fetch docs from KL│
                │  • Gather codebase  │
                │    files if needed  │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │  Evaluate total     │
                │  context size +     │
                │  depth_hint         │
                └──────────┬──────────┘
                           │
            ┌──────────────┴──────────────┐
            │                             │
            ▼                             ▼
   depth_hint=quick              depth_hint=thorough
   OR size < 16K                 OR size > 16K
   OR auto + simple question     OR auto + complex question
            │                             │
            ▼                             ▼
   ┌────────────────┐           ┌─────────────────┐
   │ Direct inject  │           │ RLM processing  │
   │ into prompt,   │           │ loop with       │
   │ single LLM call│           │ structured tools│
   └────────────────┘           └─────────────────┘
            │                             │
            └──────────────┬──────────────┘
                           ▼
                ┌─────────────────────┐
                │  Return result +    │
                │  session metrics    │
                └─────────────────────┘
```

### RLM Tool Set

| Tool | Signature | Purpose |
|------|-----------|---------|
| `search_pattern` | `(doc_id, regex) → matches[]` | Find sections matching pattern |
| `get_section` | `(doc_id, section_path) → content` | Extract specific section |
| `chunk_by_size` | `(doc_id, max_tokens) → chunks[]` | Split into token-limited pieces |
| `chunk_by_structure` | `(doc_id) → sections[]` | Split by headings/logical units |
| `query_subset` | `(content, question) → answer` | Recursive LLM call on subset |
| `summarize` | `(content) → summary` | Condense for overview |
| `request_capability` | `(description) → logged` | Signal missing tool need |

### Session Cache

All tool results cached by `hash(tool + params)` for workflow duration. Cleared when workflow ends.

---

## Agent Integration

### Architect Agent

```python
# During plan() method, when library knowledge needed:
result = await oracle_consult(
    problem="How should I structure authentication using FastAPI's security utilities?",
    depth_hint="thorough",  # Planning needs deep understanding
    working_dir="/path/to/project",
    doc_ids=["fastapi-docs", "pydantic-docs"],  # Optional: pre-identified
)
# Result injected into planning context
```

**Triggers:** Architect detects it needs library knowledge when:
- Issue mentions unfamiliar frameworks
- CLAUDE.md references libraries without detailed patterns
- Planning requires API design decisions

### Reviewer Agent

```python
# During agentic_review(), when validating library usage:
result = await oracle_consult(
    problem="Is this React Query mutation pattern correct? Does it handle optimistic updates properly?",
    depth_hint="thorough",
    working_dir="/path/to/project",
    doc_ids=["react-query-docs"],
)
# Result informs review feedback
```

**Triggers:** Reviewer consults Oracle when:
- Code uses patterns it's uncertain about
- Changes touch library integration points
- Best practices validation needed

### Spec Builder (Future)

```python
# During spec generation, when synthesizing from research:
result = await oracle_consult(
    problem="What are the key architectural patterns from this distributed systems paper that apply to our use case?",
    depth_hint="thorough",
    working_dir="/path/to/project",
    doc_ids=["distributed-systems-whitepaper"],
)
# Result feeds into spec template sections
```

**Triggers:** Spec Builder uses Oracle for:
- White paper synthesis
- RFC analysis
- Competitor doc comparison

---

## Tool Gap Detection

When Oracle's RLM processing hits a limitation, it emits a structured signal:

```python
request_capability(
    description="Need to parse and query table data from PDF documentation",
    context={
        "problem": "User asked about rate limits, but they're in a table I can't parse",
        "doc_id": "api-docs-v2",
        "attempted_tools": ["search_pattern", "get_section"],
    }
)
```

### Flow

```
Oracle hits limitation
        │
        ▼
request_capability() called
        │
        ▼
┌─────────────────────────────────────┐
│  Logged to OracleConsultation       │
│  record in ExecutionState           │
└──────────────────┬──────────────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
  Real-time event        Persisted to DB
  via WebSocket          for analytics
        │                     │
        ▼                     ▼
  Dashboard shows        Weekly report:
  "Oracle requested       "Top 5 requested
  new capability"         capabilities"
```

### Dashboard Notification

| Field | Value |
|-------|-------|
| Timestamp | 2026-01-17 14:32:01 |
| Workflow | PROJ-456 |
| Agent | Reviewer |
| Requested | "Parse table data from PDF" |
| Context | Doc: api-docs-v2, attempted: search_pattern, get_section |

---

## Relationship to Existing Oracle Plan

The existing Oracle implementation plan establishes:
- FileBundler for gathering codebase files
- Token estimation with tiktoken
- OracleConsultation state model
- FastAPI endpoint + WebSocket events
- Tool registration in drivers

### RLM Extensions

| Existing Component | RLM Extension |
|--------------------|---------------|
| FileBundler | Add Knowledge Library integration for doc retrieval |
| `oracle_consult()` | Add `depth_hint` parameter, decision logic |
| Single LLM call | RLM loop with structured tools when `thorough` |
| OracleConsultation model | Add `tools_used`, `recursive_calls`, `capability_requests` fields |
| Event types | Add `ORACLE_RLM_TOOL_CALL`, `ORACLE_CAPABILITY_REQUESTED` |

---

## Implementation Phases

| Phase | What | Depends On |
|-------|------|------------|
| **Phase 1** | Current Oracle plan (foundation) | — |
| **Phase 2** | Knowledge Library (#203) | Phase 1 |
| **Phase 3** | RLM structured tools in Oracle | Phase 2 |
| **Phase 4** | Agent integration (Architect, Reviewer) | Phase 3 |
| **Phase 5** | Spec Builder integration (#204) | Phase 3, 4 |

**Key dependency:** Knowledge Library (#203) must be implemented before Phase 3, since Oracle queries it for docs.

---

## API Changes

### Updated `oracle_consult` Signature

```python
async def oracle_consult(
    problem: str,
    depth_hint: Literal["quick", "thorough", "auto"] = "auto",
    working_dir: str | None = None,
    doc_ids: list[str] | None = None,
    files: list[str] | None = None,  # Existing: codebase glob patterns
    model: str = "gpt-5.1-pro",
    max_input_tokens: int | None = None,
) -> OracleConsultResult:
    ...
```

### Extended OracleConsultation Model

```python
class OracleConsultation(BaseModel):
    # Existing fields...
    timestamp: datetime
    problem: str
    advice: str | None
    model: str
    session_id: str
    tokens: dict[str, int]
    cost_usd: float | None
    files_consulted: list[str]
    outcome: Literal["success", "error"]
    error_message: str | None

    # New RLM fields
    depth_hint: Literal["quick", "thorough", "auto"]
    processing_mode: Literal["direct", "rlm"]
    tools_used: list[str] = []
    recursive_calls: int = 0
    capability_requests: list[dict] = []
    docs_consulted: list[str] = []  # Knowledge Library doc IDs
```

### New Event Types

```python
class EventType(StrEnum):
    # Existing Oracle events...
    ORACLE_CONSULTATION_STARTED = "oracle_consultation_started"
    ORACLE_CONSULTATION_THINKING = "oracle_consultation_thinking"
    ORACLE_CONSULTATION_COMPLETED = "oracle_consultation_completed"
    ORACLE_CONSULTATION_FAILED = "oracle_consultation_failed"

    # New RLM events
    ORACLE_RLM_TOOL_CALL = "oracle_rlm_tool_call"
    ORACLE_CAPABILITY_REQUESTED = "oracle_capability_requested"
```
