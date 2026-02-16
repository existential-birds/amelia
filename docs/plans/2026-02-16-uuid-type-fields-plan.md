# UUID Type Fields Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Change all UUID fields from `str` to `uuid.UUID` across Pydantic models, repositories, services, routes, and tests.

**Architecture:** Pure mechanical refactor. Change types in models first, then fix everything downstream — row converters, UUID generation, method params, route params, tests. No database migrations, no frontend changes, no backwards compatibility.

**Tech Stack:** Python 3.12+, Pydantic v2, FastAPI, asyncpg, pytest

**Key rule — do NOT change these (they are not UUIDs):**
- `profile_id` / `Profile.name` — human-chosen string
- `prompt_id` / `Prompt.id` / `Prompt.current_version_id` / `PromptVersion.prompt_id` — dot-notation strings
- `driver_session_id` / `BasePipelineState.driver_session_id` — provider-assigned
- `ToolCall.id` / `ToolResult.call_id` / `ToolCallData.tool_call_id` — LLM-provider strings
- `Issue.id` / `issue_id` — tracker IDs

---

### Task 1: Knowledge module models + repository

**Files:**
- Modify: `amelia/knowledge/models.py`
- Modify: `amelia/knowledge/repository.py`
- Modify: `amelia/knowledge/service.py`
- Modify: `amelia/knowledge/ingestion.py`

**Step 1: Update model fields in `amelia/knowledge/models.py`**

Add `import uuid` at top. Change these fields:
- `Document.id: str` → `id: uuid.UUID`
- `DocumentChunk.id: str` → `id: uuid.UUID`
- `DocumentChunk.document_id: str` → `document_id: uuid.UUID`
- `SearchResult.chunk_id: str` → `chunk_id: uuid.UUID`
- `SearchResult.document_id: str` → `document_id: uuid.UUID`

**Step 2: Update `amelia/knowledge/repository.py`**

- Remove `str()` wrappers in `_row_to_document` (line 361: `id=str(row["id"])` → `id=row["id"]`)
- Remove `str()` wrappers in `search_chunks` (lines 338-339: `chunk_id=str(...)` → `chunk_id=row[...]`, same for `document_id`)
- Change `doc_id = str(uuid4())` → `doc_id = uuid4()` in `create_document` (line 52)
- Change `str(uuid4())` → `uuid4()` for chunk IDs in `insert_chunks` (line 241)
- Change all method params: `document_id: str` → `document_id: uuid.UUID` in `get_document`, `update_document_status`, `update_document_tags`, `delete_document`, `insert_chunks`

**Step 3: Update `amelia/knowledge/service.py`**

- Change params: `document_id: str` → `document_id: uuid.UUID` in `queue_ingestion`, `_ingest_with_events`, `_emit_event`
- Change `id=str(uuid4())` → `id=uuid4()` for WorkflowEvent creation (line 164)

**Step 4: Update `amelia/knowledge/ingestion.py`**

- Change params: `document_id: str` → `document_id: uuid.UUID` in `ingest_document`, `_fail_document`

**Step 5: Run knowledge tests**

Run: `uv run pytest tests/unit/knowledge/ -v`
Expected: Tests may fail if they use string UUIDs — fix in Task 8.

**Step 6: Commit**

```
git add amelia/knowledge/
git commit -m "refactor(knowledge): use uuid.UUID instead of str for ID fields"
```

---

### Task 2: Core models — agentic_state, types, pipelines

**Files:**
- Modify: `amelia/core/agentic_state.py`
- Modify: `amelia/core/types.py`
- Modify: `amelia/pipelines/base.py`

**Step 1: Update `amelia/core/agentic_state.py`**

Change these fields only (leave `ToolCall.id` and `ToolResult.call_id` as `str`):
- `AgenticState.workflow_id: str` → `workflow_id: uuid.UUID`
- `AgenticState.session_id: str | None` → `session_id: uuid.UUID | None`

**Step 2: Update `amelia/core/types.py`**

- `OracleConsultation.session_id: str` → `session_id: uuid.UUID`
- `OracleConsultation.workflow_id: str | None` → `workflow_id: uuid.UUID | None`

**Step 3: Update `amelia/pipelines/base.py`**

