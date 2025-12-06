# CLI Thin Client Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** :hourglass: Not Started

**Goal:** Refactor CLI to become a thin client that delegates workflow orchestration to the FastAPI server via REST API calls.

**Architecture:** CLI commands detect the current git worktree context and make httpx-based REST calls to the local server. Commands map to server endpoints: `start` creates workflows, `approve`/`reject` send workflow actions, `status` queries active workflows, `cancel` terminates workflows. The CLI provides rich error messages and auto-detects workflow IDs from the current worktree.

**Tech Stack:** typer, httpx, rich (formatting), subprocess (git operations), pydantic (request/response models)

**Depends on:**
- Phase 2.1 Plans 1-5 (server foundation, database, workflow API, events, orchestrator)

**Breaking Change:** This refactor replaces the existing `start` command with a thin client version. The original direct-execution mode will be renamed to `start-direct`.

---

## Task 1: Verify CLI Client Dependencies

**Files:**
- Verify: `pyproject.toml` (httpx and rich already present)

**Step 1: Write the verification test**

```python
# tests/unit/client/test_dependencies.py
"""Verify CLI client dependencies are available."""
import pytest


def test_httpx_importable():
    """httpx should be importable for REST client."""
    import httpx
    assert httpx.__version__


def test_rich_importable():
    """rich should be importable for CLI output."""
    import rich
    assert rich.__version__


def test_httpx_version_sufficient():
    """httpx version should be >= 0.28.0."""
    import httpx
    from packaging.version import Version
    assert Version(httpx.__version__) >= Version("0.28.0")


def test_rich_version_sufficient():
    """rich version should be >= 14.1.0."""
    import rich
    from packaging.version import Version
    assert Version(rich.__version__) >= Version("14.1.0")
```

**Step 2: Create test directory**

```bash
mkdir -p tests/unit/client
touch tests/unit/client/__init__.py
```

**Step 3: Run test to verify dependencies exist**

Run: `uv run pytest tests/unit/client/test_dependencies.py -v`
Expected: PASS (dependencies already in pyproject.toml)

**Step 4: Commit**

```bash
git add tests/unit/client/
git commit -m "test(cli): add dependency verification tests for thin client"
```

---

## Task 2: Implement Worktree Context Detection

**Files:**
- Create: `amelia/client/__init__.py`
- Create: `amelia/client/git.py`

**Step 1: Write the failing test**

```python
# tests/unit/client/test_git.py
"""Tests for git worktree context detection."""
import pytest
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestGetWorktreeContext:
    """Tests for get_worktree_context function."""

    def test_returns_tuple(self, tmp_path):
        """Returns (worktree_path, worktree_name) tuple."""
        from amelia.client.git import get_worktree_context

        # Create a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "initial"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        with patch("subprocess.run") as mock_run:
            # Mock git rev-parse --is-inside-work-tree
            mock_run.return_value = MagicMock(
                returncode=0, stdout="true\n", stderr=""
            )

            # Second call: git rev-parse --show-toplevel
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n", stderr=""),
                MagicMock(returncode=0, stdout="/home/user/repo\n", stderr=""),
                MagicMock(returncode=0, stdout="main\n", stderr=""),
            ]

            path, name = get_worktree_context()

            assert isinstance(path, str)
            assert isinstance(name, str)
            assert path == "/home/user/repo"
            assert name == "main"

    def test_raises_when_not_in_git_repo(self):
        """Raises ValueError when not in a git repository."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128, stdout="false\n", stderr="not a git repository"
            )

            with pytest.raises(ValueError, match="Not inside a git repository"):
                get_worktree_context()

    def test_raises_when_in_bare_repo(self):
        """Raises ValueError when in a bare repository."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            # First call: --is-inside-work-tree (fails)
            # Second call: --is-bare-repository (true)
            mock_run.side_effect = [
                MagicMock(returncode=128, stdout="false\n", stderr=""),
                MagicMock(returncode=0, stdout="true\n", stderr=""),
            ]

            with pytest.raises(ValueError, match="Cannot run workflows in a bare repository"):
                get_worktree_context()

    def test_handles_detached_head(self):
        """Uses short commit hash as name for detached HEAD."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n", stderr=""),  # is-inside-work-tree
                MagicMock(returncode=0, stdout="/home/user/repo\n", stderr=""),  # show-toplevel
                MagicMock(returncode=0, stdout="HEAD\n", stderr=""),  # abbrev-ref HEAD
                MagicMock(returncode=0, stdout="abc1234\n", stderr=""),  # short hash
            ]

            path, name = get_worktree_context()

            assert path == "/home/user/repo"
            assert name == "detached-abc1234"

    def test_handles_detached_head_hash_failure(self):
        """Falls back to 'detached' if short hash fails."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n", stderr=""),  # is-inside-work-tree
                MagicMock(returncode=0, stdout="/home/user/repo\n", stderr=""),  # show-toplevel
                MagicMock(returncode=0, stdout="HEAD\n", stderr=""),  # abbrev-ref HEAD
                subprocess.CalledProcessError(1, "git"),  # short hash fails
            ]

            path, name = get_worktree_context()

            assert path == "/home/user/repo"
            assert name == "detached"

    def test_uses_directory_name_when_branch_detection_fails(self):
        """Falls back to directory name if branch detection fails."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n", stderr=""),  # is-inside-work-tree
                MagicMock(returncode=0, stdout="/home/user/my-repo\n", stderr=""),  # show-toplevel
                subprocess.CalledProcessError(1, "git"),  # abbrev-ref fails
            ]

            path, name = get_worktree_context()

            assert path == "/home/user/my-repo"
            assert name == "my-repo"

    def test_raises_runtime_error_on_toplevel_failure(self):
        """Raises RuntimeError if git rev-parse --show-toplevel fails."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n", stderr=""),  # is-inside-work-tree
                subprocess.CalledProcessError(
                    1, "git", stderr="fatal: not a git repository"
                ),  # show-toplevel
            ]

            with pytest.raises(RuntimeError, match="Failed to determine worktree root"):
                get_worktree_context()

    def test_empty_branch_name_uses_directory(self):
        """Uses directory name if branch name is empty."""
        from amelia.client.git import get_worktree_context

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="true\n", stderr=""),  # is-inside-work-tree
                MagicMock(returncode=0, stdout="/home/user/project\n", stderr=""),  # show-toplevel
                MagicMock(returncode=0, stdout="\n", stderr=""),  # empty branch name
            ]

            path, name = get_worktree_context()

            assert path == "/home/user/project"
            assert name == "project"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_git.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create client package init**

```python
# amelia/client/__init__.py
"""Amelia CLI thin client package."""
from amelia.client.git import get_worktree_context

__all__ = ["get_worktree_context"]
```

**Step 4: Implement get_worktree_context**

```python
# amelia/client/git.py
"""Git worktree context detection for CLI client."""
import subprocess
from pathlib import Path


