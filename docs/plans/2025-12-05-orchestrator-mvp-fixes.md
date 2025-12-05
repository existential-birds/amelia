# Orchestrator MVP Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix two issues in OrchestratorService - a race condition bug and an O(n) performance issue.

**Architecture:** Minimal changes to existing code. Fix sequence lock TOCTOU race with `setdefault()`. Replace `_active_tasks: dict[str, Task]` with `dict[str, tuple[str, Task]]` to cache workflow_id and eliminate DB lookup in `get_workflow_by_worktree`.

**Tech Stack:** Python 3.12, asyncio, pytest

---

## Task 1: Fix Sequence Lock Race Condition (P0 Bug)

**Problem:** Lines 270-271 have a TOCTOU race condition where two concurrent `_emit()` calls for the same workflow_id can both create separate locks, causing duplicate sequence numbers.

**Files:**
- Modify: `amelia/server/orchestrator/service.py:270-273`
- Test: `tests/unit/server/orchestrator/test_service.py`

**Step 1: Write failing test for race condition**

Add this test to `tests/unit/server/orchestrator/test_service.py`:

```python
@pytest.mark.asyncio
async def test_emit_concurrent_lock_creation_race(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """Concurrent first emits for same workflow should not create duplicate locks."""
    # Slow down the lock acquisition to increase race window
    original_get_max = mock_repository.get_max_event_sequence

    async def slow_get_max(workflow_id: str) -> int:
        await asyncio.sleep(0.01)  # Create race window
        return await original_get_max(workflow_id)

    mock_repository.get_max_event_sequence = slow_get_max

    # Fire many concurrent emits for a NEW workflow (no lock exists yet)
    tasks = [
        orchestrator._emit("race-wf", EventType.FILE_CREATED, f"File {i}")
        for i in range(10)
    ]
    await asyncio.gather(*tasks)

    # All sequences must be unique (1-10)
    calls = mock_repository.save_event.call_args_list
    sequences = [call[0][0].sequence for call in calls]
    assert len(set(sequences)) == 10, f"Duplicate sequences found: {sequences}"
    assert set(sequences) == set(range(1, 11))
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py::test_emit_concurrent_lock_creation_race -v`

Expected: FAIL with duplicate sequences (race condition manifests)

**Step 3: Fix the race condition**

In `amelia/server/orchestrator/service.py`, replace lines 269-273:

```python
# BEFORE (lines 269-273):
        # Get or create lock for this workflow
        if workflow_id not in self._sequence_locks:
            self._sequence_locks[workflow_id] = asyncio.Lock()

        async with self._sequence_locks[workflow_id]:
```

```python
# AFTER:
        # Get or create lock atomically (setdefault is atomic for dict operations)
        lock = self._sequence_locks.setdefault(workflow_id, asyncio.Lock())

        async with lock:
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py::test_emit_concurrent_lock_creation_race -v`

Expected: PASS

**Step 5: Run full test suite for service**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py -v`

Expected: All tests PASS

**Step 6: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/orchestrator/test_service.py
git commit -m "fix(orchestrator): resolve sequence lock TOCTOU race condition

Use setdefault() for atomic lock creation to prevent concurrent _emit()
calls from creating separate locks and generating duplicate sequence
numbers."
```

---

## Task 2: Optimize get_workflow_by_worktree with Cached workflow_id

**Problem:** `get_workflow_by_worktree` calls `repository.list_active()` (O(n)) then iterates to find the matching workflow. With many concurrent workflows, this is expensive.

**Solution:** Change `_active_tasks` from `dict[str, Task]` to `dict[str, tuple[str, Task]]` where the tuple is `(workflow_id, task)`. This allows O(1) lookup without DB call.

**Files:**
- Modify: `amelia/server/orchestrator/service.py:46,79-83,117,121,154,163-164,182-183,394`
- Test: `tests/unit/server/orchestrator/test_service.py`

**Step 1: Write failing test for cached lookup**

Add this test to `tests/unit/server/orchestrator/test_service.py`:

```python
@pytest.mark.asyncio
async def test_get_workflow_by_worktree_uses_cache(
    orchestrator: OrchestratorService,
    mock_repository: AsyncMock,
):
    """get_workflow_by_worktree should use cached workflow_id, not DB."""
    # Create workflow state
    mock_state = ServerExecutionState(
        id="wf-cached",
        issue_id="ISSUE-123",
        worktree_path="/cached/worktree",
        worktree_name="cached",
        workflow_status="in_progress",
        started_at=datetime.now(UTC),
    )
    mock_repository.get.return_value = mock_state

    # Simulate active workflow with cached ID
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/cached/worktree"] = ("wf-cached", task)

    # Reset mock to track calls
    mock_repository.list_active.reset_mock()

    # Get workflow by worktree
    result = await orchestrator.get_workflow_by_worktree("/cached/worktree")

    # Should NOT call list_active (O(n) query)
    mock_repository.list_active.assert_not_called()

    # Should call get() with cached workflow_id
    mock_repository.get.assert_called_once_with("wf-cached")

    # Should return the workflow
    assert result is not None
    assert result.id == "wf-cached"

    # Cleanup
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py::test_get_workflow_by_worktree_uses_cache -v`

Expected: FAIL (current impl calls list_active, not get)

**Step 3: Update type annotation**

In `amelia/server/orchestrator/service.py`, change line 46:

```python
# BEFORE:
        self._active_tasks: dict[str, asyncio.Task[None]] = {}  # worktree_path -> task
```

```python
# AFTER:
        self._active_tasks: dict[str, tuple[str, asyncio.Task[None]]] = {}  # worktree_path -> (workflow_id, task)
```

**Step 4: Update start_workflow to store tuple**

In `amelia/server/orchestrator/service.py`, change lines 79-83 (inside `async with self._start_lock:`):

```python
# BEFORE:
            # Check worktree conflict - need to find existing workflow_id
            if worktree_path in self._active_tasks:
                # Find the existing workflow_id for this worktree
                existing_workflow = await self.get_workflow_by_worktree(worktree_path)
                existing_id = existing_workflow.id if existing_workflow else "unknown"
                raise WorkflowConflictError(worktree_path, existing_id)
```

```python
# AFTER:
            # Check worktree conflict - workflow_id is cached in tuple
            if worktree_path in self._active_tasks:
                existing_id, _ = self._active_tasks[worktree_path]
                raise WorkflowConflictError(worktree_path, existing_id)
```

**Step 5: Update task registration to store tuple**

In `amelia/server/orchestrator/service.py`, change line 117:

```python
# BEFORE:
            self._active_tasks[worktree_path] = task
```

```python
# AFTER:
            self._active_tasks[worktree_path] = (workflow_id, task)
```

**Step 6: Update cleanup_task callback**

In `amelia/server/orchestrator/service.py`, the cleanup_task function (lines 120-128) needs no changes since it uses `pop()` which works for any value type.

**Step 7: Update cancel_workflow task access**

In `amelia/server/orchestrator/service.py`, change lines 163-165:

```python
# BEFORE:
        if workflow.worktree_path in self._active_tasks:
            task = self._active_tasks[workflow.worktree_path]
            task.cancel()
```

```python
# AFTER:
        if workflow.worktree_path in self._active_tasks:
            _, task = self._active_tasks[workflow.worktree_path]
            task.cancel()
```

**Step 8: Update cancel_all_workflows task access**

In `amelia/server/orchestrator/service.py`, change lines 182-187:

```python
# BEFORE:
        for worktree_path in list(self._active_tasks.keys()):
            task = self._active_tasks.get(worktree_path)
            if task:
                task.cancel()
                with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=timeout)
```

```python
# AFTER:
        for worktree_path in list(self._active_tasks.keys()):
            entry = self._active_tasks.get(worktree_path)
            if entry:
                _, task = entry
                task.cancel()
                with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=timeout)
```

**Step 9: Update get_workflow_by_worktree to use cache**

In `amelia/server/orchestrator/service.py`, replace the entire method (lines 197-219):

```python
# BEFORE:
    async def get_workflow_by_worktree(
        self,
        worktree_path: str,
    ) -> ServerExecutionState | None:
        """Get workflow by worktree path.

        Args:
            worktree_path: The worktree path.

        Returns:
            Workflow state if found, None otherwise.
        """
        # Find workflow ID from active tasks
        if worktree_path not in self._active_tasks:
            return None

        # Search repository for workflow with this worktree_path
        workflows = await self._repository.list_active()
        for workflow in workflows:
            if workflow.worktree_path == worktree_path:
                return workflow

        return None
```