- `BasePipelineState.workflow_id: str` → `workflow_id: uuid.UUID`
- Leave `profile_id: str` and `driver_session_id: str | None` unchanged.

**Step 4: Commit**

```
git add amelia/core/ amelia/pipelines/
git commit -m "refactor(core): use uuid.UUID instead of str for ID fields"
```

---

### Task 3: Server models — state, events, tokens, brainstorm, responses, websocket

**Files:**
- Modify: `amelia/server/models/state.py`
- Modify: `amelia/server/models/events.py`
- Modify: `amelia/server/models/tokens.py`
- Modify: `amelia/server/models/brainstorm.py`
- Modify: `amelia/server/models/responses.py`
- Modify: `amelia/server/models/websocket.py`

**Step 1: Update `amelia/server/models/state.py`**

- `ServerExecutionState.id: str` → `id: uuid.UUID`
- Leave `issue_id` and `profile_id` as `str`.

**Step 2: Update `amelia/server/models/events.py`**

- `WorkflowEvent.id: str` → `id: uuid.UUID`
- `WorkflowEvent.workflow_id: str` → `workflow_id: uuid.UUID`
- `WorkflowEvent.session_id: str | None` → `session_id: uuid.UUID | None`
- `WorkflowEvent.correlation_id: str | None` → `correlation_id: uuid.UUID | None`
- `WorkflowEvent.trace_id: str | None` → `trace_id: uuid.UUID | None`
- `WorkflowEvent.parent_id: str | None` → `parent_id: uuid.UUID | None`

**Step 3: Update `amelia/server/models/tokens.py`**

- `TokenUsage.id: str` with `default_factory=lambda: str(uuid4())` → `id: uuid.UUID` with `default_factory=uuid4`
- `TokenUsage.workflow_id: str` → `workflow_id: uuid.UUID`

**Step 4: Update `amelia/server/models/brainstorm.py`**

- `BrainstormingSession.id: str` → `id: uuid.UUID`
- Leave `BrainstormingSession.driver_session_id` and `BrainstormingSession.profile_id` as `str`.
- `Message.id: str` → `id: uuid.UUID`
- `Message.session_id: str` → `session_id: uuid.UUID`
- `Artifact.id: str` → `id: uuid.UUID`
- `Artifact.session_id: str` → `session_id: uuid.UUID`

**Step 5: Update `amelia/server/models/responses.py`**

- `WorkflowSummaryResponse.id: str` → `id: uuid.UUID`
- `WorkflowDetailResponse.id: str` → `id: uuid.UUID`
- `ActionResponse.workflow_id: str` → `workflow_id: uuid.UUID`

**Step 6: Update `amelia/server/models/websocket.py`**

- `SubscribeMessage.workflow_id: str` → `workflow_id: uuid.UUID`
- `UnsubscribeMessage.workflow_id: str` → `workflow_id: uuid.UUID`

**Step 7: Commit**

```
git add amelia/server/models/
git commit -m "refactor(server/models): use uuid.UUID instead of str for ID fields"
```

---

### Task 4: Client models

**Files:**
- Modify: `amelia/client/models.py`

**Step 1: Update fields**

- `CreateWorkflowResponse.id: str` → `id: uuid.UUID`
- `WorkflowResponse.id: str` → `id: uuid.UUID`
- `WorkflowSummary.id: str` → `id: uuid.UUID`
- Leave `BatchStartResponse.started: list[str]` and `BatchStartResponse.errors: dict[str, str]` as-is (JSON serialization boundary).

**Step 2: Commit**

```
git add amelia/client/
git commit -m "refactor(client): use uuid.UUID instead of str for ID fields"
```

---

### Task 5: Prompt models + protocol + repository

**Files:**
- Modify: `amelia/agents/prompts/models.py`
- Modify: `amelia/server/database/prompt_repository.py`

**Step 1: Update `amelia/agents/prompts/models.py`**

Only change UUID fields (leave all `prompt_id` fields as `str`):
- `PromptVersion.id: str` → `id: uuid.UUID`
- `ResolvedPrompt.version_id: str | None` → `version_id: uuid.UUID | None`
- `WorkflowPromptVersion.workflow_id: str` → `workflow_id: uuid.UUID`
- `WorkflowPromptVersion.version_id: str` → `version_id: uuid.UUID`

