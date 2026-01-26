# Replan Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow re-generating a plan for a blocked workflow (awaiting approval) by adding a `BLOCKED → PLANNING` transition, an orchestrator `replan_workflow()` method, a REST endpoint, and a dashboard "Replan" button.

**Architecture:** The replan flow piggybacks on existing planning infrastructure. The only new state transition is `BLOCKED → PLANNING`. The orchestrator deletes the stale LangGraph checkpoint, clears plan fields, and reuses `_run_planning_task()`. The dashboard adds a "Replan" button to `ApprovalControls` using the same fetcher pattern as Approve/Reject.

**Tech Stack:** Python 3.12+ / FastAPI / LangGraph / SQLite (backend), React 19 / React Router v7 / TypeScript / Vitest (dashboard)

---

### Task 1: State Machine — Add `BLOCKED → PLANNING` Transition

**Files:**
- Modify: `amelia/server/models/state.py:40` (VALID_TRANSITIONS dict)
- Test: `tests/unit/server/orchestrator/test_service.py` (existing state machine tests)

**Step 1: Write the failing test**

In `tests/unit/server/test_state_transitions.py` (new file):

```python
"""Unit tests for replan state transition."""
import pytest

from amelia.server.models.state import WorkflowStatus, validate_transition, InvalidStateTransitionError


class TestReplanTransition:
    """Tests for BLOCKED → PLANNING transition."""

    def test_blocked_to_planning_is_valid(self) -> None:
        """BLOCKED → PLANNING should be a valid transition for replan."""
        # Should not raise
        validate_transition(WorkflowStatus.BLOCKED, WorkflowStatus.PLANNING)

    def test_completed_to_planning_is_invalid(self) -> None:
        """Terminal states cannot transition to PLANNING."""
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(WorkflowStatus.COMPLETED, WorkflowStatus.PLANNING)

    def test_failed_to_planning_is_invalid(self) -> None:
        """Terminal states cannot transition to PLANNING."""
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(WorkflowStatus.FAILED, WorkflowStatus.PLANNING)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_state_transitions.py -v`
Expected: `test_blocked_to_planning_is_valid` FAILS with `InvalidStateTransitionError`

**Step 3: Add the transition**

In `amelia/server/models/state.py`, change line 40 from:

```python
WorkflowStatus.BLOCKED: {WorkflowStatus.IN_PROGRESS, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED},
```

to:

```python
WorkflowStatus.BLOCKED: {WorkflowStatus.PLANNING, WorkflowStatus.IN_PROGRESS, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED},
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_state_transitions.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add amelia/server/models/state.py tests/unit/server/test_state_transitions.py
git commit -m "feat(state): add BLOCKED → PLANNING transition for replan"
```

---

### Task 2: Orchestrator — Add `_delete_checkpoint()` Private Method

**Files:**
- Modify: `amelia/server/orchestrator/service.py` (add method to `OrchestratorService`)
- Test: `tests/unit/server/orchestrator/test_replan.py` (new file)

**Step 1: Write the failing test**

Create `tests/unit/server/orchestrator/test_replan.py`:

