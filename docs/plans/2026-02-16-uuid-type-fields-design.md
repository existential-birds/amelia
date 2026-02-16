# UUID Type Fields Refactor

## Problem

All Pydantic models use `id: str` for UUID fields. This loses type safety, allows arbitrary strings where UUIDs are expected, and requires manual `str()` conversions when interfacing with asyncpg (which returns `uuid.UUID`).

## Design

Pure mechanical refactor: change `str` to `uuid.UUID` on all fields that hold UUIDs.

### Changes

1. **Pydantic model fields** (51 fields) — `str` → `uuid.UUID`, update `default_factory` from `lambda: str(uuid4())` to `uuid4`
2. **Row converters** — remove `str()` wrappers (asyncpg already returns `uuid.UUID`)
3. **UUID generation sites** — `str(uuid4())` → `uuid4()`
4. **Method/route params** — `workflow_id: str` → `workflow_id: UUID` (FastAPI handles UUID path params natively)
5. **Protocol annotations** — update to match
6. **Tests** — `str(uuid4())` → `uuid4()`, replace hardcoded strings like `"test-workflow"` with `uuid4()`

### Not UUIDs (unchanged)

- `profile_id` / `Profile.name` — human-chosen string like `"work"`
- `prompt_id` / `Prompt.id` / `Prompt.current_version_id` — dot-notation strings like `"architect.system"`
- `driver_session_id` — provider-assigned session string
- `ToolCall.id` / `ToolResult.call_id` / `ToolCallData.tool_call_id` — LLM-provider strings
- `Issue.id` — tracker IDs like `"JIRA-123"`

### Constraints

- No database migrations (columns are already UUID type)
- No frontend changes (Pydantic v2 serializes `uuid.UUID` as JSON strings)
- Pure cutover, no backwards compatibility