Update `PromptRepositoryProtocol`:
- `get_version(version_id: str)` → `get_version(version_id: uuid.UUID)`
- `record_workflow_prompt(workflow_id: str, ..., version_id: str)` → `record_workflow_prompt(workflow_id: uuid.UUID, ..., version_id: uuid.UUID)`
- Leave `prompt_id: str` params unchanged.

**Step 2: Update `amelia/server/database/prompt_repository.py`**

- Change `version_id = str(uuid.uuid4())` → `version_id = uuid.uuid4()` in `create_version` (line 162)
- Remove `str()` wrapper in `get_workflow_prompts` (line 245: `workflow_id=str(row["workflow_id"])` → `workflow_id=row["workflow_id"]`)
- Update method params: `version_id: str` → `version_id: uuid.UUID` in `get_version`, `set_active_version`
- Update method params: `workflow_id: str` → `workflow_id: uuid.UUID` in `get_workflow_prompts`, `record_workflow_prompt`

**Step 3: Commit**

```
git add amelia/agents/prompts/ amelia/server/database/prompt_repository.py
git commit -m "refactor(prompts): use uuid.UUID instead of str for ID fields"
```

---

### Task 6: Workflow repository + brainstorm repository

**Files:**
- Modify: `amelia/server/database/repository.py`
- Modify: `amelia/server/database/brainstorm_repository.py`

**Step 1: Update `amelia/server/database/repository.py`**

Row converters — remove `str()` wrappers:
- `_row_to_state` line 62: `id=str(row["id"])` → `id=row["id"]`
- `_row_to_event` line 523-524: remove both `str()` wrappers
- `_row_to_token_usage` lines 749-750: remove both `str()` wrappers

Method params — change `workflow_id: str` → `workflow_id: uuid.UUID` in:
- `get`, `set_status`, `update_plan_cache`, `get_max_event_sequence`, `get_recent_events`, `get_token_usage`, `get_token_summary`
- `get_token_summaries_batch`: `workflow_ids: list[str]` → `workflow_ids: list[uuid.UUID]`

**Step 2: Update `amelia/server/database/brainstorm_repository.py`**

Row converters — these already pass UUID objects without `str()` (latent bug that this refactor fixes):
- No changes needed in `_row_to_session`, `_row_to_message`, `_row_to_artifact` — they already pass raw asyncpg values.

Method params — change `session_id: str` → `session_id: uuid.UUID` in:
- `get_session`, `delete_session`, `get_messages`, `get_max_sequence`, `get_artifacts`, `get_session_usage`
- Leave `list_sessions(profile_id: str | None)` as `str` (not a UUID).

**Step 3: Commit**

```
git add amelia/server/database/repository.py amelia/server/database/brainstorm_repository.py
git commit -m "refactor(repositories): use uuid.UUID instead of str for ID fields"
```

---

### Task 7: Routes + services + agents

**Files:**
- Modify: `amelia/server/routes/workflows.py`
- Modify: `amelia/server/routes/brainstorm.py`
- Modify: `amelia/server/routes/knowledge.py`
- Modify: `amelia/server/routes/prompts.py`
- Modify: `amelia/server/routes/oracle.py`
- Modify: `amelia/server/orchestrator/service.py`
- Modify: `amelia/server/services/brainstorm.py`
- Modify: `amelia/agents/oracle.py`
- Modify: `amelia/agents/reviewer.py`
- Modify: `amelia/agents/evaluator.py`
- Modify: `amelia/drivers/base.py`

**Step 1: Update route handler params**

`amelia/server/routes/workflows.py`:
- All `workflow_id: str` params (8 handlers) → `workflow_id: uuid.UUID`

`amelia/server/routes/brainstorm.py`:
- `session_id: str` params → `session_id: uuid.UUID`
- `workflow_id: str` → `workflow_id: uuid.UUID`
- Leave `profile_id: str` unchanged.
- Route response models: `SendMessageResponse.message_id` and `HandoffResponse.workflow_id` — update if they're in route-local models.