```python
"""Unit tests for replan_workflow orchestrator method."""
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import AgentConfig, Profile
from amelia.pipelines.implementation.state import ImplementationState
from amelia.server.events.bus import EventBus
from amelia.server.exceptions import InvalidStateError, WorkflowConflictError, WorkflowNotFoundError
from amelia.server.models.events import EventType
from amelia.server.models.state import ServerExecutionState, WorkflowStatus
from amelia.server.orchestrator.service import OrchestratorService


@pytest.fixture
def mock_event_bus() -> EventBus:
    """Create event bus for testing."""
    return EventBus()


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create mock repository."""
    repo = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.set_status = AsyncMock()
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    repo.get = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_profile_repo() -> AsyncMock:
    """Create mock profile repository."""
    repo = AsyncMock()
    agent_config = AgentConfig(driver="cli", model="sonnet")
    default_profile = Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test-repo",
        agents={
            "architect": agent_config,
            "developer": agent_config,
            "reviewer": agent_config,
            "task_reviewer": agent_config,
            "evaluator": agent_config,
        },
    )
    repo.get_profile.return_value = default_profile
    repo.get_active_profile.return_value = default_profile
    return repo


@pytest.fixture
def orchestrator(
    mock_event_bus: EventBus,
    mock_repository: AsyncMock,
    mock_profile_repo: AsyncMock,
) -> OrchestratorService:
    """Create orchestrator service."""
    return OrchestratorService(
        event_bus=mock_event_bus,
        repository=mock_repository,
        profile_repo=mock_profile_repo,
        max_concurrent=5,
    )


def make_blocked_workflow(
    workflow_id: str = "wf-replan-1",
    issue_id: str = "ISSUE-REPLAN",
) -> ServerExecutionState:
    """Create a blocked workflow with a plan ready for replan testing."""
    return ServerExecutionState(
        id=workflow_id,
        issue_id=issue_id,
        worktree_path="/tmp/test-repo",
        workflow_status=WorkflowStatus.BLOCKED,
        current_stage=None,
        planned_at=datetime.now(UTC),
        execution_state=ImplementationState(
            workflow_id=workflow_id,
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            goal="Original goal",
            plan_markdown="# Original plan",
            plan_path=None,
            key_files=["original.py"],
            total_tasks=3,
        ),
    )


class TestDeleteCheckpoint:
    """Tests for _delete_checkpoint helper."""

    async def test_delete_checkpoint_removes_data(
        self,
        orchestrator: OrchestratorService,
    ) -> None:
        """_delete_checkpoint should open sqlite and delete checkpoint data."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        mock_saver = AsyncMock()
        mock_saver_ctx = AsyncMock()
        mock_saver_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_saver_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "amelia.server.orchestrator.service.AsyncSqliteSaver"
        ) as mock_saver_class:
            mock_saver_class.from_conn_string.return_value = mock_saver_ctx

            await orchestrator._delete_checkpoint("wf-123")

            # Should have opened connection with checkpoint path
            mock_saver_class.from_conn_string.assert_called_once()
            # Should have executed delete queries
            assert mock_conn.execute.call_count >= 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_replan.py::TestDeleteCheckpoint -v`
Expected: FAIL with `AttributeError: 'OrchestratorService' object has no attribute '_delete_checkpoint'`

**Step 3: Implement `_delete_checkpoint`**

Add to `OrchestratorService` in `amelia/server/orchestrator/service.py`, after the `_emit` method:

```python
async def _delete_checkpoint(self, workflow_id: str) -> None:
    """Delete LangGraph checkpoint data for a workflow.

    Removes all checkpoint records (checkpoints, writes, blobs) for
    the given thread ID. Used by replan to start fresh.

    Args:
        workflow_id: The workflow/thread ID whose checkpoint to delete.
    """
    async with AsyncSqliteSaver.from_conn_string(
        str(self._checkpoint_path)
    ) as conn:
        for table in ("checkpoints", "writes", "checkpoint_blobs"):
            await conn.execute(
                f"DELETE FROM {table} WHERE thread_id = ?",  # noqa: S608
                (workflow_id,),
            )
        logger.info("Deleted checkpoint", workflow_id=workflow_id)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_replan.py::TestDeleteCheckpoint -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/orchestrator/test_replan.py
git commit -m "feat(orchestrator): add _delete_checkpoint for replan"
```

---

### Task 3: Orchestrator — Add `replan_workflow()` Method

**Files:**
- Modify: `amelia/server/orchestrator/service.py` (add `replan_workflow` method)
- Test: `tests/unit/server/orchestrator/test_replan.py` (add tests)

**Step 1: Write the failing tests**

Append to `tests/unit/server/orchestrator/test_replan.py`:

```python
class TestReplanWorkflow:
    """Tests for replan_workflow method."""

    async def test_replan_happy_path(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """replan_workflow should clear plan, delete checkpoint, and spawn planning task."""
        workflow = make_blocked_workflow()
        mock_repository.get.return_value = workflow

        with patch.object(orchestrator, "_delete_checkpoint", new_callable=AsyncMock) as mock_delete:
            with patch.object(orchestrator, "_run_planning_task", new_callable=AsyncMock):
                await orchestrator.replan_workflow("wf-replan-1")

        # Should have deleted checkpoint
        mock_delete.assert_awaited_once_with("wf-replan-1")

        # Should have updated workflow with cleared plan fields and PLANNING status
        mock_repository.update.assert_called()
        updated = mock_repository.update.call_args[0][0]
        assert updated.workflow_status == WorkflowStatus.PLANNING
        assert updated.current_stage == "architect"
        assert updated.planned_at is None
        assert updated.execution_state is not None
        assert updated.execution_state.goal is None
        assert updated.execution_state.plan_markdown is None
        assert updated.execution_state.key_files == []
        assert updated.execution_state.total_tasks == 1

    async def test_replan_wrong_status_raises(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """replan_workflow should reject non-blocked workflows."""
        workflow = make_blocked_workflow()
        workflow.workflow_status = WorkflowStatus.IN_PROGRESS
        mock_repository.get.return_value = workflow

        with pytest.raises(InvalidStateError, match="blocked"):
            await orchestrator.replan_workflow("wf-replan-1")

    async def test_replan_not_found_raises(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """replan_workflow should raise for missing workflow."""
        mock_repository.get.return_value = None

        with pytest.raises(WorkflowNotFoundError):
            await orchestrator.replan_workflow("nonexistent")

    async def test_replan_conflict_when_planning_running(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
    ) -> None:
        """replan_workflow should raise conflict if planning task already active."""
        workflow = make_blocked_workflow()
        mock_repository.get.return_value = workflow

        # Simulate an active planning task
        orchestrator._planning_tasks["wf-replan-1"] = MagicMock(spec=asyncio.Task)

        with pytest.raises(WorkflowConflictError, match="already running"):
            await orchestrator.replan_workflow("wf-replan-1")

    async def test_replan_emits_event(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        mock_event_bus: EventBus,
    ) -> None:
        """replan_workflow should emit a stage_started event."""
        workflow = make_blocked_workflow()
        mock_repository.get.return_value = workflow

        received_events = []
        mock_event_bus.subscribe(lambda e: received_events.append(e))

        with patch.object(orchestrator, "_delete_checkpoint", new_callable=AsyncMock):
            with patch.object(orchestrator, "_run_planning_task", new_callable=AsyncMock):
                await orchestrator.replan_workflow("wf-replan-1")

        # Should have emitted replanning event
        stage_events = [e for e in received_events if e.event_type == EventType.STAGE_STARTED]
        assert len(stage_events) >= 1
        assert any("replan" in (e.message or "").lower() for e in stage_events)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/orchestrator/test_replan.py::TestReplanWorkflow -v`
Expected: FAIL with `AttributeError: 'OrchestratorService' object has no attribute 'replan_workflow'`

**Step 3: Implement `replan_workflow`**

Add to `OrchestratorService` in `amelia/server/orchestrator/service.py`, after `set_workflow_plan`:

```python
async def replan_workflow(self, workflow_id: str) -> None:
    """Regenerate the plan for a blocked workflow.

    Deletes the stale LangGraph checkpoint, clears plan-related fields,
    transitions the workflow back to PLANNING, and spawns a fresh
    planning task using the same issue/profile.

    Args:
        workflow_id: The workflow to replan.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist.
        InvalidStateError: If workflow is not in blocked status.
        WorkflowConflictError: If a planning task is already running.
    """
    workflow = await self._repository.get(workflow_id)
    if workflow is None:
        raise WorkflowNotFoundError(workflow_id)

    if workflow.workflow_status != WorkflowStatus.BLOCKED:
        raise InvalidStateError(
            f"Workflow must be in blocked status to replan, but is in {workflow.workflow_status}",
            workflow_id=workflow_id,
            current_status=str(workflow.workflow_status),
        )

    # Defensive: reject if planning task is already running
    if workflow_id in self._planning_tasks:
        raise WorkflowConflictError(
            f"Planning task already running for workflow {workflow_id}"
        )

    # Delete stale checkpoint
    await self._delete_checkpoint(workflow_id)

    # Clear plan-related fields from execution_state
    if workflow.execution_state is not None:
        workflow.execution_state = workflow.execution_state.model_copy(
            update={
                "goal": None,
                "plan_markdown": None,
                "raw_architect_output": None,
                "plan_path": None,
                "key_files": [],
                "total_tasks": 1,
                "tool_calls": [],
                "tool_results": [],
            }
        )

    # Transition to PLANNING
    workflow.workflow_status = WorkflowStatus.PLANNING
    workflow.current_stage = "architect"
    workflow.planned_at = None
    await self._repository.update(workflow)

    # Emit replanning event
    await self._emit(
        workflow_id,
        EventType.STAGE_STARTED,
        "Replanning: regenerating plan with Architect",
        agent="architect",
        data={"stage": "architect", "replan": True},
    )

    # Resolve profile for planning task
    profile = await self._get_profile_or_fail(
        workflow_id,
        workflow.execution_state.profile_id if workflow.execution_state else "default",
        workflow.worktree_path,
    )
    if profile is None:
        raise ValueError(f"Profile not found for workflow {workflow_id}")

    profile = self._update_profile_working_dir(profile, workflow.worktree_path)

    # Spawn planning task in background (reuses existing _run_planning_task)
    task = asyncio.create_task(
        self._run_planning_task(workflow_id, workflow, workflow.execution_state, profile)
    )
    self._planning_tasks[workflow_id] = task

    def cleanup_planning(_: asyncio.Task[None]) -> None:
        self._planning_tasks.pop(workflow_id, None)

    task.add_done_callback(cleanup_planning)

    logger.info(
        "Replan started",
        workflow_id=workflow_id,
        issue_id=workflow.issue_id,
    )
```

