# CLI Thin Client Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor CLI to become a thin client that delegates workflow orchestration to the FastAPI server via REST API calls.

**Architecture:** CLI commands detect the current git worktree context and make httpx-based REST calls to the local server. Commands map to server endpoints: `start` creates workflows, `approve`/`reject` send workflow actions, `status` queries active workflows, `cancel` terminates workflows. The CLI provides rich error messages and auto-detects workflow IDs from the current worktree.

**Tech Stack:** typer, httpx, rich (formatting), subprocess (git operations), pydantic (request/response models)

**Depends on:**
- Phase 2.1 Plans 1-6 (server foundation, database, workflow API, events, WebSocket)

---

## Task 1: Add CLI Client Dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Write the failing test**

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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_dependencies.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Add dependencies to pyproject.toml**

Add to dependencies section in `pyproject.toml`:

```toml
dependencies = [
    # ... existing deps ...
    "httpx>=0.27.0",
    "rich>=13.9.0",
]
```

**Step 4: Sync dependencies**

Run: `uv sync`
Expected: Dependencies installed successfully

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/client/test_dependencies.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add pyproject.toml uv.lock tests/unit/client/test_dependencies.py
git commit -m "feat(cli): add httpx and rich dependencies for thin client"
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

**Step 1: Write the failing test**

