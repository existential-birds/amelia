# Consolidate Plan Extraction to Regex-Only Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove LLM extraction from plan import/validation, consolidate to regex-only, and unify the import path for both `queue_workflow` and `set_workflow_plan`.

**Architecture:** Drop `extract_structured` LLM calls from `extract_plan_fields`, `plan_validator_node`, and `_extract_plan_metadata`. Both API endpoints share `import_external_plan` which does read → write → regex extract → structural validate. Events emitted synchronously.

**Tech Stack:** Python 3.12, Pydantic, LangGraph, pytest-asyncio, React/TypeScript dashboard

---

### Task 1: Remove LLM from `extract_plan_fields`

**Files:**
- Modify: `amelia/pipelines/implementation/external_plan.py:154-227`
- Modify: `tests/unit/pipelines/test_external_plan.py`

**Step 1: Update tests for regex-only extraction**

In `tests/unit/pipelines/test_external_plan.py`, the `TestExtractPlanFields` class has 2 tests that use `profile=None` (regex fallback). Update these to be the canonical tests. Add a test that verifies `profile` parameter is no longer accepted (or simply not needed).

Replace the class with:

```python
class TestExtractPlanFields:
    """Tests for extract_plan_fields (regex-only, no LLM)."""

    async def test_extracts_goal_from_heading(self) -> None:
        """Extract goal from first heading."""
        content = "# Implement user auth\n\n### Task 1: Setup"
        result = await extract_plan_fields(content)
        assert "auth" in result.goal.lower() or result.goal == "Implementation plan"

    async def test_extracts_goal_from_bold_pattern(self) -> None:
        """Extract goal from **Goal:** pattern."""
        content = "**Goal:** Add user authentication\n\n### Task 1: Setup auth"
        result = await extract_plan_fields(content)
        assert result.goal == "Add user authentication"

    async def test_returns_content_as_markdown(self) -> None:
        """Plan markdown is the content as-is."""
        content = "# Plan\n\nSome content"
        result = await extract_plan_fields(content)
        assert result.plan_markdown == content

    async def test_extracts_key_files(self) -> None:
        """Extract key files from Create/Modify patterns."""
        content = "**Goal:** Test\n\n### Task 1: Files\n\nCreate: `src/auth.py`\nModify: `src/main.py`"
        result = await extract_plan_fields(content)
        assert "src/auth.py" in result.key_files
        assert "src/main.py" in result.key_files

    async def test_counts_tasks(self) -> None:
        """Extract task count from ### Task N: headers."""
        content = "**Goal:** Test\n\n### Task 1: First\n\n### Task 2: Second"
        result = await extract_plan_fields(content)
        assert result.total_tasks == 2
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/pipelines/test_external_plan.py::TestExtractPlanFields -v`
Expected: FAIL — `extract_plan_fields` still requires `profile` parameter.

**Step 3: Rewrite `extract_plan_fields` to regex-only**

In `amelia/pipelines/implementation/external_plan.py`, replace `extract_plan_fields` (lines 154-227):

```python
async def extract_plan_fields(
    content: str,
) -> ExternalPlanImportResult:
    """Extract structured plan fields using regex pattern matching.

    Args:
        content: The raw plan markdown content.

    Returns:
        ExternalPlanImportResult with goal, plan_markdown, key_files, total_tasks.
        Note: plan_path is set to Path(".") as a placeholder; callers should
        set it to the actual target path.
    """
    goal = _extract_goal_from_plan(content)
    key_files = _extract_key_files_from_plan(content)
    total_tasks = extract_task_count(content)

    return ExternalPlanImportResult(
        goal=goal,
        plan_markdown=content,
        plan_path=Path("."),  # Placeholder; caller sets actual path
        key_files=key_files,
        total_tasks=total_tasks,
    )
```

Remove unused imports from the file:
- `from amelia.agents.schemas.architect import MarkdownPlanOutput`
- `from amelia.core.extraction import extract_structured`
- `from amelia.core.types import Profile`