def get_worktree_context() -> tuple[str, str]:
    """Returns (worktree_path, worktree_name) for current directory.

    Detects the current git worktree root and derives a human-readable name
    from the current branch or directory name.

    Handles edge cases:
    - Detached HEAD: Uses short commit hash as name (e.g., "detached-abc1234")
    - Corrupted repo: Raises clear error
    - Submodules: Works correctly (has .git file pointing to parent)
    - Bare repository: Raises clear error

    Returns:
        Tuple of (absolute_worktree_path, worktree_name)

    Raises:
        ValueError: If not in a git repository or in a bare repository.
        RuntimeError: If git commands fail unexpectedly.

    Examples:
        >>> get_worktree_context()
        ('/home/user/myproject', 'main')

        >>> # In detached HEAD state
        >>> get_worktree_context()
        ('/home/user/myproject', 'detached-abc1234')
    """
    # Check if we're in a git repo at all
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        # Could be bare repo or not a repo at all
        bare_check = subprocess.run(
            ["git", "rev-parse", "--is-bare-repository"],
            capture_output=True,
            text=True,
        )
        if bare_check.returncode == 0 and bare_check.stdout.strip() == "true":
            raise ValueError("Cannot run workflows in a bare repository")
        raise ValueError("Not inside a git repository")

    # Get worktree root (works for main repo and worktrees)
    try:
        worktree_path = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to determine worktree root: {e.stderr}")

    # Get branch name for display
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        # Fallback to directory name if branch detection fails
        return worktree_path, Path(worktree_path).name

    # Handle detached HEAD state
    if branch == "HEAD":
        try:
            short_hash = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            branch = f"detached-{short_hash}"
        except subprocess.CalledProcessError:
            branch = "detached"

    # Use directory name if branch is empty
    return worktree_path, branch or Path(worktree_path).name
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/client/test_git.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/client/__init__.py amelia/client/git.py tests/unit/client/test_git.py
git commit -m "feat(client): add git worktree context detection"
```

---

## Task 3: Create API Client Class

**Files:**
- Create: `amelia/client/api.py`
- Create: `amelia/client/models.py`

**Important:** Models must match server responses exactly. See `amelia/server/models/responses.py`.

**Step 1: Write the failing test**

```python
# tests/unit/client/test_api.py
"""Tests for REST API client."""
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


class TestAmeliaClient:
    """Tests for AmeliaClient."""

    @pytest.fixture
    def client(self):
        """Create API client instance."""
        from amelia.client.api import AmeliaClient

        return AmeliaClient(base_url="http://localhost:8420")

    def test_client_initialization(self, client):
        """Client initializes with base URL."""
        assert client.base_url == "http://localhost:8420"

    @pytest.mark.asyncio
    async def test_create_workflow(self, client):
        """create_workflow sends POST request with correct payload."""
        from amelia.client.models import CreateWorkflowResponse

        # Server returns minimal response per amelia/server/models/responses.py
        mock_response = {
            "id": "wf-123",
            "status": "pending",
            "message": "Workflow created for issue ISSUE-123",
        }

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = mock_response

            result = await client.create_workflow(
                issue_id="ISSUE-123",
                worktree_path="/home/user/repo",
                worktree_name="main",
            )

            assert isinstance(result, CreateWorkflowResponse)
            assert result.id == "wf-123"
            assert result.status == "pending"

            # Verify request was made correctly
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/api/workflows"

    @pytest.mark.asyncio
    async def test_create_workflow_with_profile(self, client):
        """create_workflow includes profile when provided."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {
                "id": "wf-123",
                "status": "pending",
                "message": "Created",
            }

            await client.create_workflow(
                issue_id="ISSUE-123",
                worktree_path="/home/user/repo",
                worktree_name="main",
                profile="work",
            )

            call_kwargs = mock_request.call_args[1]
            assert call_kwargs["json"]["profile"] == "work"

    @pytest.mark.asyncio
    async def test_approve_workflow(self, client):
        """approve_workflow sends POST to correct endpoint."""
        from amelia.client.models import ActionResponse

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {"status": "approved", "workflow_id": "wf-123"}

            result = await client.approve_workflow(workflow_id="wf-123")

            assert isinstance(result, ActionResponse)
            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert call_args[0][0] == "POST"
            assert "/api/workflows/wf-123/approve" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_reject_workflow(self, client):
        """reject_workflow sends POST with feedback (not reason)."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {"status": "rejected", "workflow_id": "wf-123"}

            await client.reject_workflow(workflow_id="wf-123", feedback="Not ready")

            mock_request.assert_called_once()
            call_kwargs = mock_request.call_args[1]
            # Server uses 'feedback' field, not 'reason'
            assert call_kwargs["json"]["feedback"] == "Not ready"

    @pytest.mark.asyncio
    async def test_cancel_workflow(self, client):
        """cancel_workflow sends POST to cancel endpoint."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {"status": "cancelled", "workflow_id": "wf-123"}

            await client.cancel_workflow(workflow_id="wf-123")

            mock_request.assert_called_once()
            call_args = mock_request.call_args
            assert "/api/workflows/wf-123/cancel" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_get_active_workflows(self, client):
        """get_active_workflows fetches active workflows."""
        from amelia.client.models import WorkflowListResponse

        # Server response structure per amelia/server/models/responses.py
        mock_response = {
            "workflows": [
                {
                    "id": "wf-123",
                    "issue_id": "ISSUE-123",
                    "worktree_name": "main",
                    "status": "in_progress",
                    "started_at": "2025-12-01T10:00:00Z",
                    "current_stage": "developer",
                }
            ],
            "total": 1,
            "cursor": None,
            "has_more": False,
        }

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = mock_response

            result = await client.get_active_workflows()

            assert isinstance(result, WorkflowListResponse)
            assert len(result.workflows) == 1
            assert result.total == 1
            assert result.has_more is False

    @pytest.mark.asyncio
    async def test_get_active_workflows_filter_by_worktree(self, client):
        """get_active_workflows can filter by worktree path."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {
                "workflows": [],
                "total": 0,
                "cursor": None,
                "has_more": False,
            }

            await client.get_active_workflows(worktree_path="/home/user/repo")

            call_kwargs = mock_request.call_args[1]
            assert call_kwargs["params"]["worktree"] == "/home/user/repo"

    @pytest.mark.asyncio
    async def test_get_workflow(self, client):
        """get_workflow fetches single workflow by ID."""
        from amelia.client.models import WorkflowDetailResponse

        mock_response = {
            "id": "wf-123",
            "issue_id": "ISSUE-123",
            "worktree_path": "/home/user/repo",
            "worktree_name": "main",
            "status": "in_progress",
            "started_at": "2025-12-01T10:00:00Z",
            "completed_at": None,
            "failure_reason": None,
            "current_stage": "developer",
            "plan": None,
            "token_usage": None,
            "recent_events": [],
        }

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = mock_response

            result = await client.get_workflow(workflow_id="wf-123")

            assert isinstance(result, WorkflowDetailResponse)
            assert result.id == "wf-123"

    @pytest.mark.asyncio
    async def test_client_handles_409_conflict(self, client):
        """Client raises descriptive error on 409 Conflict."""
        from amelia.client.api import WorkflowConflictError

        # Server error format per amelia/server/routes/workflows.py
        error_response = {
            "code": "WORKFLOW_CONFLICT",
            "error": "Workflow wf-existing already active for worktree /home/user/repo",
            "details": {
                "workflow_id": "wf-existing",
                "worktree_path": "/home/user/repo",
            },
        }

        with patch.object(client, "_request") as mock_request:
            mock_request.side_effect = WorkflowConflictError(
                message=error_response["error"],
                workflow_id=error_response["details"]["workflow_id"],
                worktree_path=error_response["details"]["worktree_path"],
            )

            with pytest.raises(WorkflowConflictError) as exc_info:
                await client.create_workflow(
                    issue_id="ISSUE-123",
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                )

            assert "wf-existing" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_client_handles_429_rate_limit(self, client):
        """Client raises descriptive error on 429 Too Many Requests."""
        from amelia.client.api import ConcurrencyLimitError

        with patch.object(client, "_request") as mock_request:
            mock_request.side_effect = ConcurrencyLimitError(
                message="Concurrency limit exceeded",
                retry_after=30,
                current=5,
                limit=5,
            )

            with pytest.raises(ConcurrencyLimitError) as exc_info:
                await client.create_workflow(
                    issue_id="ISSUE-123",
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                )

            assert exc_info.value.retry_after == 30

    @pytest.mark.asyncio
    async def test_client_handles_422_invalid_state(self, client):
        """Client raises descriptive error on 422 Invalid State."""
        from amelia.client.api import InvalidStateError

        with patch.object(client, "_request") as mock_request:
            mock_request.side_effect = InvalidStateError(
                message="Workflow is not awaiting approval",
                workflow_id="wf-123",
                current_status="in_progress",
            )

            with pytest.raises(InvalidStateError) as exc_info:
                await client.approve_workflow(workflow_id="wf-123")

            assert exc_info.value.current_status == "in_progress"

    @pytest.mark.asyncio
    async def test_client_handles_connection_error(self, client):
        """Client raises descriptive error when server is unreachable."""
        from amelia.client.api import ServerUnreachableError

        with patch.object(client, "_request") as mock_request:
            mock_request.side_effect = ServerUnreachableError(
                "Cannot connect to Amelia server at http://localhost:8420"
            )

            with pytest.raises(ServerUnreachableError) as exc_info:
                await client.create_workflow(
                    issue_id="ISSUE-123",
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                )

            assert "8420" in str(exc_info.value)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_api.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create client models (matching server exactly)**