```python
# tests/unit/client/test_api.py
"""Tests for REST API client."""
import pytest
import httpx
from unittest.mock import AsyncMock, patch
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
        from amelia.client.models import WorkflowResponse

        mock_response = {
            "id": "wf-123",
            "issue_id": "ISSUE-123",
            "status": "planning",
            "worktree_path": "/home/user/repo",
            "worktree_name": "main",
            "started_at": "2025-12-01T10:00:00Z",
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                200,
                json=mock_response,
            )

            result = await client.create_workflow(
                issue_id="ISSUE-123",
                worktree_path="/home/user/repo",
                worktree_name="main",
            )

            assert isinstance(result, WorkflowResponse)
            assert result.id == "wf-123"
            assert result.issue_id == "ISSUE-123"
            assert result.status == "planning"

            # Verify request was made correctly
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs["json"]["issue_id"] == "ISSUE-123"
            assert call_kwargs["json"]["worktree_path"] == "/home/user/repo"

    @pytest.mark.asyncio
    async def test_create_workflow_with_profile(self, client):
        """create_workflow includes profile when provided."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                200,
                json={
                    "id": "wf-123",
                    "issue_id": "ISSUE-123",
                    "status": "planning",
                    "worktree_path": "/home/user/repo",
                    "worktree_name": "main",
                    "started_at": "2025-12-01T10:00:00Z",
                },
            )

            await client.create_workflow(
                issue_id="ISSUE-123",
                worktree_path="/home/user/repo",
                worktree_name="main",
                profile="work",
            )

            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs["json"]["profile"] == "work"

    @pytest.mark.asyncio
    async def test_approve_workflow(self, client):
        """approve_workflow sends POST to correct endpoint."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={"status": "approved"})

            await client.approve_workflow(workflow_id="wf-123")

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/workflows/wf-123/approve" in str(call_args)

    @pytest.mark.asyncio
    async def test_reject_workflow(self, client):
        """reject_workflow sends POST with reason."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={"status": "rejected"})

            await client.reject_workflow(workflow_id="wf-123", reason="Not ready")

            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs["json"]["reason"] == "Not ready"

    @pytest.mark.asyncio
    async def test_cancel_workflow(self, client):
        """cancel_workflow sends POST to cancel endpoint."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={"status": "cancelled"})

            await client.cancel_workflow(workflow_id="wf-123")

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/workflows/wf-123/cancel" in str(call_args)

    @pytest.mark.asyncio
    async def test_get_active_workflows(self, client):
        """get_active_workflows fetches active workflows."""
        from amelia.client.models import WorkflowListResponse

        mock_response = {
            "workflows": [
                {
                    "id": "wf-123",
                    "issue_id": "ISSUE-123",
                    "status": "in_progress",
                    "worktree_path": "/home/user/repo",
                    "worktree_name": "main",
                    "started_at": "2025-12-01T10:00:00Z",
                }
            ],
            "total": 1,
            "next_cursor": None,
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = httpx.Response(200, json=mock_response)

            result = await client.get_active_workflows()

            assert isinstance(result, WorkflowListResponse)
            assert len(result.workflows) == 1
            assert result.total == 1

    @pytest.mark.asyncio
    async def test_get_active_workflows_filter_by_worktree(self, client):
        """get_active_workflows can filter by worktree path."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = httpx.Response(
                200, json={"workflows": [], "total": 0, "next_cursor": None}
            )

            await client.get_active_workflows(worktree_path="/home/user/repo")

            call_kwargs = mock_get.call_args.kwargs
            assert "worktree" in call_kwargs["params"]
            assert call_kwargs["params"]["worktree"] == "/home/user/repo"

    @pytest.mark.asyncio
    async def test_get_workflow(self, client):
        """get_workflow fetches single workflow by ID."""
        from amelia.client.models import WorkflowResponse

        mock_response = {
            "id": "wf-123",
            "issue_id": "ISSUE-123",
            "status": "in_progress",
            "worktree_path": "/home/user/repo",
            "worktree_name": "main",
            "started_at": "2025-12-01T10:00:00Z",
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = httpx.Response(200, json=mock_response)

            result = await client.get_workflow(workflow_id="wf-123")

            assert isinstance(result, WorkflowResponse)
            assert result.id == "wf-123"

    @pytest.mark.asyncio
    async def test_client_handles_409_conflict(self, client):
        """Client raises descriptive error on 409 Conflict."""
        from amelia.client.api import WorkflowConflictError

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                409,
                json={
                    "detail": {
                        "error": "workflow_already_active",
                        "message": "Workflow already active",
                        "active_workflow": {
                            "id": "wf-existing",
                            "issue_id": "ISSUE-99",
                            "status": "in_progress",
                        },
                    }
                },
            )

            with pytest.raises(WorkflowConflictError) as exc_info:
                await client.create_workflow(
                    issue_id="ISSUE-123",
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                )

            assert "already active" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_client_handles_429_rate_limit(self, client):
        """Client raises descriptive error on 429 Too Many Requests."""
        from amelia.client.api import RateLimitError

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = httpx.Response(
                429,
                headers={"Retry-After": "30"},
                json={"detail": "Too many concurrent workflows"},
            )

            with pytest.raises(RateLimitError) as exc_info:
                await client.create_workflow(
                    issue_id="ISSUE-123",
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                )

            assert "30" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_client_handles_connection_error(self, client):
        """Client raises descriptive error when server is unreachable."""
        from amelia.client.api import ServerUnreachableError

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")

            with pytest.raises(ServerUnreachableError) as exc_info:
                await client.create_workflow(
                    issue_id="ISSUE-123",
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                )

            assert "server" in str(exc_info.value).lower()
            assert "8420" in str(exc_info.value)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_api.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create client models**

```python
# amelia/client/models.py
"""Pydantic models for API requests and responses."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateWorkflowRequest(BaseModel):
    """Request to create a new workflow."""

    issue_id: str = Field(..., min_length=1, max_length=100)
    worktree_path: str = Field(..., min_length=1, max_length=4096)
    worktree_name: str | None = Field(default=None, max_length=255)
    profile: str | None = Field(default=None, max_length=64)


class RejectWorkflowRequest(BaseModel):
    """Request to reject a workflow plan."""

    reason: str = Field(..., min_length=1, max_length=1000)


class WorkflowResponse(BaseModel):
    """Workflow detail response."""

    id: str
    issue_id: str
    status: str
    worktree_path: str
    worktree_name: str | None = None
    profile: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class WorkflowSummary(BaseModel):
    """Workflow summary for list responses."""

    id: str
    issue_id: str
    status: str
    worktree_path: str
    worktree_name: str | None = None
    started_at: datetime


class WorkflowListResponse(BaseModel):
    """Response for listing workflows."""

    workflows: list[WorkflowSummary]
    total: int
    next_cursor: str | None = None
```

**Step 4: Implement API client**

```python
# amelia/client/api.py
"""REST API client for Amelia server."""
import httpx
from typing import Any

from amelia.client.models import (
    CreateWorkflowRequest,
    RejectWorkflowRequest,
    WorkflowResponse,
    WorkflowListResponse,
)


class AmeliaClientError(Exception):
    """Base exception for API client errors."""

    pass


class ServerUnreachableError(AmeliaClientError):
    """Raised when server cannot be reached."""

    pass


class WorkflowConflictError(AmeliaClientError):
    """Raised when workflow already exists for worktree (409 Conflict)."""

    def __init__(self, message: str, active_workflow: dict[str, Any] | None = None):
        """Initialize with message and optional active workflow info."""
        super().__init__(message)
        self.active_workflow = active_workflow


class RateLimitError(AmeliaClientError):
    """Raised when rate limit is exceeded (429 Too Many Requests)."""

    def __init__(self, message: str, retry_after: int | None = None):
        """Initialize with message and optional retry-after seconds."""
        super().__init__(message)
        self.retry_after = retry_after


class WorkflowNotFoundError(AmeliaClientError):
    """Raised when workflow is not found (404)."""

    pass


class InvalidRequestError(AmeliaClientError):
    """Raised when request validation fails (400/422)."""

    pass


class AmeliaClient:
    """HTTP client for Amelia REST API.

    Provides methods for all workflow operations: create, approve, reject,
    cancel, and query. Handles errors and converts them to descriptive exceptions.

    Example:
        >>> client = AmeliaClient()
        >>> workflow = await client.create_workflow(
        ...     issue_id="ISSUE-123",
        ...     worktree_path="/home/user/repo",
        ...     worktree_name="main"
        ... )
        >>> await client.approve_workflow(workflow.id)
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8420"):
        """Initialize API client.

        Args:
            base_url: Base URL of the Amelia server (default: http://127.0.0.1:8420)
        """
        self.base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(30.0, connect=5.0)

    async def create_workflow(
        self,
        issue_id: str,
        worktree_path: str,
        worktree_name: str | None = None,
        profile: str | None = None,
    ) -> WorkflowResponse:
        """Create a new workflow.

        Args:
            issue_id: Issue identifier (e.g., "ISSUE-123")
            worktree_path: Absolute path to git worktree
            worktree_name: Human-readable name for worktree
            profile: Optional profile name for configuration

        Returns:
            WorkflowResponse with created workflow details

        Raises:
            WorkflowConflictError: If workflow already active in this worktree
            RateLimitError: If concurrent workflow limit exceeded
            ServerUnreachableError: If server is not running
            InvalidRequestError: If request validation fails
        """
        request = CreateWorkflowRequest(
            issue_id=issue_id,
            worktree_path=worktree_path,
            worktree_name=worktree_name,
            profile=profile,
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/workflows",
                    json=request.model_dump(exclude_none=True),
                )

                if response.status_code == 200:
                    return WorkflowResponse.model_validate(response.json())
                elif response.status_code == 409:
                    data = response.json()
                    detail = data.get("detail", {})
                    active = detail.get("active_workflow")
                    raise WorkflowConflictError(
                        detail.get("message", "Workflow already active"),
                        active_workflow=active,
                    )
                elif response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    raise RateLimitError(
                        f"Too many concurrent workflows. Retry after {retry_after} seconds.",
                        retry_after=int(retry_after) if retry_after else None,
                    )
                elif response.status_code in (400, 422):
                    raise InvalidRequestError(f"Invalid request: {response.json()}")
                else:
                    response.raise_for_status()

        except httpx.ConnectError as e:
            raise ServerUnreachableError(
                f"Cannot connect to Amelia server at {self.base_url}. "
                f"Is the server running? Try: amelia server"
            ) from e

    async def approve_workflow(self, workflow_id: str) -> None:
        """Approve a workflow plan.

        Args:
            workflow_id: Workflow ID to approve

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            InvalidRequestError: If workflow is not in a state that can be approved
            ServerUnreachableError: If server is not running
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/workflows/{workflow_id}/approve"
                )

                if response.status_code == 404:
                    raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")
                elif response.status_code == 400:
                    raise InvalidRequestError(response.json().get("detail", "Invalid request"))

                response.raise_for_status()

        except httpx.ConnectError as e:
            raise ServerUnreachableError(
                f"Cannot connect to Amelia server at {self.base_url}"
            ) from e

    async def reject_workflow(self, workflow_id: str, reason: str) -> None:
        """Reject a workflow plan.

        Args:
            workflow_id: Workflow ID to reject
            reason: Reason for rejection

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            InvalidRequestError: If workflow is not in a state that can be rejected
            ServerUnreachableError: If server is not running
        """
        request = RejectWorkflowRequest(reason=reason)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/workflows/{workflow_id}/reject",
                    json=request.model_dump(),
                )

                if response.status_code == 404:
                    raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")
                elif response.status_code == 400:
                    raise InvalidRequestError(response.json().get("detail", "Invalid request"))

                response.raise_for_status()

        except httpx.ConnectError as e:
            raise ServerUnreachableError(
                f"Cannot connect to Amelia server at {self.base_url}"
            ) from e

    async def cancel_workflow(self, workflow_id: str) -> None:
        """Cancel an active workflow.

        Args:
            workflow_id: Workflow ID to cancel

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            ServerUnreachableError: If server is not running
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/workflows/{workflow_id}/cancel"
                )

                if response.status_code == 404:
                    raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")

                response.raise_for_status()

        except httpx.ConnectError as e:
            raise ServerUnreachableError(
                f"Cannot connect to Amelia server at {self.base_url}"
            ) from e

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
        params = {"status": "active"}
        if worktree_path:
            params["worktree"] = worktree_path

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/workflows",
                    params=params,
                )

                response.raise_for_status()
                return WorkflowListResponse.model_validate(response.json())

        except httpx.ConnectError as e:
            raise ServerUnreachableError(
                f"Cannot connect to Amelia server at {self.base_url}"
            ) from e

    async def get_workflow(self, workflow_id: str) -> WorkflowResponse:
        """Get details of a specific workflow.

        Args:
            workflow_id: Workflow ID to fetch

        Returns:
            WorkflowResponse with workflow details

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            ServerUnreachableError: If server is not running
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/workflows/{workflow_id}"
                )

                if response.status_code == 404:
                    raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")

                response.raise_for_status()
                return WorkflowResponse.model_validate(response.json())

        except httpx.ConnectError as e:
            raise ServerUnreachableError(
                f"Cannot connect to Amelia server at {self.base_url}"
            ) from e
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
    RateLimitError,
    WorkflowNotFoundError,
    InvalidRequestError,
)

__all__ = [
    "get_worktree_context",
    "AmeliaClient",
    "AmeliaClientError",
    "ServerUnreachableError",
    "WorkflowConflictError",
    "RateLimitError",
    "WorkflowNotFoundError",
    "InvalidRequestError",
]
```

**Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/client/test_api.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/client/api.py amelia/client/models.py amelia/client/__init__.py tests/unit/client/test_api.py
git commit -m "feat(client): add REST API client with error handling"
```

---

## Task 4: Refactor 'amelia start' Command

**Files:**
- Create: `amelia/client/cli.py`
- Modify: `amelia/main.py`

**Step 1: Write the failing test**

```python
# tests/unit/client/test_cli.py
"""Tests for refactored CLI commands."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typer.testing import CliRunner