Remove the `build_plan_extraction_prompt` function (lines 34-52).

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/pipelines/test_external_plan.py::TestExtractPlanFields -v`
Expected: PASS

**Step 5: Fix callers of `extract_plan_fields` that pass `profile`**

Two callers pass `profile=...`:
- `import_external_plan` in same file (line 280): change `await extract_plan_fields(content, profile=profile)` → `await extract_plan_fields(content)`
- `_extract_plan_metadata` in `amelia/server/orchestrator/service.py` (line 2784): will be removed in Task 4, but fix for now.

**Step 6: Run full test suite for external_plan**

Run: `uv run pytest tests/unit/pipelines/test_external_plan.py -v`
Expected: PASS. Some tests in `TestImportExternalPlan` that mock `extract_structured` may need updating — remove those mocks since LLM path no longer exists.

**Step 7: Commit**

```bash
git add amelia/pipelines/implementation/external_plan.py tests/unit/pipelines/test_external_plan.py
git commit -m "refactor(extract_plan_fields): drop LLM, regex-only extraction"
```

---

### Task 2: Remove `MarkdownPlanOutput` schema and `build_plan_extraction_prompt`

**Files:**
- Modify: `amelia/agents/schemas/architect.py`
- Modify: `amelia/agents/schemas/__init__.py`

**Step 1: Remove `MarkdownPlanOutput` from schema file**

In `amelia/agents/schemas/architect.py`, remove the `MarkdownPlanOutput` class (lines 9-23). If this is the only class in the file, either leave the file empty with just the module docstring, or remove the file entirely. Check if there are other classes first.

**Step 2: Remove from `__init__.py`**

In `amelia/agents/schemas/__init__.py`:
- Remove line 8: `from amelia.agents.schemas.architect import MarkdownPlanOutput`
- Remove line 22: `"MarkdownPlanOutput",` from `__all__`

**Step 3: Search for remaining references**

Run: `uv run ruff check amelia` — any import errors will surface here.

Also grep: `grep -r "MarkdownPlanOutput" amelia/ tests/` to find stragglers.

**Step 4: Fix any remaining references**

Remove `MarkdownPlanOutput` imports from:
- `amelia/pipelines/implementation/nodes.py` (line 19) — will be cleaned up in Task 3
- Any test files that import it

**Step 5: Run lint and type check**

Run: `uv run ruff check amelia && uv run mypy amelia`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/agents/schemas/
git commit -m "refactor: remove MarkdownPlanOutput schema (no longer needed)"
```

---

### Task 3: Simplify `plan_validator_node` to regex-only

**Files:**
- Modify: `amelia/pipelines/implementation/nodes.py:37-140`
- Modify: `tests/unit/pipelines/` (any tests for plan_validator_node)

**Step 1: Check for existing tests**

Run: `grep -r "plan_validator_node" tests/` to find existing tests.

**Step 2: Write/update test for regex-only plan_validator_node**

The test should verify:
- Reads plan from disk
- Extracts goal, key_files, total_tasks via regex
- Runs `validate_plan_structure`
- Returns expected state dict
- No LLM calls made

**Step 3: Rewrite `plan_validator_node`**

In `amelia/pipelines/implementation/nodes.py`, replace `plan_validator_node` (lines 37-140):

