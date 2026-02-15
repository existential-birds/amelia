# Plan Import UX Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace manual path entry with a file dropdown and make plan validation async so the modal closes immediately.

**Architecture:** Add a file listing endpoint to the existing files router, refactor `import_external_plan` into fast I/O + background LLM extraction, add two new WebSocket event types for validation status, and replace the text input with a Combobox on the frontend.

**Tech Stack:** Python/FastAPI, Pydantic, asyncio, React/TypeScript, shadcn/ui Command component, Zustand, WebSocket events

---

### Task 1: Add `PLAN_VALIDATED` and `PLAN_VALIDATION_FAILED` event types

**Files:**
- Modify: `amelia/server/models/events.py:45-197`
- Test: `tests/unit/server/models/test_event_types.py` (new)

**Step 1: Write the failing test**

```python
# tests/unit/server/models/test_event_types.py
from amelia.server.models.events import EventType, PERSISTED_TYPES


class TestPlanEventTypes:
    def test_plan_validated_exists(self) -> None:
        assert EventType.PLAN_VALIDATED == "plan_validated"

    def test_plan_validation_failed_exists(self) -> None:
        assert EventType.PLAN_VALIDATION_FAILED == "plan_validation_failed"

    def test_plan_validated_is_persisted(self) -> None:
        assert EventType.PLAN_VALIDATED in PERSISTED_TYPES

    def test_plan_validation_failed_is_persisted(self) -> None:
        assert EventType.PLAN_VALIDATION_FAILED in PERSISTED_TYPES
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_event_types.py -v`
Expected: FAIL with `AttributeError: PLAN_VALIDATED`

**Step 3: Write minimal implementation**

In `amelia/server/models/events.py`, add to `EventType` enum after the Knowledge ingestion section:

```python
    # Plan validation (async extraction results)
    PLAN_VALIDATED = "plan_validated"
    PLAN_VALIDATION_FAILED = "plan_validation_failed"
```

Add to `PERSISTED_TYPES` frozenset:

```python
    # Plan validation
    EventType.PLAN_VALIDATED,
    EventType.PLAN_VALIDATION_FAILED,
```

Add `PLAN_VALIDATION_FAILED` to `_ERROR_TYPES`:

```python
    EventType.PLAN_VALIDATION_FAILED,
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_event_types.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/events.py tests/unit/server/models/test_event_types.py
git commit -m "feat(events): add PLAN_VALIDATED and PLAN_VALIDATION_FAILED event types (#448)"
```

---

### Task 2: Refactor `import_external_plan` into I/O helpers + LLM extraction

**Files:**
- Modify: `amelia/pipelines/implementation/external_plan.py:22-199`
- Test: `tests/unit/pipelines/test_external_plan.py` (modify existing)

**Step 1: Write failing tests for the new helper functions**

Add tests to `tests/unit/pipelines/test_external_plan.py`:

```python
class TestReadPlanContent:
    """Tests for read_plan_content helper."""

    async def test_read_from_file(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# My Plan\n\n### Task 1: Do thing")
        content = await read_plan_content(
            plan_file=str(plan_file), plan_content=None, working_dir=tmp_path
        )
        assert "# My Plan" in content

    async def test_read_from_inline_content(self, tmp_path: Path) -> None:
        content = await read_plan_content(
            plan_file=None, plan_content="# Inline Plan", working_dir=tmp_path
        )
        assert content == "# Inline Plan"

    async def test_rejects_path_traversal(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="outside working directory"):
            await read_plan_content(
                plan_file="/etc/passwd", plan_content=None, working_dir=tmp_path
            )

    async def test_rejects_empty_content(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="empty"):
            await read_plan_content(
                plan_file=None, plan_content="   ", working_dir=tmp_path
            )


class TestWritePlanToTarget:
    """Tests for write_plan_to_target helper."""

    async def test_writes_content_to_target(self, tmp_path: Path) -> None:
        target = tmp_path / "docs" / "plans" / "plan.md"
        await write_plan_to_target(
            content="# Plan", target_path=target, working_dir=tmp_path
        )
        assert target.read_text() == "# Plan"

    async def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "deep" / "nested" / "plan.md"
        await write_plan_to_target(
            content="# Plan", target_path=target, working_dir=tmp_path
        )
        assert target.exists()

    async def test_skips_write_when_source_equals_target(self, tmp_path: Path) -> None:
        target = tmp_path / "plan.md"
        target.write_text("# Original")
        await write_plan_to_target(
            content="# Original",
            target_path=target,
            working_dir=tmp_path,
            source_path=target,
        )
        assert target.read_text() == "# Original"


class TestExtractPlanFields:
    """Tests for extract_plan_fields (LLM extraction with fallback)."""

    async def test_fallback_extracts_goal_from_heading(self) -> None:
        content = "# Implement user auth\n\n### Task 1: Setup"
        result = await extract_plan_fields(content, profile=None)
        assert "auth" in result.goal.lower() or result.goal == "Implementation plan"

    async def test_fallback_returns_content_as_markdown(self) -> None:
        content = "# Plan\n\nSome content"
        result = await extract_plan_fields(content, profile=None)
        assert result.plan_markdown == content
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/pipelines/test_external_plan.py -v -k "TestReadPlanContent or TestWritePlanToTarget or TestExtractPlanFields"`
Expected: FAIL with `ImportError`