```python
# amelia/client/models.py
"""Pydantic models for API requests and responses.

IMPORTANT: These models must match the server models in amelia/server/models/.
"""
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


# Matches amelia/server/models/state.py
WorkflowStatus = Literal[
    "pending",
    "in_progress",
    "blocked",
    "completed",
    "failed",
    "cancelled",
]


# Request models - must match amelia/server/models/requests.py


class CreateWorkflowRequest(BaseModel):
    """Request to create a new workflow."""

    issue_id: str = Field(..., min_length=1, max_length=100)
    worktree_path: str = Field(...)
    worktree_name: str | None = Field(default=None)
    profile: str | None = Field(default=None)
    driver: str | None = Field(default=None)


class RejectRequest(BaseModel):
    """Request to reject a workflow plan.

    Note: Server uses 'feedback' field, NOT 'reason'.
    """

    feedback: str = Field(..., min_length=1)


# Response models - must match amelia/server/models/responses.py


class CreateWorkflowResponse(BaseModel):
    """Response from creating a new workflow.

    Note: Server returns minimal info - id, status, message only.
    """

    id: str
    status: WorkflowStatus
    message: str


class WorkflowSummary(BaseModel):
    """Summary of a workflow for list views.

    Note: Does NOT include worktree_path - only worktree_name.
    """

    id: str
    issue_id: str
    worktree_name: str
    status: WorkflowStatus
    started_at: datetime | None = None
    current_stage: str | None = None


class WorkflowListResponse(BaseModel):
    """Response containing a list of workflows.

    Note: Uses 'cursor' not 'next_cursor', includes 'has_more'.
    """

    workflows: list[WorkflowSummary]
    total: int
    cursor: str | None = None
    has_more: bool = False


class TokenSummary(BaseModel):
    """Summary of token usage and costs."""

    total_tokens: int
    total_cost_usd: float


class WorkflowDetailResponse(BaseModel):
    """Detailed workflow information."""

    id: str
    issue_id: str
    worktree_path: str
    worktree_name: str
    status: WorkflowStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    current_stage: str | None = None
    plan: dict[str, Any] | None = None
    token_usage: TokenSummary | None = None
    recent_events: list[dict[str, Any]] = Field(default_factory=list)


class ActionResponse(BaseModel):
    """Response for workflow action endpoints (approve/reject/cancel)."""

    status: str
    workflow_id: str


class ErrorResponse(BaseModel):
    """Error response from server.

    Matches amelia/server/models/responses.py:ErrorResponse
    """

    error: str
    code: str
    details: dict[str, Any] | None = None
```

**Step 4: Implement API client**