`amelia/server/routes/knowledge.py`:
- `document_id: str` params → `document_id: uuid.UUID`

`amelia/server/routes/prompts.py`:
- `version_id: str` → `version_id: uuid.UUID`
- Leave all `prompt_id: str` unchanged.

`amelia/server/routes/oracle.py`:
- `workflow_id: str | None` → `workflow_id: uuid.UUID | None`
- Leave `profile_id` unchanged.

**Step 2: Update orchestrator service**

`amelia/server/orchestrator/service.py`:
- All `workflow_id: str` method params → `workflow_id: uuid.UUID`
- All `workflow_id = str(uuid4())` → `workflow_id = uuid4()`
- All `id=str(uuid4())` for WorkflowEvent creation → `id=uuid4()`

**Step 3: Update brainstorm service**

`amelia/server/services/brainstorm.py`:
- All `session_id: str` params → `session_id: uuid.UUID`
- All `id=str(uuid4())` → `id=uuid4()`
- All `workflow_id = str(uuid4())` → `workflow_id = uuid4()`
- Leave `profile_id: str` and `driver_session_id: str` unchanged.

**Step 4: Update agents**

`amelia/agents/oracle.py`:
- `id=str(uuid4())` → `id=uuid4()` for event creation (line 85)
- `session_id = str(uuid4())` → `session_id = uuid4()` (line 119)

`amelia/agents/reviewer.py`:
- `id=str(uuid4())` → `id=uuid4()` (line 218)

`amelia/agents/evaluator.py`:
- `id=str(uuid4())` → `id=uuid4()` (lines 200, 278)

`amelia/drivers/base.py`:
- `id=str(uuid4())` → `id=uuid4()` (line 119)

**Step 5: Commit**

```
git add amelia/server/routes/ amelia/server/orchestrator/ amelia/server/services/ amelia/agents/ amelia/drivers/
git commit -m "refactor(routes/services/agents): use uuid.UUID instead of str for ID fields"
```

---

### Task 8: Fix all tests

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/integration/conftest.py`
- Modify: All test files that construct models with string UUIDs

**Step 1: Update shared fixtures**

`tests/conftest.py`:
- `workflow_id = kwargs.pop("workflow_id", str(uuid4()))` → `workflow_id = kwargs.pop("workflow_id", uuid4())`

`tests/integration/conftest.py`:
- Same pattern.

**Step 2: Update unit tests**

For each test file, replace `str(uuid4())` with `uuid4()` and replace hardcoded non-UUID strings (like `"test-workflow"`, `"wf-123"`, `"abc-123"`) with `uuid4()` where they're used as UUID fields.

Key test files:
- `tests/unit/server/database/conftest.py`
- `tests/unit/server/database/test_usage_repository.py`
- `tests/unit/server/database/test_repository_backfill.py`
- `tests/unit/server/database/test_repository_tokens.py`
- `tests/unit/server/database/test_repository_usage.py`
- `tests/unit/server/database/test_prompt_repository.py`
- `tests/unit/core/test_execution_state.py`
- `tests/unit/core/test_save_token_usage.py`
- `tests/unit/core/test_developer_node.py`
- `tests/unit/core/test_oracle_types.py`
- `tests/unit/core/test_token_usage_extraction.py`
- `tests/unit/pipelines/test_architect_node_config.py`
- `tests/unit/server/models/test_brainstorm_models.py`
- `tests/integration/server/database/test_repository.py`

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass.

**Step 4: Commit**

```
git add tests/
git commit -m "refactor(tests): use uuid.UUID instead of str for ID fields"
```

---

### Task 9: Type check and final verification

**Step 1: Run mypy**

Run: `uv run mypy amelia`
Expected: No new errors. Fix any type mismatches.

**Step 2: Run ruff**

Run: `uv run ruff check amelia tests`
Expected: Clean. Fix any unused imports (e.g., leftover `str` usage).

**Step 3: Run full test suite including integration**

Run: `uv run pytest tests/unit/ -v && uv run pytest tests/integration/ -m integration -v`
Expected: All pass.

**Step 4: Final commit if any fixes were needed**

```
git add -A
git commit -m "refactor: fix type check and lint issues from UUID migration"
```