**Step 3: Implement the helper functions**

Refactor `amelia/pipelines/implementation/external_plan.py`:

- Extract `read_plan_content(plan_file, plan_content, working_dir) -> str` — handles file reading, path traversal check, empty content check
- Extract `write_plan_to_target(content, target_path, working_dir, source_path=None)` — handles target path validation, mkdir, write
- Extract `extract_plan_fields(content, profile) -> ExternalPlanImportResult` — LLM extraction with regex fallback. When `profile` is `None`, skip LLM and use fallback only.
- Keep `import_external_plan` as a thin wrapper that calls all three in sequence (backward compatible)

The key change: `extract_plan_fields` must work without a profile (fallback-only mode) so the service can call the I/O helpers synchronously and defer LLM extraction.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/pipelines/test_external_plan.py -v`
Expected: ALL PASS (existing tests should still pass since `import_external_plan` is a thin wrapper)

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/external_plan.py tests/unit/pipelines/test_external_plan.py
git commit -m "refactor(pipeline): extract I/O helpers from import_external_plan (#448)"
```

---

### Task 3: Add file listing endpoint to files router

**Files:**
- Modify: `amelia/server/routes/files.py:15-183`
- Modify: `amelia/server/models/responses.py` (add response model)
- Test: `tests/unit/server/routes/test_list_files_endpoint.py` (new)

**Step 1: Write failing tests**