class TestStartCommand:
    """Tests for 'amelia start' command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_start_command_exists(self, runner):
        """'amelia start' command is registered."""
        from amelia.main import app

        result = runner.invoke(app, ["start", "--help"])
        assert result.exit_code == 0
        assert "Start a workflow for an issue" in result.stdout

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_detects_worktree(self, mock_client_class, mock_worktree, runner):
        """start command auto-detects worktree context."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            issue_id="ISSUE-123",
            status="planning",
            worktree_path="/home/user/repo",
            worktree_name="main",
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
            issue_id="ISSUE-123",
            status="planning",
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
        assert "Cannot connect" in result.stdout or "server" in result.stdout.lower()
        assert "amelia server" in result.stdout

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_start_handles_workflow_conflict(self, mock_client_class, mock_worktree, runner):
        """start command shows active workflow details on conflict."""
        from amelia.main import app
        from amelia.client.api import WorkflowConflictError

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.create_workflow.side_effect = WorkflowConflictError(
            "Workflow already active",
            active_workflow={
                "id": "wf-existing",
                "issue_id": "ISSUE-99",
                "status": "in_progress",
            },
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 1
        assert "already active" in result.stdout.lower()
        assert "ISSUE-99" in result.stdout
        assert "amelia cancel" in result.stdout

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
            issue_id="ISSUE-123",
            status="planning",
            worktree_path="/home/user/repo",
            worktree_name="main",
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["start", "ISSUE-123"])

        assert result.exit_code == 0
        assert "wf-123" in result.stdout
        assert "ISSUE-123" in result.stdout
        assert "planning" in result.stdout.lower()
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
    RateLimitError,
    WorkflowNotFoundError,
    InvalidRequestError,
)