```python
async def plan_validator_node(
    state: ImplementationState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Validate and extract structure from plan file using regex.

    Reads the plan file and extracts structured fields (goal, key_files)
    using pattern matching. Runs structural validation to check for
    required headers and minimum content.

    Args:
        state: Current execution state.
        config: RunnableConfig with profile in configurable.

    Returns:
        Partial state dict with goal, plan_markdown, plan_path, key_files,
        total_tasks, plan_validation_result, plan_revision_count.

    Raises:
        ValueError: If plan file not found or empty.
    """
    event_bus, workflow_id, profile = extract_config_params(config or {})

    if not state.issue:
        raise ValueError("Issue is required in state for plan validation")

    # Resolve plan path
    plan_rel_path = resolve_plan_path(profile.plan_path_pattern, state.issue.id)
    working_dir = Path(profile.repo_root)
    plan_path = working_dir / plan_rel_path

    logger.info(
        "Orchestrator: Validating plan structure",
        plan_path=str(plan_path),
        workflow_id=workflow_id,
    )

    # Read plan file - fail fast if not found
    if not plan_path.exists():
        raise ValueError(f"Plan file not found at {plan_path}")

    plan_content = await asyncio.to_thread(plan_path.read_text)
    if not plan_content.strip():
        raise ValueError(f"Plan file is empty at {plan_path}")

    # Extract fields using regex
    goal = _extract_goal_from_plan(plan_content)
    key_files = _extract_key_files_from_plan(plan_content)
    total_tasks = extract_task_count(plan_content)

    # Run structural validation
    validation_result = validate_plan_structure(goal, plan_content)

    revision_count = state.plan_revision_count
    if not validation_result.valid:
        revision_count += 1
        logger.warning(
            "Plan structural validation failed",
            issues=validation_result.issues,
            severity=validation_result.severity.value,
            revision_count=revision_count,
            workflow_id=workflow_id,
        )

    logger.info(
        "Plan validated",
        goal=goal,
        key_files_count=len(key_files),
        total_tasks=total_tasks,
        workflow_id=workflow_id,
    )

    return {
        "goal": goal,
        "plan_markdown": plan_content,
        "plan_path": plan_path,
        "key_files": key_files,
        "total_tasks": total_tasks,
        "plan_validation_result": validation_result,
        "plan_revision_count": revision_count,
    }
```

Remove unused imports:
- `from amelia.agents.schemas.architect import MarkdownPlanOutput`
- `from amelia.core.exceptions import SchemaValidationError`
- `from amelia.core.extraction import extract_structured`
- `from amelia.pipelines.implementation.external_plan import build_plan_extraction_prompt`

**Step 4: Run tests**

Run: `uv run pytest tests/unit/pipelines/ -v -k "plan_validator"`
Expected: PASS

**Step 5: Run lint and type check**

Run: `uv run ruff check amelia && uv run mypy amelia`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/pipelines/implementation/nodes.py tests/
git commit -m "refactor(plan_validator_node): drop LLM, use regex extraction"
```

---

### Task 4: Add structural validation to `import_external_plan`

**Files:**
- Modify: `amelia/pipelines/implementation/external_plan.py:229-299`
- Modify: `tests/unit/pipelines/test_external_plan.py`

**Step 1: Write failing test**

Add to `TestImportExternalPlan`:

```python
async def test_import_runs_structural_validation(self, mock_profile: Profile, tmp_path: Path) -> None:
    """Import runs structural validation and includes result."""
    plan_content = "**Goal:** Add auth\n\n### Task 1: Setup\n\nCreate: `src/auth.py`\n" + ("x" * 200)
    plan_file = tmp_path / "worktree" / "docs" / "plan.md"
    plan_file.parent.mkdir(parents=True, exist_ok=True)
    plan_file.write_text(plan_content)
    target_path = tmp_path / "worktree" / "docs" / "plans" / "plan.md"

    with patch("amelia.pipelines.implementation.external_plan.extract_plan_fields") as mock_extract:
        mock_extract.return_value = ExternalPlanImportResult(
            goal="Add auth",
            plan_markdown=plan_content,
            plan_path=target_path,
            key_files=["src/auth.py"],
            total_tasks=1,
        )
        result = await import_external_plan(
            plan_file=str(plan_file),
            plan_content=None,
            target_path=target_path,
            profile=mock_profile,
            workflow_id=uuid4(),
        )
    assert result.validation_result is not None
    assert result.validation_result.valid is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_external_plan.py::TestImportExternalPlan::test_import_runs_structural_validation -v`
Expected: FAIL — `ExternalPlanImportResult` has no `validation_result` field.

**Step 3: Add `validation_result` to `ExternalPlanImportResult`**

In `amelia/pipelines/implementation/external_plan.py`, update the model:

```python
from amelia.pipelines.implementation.utils import (
    PlanValidationResult,
    _extract_goal_from_plan,
    _extract_key_files_from_plan,
    extract_task_count,
    validate_plan_structure,
)

