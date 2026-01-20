# Brainstorm Handoff Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make brainstorm handoff create real workflows instead of fake UUIDs, and add GET endpoint for viewing design documents.

**Architecture:** Update `BrainstormService.handoff_to_implementation` to accept orchestrator and worktree_path, load settings to check tracker type, and call `orchestrator.queue_workflow()` for noop tracker. Add `GET /api/files/{path}` endpoint reusing existing validation logic.

**Tech Stack:** FastAPI, Pydantic, pytest, Python async

---

### Task 1: Add Orchestrator and CWD Dependencies to Handoff Route

**Files:**
- Modify: `amelia/server/routes/brainstorm.py:407-443`

**Step 1: Update imports**

Add `get_orchestrator` import and `OrchestratorService` type:

```python
from amelia.server.dependencies import get_orchestrator
from amelia.server.orchestrator.service import OrchestratorService
```

**Step 2: Add dependencies to handoff endpoint**

Update the function signature to include orchestrator and cwd:

```python
@router.post(
    "/sessions/{session_id}/handoff",
    response_model=HandoffResponse,
)
async def handoff_to_implementation(
    session_id: str,
    request: HandoffRequest,
    service: BrainstormService = Depends(get_brainstorm_service),
    orchestrator: OrchestratorService = Depends(get_orchestrator),
    cwd: str = Depends(get_cwd),
) -> HandoffResponse:
```

**Step 3: Pass new parameters to service**

Update the service call:

```python
result = await service.handoff_to_implementation(
    session_id=session_id,
    artifact_path=request.artifact_path,
    issue_title=request.issue_title,
    issue_description=request.issue_description,
    orchestrator=orchestrator,
    worktree_path=cwd,
)
```

**Step 4: Run type check**

Run: `uv run mypy amelia/server/routes/brainstorm.py`
Expected: Type error about service method signature mismatch (not yet updated)

**Step 5: Commit**

```bash
git add amelia/server/routes/brainstorm.py
git commit -m "feat(routes): add orchestrator and cwd dependencies to handoff endpoint"
```

---

### Task 2: Update BrainstormService.handoff_to_implementation Signature

**Files:**
- Modify: `amelia/server/services/brainstorm.py:926-983`
- Test: `tests/unit/server/services/test_brainstorm_service.py`

**Step 1: Write failing test for orchestrator parameter**

Add to `tests/unit/server/services/test_brainstorm_service.py` in `TestHandoff` class:

```python
async def test_handoff_calls_orchestrator_queue_workflow(
    self,
    service: BrainstormService,
    mock_repository: MagicMock,
) -> None:
    """Should call orchestrator.queue_workflow with correct parameters."""
    now = datetime.now(UTC)
    mock_session = BrainstormingSession(
        id="sess-1", profile_id="work", status="ready_for_handoff",
        created_at=now, updated_at=now,
    )
    mock_repository.get_session.return_value = mock_session
    mock_repository.get_artifacts.return_value = [
        Artifact(
            id="art-1", session_id="sess-1", type="design",
            path="docs/plans/design.md", created_at=now,
        )
    ]

    mock_orchestrator = MagicMock()
    mock_orchestrator.queue_workflow = AsyncMock(return_value="wf-real-123")

    result = await service.handoff_to_implementation(
        session_id="sess-1",
        artifact_path="docs/plans/design.md",
        issue_title="Implement feature X",
        orchestrator=mock_orchestrator,
        worktree_path="/path/to/worktree",
    )

    assert result["workflow_id"] == "wf-real-123"
    mock_orchestrator.queue_workflow.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py::TestHandoff::test_handoff_calls_orchestrator_queue_workflow -v`
Expected: FAIL with TypeError (unexpected keyword argument 'orchestrator')

**Step 3: Update method signature**

Update `amelia/server/services/brainstorm.py` method signature:

```python
async def handoff_to_implementation(
    self,
    session_id: str,
    artifact_path: str,
    issue_title: str | None = None,
    issue_description: str | None = None,
    orchestrator: "OrchestratorService | None" = None,
    worktree_path: str | None = None,
) -> dict[str, str]:
```

Add import at top of file:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amelia.server.orchestrator.service import OrchestratorService
```

**Step 4: Run test to verify it still fails**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py::TestHandoff::test_handoff_calls_orchestrator_queue_workflow -v`
Expected: FAIL (orchestrator not used yet, still returns fake UUID)

**Step 5: Commit**

```bash
git add amelia/server/services/brainstorm.py tests/unit/server/services/test_brainstorm_service.py
git commit -m "test: add test for handoff orchestrator integration"
```

---