console = Console()


def start_command(
    issue_id: Annotated[str, typer.Argument(help="Issue ID to work on (e.g., ISSUE-123)")],
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Profile name for configuration"),
    ] = None,
) -> None:
    """Start a workflow for an issue.

    Detects the current git worktree and creates a new workflow via the API server.
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
        )

    try:
        workflow = asyncio.run(_create())

        console.print(f"[green]✓[/green] Workflow started: [bold]{workflow.id}[/bold]")
        console.print(f"  Issue: {workflow.issue_id}")
        console.print(f"  Worktree: {workflow.worktree_path}")
        console.print(f"  Status: {workflow.status}")
        console.print("\n[dim]View in dashboard: http://127.0.0.1:8420[/dim]")

    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1)

    except WorkflowConflictError as e:
        console.print(f"[red]Error:[/red] Workflow already active in {worktree_path}")

        if e.active_workflow:
            active = e.active_workflow
            console.print(f"\n  Active workflow: [bold]{active['id']}[/bold] ({active['issue_id']})")
            console.print(f"  Status: {active['status']}")

        console.print("\n[yellow]To start a new workflow:[/yellow]")
        console.print("  - Cancel the existing one: [bold]amelia cancel[/bold]")
        console.print("  - Or use a different worktree: [bold]git worktree add ../project-issue-123[/bold]")
        raise typer.Exit(1)

    except RateLimitError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    except InvalidRequestError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
```

**Step 4: Register start command in main CLI**

Modify `amelia/main.py` to add the start command:

```python
from amelia.client.cli import start_command

# In the main app definition
app.command(name="start")(start_command)
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/client/test_cli.py::TestStartCommand -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/client/cli.py amelia/main.py tests/unit/client/test_cli.py
git commit -m "feat(cli): refactor 'amelia start' to use REST API"
```

---

## Task 5: Implement 'amelia approve' Command

**Files:**
- Modify: `amelia/client/cli.py`
- Modify: `amelia/main.py`
- Modify: `tests/unit/client/test_cli.py`

**Step 1: Write the failing test**

```python
# tests/unit/client/test_cli.py (add to existing file)

class TestApproveCommand:
    """Tests for 'amelia approve' command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_approve_command_exists(self, runner):
        """'amelia approve' command is registered."""
        from amelia.main import app

        result = runner.invoke(app, ["approve", "--help"])
        assert result.exit_code == 0

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_approve_finds_workflow_by_worktree(self, mock_client_class, mock_worktree, runner):
        """approve command finds workflow ID from current worktree."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="blocked",
                    worktree_path="/home/user/repo",
                )
            ],
            total=1,
        )
        mock_client.approve_workflow.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["approve"])

        assert result.exit_code == 0
        mock_client.get_active_workflows.assert_called_once_with(worktree_path="/home/user/repo")
        mock_client.approve_workflow.assert_called_once_with(workflow_id="wf-123")

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_approve_shows_error_when_no_workflow(self, mock_client_class, mock_worktree, runner):
        """approve command shows error when no workflow active."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(workflows=[], total=0)
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["approve"])

        assert result.exit_code == 1
        assert "no workflow" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_approve_shows_error_when_not_blocked(self, mock_client_class, mock_worktree, runner):
        """approve command shows error when workflow not awaiting approval."""
        from amelia.main import app
        from amelia.client.api import InvalidRequestError

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="in_progress",
                    worktree_path="/home/user/repo",
                )
            ],
            total=1,
        )
        mock_client.approve_workflow.side_effect = InvalidRequestError(
            "Workflow is not awaiting approval"
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["approve"])

        assert result.exit_code == 1
        assert "not awaiting approval" in result.stdout.lower()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_approve_shows_success(self, mock_client_class, mock_worktree, runner):
        """approve command shows success message."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="blocked",
                )
            ]
        )
        mock_client.approve_workflow.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["approve"])

        assert result.exit_code == 0
        assert "approved" in result.stdout.lower()
        assert "wf-123" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_cli.py::TestApproveCommand -v`
Expected: FAIL (command not found)

**Step 3: Implement approve command**

Add to `amelia/client/cli.py`:

```python
def approve_command() -> None:
    """Approve the workflow plan in the current worktree.

    Auto-detects the workflow from the current git worktree.
    """
    # Detect worktree context
    try:
        worktree_path, _ = get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Find workflow in this worktree
    client = AmeliaClient()

    async def _approve():
        # Get workflows for this worktree
        result = await client.get_active_workflows(worktree_path=worktree_path)

        if not result.workflows:
            console.print(f"[red]Error:[/red] No workflow active in {worktree_path}")
            console.print("\n[yellow]Start a workflow:[/yellow] amelia start ISSUE-123")
            raise typer.Exit(1)

        workflow = result.workflows[0]

        # Approve it
        try:
            await client.approve_workflow(workflow_id=workflow.id)
            console.print(f"[green]✓[/green] Plan approved for workflow [bold]{workflow.id}[/bold]")
            console.print(f"  Issue: {workflow.issue_id}")
            console.print("\n[dim]Workflow will now continue execution.[/dim]")
        except InvalidRequestError as e:
            console.print(f"[red]Error:[/red] No workflow awaiting approval")
            console.print(f"\n  Current workflow: [bold]{workflow.id}[/bold] ({workflow.issue_id})")
            console.print(f"  Status: {workflow.status} (not blocked)")
            raise typer.Exit(1)

    try:
        asyncio.run(_approve())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1)
```

**Step 4: Register approve command**

Add to `amelia/main.py`:

```python
from amelia.client.cli import start_command, approve_command

app.command(name="approve")(approve_command)
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/client/test_cli.py::TestApproveCommand -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/client/cli.py amelia/main.py tests/unit/client/test_cli.py
git commit -m "feat(cli): add 'amelia approve' command"
```

---

## Task 6: Implement 'amelia reject' Command

**Files:**
- Modify: `amelia/client/cli.py`
- Modify: `amelia/main.py`
- Modify: `tests/unit/client/test_cli.py`

**Step 1: Write the failing test**

```python
# tests/unit/client/test_cli.py (add to existing file)

class TestRejectCommand:
    """Tests for 'amelia reject' command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_reject_command_exists(self, runner):
        """'amelia reject' command is registered."""
        from amelia.main import app

        result = runner.invoke(app, ["reject", "--help"])
        assert result.exit_code == 0

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_reject_with_reason(self, mock_client_class, mock_worktree, runner):
        """reject command sends reason to API."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[MagicMock(id="wf-123", issue_id="ISSUE-123")]
        )
        mock_client.reject_workflow.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["reject", "Not ready yet"])

        assert result.exit_code == 0
        mock_client.reject_workflow.assert_called_once_with(
            workflow_id="wf-123", reason="Not ready yet"
        )

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_reject_shows_error_when_no_workflow(self, mock_client_class, mock_worktree, runner):
        """reject command shows error when no workflow active."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(workflows=[], total=0)
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["reject", "reason"])

        assert result.exit_code == 1
        assert "no workflow" in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_cli.py::TestRejectCommand -v`
Expected: FAIL (command not found)

**Step 3: Implement reject command**

Add to `amelia/client/cli.py`:

```python
def reject_command(
    reason: Annotated[str, typer.Argument(help="Reason for rejecting the plan")],
) -> None:
    """Reject the workflow plan in the current worktree.

    Provide a reason that will be sent to the Architect agent for replanning.
    """
    # Detect worktree context
    try:
        worktree_path, _ = get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Find workflow in this worktree
    client = AmeliaClient()

    async def _reject():
        # Get workflows for this worktree
        result = await client.get_active_workflows(worktree_path=worktree_path)

        if not result.workflows:
            console.print(f"[red]Error:[/red] No workflow active in {worktree_path}")
            console.print("\n[yellow]Start a workflow:[/yellow] amelia start ISSUE-123")
            raise typer.Exit(1)

        workflow = result.workflows[0]

        # Reject it
        try:
            await client.reject_workflow(workflow_id=workflow.id, reason=reason)
            console.print(f"[yellow]✗[/yellow] Plan rejected for workflow [bold]{workflow.id}[/bold]")
            console.print(f"  Reason: {reason}")
            console.print("\n[dim]Architect will replan based on your feedback.[/dim]")
        except InvalidRequestError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    try:
        asyncio.run(_reject())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1)