class ExternalPlanImportResult(BaseModel):
    """Result of importing an external plan."""

    goal: str
    plan_markdown: str | None = None
    plan_path: Path
    key_files: list[str] = Field(default_factory=list)
    total_tasks: int
    validation_result: PlanValidationResult | None = None
```

**Step 4: Add `validate_plan_structure` call to `import_external_plan`**

After the `extract_plan_fields` call, add:

```python
    validation_result = validate_plan_structure(result.goal, content)

    return ExternalPlanImportResult(
        goal=result.goal,
        plan_markdown=result.plan_markdown,
        plan_path=resolved_target,
        key_files=result.key_files,
        total_tasks=result.total_tasks,
        validation_result=validation_result,
    )
```

**Step 5: Run tests**

Run: `uv run pytest tests/unit/pipelines/test_external_plan.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/pipelines/implementation/external_plan.py tests/unit/pipelines/test_external_plan.py
git commit -m "feat(import_external_plan): add structural validation at import time"
```

---

### Task 5: Consolidate `set_workflow_plan` to use `import_external_plan`

**Files:**
- Modify: `amelia/server/orchestrator/service.py`
- Modify: `tests/unit/server/test_orchestrator_set_plan.py`

**Step 1: Update tests**

In `tests/unit/server/test_orchestrator_set_plan.py`:

- `test_set_plan_returns_validating_status`: rename to `test_set_plan_returns_ready_status`, assert `result["status"] == "ready"` and `result["goal"]` is populated.
- `test_set_plan_saves_plan_cache_with_null_goal`: update to assert goal is populated (no longer null).
- Remove any assertions about background tasks or `asyncio.create_task`.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/test_orchestrator_set_plan.py -v`
Expected: FAIL — `set_workflow_plan` still returns `"validating"`.

**Step 3: Rewrite `set_workflow_plan` to use `import_external_plan`**

Replace the inline read/write/extract logic with a call to `import_external_plan`. The method becomes:

1. Load workflow, validate status (existing guard checks stay)
2. Resolve profile and plan path (existing code)
3. Call `import_external_plan(plan_file, plan_content, target_path, profile, workflow_id)`
4. Save `PlanCache` with goal populated
5. Emit `PLAN_VALIDATED` or `PLAN_VALIDATION_FAILED` based on `plan_result.validation_result`
6. Return `{"status": "ready", "goal": ..., "key_files": [...], "total_tasks": N}`

Remove:
- The `asyncio.create_task(self._extract_plan_metadata(...))` block
- All inline `read_plan_content` / `write_plan_to_target` / `extract_task_count` calls
- The `source_path` resolution logic (now inside `import_external_plan`)

**Step 4: Remove `_extract_plan_metadata` method**

Delete the entire `_extract_plan_metadata` method (lines 2759-2841).

**Step 5: Clean up imports in service.py**

Remove from the `external_plan` import block:
- `extract_plan_fields` (no longer called directly)
- `read_plan_content` (no longer called directly by set_workflow_plan — check if used elsewhere first)
- `write_plan_to_target` (same check)

**Step 6: Run tests**

Run: `uv run pytest tests/unit/server/test_orchestrator_set_plan.py -v`
Expected: PASS

**Step 7: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: PASS

**Step 8: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/test_orchestrator_set_plan.py
git commit -m "refactor(set_workflow_plan): use import_external_plan, drop background LLM task"
```

---

### Task 6: Update `SetPlanResponse` and API route

**Files:**
- Modify: `amelia/server/models/responses.py:240-259`
- Modify: `amelia/server/routes/workflows.py`
- Modify: `tests/unit/server/test_set_plan_endpoint.py`

**Step 1: Update `SetPlanResponse` model**

```python
class SetPlanResponse(BaseModel):
    """Response from setting an external plan on a workflow.

    Attributes:
        status: 'ready' or 'invalid'.
        total_tasks: Number of tasks in the plan.
        goal: Extracted goal.
        key_files: Key files found in the plan.
    """

    status: Annotated[str, Field(description="'ready' or 'invalid'")]
    total_tasks: Annotated[int, Field(description="Number of tasks in the plan")]
    goal: Annotated[str, Field(description="Extracted goal from the plan")]
    key_files: Annotated[
        list[str],
        Field(default_factory=list, description="Key files found in the plan"),
    ]