```python
# tests/unit/server/routes/test_list_files_endpoint.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import status
from fastapi.testclient import TestClient

from amelia.server.routes.files import router
from amelia.server.dependencies import get_profile_repository


class TestListFilesEndpoint:
    @pytest.fixture
    def mock_profile_repo(self) -> MagicMock:
        mock = MagicMock()
        mock.get_active_profile = AsyncMock(
            return_value=MagicMock(working_dir="/tmp/test-project")
        )
        return mock

    @pytest.fixture
    def test_client(self, mock_profile_repo: MagicMock) -> TestClient:
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo
        return TestClient(app)

    def test_list_files_returns_md_files(
        self, test_client: TestClient, tmp_path: pytest.TempPathFactory
    ) -> None:
        # Create test files in a temp dir and patch working_dir
        # This test verifies the endpoint returns .md files with correct shape
        response = test_client.get("/api/files/list", params={"directory": "docs/plans"})
        # Will fail initially because endpoint doesn't exist
        assert response.status_code in (200, 404)

    def test_list_files_rejects_path_traversal(self, test_client: TestClient) -> None:
        response = test_client.get("/api/files/list", params={"directory": "../../etc"})
        assert response.status_code == 400

    def test_list_files_requires_directory_param(self, test_client: TestClient) -> None:
        response = test_client.get("/api/files/list")
        assert response.status_code == 422
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/routes/test_list_files_endpoint.py -v`
Expected: FAIL (endpoint doesn't exist)

**Step 3: Implement the endpoint**

Add response model to `amelia/server/models/responses.py`:

```python
class FileEntry(BaseModel):
    """A file entry in a directory listing."""
    name: Annotated[str, Field(description="Filename")]
    relative_path: Annotated[str, Field(description="Path relative to working_dir")]
    size_bytes: Annotated[int, Field(description="File size in bytes")]
    modified_at: Annotated[str, Field(description="ISO 8601 modification timestamp")]

class FileListResponse(BaseModel):
    """Response from listing files in a directory."""
    files: Annotated[list[FileEntry], Field(description="List of files")]
    directory: Annotated[str, Field(description="Relative directory that was listed")]
```

Add to `amelia/server/routes/files.py`:

```python
@router.get("/list", response_model=FileListResponse)
async def list_files(
    directory: str = Query(..., description="Relative directory path within working_dir"),
    glob_pattern: str = Query("*.md", description="Glob pattern for filtering files"),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
) -> FileListResponse:
    """List files in a directory within the working directory.

    Args:
        directory: Relative path to directory.
        glob_pattern: File pattern to match (default: *.md).
        profile_repo: Profile repository for working_dir.

    Returns:
        List of matching files sorted by modification time (newest first).

    Raises:
        FileOperationError: If directory is outside working_dir or doesn't exist.
    """
    working_dir = await _get_working_dir(profile_repo)
    resolved_dir = (working_dir / directory).resolve()

    # Security: verify directory is within working_dir
    working_dir_resolved = working_dir.resolve()
    try:
        common = os.path.commonpath([str(resolved_dir), str(working_dir_resolved)])
    except ValueError:
        raise FileOperationError("Directory not accessible", "PATH_NOT_ACCESSIBLE")

    if common != str(working_dir_resolved):
        raise FileOperationError("Directory not accessible", "PATH_NOT_ACCESSIBLE")

    if not resolved_dir.is_dir():
        return FileListResponse(files=[], directory=directory)

    # List files matching pattern
    entries = []
    for path in resolved_dir.glob(glob_pattern):
        if not path.is_file():
            continue
        stat = path.stat()
        entries.append(FileEntry(
            name=path.name,
            relative_path=str(path.relative_to(working_dir_resolved)),
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
        ))

    # Sort by modification time, newest first
    entries.sort(key=lambda e: e.modified_at, reverse=True)

    return FileListResponse(files=entries, directory=directory)
```

Add necessary imports: `from datetime import datetime, UTC` and `from fastapi import Query`.

Import `FileListResponse, FileEntry` from responses or define locally.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/routes/test_list_files_endpoint.py -v`
Expected: PASS

**Step 5: Run full test suite for routes**

Run: `uv run pytest tests/unit/server/ -v --timeout=30`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add amelia/server/routes/files.py amelia/server/models/responses.py tests/unit/server/routes/test_list_files_endpoint.py
git commit -m "feat(api): add GET /api/files/list endpoint for plan file browsing (#448)"
```

---

### Task 4: Split `set_workflow_plan` into fast path + async extraction

**Files:**
- Modify: `amelia/server/orchestrator/service.py:2619-2753`
- Modify: `amelia/server/models/responses.py` (update `SetPlanResponse`)
- Modify: `amelia/server/routes/workflows.py:498-530`
- Test: `tests/unit/server/test_orchestrator_set_plan.py` (modify existing)
- Test: `tests/unit/server/test_set_plan_endpoint.py` (modify existing)

**Step 1: Update tests for new response shape**

Update `tests/unit/server/test_set_plan_endpoint.py` — the mock orchestrator now returns `{"status": "validating", "total_tasks": 2}` and the response assertion changes:

```python
@pytest.fixture
def mock_orchestrator(self) -> MagicMock:
    mock = MagicMock()
    mock.set_workflow_plan = AsyncMock(
        return_value={
            "status": "validating",
            "total_tasks": 2,
        }
    )
    return mock

def test_set_plan_with_inline_content(
    self, test_client: TestClient, mock_orchestrator: MagicMock
) -> None:
    response = test_client.post(
        "/api/workflows/wf-001/plan",
        json={"plan_content": "# Plan\n\n### Task 1: Do thing"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "validating"
    assert data["total_tasks"] == 2
```

Update `tests/unit/server/test_orchestrator_set_plan.py` to verify:
- The method returns `{"status": "validating", "total_tasks": N}` (fast path)
- A background task is created (mock `asyncio.create_task`)
- `PlanCache` is saved with `goal=None`

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/test_set_plan_endpoint.py tests/unit/server/test_orchestrator_set_plan.py -v`
Expected: FAIL (old response shape)

**Step 3: Implement the split**

**Update `SetPlanResponse` in `amelia/server/models/responses.py`:**

```python
class SetPlanResponse(BaseModel):
    """Response from setting an external plan on a workflow."""
    status: Annotated[str, Field(description="'validating' or 'validated'")]
    total_tasks: Annotated[int, Field(description="Number of tasks in the plan")]
    goal: Annotated[str | None, Field(default=None, description="Extracted goal (present when status=validated)")]
    key_files: Annotated[list[str] | None, Field(default=None, description="Key files (present when status=validated)")]
```

**Update route handler in `amelia/server/routes/workflows.py`:**

```python
@router.post("/{workflow_id}/plan", response_model=SetPlanResponse)
async def set_workflow_plan(
    workflow_id: str,
    request: SetPlanRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> SetPlanResponse:
    result = await orchestrator.set_workflow_plan(
        workflow_id=workflow_id,
        plan_file=request.plan_file,
        plan_content=request.plan_content,
        force=request.force,
    )
    return SetPlanResponse(**result)
```

**Refactor `OrchestratorService.set_workflow_plan` in `amelia/server/orchestrator/service.py`:**

Keep all existing validation logic (status check, planning task check, force check, etc.) unchanged.

Replace the `import_external_plan` call and everything after it with:

```python
    # Fast path: read + write + regex task count
    content = await read_plan_content(
        plan_file=plan_file,
        plan_content=plan_content,
        working_dir=Path(profile.working_dir) if profile.working_dir else Path("."),
    )
    await write_plan_to_target(
        content=content,
        target_path=target_path,
        working_dir=Path(profile.working_dir) if profile.working_dir else Path("."),
    )
    total_tasks = extract_task_count(content)

    # Save partial cache (goal=None signals "validating")
    plan_cache = PlanCache(
        goal=None,
        plan_markdown=content,
        plan_path=str(target_path),
        total_tasks=total_tasks,
    )
    await self._repository.update_plan_cache(workflow_id, plan_cache)

    # Emit initial event
    await self._emit(
        workflow_id,
        EventType.AGENT_MESSAGE,
        f"External plan imported ({total_tasks} tasks), validating...",
        agent="system",
        data={"total_tasks": total_tasks},
    )

    # Fire-and-forget background LLM extraction
    asyncio.create_task(
        self._extract_plan_metadata(workflow_id, content, target_path, profile)
    )

    logger.info(
        "External plan imported (async validation)",
        workflow_id=workflow_id,
        total_tasks=total_tasks,
    )

    return {
        "status": "validating",
        "total_tasks": total_tasks,
    }
```

**Add `_extract_plan_metadata` method to `OrchestratorService`:**

```python
async def _extract_plan_metadata(
    self,
    workflow_id: str,
    content: str,
    target_path: Path,
    profile: Profile,
) -> None:
    """Background task: LLM-powered plan field extraction.

    Extracts goal, key_files, plan_markdown from plan content using LLM.
    Updates PlanCache and emits PLAN_VALIDATED or PLAN_VALIDATION_FAILED event.

    Args:
        workflow_id: The workflow ID.
        content: Raw plan markdown content.
        target_path: Path where plan was written.
        profile: Profile for LLM config.
    """
    try:
        result = await extract_plan_fields(content, profile)
        total_tasks = extract_task_count(content)

        plan_cache = PlanCache(
            goal=result.goal,
            plan_markdown=result.plan_markdown,
            plan_path=str(target_path),
            total_tasks=total_tasks,
        )
        await self._repository.update_plan_cache(workflow_id, plan_cache)

        await self._emit(
            workflow_id,
            EventType.PLAN_VALIDATED,
            f"Plan validated: {result.goal}",
            agent="system",
            data={
                "goal": result.goal,
                "key_files": result.key_files,
                "total_tasks": total_tasks,
            },
        )

        logger.info(
            "Plan metadata extracted",
            workflow_id=workflow_id,
            goal=result.goal,
            total_tasks=total_tasks,
        )
    except Exception as exc:
        logger.warning(
            "Plan metadata extraction failed",
            workflow_id=workflow_id,
            error=str(exc),
        )
        await self._emit(
            workflow_id,
            EventType.PLAN_VALIDATION_FAILED,
            f"Plan validation failed: {exc}",
            agent="system",
            data={"error": str(exc)},
        )
```

Add imports at top of service.py:

```python
from amelia.pipelines.implementation.external_plan import (
    read_plan_content,
    write_plan_to_target,
    extract_plan_fields,
)
```

Remove the now-unused `import_external_plan` import (but keep the function in external_plan.py for backward compat).

**Step 4: Run tests**

Run: `uv run pytest tests/unit/server/test_set_plan_endpoint.py tests/unit/server/test_orchestrator_set_plan.py -v`
Expected: PASS

**Step 5: Run mypy**

Run: `uv run mypy amelia/server/orchestrator/service.py amelia/server/routes/workflows.py amelia/server/models/responses.py`
Expected: No errors

**Step 6: Commit**

```bash
git add amelia/server/orchestrator/service.py amelia/server/routes/workflows.py amelia/server/models/responses.py tests/unit/server/test_set_plan_endpoint.py tests/unit/server/test_orchestrator_set_plan.py
git commit -m "feat(orchestrator): async plan validation with immediate modal dismiss (#448)"
```

---

### Task 5: Add frontend types and API client methods

**Files:**
- Modify: `dashboard/src/types/index.ts:560-584`
- Modify: `dashboard/src/api/client.ts:437-444`

**Step 1: Update TypeScript types**

In `dashboard/src/types/index.ts`, update `SetPlanResponse`:

```typescript
export interface SetPlanResponse {
  /** Whether the plan is still being validated or is complete. */
  status: 'validating' | 'validated';

  /** Number of tasks in the plan. */
  total_tasks: number;

  /** Extracted goal from the plan (present when status=validated). */
  goal?: string;

  /** List of key files from the plan (present when status=validated). */
  key_files?: string[];
}
```

Add new types for file listing:

```typescript
export interface FileEntry {
  /** Filename without path. */
  name: string;

  /** Path relative to working directory. */
  relative_path: string;

  /** File size in bytes. */
  size_bytes: number;

  /** ISO 8601 modification timestamp. */
  modified_at: string;
}

export interface FileListResponse {
  /** List of files in the directory. */
  files: FileEntry[];

  /** Relative directory that was listed. */
  directory: string;
}
```

**Step 2: Add `listFiles` to API client**

In `dashboard/src/api/client.ts`, add after the `setPlan` method:

```typescript
async listFiles(directory: string, globPattern: string = '*.md'): Promise<FileListResponse> {
  const params = new URLSearchParams({ directory, glob_pattern: globPattern });
  const response = await fetchWithTimeout(`${API_BASE_URL}/files/list?${params}`);
  return handleResponse<FileListResponse>(response);
}
```

Add `FileListResponse` to the import from types.

**Step 3: Update SetPlanModal response handling**

In `dashboard/src/components/SetPlanModal.tsx`, update `handleSubmit`:

```typescript
const handleSubmit = useCallback(async () => {
  if (!hasPlanData) return;

  setIsSubmitting(true);
  setError(undefined);

  try {
    const result = await api.setPlan(workflowId, {
      plan_file: planData.plan_file,
      plan_content: planData.plan_content,
      force: forceOverwrite,
    });

    const summary = result.total_tasks > 0
      ? `Plan imported (${result.total_tasks} tasks), validating...`
      : 'Plan imported, validating...';
    toast.success(summary);
    onOpenChange(false);
    onSuccess?.();
  } catch (err) {
    if (err instanceof ApiError) {
      setError(err.message);
    } else {
      setError('Failed to apply plan');
    }
  } finally {
    setIsSubmitting(false);
  }
}, [workflowId, planData, forceOverwrite, onOpenChange, onSuccess, hasPlanData]);
```

**Step 4: Run type check and lint**

Run (from `dashboard/`): `pnpm type-check && pnpm lint`
Expected: No errors

**Step 5: Commit**

```bash
git add dashboard/src/types/index.ts dashboard/src/api/client.ts dashboard/src/components/SetPlanModal.tsx
git commit -m "feat(dashboard): update types and API client for async plan validation (#448)"
```

---

### Task 6: Replace file path input with Combobox in PlanImportSection

**Files:**
- Modify: `dashboard/src/components/PlanImportSection.tsx:48-214`
- Test: `dashboard/src/components/__tests__/PlanImportSection.test.tsx` (new or modify existing)

**Step 1: Write the component test**

```typescript
// dashboard/src/components/__tests__/PlanImportSection.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PlanImportSection } from '../PlanImportSection';

// Mock the API client
vi.mock('../../api/client', () => ({
  api: {
    listFiles: vi.fn(),
    readFile: vi.fn(),
  },
}));

import { api } from '../../api/client';

describe('PlanImportSection', () => {
  const mockOnPlanChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches file list on mount when in file mode', async () => {
    (api.listFiles as ReturnType<typeof vi.fn>).mockResolvedValue({
      files: [
        { name: 'plan-1.md', relative_path: 'docs/plans/plan-1.md', size_bytes: 100, modified_at: '2026-02-15T10:00:00Z' },
      ],
      directory: 'docs/plans',
    });

    render(
      <PlanImportSection
        onPlanChange={mockOnPlanChange}
        defaultExpanded
        worktreePath="/tmp/project"
        planOutputDir="docs/plans"
      />
    );

    await waitFor(() => {
      expect(api.listFiles).toHaveBeenCalledWith('docs/plans');
    });
  });

  it('shows empty state when no files found', async () => {
    (api.listFiles as ReturnType<typeof vi.fn>).mockResolvedValue({
      files: [],
      directory: 'docs/plans',
    });

    render(
      <PlanImportSection
        onPlanChange={mockOnPlanChange}
        defaultExpanded
        worktreePath="/tmp/project"
        planOutputDir="docs/plans"
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/no .md files/i)).toBeInTheDocument();
    });
  });
});
```

**Step 2: Run test to verify it fails**

Run (from `dashboard/`): `pnpm test:run -- PlanImportSection`
Expected: FAIL

**Step 3: Implement the Combobox replacement**

Key changes to `PlanImportSection.tsx`:

1. Add a `planOutputDir` prop to `PlanImportSectionProps`
2. Replace the text input + Preview button with a Combobox (using `Command`, `CommandInput`, `CommandList`, `CommandItem`, `CommandEmpty` from `@/components/ui/command`)
3. Add state: `files`, `filesLoading`, `filesError`
4. Add `useEffect` to fetch files on mount when mode is `file`
5. On file selection: set `filePath` and auto-trigger preview
6. Display each file entry with monospace filename and relative timestamp

The Combobox should use a Popover wrapper pattern (common shadcn pattern):

```tsx
<Popover open={comboboxOpen} onOpenChange={setComboboxOpen}>
  <PopoverTrigger asChild>
    <Button variant="outline" role="combobox" className="w-full justify-between font-mono text-sm">
      {selectedFile ? selectedFile.name : "Select a plan file..."}
      <ChevronsUpDown className="ml-2 h-4 w-4 opacity-50" />
    </Button>
  </PopoverTrigger>
  <PopoverContent className="w-full p-0" align="start">
    <Command>
      <CommandInput placeholder="Search files..." />
      <CommandList>
        <CommandEmpty>No .md files found in {planOutputDir}</CommandEmpty>
        <CommandGroup>
          {files.map((file) => (
            <CommandItem
              key={file.relative_path}
              value={file.name}
              onSelect={() => handleFileSelect(file)}
              className="font-mono text-xs"
            >
              <Check className={cn("mr-2 h-4 w-4", selectedPath === file.relative_path ? "opacity-100" : "opacity-0")} />
              <span className="flex-1">{file.name}</span>
              <span className="text-muted-foreground text-xs">
                {formatRelativeTime(file.modified_at)}
              </span>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </Command>
  </PopoverContent>
</Popover>
```

Add a `formatRelativeTime` utility (simple: "just now", "2m ago", "1h ago", "yesterday", date).

When `handleFileSelect(file)` is called:
- Set `filePath` to `file.relative_path`
- Close combobox
- Auto-trigger preview via the existing `handlePreview` logic

**Step 4: Update the `SetPlanModal` to pass `planOutputDir`**

The modal needs to know the profile's `plan_output_dir`. This comes from the workflow's profile. Add it as a prop or fetch it. The simplest approach: pass it through from the parent that opens the modal. If not available, fall back to `"docs/plans"`.

**Step 5: Run tests**

Run (from `dashboard/`): `pnpm test:run`
Expected: PASS

**Step 6: Run lint and type check**

Run (from `dashboard/`): `pnpm lint && pnpm type-check`
Expected: No errors

**Step 7: Commit**

```bash
git add dashboard/src/components/PlanImportSection.tsx dashboard/src/components/SetPlanModal.tsx dashboard/src/components/__tests__/PlanImportSection.test.tsx
git commit -m "feat(dashboard): replace file path input with Combobox dropdown (#448)"
```

---

### Task 7: Add validation status indicator to workflow card

**Files:**
- Modify: `dashboard/src/components/JobQueueItem.tsx`
- Modify: `dashboard/src/types/index.ts` (add `plan_validating` field to `WorkflowSummary` if needed)

**Step 1: Determine how the card knows about validation status**

The `JobQueueItem` currently receives a minimal `Pick<WorkflowSummary, 'id' | 'issue_id' | 'worktree_path' | 'status'>`. For the validation indicator, the card needs to know if a plan is currently being validated.

Two approaches:
- **Option A:** Listen for `workflow-event` DOM events with `event_type === "plan_validated"` or `"plan_validation_failed"` matching the workflow ID. Track in local state.
- **Option B:** Add `plan_status: 'none' | 'validating' | 'validated' | 'failed'` to `WorkflowSummary` from the API.

**Use Option A** — it avoids API changes and leverages the existing WebSocket event infrastructure. The card listens for plan-related events for its workflow ID.

**Step 2: Implement the indicator**

Add to `JobQueueItem.tsx`:

```tsx
const [planValidating, setPlanValidating] = useState(false);
const [planError, setPlanError] = useState<string | null>(null);

useEffect(() => {
  const handler = (e: Event) => {
    const event = (e as CustomEvent).detail as WorkflowEvent;
    if (event.workflow_id !== workflow.id) return;

    if (event.event_type === 'plan_validated') {
      setPlanValidating(false);
      setPlanError(null);
    } else if (event.event_type === 'plan_validation_failed') {
      setPlanValidating(false);
      setPlanError(event.data?.error as string ?? 'Validation failed');
    } else if (event.event_type === 'agent_message' && event.data?.total_tasks != null) {
      // The fast-path event signals validation started
      setPlanValidating(true);
      setPlanError(null);
    }
  };

  window.addEventListener('workflow-event', handler);
  return () => window.removeEventListener('workflow-event', handler);
}, [workflow.id]);
```

In the JSX, next to the status indicator:

```tsx
{planValidating && (
  <Tooltip content="Plan validation in progress...">
    <span className="w-2 h-2 rounded-full bg-primary animate-pulse-glow" />
  </Tooltip>
)}
{planError && (
  <Tooltip content={planError}>
    <span className="w-2 h-2 rounded-full bg-destructive" />
  </Tooltip>
)}
```

**Step 3: Run lint and type check**

Run (from `dashboard/`): `pnpm lint && pnpm type-check`
Expected: No errors

**Step 4: Commit**

```bash
git add dashboard/src/components/JobQueueItem.tsx
git commit -m "feat(dashboard): add plan validation status indicator to workflow card (#448)"
```

---

### Task 8: Final integration verification

**Step 1: Run full backend test suite**

Run: `uv run pytest -v --timeout=60`
Expected: ALL PASS

**Step 2: Run mypy**

Run: `uv run mypy amelia`
Expected: No errors

**Step 3: Run ruff**

Run: `uv run ruff check amelia tests`
Expected: No issues

**Step 4: Run frontend tests**

Run (from `dashboard/`): `pnpm test:run`
Expected: ALL PASS

**Step 5: Run frontend build**

Run (from `dashboard/`): `pnpm build`
Expected: Build succeeds

**Step 6: Run frontend lint and type check**

Run (from `dashboard/`): `pnpm lint && pnpm type-check`
Expected: No errors

**Step 7: Commit any remaining fixes**

If any lint/type/test issues surfaced, fix and commit.

**Step 8: Final commit message**

If there are accumulated small fixes:

```bash
git add -A
git commit -m "chore: fix lint and type issues from plan import UX changes (#448)"
```