```

**Step 4: Register reject command**

Add to `amelia/main.py`:

```python
from amelia.client.cli import start_command, approve_command, reject_command

app.command(name="reject")(reject_command)
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/client/test_cli.py::TestRejectCommand -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/client/cli.py amelia/main.py tests/unit/client/test_cli.py
git commit -m "feat(cli): add 'amelia reject' command"
```

---

## Task 7: Implement 'amelia status' Command

**Files:**
- Modify: `amelia/client/cli.py`
- Modify: `amelia/main.py`
- Modify: `tests/unit/client/test_cli.py`

**Step 1: Write the failing test**

```python
# tests/unit/client/test_cli.py (add to existing file)

class TestStatusCommand:
    """Tests for 'amelia status' command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_status_command_exists(self, runner):
        """'amelia status' command is registered."""
        from amelia.main import app

        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_status_shows_current_worktree(self, mock_client_class, mock_worktree, runner):
        """status command shows workflow for current worktree."""
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
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                    started_at=datetime(2025, 12, 1, 10, 0, 0),
                )
            ],
            total=1,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "wf-123" in result.stdout
        assert "ISSUE-123" in result.stdout
        assert "in_progress" in result.stdout

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_status_all_shows_all_worktrees(self, mock_client_class, mock_worktree, runner):
        """status --all shows workflows from all worktrees."""
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
                    worktree_path="/home/user/repo",
                    worktree_name="main",
                    started_at=datetime(2025, 12, 1, 10, 0, 0),
                ),
                MagicMock(
                    id="wf-456",
                    issue_id="ISSUE-456",
                    status="blocked",
                    worktree_path="/home/user/repo2",
                    worktree_name="feature-x",
                    started_at=datetime(2025, 12, 1, 11, 0, 0),
                ),
            ],
            total=2,
        )
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["status", "--all"])

        assert result.exit_code == 0
        mock_client.get_active_workflows.assert_called_once_with(worktree_path=None)
        assert "wf-123" in result.stdout
        assert "wf-456" in result.stdout

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_status_shows_no_workflows_message(self, mock_client_class, mock_worktree, runner):
        """status command shows message when no workflows active."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(workflows=[], total=0)
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "no active" in result.stdout.lower() or "no workflow" in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_cli.py::TestStatusCommand -v`
Expected: FAIL (command not found)

**Step 3: Implement status command**

Add to `amelia/client/cli.py`:

```python
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
    # Detect worktree context (if filtering to current)
    worktree_path = None
    if not all_worktrees:
        try:
            worktree_path, _ = get_worktree_context()
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    # Get workflows via API
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
        table.add_column("Workflow ID", style="cyan", no_wrap=True)
        table.add_column("Issue", style="magenta")
        table.add_column("Status", style="yellow")
        table.add_column("Worktree", style="green")
        table.add_column("Started", style="blue")

        for wf in result.workflows:
            table.add_row(
                wf.id,
                wf.issue_id,
                wf.status,
                wf.worktree_name or wf.worktree_path,
                wf.started_at.strftime("%Y-%m-%d %H:%M"),
            )

        console.print(table)
        console.print(f"\n[dim]Total: {result.total} workflow(s)[/dim]")

    try:
        asyncio.run(_status())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1)