```python
# amelia/client/api.py
"""REST API client for Amelia server."""
import httpx
from typing import Any

from amelia.client.models import (
    CreateWorkflowRequest,
    CreateWorkflowResponse,
    RejectRequest,
    WorkflowDetailResponse,
    WorkflowListResponse,
    ActionResponse,
    ErrorResponse,
)


class AmeliaClientError(Exception):
    """Base exception for API client errors."""

    pass


class ServerUnreachableError(AmeliaClientError):
    """Raised when server cannot be reached."""

    pass


class WorkflowConflictError(AmeliaClientError):
    """Raised when workflow already exists for worktree (409 Conflict)."""

    def __init__(
        self,
        message: str,
        workflow_id: str | None = None,
        worktree_path: str | None = None,
    ):
        """Initialize with message and conflict details."""
        super().__init__(message)
        self.workflow_id = workflow_id
        self.worktree_path = worktree_path


class ConcurrencyLimitError(AmeliaClientError):
    """Raised when concurrent workflow limit exceeded (429 Too Many Requests)."""

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        current: int | None = None,
        limit: int | None = None,
    ):
        """Initialize with message and retry info."""
        super().__init__(message)
        self.retry_after = retry_after
        self.current = current
        self.limit = limit


class InvalidStateError(AmeliaClientError):
    """Raised when workflow is not in valid state for operation (422)."""

    def __init__(
        self,
        message: str,
        workflow_id: str | None = None,
        current_status: str | None = None,
    ):
        """Initialize with message and state info."""
        super().__init__(message)
        self.workflow_id = workflow_id
        self.current_status = current_status


class WorkflowNotFoundError(AmeliaClientError):
    """Raised when workflow is not found (404)."""

    def __init__(self, workflow_id: str):
        """Initialize with workflow ID."""
        super().__init__(f"Workflow not found: {workflow_id}")
        self.workflow_id = workflow_id


class ValidationError(AmeliaClientError):
    """Raised when request validation fails (400)."""

    pass


class AmeliaClient:
    """HTTP client for Amelia REST API.

    Provides methods for all workflow operations: create, approve, reject,
    cancel, and query. Handles errors and converts them to descriptive exceptions.

    Example:
        >>> client = AmeliaClient()
        >>> response = await client.create_workflow(
        ...     issue_id="ISSUE-123",
        ...     worktree_path="/home/user/repo",
        ...     worktree_name="main"
        ... )
        >>> await client.approve_workflow(response.id)
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8420"):
        """Initialize API client.

        Args:
            base_url: Base URL of the Amelia server (default: http://127.0.0.1:8420)
        """
        self.base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(30.0, connect=5.0)

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make HTTP request and handle errors.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., /api/workflows)
            json: Request body as dict
            params: Query parameters

        Returns:
            Response JSON as dict

        Raises:
            ServerUnreachableError: If server is not running
            WorkflowConflictError: On 409 Conflict
            ConcurrencyLimitError: On 429 Too Many Requests
            InvalidStateError: On 422 Unprocessable Entity
            WorkflowNotFoundError: On 404 Not Found
            ValidationError: On 400 Bad Request
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method=method,
                    url=f"{self.base_url}{path}",
                    json=json,
                    params=params,
                )

                if response.status_code in (200, 201):
                    return response.json()

                # Parse error response
                try:
                    error_data = response.json()
                    error = ErrorResponse.model_validate(error_data)
                except Exception:
                    error = ErrorResponse(
                        code="UNKNOWN",
                        error=response.text or f"HTTP {response.status_code}",
                    )

                if response.status_code == 409:
                    details = error.details or {}
                    raise WorkflowConflictError(
                        message=error.error,
                        workflow_id=details.get("workflow_id"),
                        worktree_path=details.get("worktree_path"),
                    )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    details = error.details or {}
                    raise ConcurrencyLimitError(
                        message=error.error,
                        retry_after=int(retry_after) if retry_after else None,
                        current=details.get("current"),
                        limit=details.get("limit"),
                    )

                if response.status_code == 422:
                    details = error.details or {}
                    raise InvalidStateError(
                        message=error.error,
                        workflow_id=details.get("workflow_id"),
                        current_status=details.get("current_status"),
                    )

                if response.status_code == 404:
                    details = error.details or {}
                    raise WorkflowNotFoundError(
                        workflow_id=details.get("workflow_id", "unknown")
                    )

                if response.status_code == 400:
                    raise ValidationError(error.error)

                # Generic error for other status codes
                response.raise_for_status()

        except httpx.ConnectError as e:
            raise ServerUnreachableError(
                f"Cannot connect to Amelia server at {self.base_url}. "
                f"Is the server running? Try: amelia server"
            ) from e

        # Should not reach here, but satisfy type checker
        return {}

    async def create_workflow(
        self,
        issue_id: str,
        worktree_path: str,
        worktree_name: str | None = None,
        profile: str | None = None,
        driver: str | None = None,
    ) -> CreateWorkflowResponse:
        """Create a new workflow.

        Args:
            issue_id: Issue identifier (e.g., "ISSUE-123")
            worktree_path: Absolute path to git worktree
            worktree_name: Human-readable name for worktree
            profile: Optional profile name for configuration
            driver: Optional driver override (e.g., "sdk:claude")

        Returns:
            CreateWorkflowResponse with id, status, and message

        Raises:
            WorkflowConflictError: If workflow already active in this worktree
            ConcurrencyLimitError: If concurrent workflow limit exceeded
            ServerUnreachableError: If server is not running
            ValidationError: If request validation fails
        """
        request = CreateWorkflowRequest(
            issue_id=issue_id,
            worktree_path=worktree_path,
            worktree_name=worktree_name,
            profile=profile,
            driver=driver,
        )

        data = await self._request(
            "POST",
            "/api/workflows",
            json=request.model_dump(exclude_none=True),
        )
        return CreateWorkflowResponse.model_validate(data)

    async def approve_workflow(self, workflow_id: str) -> ActionResponse:
        """Approve a workflow plan.

        Args:
            workflow_id: Workflow ID to approve

        Returns:
            ActionResponse with status and workflow_id

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            InvalidStateError: If workflow is not in blocked state
            ServerUnreachableError: If server is not running
        """
        data = await self._request(
            "POST",
            f"/api/workflows/{workflow_id}/approve",
        )
        return ActionResponse.model_validate(data)

    async def reject_workflow(self, workflow_id: str, feedback: str) -> ActionResponse:
        """Reject a workflow plan.

        Args:
            workflow_id: Workflow ID to reject
            feedback: Reason for rejection (server uses 'feedback' field)

        Returns:
            ActionResponse with status and workflow_id

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            InvalidStateError: If workflow is not in blocked state
            ServerUnreachableError: If server is not running
        """
        request = RejectRequest(feedback=feedback)

        data = await self._request(
            "POST",
            f"/api/workflows/{workflow_id}/reject",
            json=request.model_dump(),
        )
        return ActionResponse.model_validate(data)

    async def cancel_workflow(self, workflow_id: str) -> ActionResponse:
        """Cancel an active workflow.

        Args:
            workflow_id: Workflow ID to cancel

        Returns:
            ActionResponse with status and workflow_id

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            InvalidStateError: If workflow is in terminal state
            ServerUnreachableError: If server is not running
        """
        data = await self._request(
            "POST",
            f"/api/workflows/{workflow_id}/cancel",
        )
        return ActionResponse.model_validate(data)

    async def get_active_workflows(
        self, worktree_path: str | None = None
    ) -> WorkflowListResponse:
        """Get list of active workflows.

        Args:
            worktree_path: Optional filter by worktree path

        Returns:
            WorkflowListResponse with list of workflows

        Raises:
            ServerUnreachableError: If server is not running
        """
        params: dict[str, Any] = {}
        if worktree_path:
            params["worktree"] = worktree_path

        data = await self._request(
            "GET",
            "/api/workflows/active",
            params=params if params else None,
        )
        return WorkflowListResponse.model_validate(data)

    async def get_workflow(self, workflow_id: str) -> WorkflowDetailResponse:
        """Get details of a specific workflow.

        Args:
            workflow_id: Workflow ID to fetch

        Returns:
            WorkflowDetailResponse with workflow details

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            ServerUnreachableError: If server is not running
        """
        data = await self._request(
            "GET",
            f"/api/workflows/{workflow_id}",
        )
        return WorkflowDetailResponse.model_validate(data)
```

**Step 5: Update client package**

```python
# amelia/client/__init__.py
"""Amelia CLI thin client package."""
from amelia.client.git import get_worktree_context
from amelia.client.api import (
    AmeliaClient,
    AmeliaClientError,
    ServerUnreachableError,
    WorkflowConflictError,
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowNotFoundError,
    ValidationError,
)

__all__ = [
    "get_worktree_context",
    "AmeliaClient",
    "AmeliaClientError",
    "ServerUnreachableError",
    "WorkflowConflictError",
    "ConcurrencyLimitError",
    "InvalidStateError",
    "WorkflowNotFoundError",
    "ValidationError",
]
```

**Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/client/test_api.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/client/api.py amelia/client/models.py amelia/client/__init__.py tests/unit/client/test_api.py
git commit -m "feat(client): add REST API client with server-aligned models"
```

---

## Task 4: Migrate Existing 'start' Command and Add Thin Client Version

**Files:**
- Modify: `amelia/main.py`
- Create: `amelia/client/cli.py`

**Important:** This is a breaking change. The existing `start` command (direct orchestrator execution) is renamed to `start-direct`. The new `start` command delegates to the server.

**Step 1: Write the failing test**

```python
# tests/unit/client/test_cli.py
"""Tests for refactored CLI commands."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typer.testing import CliRunner


class TestStartCommand:
    """Tests for 'amelia start' command (thin client version)."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_start_command_exists(self, runner):
        """'amelia start' command is registered."""
        from amelia.main import app

        result = runner.invoke(app, ["start", "--help"])
        assert result.exit_code == 0
        assert "Start a workflow" in result.stdout

    def test_start_direct_command_exists(self, runner):
        """'amelia start-direct' command is registered (legacy behavior)."""
        from amelia.main import app

        result = runner.invoke(app, ["start-direct", "--help"])
        assert result.exit_code == 0
        assert "Starts the Amelia orchestrator" in result.stdout

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_detects_worktree(self, mock_client_class, mock_worktree, runner):
        """start command auto-detects worktree context."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            status="pending",
            message="Workflow created",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 0
        mock_worktree.assert_called_once()
        mock_client.create_workflow.assert_called_once()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_with_profile(self, mock_client_class, mock_worktree, runner):
        """start command passes profile to API."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            status="pending",
            message="Created",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["start", "ISSUE-123", "--profile", "work"])

        assert result.exit_code == 0
        call_kwargs = mock_client.create_workflow.call_args.kwargs
        assert call_kwargs["profile"] == "work"

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_handles_server_unreachable(self, mock_client_class, mock_worktree, runner):
        """start command shows helpful error when server unreachable."""
        from amelia.main import app
        from amelia.client.api import ServerUnreachableError

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.side_effect = ServerUnreachableError(
            "Cannot connect to server"
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 1
        assert "server" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_handles_workflow_conflict(self, mock_client_class, mock_worktree, runner):
        """start command shows active workflow details on conflict."""
        from amelia.main import app
        from amelia.client.api import WorkflowConflictError

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.side_effect = WorkflowConflictError(
            message="Workflow already active",
            workflow_id="wf-existing",
            worktree_path="/home/user/repo",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 1
        assert "already active" in result.stdout.lower() or "conflict" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    def test_start_handles_not_in_git_repo(self, mock_worktree, runner):
        """start command shows error when not in git repo."""
        from amelia.main import app

        mock_worktree.side_effect = ValueError("Not inside a git repository")

        result = runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 1
        assert "git repository" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    def test_start_handles_bare_repo(self, mock_worktree, runner):
        """start command shows error for bare repository."""
        from amelia.main import app

        mock_worktree.side_effect = ValueError("Cannot run workflows in a bare repository")

        result = runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 1
        assert "bare repository" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_shows_success_message(self, mock_client_class, mock_worktree, runner):
        """start command shows success with workflow ID."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            status="pending",
            message="Workflow created for issue ISSUE-123",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 0
        assert "wf-123" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_cli.py::TestStartCommand -v`
Expected: FAIL (command not found or old implementation)

**Step 3: Implement CLI commands module**

```python
# amelia/client/cli.py
"""Thin client CLI commands that delegate to the REST API."""
import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from amelia.client.git import get_worktree_context
from amelia.client.api import (
    AmeliaClient,
    ServerUnreachableError,
    WorkflowConflictError,
    ConcurrencyLimitError,
    InvalidStateError,
    WorkflowNotFoundError,
)


console = Console()


def start_command(
    issue_id: Annotated[str, typer.Argument(help="Issue ID to work on (e.g., ISSUE-123)")],
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Profile name for configuration"),
    ] = None,
    driver: Annotated[
        str | None,
        typer.Option("--driver", "-d", help="Driver override (e.g., sdk:claude)"),
    ] = None,
) -> None:
    """Start a workflow for an issue via the server.

    Detects the current git worktree and creates a new workflow via the API server.
    The server manages orchestration and state persistence.

    For direct local execution without server, use 'amelia start-direct'.
    """
    # Detect worktree context
    try:
        worktree_path, worktree_name = get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\nMake sure you're in a git repository working directory.")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Create workflow via API
    client = AmeliaClient()

    async def _create():
        return await client.create_workflow(
            issue_id=issue_id,
            worktree_path=worktree_path,
            worktree_name=worktree_name,
            profile=profile,
            driver=driver,
        )

    try:
        response = asyncio.run(_create())

        console.print(f"[green]Workflow started:[/green] [bold]{response.id}[/bold]")
        console.print(f"  Status: {response.status}")
        console.print(f"  {response.message}")
        console.print(f"\n[dim]Worktree: {worktree_path} ({worktree_name})[/dim]")
        console.print("[dim]View in dashboard: http://127.0.0.1:8420[/dim]")

    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1)

    except WorkflowConflictError as e:
        console.print(f"[red]Error:[/red] Workflow already active in this worktree")
        if e.workflow_id:
            console.print(f"\n  Active workflow: [bold]{e.workflow_id}[/bold]")
        console.print("\n[yellow]Options:[/yellow]")
        console.print("  - Cancel existing: [bold]amelia cancel[/bold]")
        console.print("  - Check status: [bold]amelia status[/bold]")
        console.print("  - Use different worktree: [bold]git worktree add ...[/bold]")
        raise typer.Exit(1)

    except ConcurrencyLimitError as e:
        console.print(f"[red]Error:[/red] {e}")
        if e.retry_after:
            console.print(f"\nRetry after {e.retry_after} seconds.")
        raise typer.Exit(1)


def approve_command() -> None:
    """Approve the workflow plan in the current worktree.

    Auto-detects the workflow from the current git worktree.
    Only works when a workflow is in 'blocked' state awaiting approval.
    """
    try:
        worktree_path, _ = get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    client = AmeliaClient()

    async def _approve():
        # Get workflows for this worktree
        result = await client.get_active_workflows(worktree_path=worktree_path)

        if not result.workflows:
            console.print(f"[red]Error:[/red] No active workflow in this worktree")
            console.print("\n[yellow]Start a workflow:[/yellow] amelia start ISSUE-123")
            raise typer.Exit(1)

        workflow = result.workflows[0]

        # Check if workflow is in blocked state
        if workflow.status != "blocked":
            console.print(f"[red]Error:[/red] Workflow is not awaiting approval")
            console.print(f"\n  Workflow: [bold]{workflow.id}[/bold]")
            console.print(f"  Status: {workflow.status}")
            console.print("\nWorkflows can only be approved when in 'blocked' state.")
            raise typer.Exit(1)

        # Approve it
        try:
            response = await client.approve_workflow(workflow_id=workflow.id)
            console.print(f"[green]Plan approved:[/green] [bold]{workflow.id}[/bold]")
            console.print(f"  Issue: {workflow.issue_id}")
            console.print("\n[dim]Workflow will now continue execution.[/dim]")
        except InvalidStateError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    try:
        asyncio.run(_approve())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1)


def reject_command(
    feedback: Annotated[str, typer.Argument(help="Feedback explaining what needs to change")],
) -> None:
    """Reject the workflow plan in the current worktree.

    Provide feedback that will be sent to the Architect agent for replanning.
    Only works when a workflow is in 'blocked' state awaiting approval.
    """
    try:
        worktree_path, _ = get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    client = AmeliaClient()

    async def _reject():
        result = await client.get_active_workflows(worktree_path=worktree_path)

        if not result.workflows:
            console.print(f"[red]Error:[/red] No active workflow in this worktree")
            console.print("\n[yellow]Start a workflow:[/yellow] amelia start ISSUE-123")
            raise typer.Exit(1)

        workflow = result.workflows[0]

        # Check if workflow is in blocked state
        if workflow.status != "blocked":
            console.print(f"[red]Error:[/red] Workflow is not awaiting approval")
            console.print(f"\n  Workflow: [bold]{workflow.id}[/bold]")
            console.print(f"  Status: {workflow.status}")
            raise typer.Exit(1)

        try:
            await client.reject_workflow(workflow_id=workflow.id, feedback=feedback)
            console.print(f"[yellow]Plan rejected:[/yellow] [bold]{workflow.id}[/bold]")
            console.print(f"  Feedback: {feedback}")
            console.print("\n[dim]Architect will replan based on your feedback.[/dim]")
        except InvalidStateError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    try:
        asyncio.run(_reject())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1)


def status_command(
    all_worktrees: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show workflows from all worktrees"),
    ] = False,
) -> None:
    """Show status of active workflows.

    By default, shows workflow for the current worktree only.
    Use --all to see workflows from all worktrees.
    """
    worktree_path = None
    if not all_worktrees:
        try:
            worktree_path, _ = get_worktree_context()
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    client = AmeliaClient()

    async def _status():
        result = await client.get_active_workflows(worktree_path=worktree_path)

        if not result.workflows:
            if all_worktrees:
                console.print("[dim]No active workflows across all worktrees.[/dim]")
            else:
                console.print(f"[dim]No active workflow in {worktree_path}[/dim]")
                console.print("\n[yellow]Start a workflow:[/yellow] amelia start ISSUE-123")
            return

        # Display workflows in a table
        table = Table(title="Active Workflows", show_header=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Issue", style="magenta")
        table.add_column("Status", style="yellow")
        table.add_column("Worktree", style="green")
        table.add_column("Stage", style="blue")

        for wf in result.workflows:
            status_style = {
                "pending": "dim",
                "in_progress": "yellow",
                "blocked": "red bold",
                "completed": "green",
                "failed": "red",
                "cancelled": "dim",
            }.get(wf.status, "white")

            table.add_row(
                wf.id,
                wf.issue_id,
                f"[{status_style}]{wf.status}[/{status_style}]",
                wf.worktree_name,
                wf.current_stage or "-",
            )

        console.print(table)
        console.print(f"\n[dim]Total: {result.total} workflow(s)[/dim]")

    try:
        asyncio.run(_status())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1)


def cancel_command(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Cancel the active workflow in the current worktree.

    Requires confirmation unless --force is used.
    """
    try:
        worktree_path, _ = get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    client = AmeliaClient()

    async def _cancel():
        result = await client.get_active_workflows(worktree_path=worktree_path)

        if not result.workflows:
            console.print(f"[red]Error:[/red] No active workflow in this worktree")
            raise typer.Exit(1)

        workflow = result.workflows[0]

        # Confirm cancellation
        if not force:
            console.print(f"Cancel workflow [bold]{workflow.id}[/bold] ({workflow.issue_id})?")
            confirm = typer.confirm("Are you sure?")
            if not confirm:
                console.print("[yellow]Cancelled.[/yellow]")
                raise typer.Exit(1)

        await client.cancel_workflow(workflow_id=workflow.id)
        console.print(f"[yellow]Workflow cancelled:[/yellow] [bold]{workflow.id}[/bold]")

    try:
        asyncio.run(_cancel())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1)
    except InvalidStateError as e:
        console.print(f"[red]Error:[/red] Cannot cancel - {e}")
        raise typer.Exit(1)
```

**Step 4: Update main.py to register new commands and rename existing start**

Replace the entire `amelia/main.py`:

```python
# amelia/main.py
"""Amelia CLI - Agentic Coding Orchestrator."""
import asyncio

import typer
from langgraph.checkpoint.memory import MemorySaver

from amelia.agents.architect import Architect
from amelia.config import load_settings, validate_profile
from amelia.core.orchestrator import call_reviewer_node, create_orchestrator_graph
from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile, Settings
from amelia.drivers.factory import DriverFactory
from amelia.logging import configure_logging
from amelia.server.cli import server_app
from amelia.tools.shell_executor import run_shell_command
from amelia.trackers.factory import create_tracker
from amelia.utils.design_parser import parse_design

# Import thin client commands
from amelia.client.cli import (
    start_command,
    approve_command,
    reject_command,
    status_command,
    cancel_command,
)


app = typer.Typer(help="Amelia Agentic Orchestrator CLI")
app.add_typer(server_app, name="server")


@app.callback()
def main_callback() -> None:
    """Amelia: A local agentic coding system."""
    configure_logging()


def _get_active_profile(settings: Settings, profile_name: str | None) -> Profile:
    """Get the active profile from settings, either specified or default."""
    if profile_name:
        if profile_name not in settings.profiles:
            typer.echo(f"Error: Profile '{profile_name}' not found in settings.", err=True)
            raise typer.Exit(code=1)
        return settings.profiles[profile_name]
    else:
        return settings.profiles[settings.active_profile]


def _safe_load_settings() -> Settings:
    """Load settings from configuration file with error handling."""
    try:
        return load_settings()
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None
    except Exception as e:
        typer.echo(f"Error loading settings: {e}", err=True)
        raise typer.Exit(code=1) from None


# Register thin client commands
app.command(name="start")(start_command)
app.command(name="approve")(approve_command)
app.command(name="reject")(reject_command)
app.command(name="status")(status_command)
app.command(name="cancel")(cancel_command)


# Legacy direct execution command (renamed from 'start')
@app.command(name="start-direct")
def start_direct(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="The ID of the issue to work on (e.g., PROJ-123)."),
    profile_name: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help="Specify the profile to use from settings.amelia.yaml."
    ),
) -> None:
    """Starts the Amelia orchestrator directly without the server.

    This is the legacy execution mode that runs the full orchestrator locally.
    For server-managed execution with persistence, use 'amelia start' instead.
    """
    settings = _safe_load_settings()
    active_profile = _get_active_profile(settings, profile_name)

    try:
        validate_profile(active_profile)
    except ValueError as e:
        typer.echo(f"Profile validation failed: {e}", err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"Starting Amelia (direct mode) with profile: {active_profile.name}")
    typer.echo(f"  Driver: {active_profile.driver}, Tracker: {active_profile.tracker}")

    checkpoint_saver = MemorySaver()
    app_graph = create_orchestrator_graph(checkpoint_saver=checkpoint_saver)

    tracker = create_tracker(active_profile)
    try:
        issue = tracker.get_issue(issue_id)
    except ValueError as e:
        typer.echo(f"Error fetching issue: {e}", err=True)
        raise typer.Exit(code=1) from None

    initial_state = ExecutionState(profile=active_profile, issue=issue)

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            typer.echo("Warning: event loop already running", err=True)
            raise RuntimeError("Async event loop already running. Cannot use asyncio.run()")

        asyncio.run(app_graph.ainvoke(initial_state))

    except Exception as e:
        typer.echo(f"An unexpected error occurred during orchestration: {e}", err=True)
        raise typer.Exit(code=1) from None