```

Note: `goal` and `key_files` are no longer optional — they're always populated by regex.

**Step 2: Update endpoint route if needed**

Check `amelia/server/routes/workflows.py` line 538: `return SetPlanResponse(**result)`. The `result` dict from `set_workflow_plan` must now include `goal` and `key_files` as non-optional. This should work if Task 5 was done correctly.

**Step 3: Update endpoint tests**

In `tests/unit/server/test_set_plan_endpoint.py`, update mock return values to include `status="ready"`, `goal=...`, `key_files=[...]`.

**Step 4: Run tests**

Run: `uv run pytest tests/unit/server/test_set_plan_endpoint.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/responses.py amelia/server/routes/workflows.py tests/unit/server/test_set_plan_endpoint.py
git commit -m "refactor(SetPlanResponse): always return goal/key_files, status=ready"
```

---

### Task 7: Update dashboard for synchronous plan response

**Files:**
- Modify: `dashboard/src/components/JobQueueItem.tsx:101-118`
- Modify: `dashboard/src/components/__tests__/SetPlanModal.test.tsx`
- Modify: `dashboard/src/components/__tests__/PendingWorkflowControls.test.tsx`

**Step 1: Simplify `JobQueueItem` plan state**

The `planValidating` state and the `agent_message` event handler for `total_tasks` are no longer needed — the API returns immediately with the final state. Keep `planError` for handling `plan_validation_failed` events.

Update the event handler (lines 109-118):
```typescript
if (event.event_type === 'plan_validated') {
  setPlanError(null);
} else if (event.event_type === 'plan_validation_failed') {
  setPlanError((event.data?.error as string) ?? 'Validation failed');
}
```

Remove `planValidating` state and its UI indicators (the pulsing indicator around line 152). The plan is either ready or has an error — no intermediate "validating" state.

**Step 2: Update `SetPlanModal` tests**

In `dashboard/src/components/__tests__/SetPlanModal.test.tsx`, update mock responses:
- Change `{ status: 'validating', ... }` to `{ status: 'ready', goal: '...', key_files: [...], total_tasks: N }`
- Remove any assertions about "validating" state

**Step 3: Update `PendingWorkflowControls` tests**

In `dashboard/src/components/__tests__/PendingWorkflowControls.test.tsx`, update `key_files: []` mock data if needed.

**Step 4: Run dashboard tests**

Run (from dashboard/): `pnpm test:run`
Expected: PASS

**Step 5: Run type check**

Run (from dashboard/): `pnpm type-check`
Expected: PASS

**Step 6: Commit**

```bash
git add dashboard/src/
git commit -m "refactor(dashboard): remove plan validating state, use synchronous response"
```

---

### Task 8: Final cleanup and verification

**Files:**
- Various — cleanup pass

**Step 1: Run ruff to find unused imports**

Run: `uv run ruff check --fix amelia tests`

**Step 2: Run mypy**

Run: `uv run mypy amelia`

**Step 3: Run full backend test suite**

Run: `uv run pytest`

**Step 4: Run dashboard build**

Run (from dashboard/): `pnpm build`

**Step 5: Run dashboard tests**

Run (from dashboard/): `pnpm test:run`

**Step 6: Verify no remaining LLM references in plan extraction**

Run: `grep -r "extract_structured\|MarkdownPlanOutput\|build_plan_extraction_prompt" amelia/ tests/`
Expected: No matches (or only in unrelated files).

**Step 7: Commit any cleanup**

```bash
git add -A
git commit -m "chore: cleanup unused imports after plan extraction consolidation"
```