```python
# AFTER:
    async def get_workflow_by_worktree(
        self,
        worktree_path: str,
    ) -> ServerExecutionState | None:
        """Get workflow by worktree path.

        Args:
            worktree_path: The worktree path.

        Returns:
            Workflow state if found, None otherwise.
        """
        # Use cached workflow_id for O(1) lookup
        entry = self._active_tasks.get(worktree_path)
        if not entry:
            return None

        workflow_id, _ = entry
        return await self._repository.get(workflow_id)
```

**Step 10: Update reject_workflow task access**

In `amelia/server/orchestrator/service.py`, change lines 393-395:

```python
# BEFORE:
            if workflow.worktree_path in self._active_tasks:
                self._active_tasks[workflow.worktree_path].cancel()
```

```python
# AFTER:
            if workflow.worktree_path in self._active_tasks:
                _, task = self._active_tasks[workflow.worktree_path]
                task.cancel()
```

**Step 11: Run the new test**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py::test_get_workflow_by_worktree_uses_cache -v`

Expected: PASS

**Step 12: Update existing tests that access _active_tasks directly**

Several existing tests directly manipulate `_active_tasks`. Update them in `tests/unit/server/orchestrator/test_service.py`:

In `test_start_workflow_conflict` (lines 88-90):

```python
# BEFORE:
    orchestrator._active_tasks["/path/to/worktree"] = asyncio.create_task(
        asyncio.sleep(1)
    )
```

```python
# AFTER:
    orchestrator._active_tasks["/path/to/worktree"] = (
        "existing-wf",
        asyncio.create_task(asyncio.sleep(1)),
    )
```

And update cleanup (lines 102-104):

```python
# BEFORE:
    orchestrator._active_tasks["/path/to/worktree"].cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await orchestrator._active_tasks["/path/to/worktree"]
```

```python
# AFTER:
    _, task = orchestrator._active_tasks["/path/to/worktree"]
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
```

In `test_start_workflow_concurrency_limit` (lines 114-117):

```python
# BEFORE:
    for i in range(5):
        task = asyncio.create_task(asyncio.sleep(1))
        orchestrator._active_tasks[f"/path/to/worktree{i}"] = task
        tasks.append(task)
```

```python
# AFTER:
    for i in range(5):
        task = asyncio.create_task(asyncio.sleep(1))
        orchestrator._active_tasks[f"/path/to/worktree{i}"] = (f"wf-{i}", task)
        tasks.append(task)
```

In `test_cancel_workflow` (lines 153-154):

```python
# BEFORE:
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/path/to/worktree"] = task
```

```python
# AFTER:
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/path/to/worktree"] = ("wf-1", task)
```

In `test_get_active_workflows` (lines 203-204):

```python
# BEFORE:
    orchestrator._active_tasks["/path/1"] = MagicMock()
    orchestrator._active_tasks["/path/2"] = MagicMock()
```

```python
# AFTER:
    orchestrator._active_tasks["/path/1"] = ("wf-1", MagicMock())
    orchestrator._active_tasks["/path/2"] = ("wf-2", MagicMock())
```

In `test_reject_workflow_success` (lines 343-344):

```python
# BEFORE:
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/path/to/worktree"] = task
```

```python
# AFTER:
    task = asyncio.create_task(asyncio.sleep(100))
    orchestrator._active_tasks["/path/to/worktree"] = ("wf-1", task)
```

**Step 13: Run full test suite**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py -v`

Expected: All tests PASS

**Step 14: Run type checker**

Run: `uv run mypy amelia/server/orchestrator/service.py`

Expected: No errors

**Step 15: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/orchestrator/test_service.py
git commit -m "perf(orchestrator): cache workflow_id in _active_tasks for O(1) lookup

Change _active_tasks from dict[str, Task] to dict[str, tuple[str, Task]]
where tuple is (workflow_id, task). This eliminates the O(n) database
call in get_workflow_by_worktree, replacing it with O(1) cache lookup
followed by direct repository.get() call."
```

---

## Verification

**Final verification steps:**

Run: `uv run pytest tests/unit/server/orchestrator/ -v`

Run: `uv run ruff check amelia/server/orchestrator/`

Run: `uv run mypy amelia/server/orchestrator/`

All should pass with no errors.