@app.command(name="plan-only")
def plan_only_command(
    ctx: typer.Context,
    issue_id: str = typer.Argument(..., help="The ID of the issue to generate a plan for."),
    profile_name: str | None = typer.Option(
        None, "--profile", "-p", help="Specify the profile to use from settings.amelia.yaml."
    ),
    design_path: str | None = typer.Option(
        None, "--design", "-d", help="Path to design markdown file from brainstorming."
    ),
) -> None:
    """Generates a plan for the specified issue using the Architect agent without execution."""
    async def _run() -> None:
        settings = _safe_load_settings()
        active_profile = _get_active_profile(settings, profile_name)

        try:
            validate_profile(active_profile)
        except ValueError as e:
            typer.echo(f"Profile validation failed: {e}", err=True)
            raise typer.Exit(code=1) from None

        typer.echo(f"Generating plan for issue {issue_id} with profile: {active_profile.name}")

        tracker = create_tracker(active_profile)
        try:
            issue = tracker.get_issue(issue_id)
        except ValueError as e:
            typer.echo(f"Error fetching issue: {e}", err=True)
            raise typer.Exit(code=1) from None

        design = None
        if design_path:
            try:
                driver = DriverFactory.get_driver(active_profile.driver)
                design = await parse_design(design_path, driver)
                typer.echo(f"Loaded design from: {design_path}")
            except FileNotFoundError:
                typer.echo(f"Error: Design file not found: {design_path}", err=True)
                raise typer.Exit(code=1) from None

        architect = Architect(DriverFactory.get_driver(active_profile.driver))
        result = await architect.plan(issue, design=design, output_dir=active_profile.plan_output_dir)

        typer.echo("\n--- GENERATED PLAN ---")
        if result.task_dag and result.task_dag.tasks:
            for task in result.task_dag.tasks:
                deps = f" (Dependencies: {', '.join(task.dependencies)})" if task.dependencies else ""
                typer.echo(f"  - [{task.id}] {task.description}{deps}")

            typer.echo(f"\nPlan saved to: {result.markdown_path}")
        else:
            typer.echo("No plan generated.")

    asyncio.run(_run())