### Task 3: Implement Real Workflow Creation in Handoff

**Files:**
- Modify: `amelia/server/services/brainstorm.py:926-983`
- Test: `tests/unit/server/services/test_brainstorm_service.py`

**Step 1: Add imports**

Add to `amelia/server/services/brainstorm.py`:

```python
from amelia.server.models.requests import CreateWorkflowRequest
```

**Step 2: Implement orchestrator call**

Replace the fake UUID generation with real orchestrator call in `handoff_to_implementation`:

```python
async def handoff_to_implementation(
    self,
    session_id: str,
    artifact_path: str,
    issue_title: str | None = None,
    issue_description: str | None = None,
    orchestrator: "OrchestratorService | None" = None,
    worktree_path: str | None = None,
) -> dict[str, str]:
    """Hand off brainstorming session to implementation pipeline.

    Args:
        session_id: Session to hand off.
        artifact_path: Path to the design artifact.
        issue_title: Optional title for the implementation issue.
        issue_description: Optional description for the implementation issue.
        orchestrator: Orchestrator service for creating workflows.
        worktree_path: Path to the worktree for loading settings.

    Returns:
        Dict with workflow_id for the implementation pipeline.

    Raises:
        ValueError: If session or artifact not found.
        NotImplementedError: If tracker is not noop.
    """
    session = await self._repository.get_session(session_id)
    if session is None:
        raise ValueError(f"Session not found: {session_id}")

    # Validate artifact exists
    artifacts = await self._repository.get_artifacts(session_id)
    artifact = next((a for a in artifacts if a.path == artifact_path), None)
    if artifact is None:
        raise ValueError(f"Artifact not found: {artifact_path}")

    # Generate workflow ID - either from orchestrator or fallback
    if orchestrator is not None and worktree_path is not None:
        # Create issue ID from session ID (safe characters only)
        issue_id = f"brainstorm-{session_id}"

        # Queue workflow with orchestrator
        request = CreateWorkflowRequest(
            issue_id=issue_id,
            worktree_path=worktree_path,
            task_title=issue_title or f"Implement design from {artifact_path}",
            task_description=issue_description,
            start=False,  # Queue only, don't start
        )
        workflow_id = await orchestrator.queue_workflow(request)
    else:
        # Fallback for backwards compatibility (e.g., tests without orchestrator)
        workflow_id = str(uuid4())

    # Update session status to completed
    session.status = "completed"
    session.updated_at = datetime.now(UTC)
    await self._repository.update_session(session)

    # Emit session completed event
    event = WorkflowEvent(
        id=str(uuid4()),
        workflow_id=session_id,
        sequence=0,
        timestamp=datetime.now(UTC),
        agent="brainstormer",
        event_type=EventType.BRAINSTORM_SESSION_COMPLETED,
        message=f"Session completed, handed off to implementation {workflow_id}",
        data={
            "session_id": session_id,
            "workflow_id": workflow_id,
            "artifact_path": artifact_path,
        },
    )
    self._event_bus.emit(event)

    return {"workflow_id": workflow_id, "status": "created"}
```

**Step 3: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py::TestHandoff::test_handoff_calls_orchestrator_queue_workflow -v`
Expected: PASS

**Step 4: Run all handoff tests**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py::TestHandoff -v`
Expected: All PASS (existing tests use default None for orchestrator)

**Step 5: Commit**

```bash
git add amelia/server/services/brainstorm.py
git commit -m "feat(brainstorm): call orchestrator.queue_workflow in handoff"
```

---

### Task 4: Add Test for Non-Noop Tracker Error

**Files:**
- Test: `tests/unit/server/services/test_brainstorm_service.py`

**Step 1: Write failing test for non-noop tracker**

Add to `TestHandoff` class:

```python
async def test_handoff_raises_for_non_noop_tracker(
    self,
    service: BrainstormService,
    mock_repository: MagicMock,
) -> None:
    """Should raise NotImplementedError for non-noop tracker."""
    now = datetime.now(UTC)
    mock_session = BrainstormingSession(
        id="sess-1", profile_id="work", status="ready_for_handoff",
        created_at=now, updated_at=now,
    )
    mock_repository.get_session.return_value = mock_session
    mock_repository.get_artifacts.return_value = [
        Artifact(
            id="art-1", session_id="sess-1", type="design",
            path="docs/plans/design.md", created_at=now,
        )
    ]

    mock_orchestrator = MagicMock()
    # Simulate ValueError from orchestrator when tracker is not noop
    mock_orchestrator.queue_workflow = AsyncMock(
        side_effect=ValueError("task_title can only be used with noop tracker")
    )

    with pytest.raises(ValueError, match="noop tracker"):
        await service.handoff_to_implementation(
            session_id="sess-1",
            artifact_path="docs/plans/design.md",
            issue_title="Implement feature X",
            orchestrator=mock_orchestrator,
            worktree_path="/path/to/worktree",
        )
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py::TestHandoff::test_handoff_raises_for_non_noop_tracker -v`
Expected: PASS (error propagates from orchestrator)