```

**Step 4: Register status command**

Add to `amelia/main.py`:

```python
from amelia.client.cli import start_command, approve_command, reject_command, status_command

app.command(name="status")(status_command)
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/client/test_cli.py::TestStatusCommand -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/client/cli.py amelia/main.py tests/unit/client/test_cli.py
git commit -m "feat(cli): add 'amelia status' command with rich table output"
```

---

## Task 8: Implement 'amelia cancel' Command

**Files:**
- Modify: `amelia/client/cli.py`
- Modify: `amelia/main.py`
- Modify: `tests/unit/client/test_cli.py`

**Step 1: Write the failing test**

```python
# tests/unit/client/test_cli.py (add to existing file)

class TestCancelCommand:
    """Tests for 'amelia cancel' command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_cancel_command_exists(self, runner):
        """'amelia cancel' command is registered."""
        from amelia.main import app

        result = runner.invoke(app, ["cancel", "--help"])
        assert result.exit_code == 0

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_cancel_finds_workflow_by_worktree(self, mock_client_class, mock_worktree, runner):
        """cancel command finds workflow from current worktree."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[MagicMock(id="wf-123", issue_id="ISSUE-123")]
        )
        mock_client.cancel_workflow.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["cancel"], input="y\n")

        assert result.exit_code == 0
        mock_client.cancel_workflow.assert_called_once_with(workflow_id="wf-123")

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_cancel_requires_confirmation(self, mock_client_class, mock_worktree, runner):
        """cancel command requires user confirmation."""
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

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_cancel_force_skips_confirmation(self, mock_client_class, mock_worktree, runner):
        """cancel --force skips confirmation prompt."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[MagicMock(id="wf-123", issue_id="ISSUE-123")]
        )
        mock_client.cancel_workflow.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["cancel", "--force"])

        assert result.exit_code == 0
        mock_client.cancel_workflow.assert_called_once()

    @patch("amelia.client.cli.get_worktree_context")
    @patch("amelia.client.cli.AmeliaClient")
    def test_cancel_shows_error_when_no_workflow(self, mock_client_class, mock_worktree, runner):
        """cancel command shows error when no workflow active."""
        from amelia.main import app

        mock_worktree.return_value = ("/home/user/repo", "main")

        mock_client = AsyncMock()
        mock_client.get_active_workflows.return_value = MagicMock(workflows=[], total=0)
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["cancel"])

        assert result.exit_code == 1
        assert "no workflow" in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_cli.py::TestCancelCommand -v`
Expected: FAIL (command not found)

**Step 3: Implement cancel command**

Add to `amelia/client/cli.py`:

```python
def cancel_command(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Cancel the active workflow in the current worktree.

    Requires confirmation unless --force is used.
    """
    # Detect worktree context
    try:
        worktree_path, _ = get_worktree_context()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Find workflow in this worktree
    client = AmeliaClient()

    async def _cancel():
        # Get workflows for this worktree
        result = await client.get_active_workflows(worktree_path=worktree_path)

        if not result.workflows:
            console.print(f"[red]Error:[/red] No workflow active in {worktree_path}")
            raise typer.Exit(1)

        workflow = result.workflows[0]

        # Confirm cancellation
        if not force:
            console.print(f"Cancel workflow [bold]{workflow.id}[/bold] ({workflow.issue_id})?")
            confirm = typer.confirm("Are you sure?")
            if not confirm:
                console.print("[yellow]Cancelled.[/yellow]")
                raise typer.Exit(1)

        # Cancel it
        await client.cancel_workflow(workflow_id=workflow.id)
        console.print(f"[yellow]✗[/yellow] Workflow [bold]{workflow.id}[/bold] cancelled")

    try:
        asyncio.run(_cancel())
    except ServerUnreachableError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]Start the server:[/yellow] amelia server")
        raise typer.Exit(1)