@app.command()
def review(
    ctx: typer.Context,
    local: bool = typer.Option(
        False,
        "--local",
        "-l",
        help="Review local uncommitted changes (git diff)."
    ),
    profile_name: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help="Specify the profile to use from settings.amelia.yaml."
    ),
) -> None:
    """Triggers a review process for the current project."""
    async def _run() -> None:
        typer.echo("Starting Amelia Review process...")

        settings = _safe_load_settings()

        if profile_name:
            if profile_name not in settings.profiles:
                typer.echo(f"Error: Profile '{profile_name}' not found in settings.", err=True)
                raise typer.Exit(code=1)
            active_profile = settings.profiles[profile_name]
        else:
            active_profile = settings.profiles[settings.active_profile]

        try:
            validate_profile(active_profile)
        except ValueError as e:
            typer.echo(f"Profile validation failed: {e}", err=True)
            raise typer.Exit(code=1) from None

        if local:
            typer.echo("Reviewing local uncommitted changes...")
            try:
                code_changes = await run_shell_command("git diff")
                if not code_changes:
                    typer.echo("No local uncommitted changes found to review.", err=True)
                    raise typer.Exit(code=0)
                typer.echo(f"Found local changes (first 500 chars):\n{code_changes[:500]}...")

                dummy_issue = Issue(
                    id="LOCAL-REVIEW",
                    title="Local Code Review",
                    description="Review local uncommitted changes."
                )

                initial_state = ExecutionState(
                    profile=active_profile,
                    issue=dummy_issue,
                    code_changes_for_review=code_changes
                )

                result_state = await call_reviewer_node(initial_state)

                if result_state.review_results:
                    review_result = result_state.review_results[-1]
                    typer.echo(f"\n--- REVIEW RESULT ({review_result.reviewer_persona}) ---")
                    typer.echo(f"Approved: {review_result.approved}")
                    typer.echo(f"Severity: {review_result.severity}")
                    typer.echo("Comments:")
                    for comment in review_result.comments:
                        typer.echo(f"- {comment}")
                else:
                    typer.echo("No review results obtained.")

            except RuntimeError as e:
                typer.echo(f"Error getting local changes: {e}", err=True)
                raise typer.Exit(code=1) from None
        else:
            typer.echo("Please specify '--local' to review local changes.", err=True)
            raise typer.Exit(code=1)

    asyncio.run(_run())


if __name__ == "__main__":
    app()
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/client/test_cli.py::TestStartCommand -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/client/cli.py amelia/main.py tests/unit/client/test_cli.py
git commit -m "feat(cli): refactor to thin client with server delegation

BREAKING CHANGE: 'amelia start' now delegates to server API.
Use 'amelia start-direct' for legacy direct orchestrator execution."
```

---

## Task 5: Add Tests for Remaining CLI Commands

**Files:**
- Modify: `tests/unit/client/test_cli.py`

**Step 1: Add tests for approve, reject, status, cancel commands**

```python
# tests/unit/client/test_cli.py (append to existing file)

class TestApproveCommand:
    """Tests for 'amelia approve' command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_approve_command_exists(self, runner):
        from amelia.main import app
        result = runner.invoke(app, ["approve", "--help"])
        assert result.exit_code == 0

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_approve_finds_workflow_by_worktree(self, mock_client_class, mock_worktree, runner):
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="blocked",  # Must be blocked for approval
                    worktree_name="main",
                )
            ],
            total=1,
        )
        mock_client.approve_workflow.return_value = MagicMock(
            status="approved", workflow_id="wf-123"
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["approve"])

        assert result.exit_code == 0
        mock_client.approve_workflow.assert_called_once_with(workflow_id="wf-123")

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_approve_shows_error_when_no_workflow(self, mock_client_class, mock_worktree, runner):
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(workflows=[], total=0)
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["approve"])

        assert result.exit_code == 1
        assert "no active workflow" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_approve_shows_error_when_not_blocked(self, mock_client_class, mock_worktree, runner):
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="in_progress",  # Not blocked
                    worktree_name="main",
                )
            ],
            total=1,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["approve"])

        assert result.exit_code == 1
        assert "not awaiting approval" in result.stdout.lower()


class TestRejectCommand:
    """Tests for 'amelia reject' command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_reject_command_exists(self, runner):
        from amelia.main import app
        result = runner.invoke(app, ["reject", "--help"])
        assert result.exit_code == 0

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_reject_with_feedback(self, mock_client_class, mock_worktree, runner):
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[MagicMock(id="wf-123", issue_id="ISSUE-123", status="blocked")]
        )
        mock_client.reject_workflow.return_value = MagicMock(
            status="rejected", workflow_id="wf-123"
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["reject", "Not ready yet"])

        assert result.exit_code == 0
        mock_client.reject_workflow.assert_called_once_with(
            workflow_id="wf-123", feedback="Not ready yet"
        )