**Step 3: Commit**

```bash
git add tests/unit/server/services/test_brainstorm_service.py
git commit -m "test: add test for non-noop tracker error in handoff"
```

---

### Task 5: Add GET File Endpoint

**Files:**
- Modify: `amelia/server/routes/files.py:27-101`
- Test: `tests/unit/server/routes/test_files.py`

**Step 1: Write failing test for GET endpoint**

Add new test class to `tests/unit/server/routes/test_files.py`:

```python
class TestGetFile:
    """Tests for GET /api/files/{file_path:path} endpoint."""

    @pytest.fixture
    def mock_config(self, tmp_path: Path) -> MagicMock:
        """Create a mock config with working_dir set to tmp_path."""
        config = MagicMock()
        config.working_dir = Path(tempfile.gettempdir())
        return config

    @pytest.fixture
    def app(self, mock_config: MagicMock) -> FastAPI:
        """Create test app with files router."""
        application = FastAPI()
        application.include_router(router, prefix="/api/files")
        application.dependency_overrides[get_config] = lambda: mock_config
        return application

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def temp_file(self) -> Iterator[str]:
        """Create a temporary markdown file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            f.write("# Design Document\n\n## Overview\n\nThis is the design.")
            path = f.name
        yield path
        if os.path.exists(path):
            os.unlink(path)

    def test_gets_file_content(self, client: TestClient, temp_file: str) -> None:
        """Should return file content with text/plain content-type."""
        response = client.get(f"/api/files/{temp_file}")

        assert response.status_code == 200
        assert "Design Document" in response.text
        assert response.headers["content-type"].startswith("text/")

    def test_returns_404_for_missing_file(self, client: TestClient) -> None:
        """Should return 404 when file doesn't exist."""
        missing_file = Path(tempfile.gettempdir()) / "nonexistent_file_99999.md"
        response = client.get(f"/api/files/{missing_file}")

        assert response.status_code == 404

    def test_returns_400_for_path_outside_working_dir(
        self, app: FastAPI
    ) -> None:
        """Should return 400 when path is outside working_dir."""
        mock_config = MagicMock()
        mock_config.working_dir = Path("/some/restricted/directory")
        app.dependency_overrides[get_config] = lambda: mock_config

        client = TestClient(app)
        response = client.get("/api/files/etc/passwd")

        assert response.status_code == 400
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/routes/test_files.py::TestGetFile -v`
Expected: FAIL with 404 (endpoint doesn't exist)

**Step 3: Implement GET endpoint**

Add to `amelia/server/routes/files.py` after the existing `read_file` function:

```python
@router.get("/{file_path:path}")
async def get_file(
    file_path: str,
    config: ServerConfig = Depends(get_config),
) -> Response:
    """Get file content by path.

    Args:
        file_path: Absolute path to the file.
        config: Server configuration.

    Returns:
        File content as plain text response.

    Raises:
        HTTPException: 400 if path is invalid or outside working_dir.
        HTTPException: 404 if file doesn't exist.
    """
    path = Path(file_path)

    # Validate absolute path
    if not path.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Path must be absolute", "code": "INVALID_PATH"},
        )

    # Resolve to handle symlinks and ..
    try:
        resolved_path = path.resolve()
    except (OSError, RuntimeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"Invalid path: {e}", "code": "INVALID_PATH"},
        ) from e

    # Check working_dir restriction
    working_dir_resolved = config.working_dir.resolve()
    try:
        resolved_path.relative_to(working_dir_resolved)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Path not accessible (outside working directory)",
                "code": "PATH_NOT_ACCESSIBLE",
            },
        ) from e

    # Check file exists
    if not resolved_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "File not found", "code": "FILE_NOT_FOUND"},
        )

    if not resolved_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Path is not a file", "code": "NOT_A_FILE"},
        )

    # Read content
    try:
        content = await asyncio.to_thread(resolved_path.read_text, encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": f"Failed to read file: {e}", "code": "READ_ERROR"},
        ) from e

    # Determine content type based on extension
    suffix = resolved_path.suffix.lower()
    content_type = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".json": "application/json",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
    }.get(suffix, "text/plain")

    return Response(content=content, media_type=content_type)
```

Add import at top:

```python
from fastapi.responses import Response
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/routes/test_files.py::TestGetFile -v`
Expected: All PASS

**Step 5: Run all files tests**

Run: `uv run pytest tests/unit/server/routes/test_files.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add amelia/server/routes/files.py tests/unit/server/routes/test_files.py
git commit -m "feat(files): add GET endpoint for viewing files"
```

---

### Task 6: Add Route-Level Error Handling Tests

**Files:**
- Test: `tests/unit/server/routes/test_brainstorm.py` (create if needed)

**Step 1: Check if route tests exist**

Run: `ls tests/unit/server/routes/test_brainstorm*.py`

**Step 2: If no tests exist, create basic route test file**

Create `tests/unit/server/routes/test_brainstorm_handoff.py`:

```python
"""Tests for brainstorm handoff route error handling."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from amelia.server.routes.brainstorm import (
    get_brainstorm_service,
    get_cwd,
    router,
)
from amelia.server.dependencies import get_orchestrator


class TestHandoffRoute:
    """Tests for POST /sessions/{id}/handoff endpoint."""

    @pytest.fixture
    def mock_service(self) -> MagicMock:
        """Create mock brainstorm service."""
        service = MagicMock()
        service.handoff_to_implementation = AsyncMock()
        return service

    @pytest.fixture
    def mock_orchestrator(self) -> MagicMock:
        """Create mock orchestrator."""
        return MagicMock()

    @pytest.fixture
    def app(
        self, mock_service: MagicMock, mock_orchestrator: MagicMock
    ) -> FastAPI:
        """Create test app with brainstorm router."""
        application = FastAPI()
        application.include_router(router, prefix="/api/brainstorm")
        application.dependency_overrides[get_brainstorm_service] = lambda: mock_service
        application.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
        application.dependency_overrides[get_cwd] = lambda: "/test/worktree"
        return application

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_handoff_returns_workflow_id(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """Should return workflow_id from service."""
        mock_service.handoff_to_implementation.return_value = {
            "workflow_id": "wf-123",
            "status": "created",
        }

        response = client.post(
            "/api/brainstorm/sessions/sess-1/handoff",
            json={"artifact_path": "docs/design.md", "issue_title": "Feature X"},
        )

        assert response.status_code == 200
        assert response.json()["workflow_id"] == "wf-123"

    def test_handoff_passes_orchestrator_to_service(
        self,
        client: TestClient,
        mock_service: MagicMock,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Should pass orchestrator and cwd to service."""
        mock_service.handoff_to_implementation.return_value = {
            "workflow_id": "wf-123",
            "status": "created",
        }

        client.post(
            "/api/brainstorm/sessions/sess-1/handoff",
            json={"artifact_path": "docs/design.md"},
        )

        call_kwargs = mock_service.handoff_to_implementation.call_args.kwargs
        assert call_kwargs["orchestrator"] is mock_orchestrator
        assert call_kwargs["worktree_path"] == "/test/worktree"

    def test_handoff_returns_404_for_missing_session(
        self,
        client: TestClient,
        mock_service: MagicMock,
    ) -> None:
        """Should return 404 when session not found."""
        mock_service.handoff_to_implementation.side_effect = ValueError(
            "Session not found: sess-999"
        )

        response = client.post(
            "/api/brainstorm/sessions/sess-999/handoff",
            json={"artifact_path": "docs/design.md"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/server/routes/test_brainstorm_handoff.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add tests/unit/server/routes/test_brainstorm_handoff.py
git commit -m "test: add route-level tests for brainstorm handoff"
```

---

### Task 7: Run Full Test Suite and Type Check

**Files:** None (verification only)

**Step 1: Run mypy**

Run: `uv run mypy amelia`
Expected: No errors

**Step 2: Run ruff**

Run: `uv run ruff check amelia tests`
Expected: No errors (or auto-fix with `--fix`)

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit -v`
Expected: All PASS

**Step 4: Commit any fixes**

If any fixes were needed:

```bash
git add -A
git commit -m "fix: address linting and type errors"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add orchestrator/cwd dependencies to route | `routes/brainstorm.py` |
| 2 | Update service method signature | `services/brainstorm.py`, tests |
| 3 | Implement real workflow creation | `services/brainstorm.py` |
| 4 | Add non-noop tracker error test | tests |
| 5 | Add GET file endpoint | `routes/files.py`, tests |
| 6 | Add route-level error handling tests | tests |
| 7 | Run full verification | None |

## Out of Scope

- Jira/GitHub tracker support (error propagates from orchestrator)
- Auto-creating issues in external trackers
- Passing design document content to Architect