Note: The import for `asyncio` is already present in the file.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/orchestrator/test_replan.py::TestReplanWorkflow -v`
Expected: All 5 tests PASS

**Step 5: Run full unit test suite to check for regressions**

Run: `uv run pytest tests/unit/ -x --timeout=30`
Expected: All PASS

**Step 6: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/orchestrator/test_replan.py
git commit -m "feat(orchestrator): add replan_workflow method"
```

---

### Task 4: REST Endpoint — Add `POST /{id}/replan` Route

**Files:**
- Modify: `amelia/server/routes/workflows.py` (add route handler)
- Test: `tests/unit/server/routes/test_workflow_routes.py` (add tests) or new file

**Step 1: Write the failing test**

Create `tests/unit/server/routes/test_replan_route.py`:

```python
"""Unit tests for the replan workflow route handler."""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.exceptions import InvalidStateError, WorkflowConflictError, WorkflowNotFoundError
from amelia.server.routes.workflows import configure_exception_handlers, router


def get_orchestrator_mock() -> MagicMock:
    """Create mock orchestrator."""
    mock = MagicMock()
    mock.replan_workflow = AsyncMock()
    return mock


def create_test_client(orchestrator_mock: MagicMock) -> TestClient:
    """Create test client with mocked orchestrator."""
    app = FastAPI()

    @asynccontextmanager
    async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
        yield

    app.router.lifespan_context = noop_lifespan

    # Wire the dependency
    from amelia.server.dependencies import get_orchestrator
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator_mock

    app.include_router(router, prefix="/api/workflows")
    configure_exception_handlers(app)
    return TestClient(app)


class TestReplanRoute:
    """Tests for POST /api/workflows/{id}/replan."""

    def test_replan_success(self) -> None:
        """Should return 200 with workflow_id and status."""
        orch = get_orchestrator_mock()
        client = create_test_client(orch)

        response = client.post("/api/workflows/wf-123/replan")

        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "wf-123"
        assert data["status"] == "planning"
        orch.replan_workflow.assert_awaited_once_with("wf-123")

    def test_replan_not_found(self) -> None:
        """Should return 404 for missing workflow."""
        orch = get_orchestrator_mock()
        orch.replan_workflow.side_effect = WorkflowNotFoundError("wf-missing")
        client = create_test_client(orch)

        response = client.post("/api/workflows/wf-missing/replan")
        assert response.status_code == 404

    def test_replan_wrong_status(self) -> None:
        """Should return 422 for non-blocked workflow."""
        orch = get_orchestrator_mock()
        orch.replan_workflow.side_effect = InvalidStateError(
            "Workflow must be in blocked status",
            workflow_id="wf-wrong",
            current_status="in_progress",
        )
        client = create_test_client(orch)

        response = client.post("/api/workflows/wf-wrong/replan")
        assert response.status_code == 422

    def test_replan_conflict(self) -> None:
        """Should return 409 when planning already running."""
        orch = get_orchestrator_mock()
        orch.replan_workflow.side_effect = WorkflowConflictError(
            "Planning task already running for workflow wf-busy"
        )
        client = create_test_client(orch)

        response = client.post("/api/workflows/wf-busy/replan")
        assert response.status_code == 409
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/routes/test_replan_route.py -v`
Expected: FAIL with 404 (route doesn't exist yet) or similar

**Step 3: Implement the route handler**

Add to `amelia/server/routes/workflows.py`, after the `reject_workflow` function:

```python
@router.post("/{workflow_id}/replan", response_model=ActionResponse)
async def replan_workflow(
    workflow_id: str,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> ActionResponse:
    """Replan a blocked workflow by regenerating the Architect plan.

    Deletes the stale checkpoint, clears plan fields, and spawns a
    new planning task. The workflow transitions from blocked to planning.

    Args:
        workflow_id: Unique workflow identifier.
        orchestrator: Orchestrator service dependency.

    Returns:
        ActionResponse with status "planning" and workflow_id.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist.
        InvalidStateError: If workflow is not in blocked state.
        WorkflowConflictError: If planning task is already running.
    """
    await orchestrator.replan_workflow(workflow_id)
    logger.info("Replan started", workflow_id=workflow_id)
    return ActionResponse(status="planning", workflow_id=workflow_id)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/routes/test_replan_route.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add amelia/server/routes/workflows.py tests/unit/server/routes/test_replan_route.py
git commit -m "feat(api): add POST /workflows/{id}/replan endpoint"
```

---

### Task 5: Dashboard — Add `replanWorkflow` API Client Method

**Files:**
- Modify: `dashboard/src/api/client.ts` (add method)

**Step 1: Add the API method**

Add to the `api` object in `dashboard/src/api/client.ts`, alongside `approveWorkflow` and `rejectWorkflow`:

```typescript
async replanWorkflow(id: string): Promise<void> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/workflows/${id}/replan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  await handleResponse(response);
},
```

**Step 2: Commit**

```bash
git add dashboard/src/api/client.ts
git commit -m "feat(dashboard): add replanWorkflow API client method"
```

---

### Task 6: Dashboard — Add `replanAction` Router Action

**Files:**
- Modify: `dashboard/src/actions/workflows.ts` (add action)
- Modify: `dashboard/src/actions/index.ts` (re-export)
- Modify: `dashboard/src/router.tsx` (register route)

**Step 1: Add the action function**

Add to `dashboard/src/actions/workflows.ts`, after `cancelAction`:

```typescript
/**
 * Replans a blocked workflow by regenerating the Architect plan.
 *
 * Handles the replan action for a workflow route, sending the request to the API.
 *
 * @param args - React Router action function arguments containing route params.
 * @returns Action result indicating successful replan initiation or error details.
 * @example
 * ```typescript
 * const result = await replanAction({ params: { id: 'workflow-123' } });
 * // Success: { success: true, action: 'replanning' }
 * // Error: { success: false, action: 'replanning', error: 'Workflow ID required' }
 * ```
 */
export async function replanAction({ params }: ActionFunctionArgs): Promise<ActionResult> {
  if (!params.id) {
    return { success: false, action: 'replanning', error: 'Workflow ID required' };
  }

  try {
    await api.replanWorkflow(params.id);
    return { success: true, action: 'replanning' };
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to replan workflow';
    return { success: false, action: 'replanning', error: message };
  }
}
```

**Step 2: Update the barrel export**

In `dashboard/src/actions/index.ts`, change:
```typescript
export { approveAction, rejectAction, cancelAction } from './workflows';
```
to:
```typescript
export { approveAction, rejectAction, cancelAction, replanAction } from './workflows';
```

**Step 3: Register the route**

In `dashboard/src/router.tsx`, add after the cancel action route (line 86):

```typescript
{
  path: 'workflows/:id/replan',
  action: replanAction,
},
```

And update the import on line 12:
```typescript
import { approveAction, rejectAction, cancelAction, replanAction } from '@/actions/workflows';
```

Also update the JSDoc route list to include `workflows/:id/replan`.

**Step 4: Commit**

```bash
git add dashboard/src/actions/workflows.ts dashboard/src/actions/index.ts dashboard/src/router.tsx
git commit -m "feat(dashboard): add replan router action and route"
```

---

### Task 7: Dashboard — Add "Replan" Button to `ApprovalControls`

**Files:**
- Modify: `dashboard/src/components/ApprovalControls.tsx`
- Test: `dashboard/src/components/ApprovalControls.test.tsx` (new or existing)

**Step 1: Write the failing test**

Create `dashboard/src/components/__tests__/ApprovalControls.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ApprovalControls } from '../ApprovalControls';

function renderWithRouter(workflowId: string, status: 'pending' | 'approved' | 'rejected' = 'pending') {
  const routes = [
    {
      path: '/',
      element: (
        <ApprovalControls
          workflowId={workflowId}
          planSummary="Test plan"
          planMarkdown="# Plan"
          status={status}
        />
      ),
    },
    { path: '/workflows/:id/approve', action: async () => ({ success: true }) },
    { path: '/workflows/:id/reject', action: async () => ({ success: true }) },
    { path: '/workflows/:id/replan', action: async () => ({ success: true }) },
  ];

  const router = createMemoryRouter(routes, { initialEntries: ['/'] });
  return render(<RouterProvider router={router} />);
}

describe('ApprovalControls', () => {
  it('should render Replan button when status is pending', () => {
    renderWithRouter('wf-123', 'pending');
    expect(screen.getByRole('button', { name: /replan/i })).toBeInTheDocument();
  });

  it('should not render Replan button when status is approved', () => {
    renderWithRouter('wf-123', 'approved');
    expect(screen.queryByRole('button', { name: /replan/i })).not.toBeInTheDocument();
  });

  it('should not render Replan button when status is rejected', () => {
    renderWithRouter('wf-123', 'rejected');
    expect(screen.queryByRole('button', { name: /replan/i })).not.toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test:run -- --reporter=verbose src/components/__tests__/ApprovalControls.test.tsx`
Expected: FAIL — "Replan" button not found

**Step 3: Add the Replan button to `ApprovalControls`**

In `dashboard/src/components/ApprovalControls.tsx`:

1. Add a `replanFetcher`:

```tsx
const replanFetcher = useFetcher<ActionResponse>();
```

2. Update `isPending` to include replan:

```tsx
const isPending = approveFetcher.state !== 'idle' || rejectFetcher.state !== 'idle' || replanFetcher.state !== 'idle';
```

3. Add a `RefreshCw` import from lucide-react:

```tsx
import { Check, X, ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
```

4. Add the Replan button inside the `status === 'pending'` block, after the Reject button group (after line 175, before `</div>`):

```tsx
<replanFetcher.Form method="post" action={`/workflows/${workflowId}/replan`}>
  <Button
    type="submit"
    variant="outline"
    disabled={isPending}
    className="border-accent text-accent hover:bg-accent hover:text-foreground focus-visible:ring-accent/50"
  >
    {replanFetcher.state !== 'idle' ? (
      <Loader className="w-4 h-4 mr-2" />
    ) : (
      <RefreshCw className="w-4 h-4 mr-2" />
    )}
    Replan
  </Button>
</replanFetcher.Form>
```

5. Add error display for replan fetcher alongside the existing error displays (after `rejectFetcher.data?.error`):

```tsx
{replanFetcher.data?.error && (
  <p className="text-sm text-destructive mt-2">{replanFetcher.data.error}</p>
)}
```

**Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test:run -- --reporter=verbose src/components/__tests__/ApprovalControls.test.tsx`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add dashboard/src/components/ApprovalControls.tsx dashboard/src/components/__tests__/ApprovalControls.test.tsx
git commit -m "feat(dashboard): add Replan button to ApprovalControls"
```

---

### Task 8: Integration Test — Replan Lifecycle

**Files:**
- Create: `tests/integration/test_replan_flow.py`

This is the critical test. It validates the full replan cycle: `PENDING → PLANNING → BLOCKED → (replan) → PLANNING → BLOCKED`.

**Step 1: Write the integration test**

Create `tests/integration/test_replan_flow.py`:

```python
"""Integration tests for the replan workflow lifecycle.

Tests the full replan cycle with real OrchestratorService, real LangGraph graph,
mocking only at the LLM HTTP boundary.
"""
import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository, ProfileRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType
from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.models.state import WorkflowStatus
from amelia.server.orchestrator.service import OrchestratorService
from tests.conftest import init_git_repo


@pytest.fixture
def temp_checkpoint_db(tmp_path: Path) -> str:
    """Temporary checkpoint database path."""
    return str(tmp_path / "checkpoints.db")


@pytest.fixture
async def test_db(tmp_path: Path) -> AsyncGenerator[Database, None]:
    """Create and initialize test database."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.ensure_schema()
    yield db
    await db.close()


@pytest.fixture
def test_repository(test_db: Database) -> WorkflowRepository:
    """Create repository backed by test database."""
    return WorkflowRepository(test_db)


@pytest.fixture
def test_profile_repository(test_db: Database) -> ProfileRepository:
    """Create profile repository backed by test database."""
    return ProfileRepository(test_db)


@pytest.fixture
def test_event_bus() -> EventBus:
    """Create event bus for testing."""
    return EventBus()


@pytest.fixture
def valid_worktree(tmp_path: Path) -> str:
    """Create a valid git worktree for testing."""
    worktree = tmp_path / "test-repo"
    worktree.mkdir()
    init_git_repo(worktree)
    return str(worktree)


@pytest.fixture
async def test_orchestrator(
    test_event_bus: EventBus,
    test_repository: WorkflowRepository,
    test_profile_repository: ProfileRepository,
    temp_checkpoint_db: str,
) -> OrchestratorService:
    """Create real OrchestratorService with test dependencies."""
    return OrchestratorService(
        event_bus=test_event_bus,
        repository=test_repository,
        profile_repo=test_profile_repository,
        checkpoint_path=temp_checkpoint_db,
    )


def create_planning_graph_mock(
    goal: str = "Test goal",
    plan_markdown: str = "## Plan\n\n### Task 1: Do thing\n- Step 1",
) -> MagicMock:
    """Create a mock LangGraph graph that simulates planning with interrupt."""
    from tests.conftest import AsyncIteratorMock

    mock_graph = MagicMock()

    checkpoint_values = {
        "goal": goal,
        "plan_markdown": plan_markdown,
        "profile_id": "test",
    }
    mock_checkpoint = MagicMock()
    mock_checkpoint.values = checkpoint_values
    mock_checkpoint.next = []
    mock_graph.aget_state = AsyncMock(return_value=mock_checkpoint)

    astream_items = [
        ("updates", {"architect_node": {"goal": goal, "plan_markdown": plan_markdown}}),
        ("updates", {"__interrupt__": ("Paused for approval",)}),
    ]
    mock_graph.astream = lambda *args, **kwargs: AsyncIteratorMock(astream_items)
    mock_graph.aupdate_state = AsyncMock()

    return mock_graph


@asynccontextmanager
async def mock_langgraph_for_planning(
    goal: str = "Test goal",
    plan_markdown: str = "## Plan\n\n### Task 1: Do thing\n- Step 1",
) -> AsyncGenerator[MagicMock, None]:
    """Context manager that mocks LangGraph for planning tests."""
    mock_graph = create_planning_graph_mock(goal=goal, plan_markdown=plan_markdown)

    mock_saver = AsyncMock()
    mock_saver_class = MagicMock()
    mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
        return_value=mock_saver
    )
    mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

    with (
        patch(
            "amelia.server.orchestrator.service.AsyncSqliteSaver", mock_saver_class
        ),
        patch.object(
            OrchestratorService, "_create_server_graph", return_value=mock_graph
        ),
    ):
        yield mock_graph


@pytest.mark.integration
class TestReplanFlow:
    """Integration tests for the full replan lifecycle."""

    async def test_replan_full_cycle(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        test_profile_repository: ProfileRepository,
        valid_worktree: str,
        test_event_bus: EventBus,
    ) -> None:
        """Full cycle: PENDING → PLANNING → BLOCKED → replan → PLANNING → BLOCKED."""
        from amelia.core.types import AgentConfig, Profile

        # Create a test profile in the profile repo
        agent_config = AgentConfig(driver="cli", model="sonnet")
        profile = Profile(
            name="test",
            tracker="noop",
            working_dir=valid_worktree,
            agents={
                "architect": agent_config,
                "developer": agent_config,
                "reviewer": agent_config,
                "task_reviewer": agent_config,
                "evaluator": agent_config,
            },
        )
        await test_profile_repository.save_profile(profile)
        await test_profile_repository.set_active_profile("test")

        # Track events
        received_events = []
        test_event_bus.subscribe(lambda e: received_events.append(e))

        # Phase 1: queue_and_plan_workflow → PLANNING → BLOCKED
        request = CreateWorkflowRequest(
            issue_id="ISSUE-REPLAN-INTEG",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
            task_title="Test replan feature",
        )

        async with mock_langgraph_for_planning(
            goal="Original goal from architect",
            plan_markdown="# Original Plan\n\n### Task 1: Original task",
        ):
            workflow_id = await test_orchestrator.queue_and_plan_workflow(request)

            # Wait for background planning task
            if workflow_id in test_orchestrator._planning_tasks:
                await test_orchestrator._planning_tasks[workflow_id]

        # Verify Phase 1: workflow should be BLOCKED with original plan
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.workflow_status == WorkflowStatus.BLOCKED
        assert workflow.planned_at is not None
        assert workflow.execution_state is not None
        assert workflow.execution_state.goal == "Original goal from architect"
        assert "Original Plan" in (workflow.execution_state.plan_markdown or "")

        original_planned_at = workflow.planned_at

        # Phase 2: replan → PLANNING → BLOCKED (with new plan)
        async with mock_langgraph_for_planning(
            goal="New goal after replan",
            plan_markdown="# Revised Plan\n\n### Task 1: Revised task",
        ):
            await test_orchestrator.replan_workflow(workflow_id)

            # Wait for background planning task
            if workflow_id in test_orchestrator._planning_tasks:
                await test_orchestrator._planning_tasks[workflow_id]

        # Verify Phase 2: workflow should be BLOCKED again with NEW plan
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.workflow_status == WorkflowStatus.BLOCKED
        assert workflow.planned_at is not None
        assert workflow.planned_at != original_planned_at  # New timestamp
        assert workflow.execution_state is not None
        assert workflow.execution_state.goal == "New goal after replan"
        assert "Revised Plan" in (workflow.execution_state.plan_markdown or "")

        # Verify events include replanning
        stage_events = [e for e in received_events if e.event_type == EventType.STAGE_STARTED]
        replan_events = [e for e in stage_events if "replan" in (e.message or "").lower()]
        assert len(replan_events) >= 1

        # Verify approval events for both planning cycles
        approval_events = [e for e in received_events if e.event_type == EventType.APPROVAL_REQUIRED]
        assert len(approval_events) == 2  # One per planning cycle
```

**Step 2: Run the integration test**

Run: `uv run pytest tests/integration/test_replan_flow.py -v --timeout=30`
Expected: PASS (uses mocked LangGraph at the boundary)

**Step 3: Commit**

```bash
git add tests/integration/test_replan_flow.py
git commit -m "test(integration): add replan lifecycle test"
```

---

### Task 9: Dashboard Tests — Run Full Suite and Fix

**Files:**
- Existing dashboard test files

**Step 1: Run dashboard tests**

Run: `cd dashboard && pnpm test:run`
Expected: All PASS (no regressions from the Replan button changes)

**Step 2: Run dashboard lint and type-check**

Run: `cd dashboard && pnpm lint && pnpm type-check`
Expected: No errors

**Step 3: Fix any failures**

If any existing tests break (e.g., snapshot tests or tests that count buttons), update them to account for the new Replan button.

**Step 4: Commit any fixes**

```bash
git add dashboard/
git commit -m "test(dashboard): fix tests for replan button addition"
```

---

### Task 10: Final Validation — Full Test Suite

**Files:** None (validation only)

**Step 1: Run full Python test suite**

Run: `uv run pytest tests/ -x --timeout=60`
Expected: All PASS

**Step 2: Run linting and type checking**

Run: `uv run ruff check amelia tests && uv run mypy amelia`
Expected: No errors

**Step 3: Run dashboard build**

Run: `cd dashboard && pnpm build`
Expected: Build succeeds

**Step 4: Fix any issues found**

Address any lint, type, or test failures.

**Step 5: Commit fixes and final commit**

```bash
git add -A
git commit -m "chore: fix lint and type issues from replan feature"
```