class TestStatusCommand:
    """Tests for 'amelia status' command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_status_command_exists(self, runner):
        from amelia.main import app
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_status_shows_current_worktree(self, mock_client_class, mock_worktree, runner):
        from amelia.main import app
        from datetime import datetime

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="in_progress",
                    worktree_name="main",
                    started_at=datetime(2025, 12, 1, 10, 0, 0),
                    current_stage="developer",
                )
            ],
            total=1,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "wf-123" in result.stdout
        assert "ISSUE-123" in result.stdout

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_status_all_flag(self, mock_client_class, mock_worktree, runner):
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(workflows=[], total=0)
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["status", "--all"])

        assert result.exit_code == 0
        # Should call without worktree filter
        mock_client.get_active_workflows.assert_called_once_with(worktree_path=None)


class TestCancelCommand:
    """Tests for 'amelia cancel' command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_cancel_command_exists(self, runner):
        from amelia.main import app
        result = runner.invoke(app, ["cancel", "--help"])
        assert result.exit_code == 0

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_cancel_with_force(self, mock_client_class, mock_worktree, runner):
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[MagicMock(id="wf-123", issue_id="ISSUE-123")]
        )
        mock_client.cancel_workflow.return_value = MagicMock(
            status="cancelled", workflow_id="wf-123"
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["cancel", "--force"])

        assert result.exit_code == 0
        mock_client.cancel_workflow.assert_called_once()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_cancel_requires_confirmation(self, mock_client_class, mock_worktree, runner):
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[MagicMock(id="wf-123", issue_id="ISSUE-123")]
        )
        mock_client_class.return_value = mock_client

        # User declines
        result = runner.invoke(app, ["cancel"], input="n\n")

        assert result.exit_code == 1
        mock_client.cancel_workflow.assert_not_called()
```

**Step 2: Run all CLI tests**

Run: `uv run pytest tests/unit/client/test_cli.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/unit/client/test_cli.py
git commit -m "test(cli): add tests for approve, reject, status, cancel commands"
```

---

## Task 6: Integration Tests

**Files:**
- Create: `tests/integration/test_cli_thin_client.py`

**Step 1: Write integration tests**

```python
# tests/integration/test_cli_thin_client.py
"""Integration tests for CLI thin client workflows."""
import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from typer.testing import CliRunner


class TestCLIThinClientFlows:
    """Integration tests for full CLI thin client workflows."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def mock_git_repo(self, tmp_path):
        """Create a temporary git repository."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "initial"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        return repo_path

    @patch("amelia.client.cli.AmeliaClient")
    def test_start_approve_flow(self, mock_client_class, runner, mock_git_repo):
        """Test start -> approve flow."""
        from amelia.main import app

        mock_client = AsyncMock()

        # Mock start workflow response
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            status="pending",
            message="Workflow created",
        )

        # Mock get workflows for approve (workflow is blocked)
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="blocked",
                    worktree_name="main",
                )
            ],
            total=1,
        )
        mock_client.approve_workflow.return_value = MagicMock(
            status="approved", workflow_id="wf-123"
        )

        mock_client_class.return_value = mock_client

        with patch("os.getcwd", return_value=str(mock_git_repo)):
            # Start workflow
            result = runner.invoke(app, ["start", "ISSUE-123"])
            assert result.exit_code == 0
            assert "wf-123" in result.stdout

            # Approve workflow
            result = runner.invoke(app, ["approve"])
            assert result.exit_code == 0
            assert "approved" in result.stdout.lower()

    def test_error_when_not_in_git_repo(self, runner, tmp_path):
        """All commands fail gracefully when not in git repo."""
        from amelia.main import app

        with patch("os.getcwd", return_value=str(tmp_path)):
            # start
            result = runner.invoke(app, ["start", "ISSUE-123"])
            assert result.exit_code == 1
            assert "git repository" in result.stdout.lower()

            # approve
            result = runner.invoke(app, ["approve"])
            assert result.exit_code == 1

            # reject
            result = runner.invoke(app, ["reject", "reason"])
            assert result.exit_code == 1

            # cancel
            result = runner.invoke(app, ["cancel"])
            assert result.exit_code == 1
```

**Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_cli_thin_client.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_cli_thin_client.py
git commit -m "test(cli): add integration tests for thin client flows"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] `uv run pytest tests/unit/client/ -v` - All unit tests pass
- [ ] `uv run pytest tests/integration/test_cli_thin_client.py -v` - Integration tests pass
- [ ] `uv run ruff check amelia/client` - No linting errors
- [ ] `uv run mypy amelia/client` - No type errors
- [ ] `uv run amelia start --help` - Shows thin client help
- [ ] `uv run amelia start-direct --help` - Shows legacy direct execution help
- [ ] `uv run amelia approve --help` - Shows help text
- [ ] `uv run amelia reject --help` - Shows help text
- [ ] `uv run amelia status --help` - Shows help text
- [ ] `uv run amelia cancel --help` - Shows help text

Manual testing (requires running server):
- [ ] `uv run amelia server` - Start server in one terminal
- [ ] `cd /path/to/git/repo && uv run amelia start ISSUE-123` - Creates workflow
- [ ] `uv run amelia status` - Shows active workflow
- [ ] `uv run amelia status --all` - Shows all workflows
- [ ] `uv run amelia approve` - Approves workflow (when blocked)
- [ ] `uv run amelia cancel` - Cancels workflow with confirmation

---

## Summary

This plan refactors the CLI into a thin client that delegates all workflow orchestration to the FastAPI server:

| Component | File | Purpose |
|-----------|------|---------|
| Dependencies | `pyproject.toml` | httpx, rich already present |
| Git Utils | `amelia/client/git.py` | Worktree context detection |
| Models | `amelia/client/models.py` | Server-aligned Pydantic models |
| API Client | `amelia/client/api.py` | httpx REST client with error handling |
| CLI Commands | `amelia/client/cli.py` | Thin client commands |
| Main | `amelia/main.py` | Register commands, rename legacy `start` |

**Key Changes from Original Plan:**
1. Dependencies already exist - verification only
2. Models aligned with server (`feedback` not `reason`, `cursor` not `next_cursor`)
3. Error handling matches server's `ErrorResponse` format
4. Existing `start` command renamed to `start-direct`
5. Added workflow status check before approve/reject
6. Fixed pagination field names

**Breaking Change:** `amelia start` now delegates to server. Use `amelia start-direct` for legacy behavior.

**Next PR:** WebSocket Event Stream Client (Plan 8)