```

**Step 4: Register cancel command**

Add to `amelia/main.py`:

```python
from amelia.client.cli import (
    start_command,
    approve_command,
    reject_command,
    status_command,
    cancel_command,
)

app.command(name="cancel")(cancel_command)
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/client/test_cli.py::TestCancelCommand -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/client/cli.py amelia/main.py tests/unit/client/test_cli.py
git commit -m "feat(cli): add 'amelia cancel' command with confirmation"
```

---

## Task 9: Integration Tests - End-to-End CLI Flows

**Files:**
- Create: `tests/integration/test_cli_flows.py`

**Step 1: Write integration tests**

```python
# tests/integration/test_cli_flows.py
"""Integration tests for CLI command flows."""
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from typer.testing import CliRunner


class TestCLIFlows:
    """Integration tests for full CLI workflows."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_git_repo(self, tmp_path):
        """Create a temporary git repository."""
        import subprocess

        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        # Initialize git repo
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
        from datetime import datetime

        mock_client = AsyncMock()

        # Mock start workflow response
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            issue_id="ISSUE-123",
            status="planning",
            worktree_path=str(mock_git_repo),
            worktree_name="main",
            started_at=datetime.utcnow(),
        )

        # Mock get workflows for approve
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="blocked",
                    worktree_path=str(mock_git_repo),
                )
            ]
        )
        mock_client.approve_workflow.return_value = None

        mock_client_class.return_value = mock_client

        # Start workflow
        with patch("os.getcwd", return_value=str(mock_git_repo)):
            result = runner.invoke(app, ["start", "ISSUE-123"])
            assert result.exit_code == 0
            assert "wf-123" in result.stdout

            # Approve workflow
            result = runner.invoke(app, ["approve"])
            assert result.exit_code == 0
            assert "approved" in result.stdout.lower()

    @patch("amelia.client.cli.AmeliaClient")
    def test_start_reject_flow(self, mock_client_class, runner, mock_git_repo):
        """Test start -> reject flow."""
        from amelia.main import app
        from datetime import datetime

        mock_client = AsyncMock()

        # Mock start workflow response
        mock_client.create_workflow.return_value = MagicMock(
            id="wf-123",
            issue_id="ISSUE-123",
            status="planning",
            worktree_path=str(mock_git_repo),
            worktree_name="main",
            started_at=datetime.utcnow(),
        )

        # Mock get workflows for reject
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="blocked",
                )
            ]
        )
        mock_client.reject_workflow.return_value = None

        mock_client_class.return_value = mock_client

        # Start workflow
        with patch("os.getcwd", return_value=str(mock_git_repo)):
            result = runner.invoke(app, ["start", "ISSUE-123"])
            assert result.exit_code == 0

            # Reject workflow
            result = runner.invoke(app, ["reject", "Not ready"])
            assert result.exit_code == 0
            assert "rejected" in result.stdout.lower()

    @patch("amelia.client.cli.AmeliaClient")
    def test_status_cancel_flow(self, mock_client_class, runner, mock_git_repo):
        """Test status -> cancel flow."""
        from amelia.main import app
        from datetime import datetime

        mock_client = AsyncMock()

        # Mock get workflows
        mock_client.get_active_workflows.return_value = MagicMock(
            workflows=[
                MagicMock(
                    id="wf-123",
                    issue_id="ISSUE-123",
                    status="in_progress",
                    worktree_path=str(mock_git_repo),
                    worktree_name="main",
                    started_at=datetime(2025, 12, 1, 10, 0, 0),
                )
            ],
            total=1,
        )
        mock_client.cancel_workflow.return_value = None

        mock_client_class.return_value = mock_client

        # Check status
        with patch("os.getcwd", return_value=str(mock_git_repo)):
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            assert "wf-123" in result.stdout

            # Cancel with force
            result = runner.invoke(app, ["cancel", "--force"])
            assert result.exit_code == 0
            assert "cancelled" in result.stdout.lower()

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
            assert "git repository" in result.stdout.lower()

            # reject
            result = runner.invoke(app, ["reject", "reason"])
            assert result.exit_code == 1
            assert "git repository" in result.stdout.lower()

            # cancel
            result = runner.invoke(app, ["cancel"])
            assert result.exit_code == 1
            assert "git repository" in result.stdout.lower()
```

**Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_cli_flows.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_cli_flows.py
git commit -m "test(cli): add integration tests for CLI command flows"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] `uv run pytest tests/unit/client/ -v` - All unit tests pass
- [ ] `uv run pytest tests/integration/test_cli_flows.py -v` - Integration tests pass
- [ ] `uv run ruff check amelia/client` - No linting errors
- [ ] `uv run mypy amelia/client` - No type errors
- [ ] `uv run amelia start --help` - Shows help text
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
- [ ] Error handling:
  - [ ] `uv run amelia start ISSUE-123` (when workflow active) - Shows conflict error
  - [ ] `cd /tmp && uv run amelia start ISSUE-123` - Shows git repo error
  - [ ] Stop server, then `uv run amelia start ISSUE-123` - Shows server unreachable error

---

## Summary

This plan refactors the CLI into a thin client that delegates all workflow orchestration to the FastAPI server:

| Component | File | Purpose |
|-----------|------|---------|
| Dependencies | `pyproject.toml` | httpx, rich for HTTP and formatting |
| Git Utils | `amelia/client/git.py` | Worktree context detection with edge cases |
| Models | `amelia/client/models.py` | Pydantic request/response models |
| API Client | `amelia/client/api.py` | httpx-based REST client with error handling |
| CLI Commands | `amelia/client/cli.py` | Thin client commands delegating to API |
| Integration | `amelia/main.py` | Register commands in main Typer app |

**Key Features:**
- Auto-detection of workflow ID from current git worktree
- Rich error messages with actionable suggestions
- Edge case handling: detached HEAD, bare repo, submodules
- User-friendly status display with rich tables
- Confirmation prompts for destructive operations
- Clear connection error messages when server is down

**Next PR:** WebSocket Event Stream Client (Plan 8)
