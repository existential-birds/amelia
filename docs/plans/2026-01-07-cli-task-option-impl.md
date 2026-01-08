# CLI Task Option Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `--title` and `--description` CLI flags to enable ad-hoc tasks with the noop tracker, bypassing issue lookup.

**Architecture:** Flags pass through CLI → API client → server request model → orchestrator, where noop tracker with task_title constructs Issue directly instead of calling tracker.get_issue().

**Tech Stack:** Typer (CLI), Pydantic (models), httpx (API client), pytest (testing)

---

## Task 1: Add task_title/task_description to Server Request Model

**Files:**
- Modify: `amelia/server/models/requests.py:67-107` (CreateWorkflowRequest)
- Test: `tests/unit/server/models/test_requests.py`

**Step 1: Write failing test for task_description without task_title**

```python
# Add to tests/unit/server/models/test_requests.py

def test_task_description_without_title_rejected():
    """task_description without task_title is rejected."""
    with pytest.raises(ValidationError):
        CreateWorkflowRequest(
            issue_id="TASK-1",
            worktree_path="/absolute/path",
            task_description="Some description without title",
        )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_requests.py::test_task_description_without_title_rejected -v`
Expected: FAIL with "CreateWorkflowRequest object has no attribute 'task_description'"

**Step 3: Write failing test for valid task fields**

```python
# Add to tests/unit/server/models/test_requests.py

def test_task_fields_valid():
    """task_title and task_description are accepted together."""
    req = CreateWorkflowRequest(
        issue_id="TASK-1",
        worktree_path="/absolute/path",
        task_title="Add logout button",
        task_description="Add to navbar with confirmation",
    )
    assert req.task_title == "Add logout button"
    assert req.task_description == "Add to navbar with confirmation"


def test_task_title_only_valid():
    """task_title alone is valid (description defaults to None)."""
    req = CreateWorkflowRequest(
        issue_id="TASK-1",
        worktree_path="/absolute/path",
        task_title="Fix typo in README",
    )
    assert req.task_title == "Fix typo in README"
    assert req.task_description is None
```

**Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/models/test_requests.py::test_task_fields_valid tests/unit/server/models/test_requests.py::test_task_title_only_valid -v`
Expected: FAIL with field not found errors

**Step 5: Add task_title and task_description fields to CreateWorkflowRequest**

```python
# In amelia/server/models/requests.py, add to CreateWorkflowRequest class after driver field (around line 107):

    task_title: Annotated[
        str | None,
        Field(
            default=None,
            max_length=500,
            description="Task title for noop tracker (bypasses issue lookup)",
        ),
    ] = None
    task_description: Annotated[
        str | None,
        Field(
            default=None,
            max_length=5000,
            description="Task description for noop tracker (requires task_title)",
        ),
    ] = None

    @model_validator(mode="after")
    def validate_task_fields(self) -> "CreateWorkflowRequest":
        """Validate task_description requires task_title."""
        if self.task_description is not None and self.task_title is None:
            raise ValueError("task_description requires task_title")
        return self
```

Note: Also add `from pydantic import model_validator` to imports at top of file.

**Step 6: Run all tests to verify they pass**

Run: `uv run pytest tests/unit/server/models/test_requests.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/server/models/requests.py tests/unit/server/models/test_requests.py
git commit -m "$(cat <<'EOF'
feat(api): add task_title/task_description to CreateWorkflowRequest

Add optional fields for specifying task details directly, bypassing
issue tracker lookup. task_description requires task_title to be set.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add task_title/task_description to Client API Method

**Files:**
- Modify: `amelia/client/models.py:7-21` (CreateWorkflowRequest)
- Modify: `amelia/client/api.py:141-184` (create_workflow method)

**Step 1: Add fields to client-side CreateWorkflowRequest model**

```python
# In amelia/client/models.py, add to CreateWorkflowRequest class:

    task_title: str | None = Field(default=None, max_length=500)
    task_description: str | None = Field(default=None, max_length=5000)
```

**Step 2: Update create_workflow method signature**

```python
# In amelia/client/api.py, update create_workflow method (around line 141):

    async def create_workflow(
        self,
        issue_id: str,
        worktree_path: str,
        worktree_name: str | None = None,
        profile: str | None = None,
        task_title: str | None = None,
        task_description: str | None = None,
    ) -> CreateWorkflowResponse:
        """Create a new workflow.

        Args:
            issue_id: Issue identifier (e.g., "ISSUE-123")
            worktree_path: Absolute path to git worktree
            worktree_name: Human-readable name for worktree
            profile: Optional profile name for configuration
            task_title: Optional task title for noop tracker (bypasses issue lookup)
            task_description: Optional task description (requires task_title)

        Returns:
            CreateWorkflowResponse with workflow id and initial status

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
            task_title=task_title,
            task_description=task_description,
        )
        # ... rest of method unchanged
```

**Step 3: Run type checking**

Run: `uv run mypy amelia/client/api.py amelia/client/models.py`
Expected: PASS

**Step 4: Commit**

```bash
git add amelia/client/api.py amelia/client/models.py
git commit -m "$(cat <<'EOF'
feat(client): add task_title/task_description to API client

Pass task fields through to server for noop tracker workflows.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add --title/--description to CLI start_command

**Files:**
- Modify: `amelia/client/cli.py:90-129` (start_command)
- Test: Create new test file `tests/unit/client/test_cli_start.py`

**Step 1: Write failing test for --description without --title**

```python
# Create tests/unit/client/test_cli_start.py

"""Tests for CLI start command."""
import pytest
from typer.testing import CliRunner

from amelia.main import app


class TestStartCommandTaskFlags:
    """Tests for --title and --description flags on start command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_description_without_title_errors(self, runner):
        """--description without --title should error at client side."""
        result = runner.invoke(
            app,
            ["start", "TASK-1", "--description", "Some description"],
        )
        assert result.exit_code != 0
        assert "requires" in result.stdout.lower() or "title" in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_cli_start.py::TestStartCommandTaskFlags::test_description_without_title_errors -v`
Expected: FAIL (option not recognized)

**Step 3: Write failing test for valid --title flag**

```python
# Add to tests/unit/client/test_cli_start.py
from unittest.mock import patch, AsyncMock

    def test_title_flag_passed_to_client(self, runner, tmp_path):
        """--title should be passed to API client."""
        # Create mock git worktree
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").touch()

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(worktree), "repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(return_value=MagicMock(
                id="wf-123", status="pending"
            ))

            result = runner.invoke(
                app,
                ["start", "TASK-1", "-p", "noop", "--title", "Add logout button"],
            )

            # Verify create_workflow was called with task_title
            mock_client.create_workflow.assert_called_once()
            call_kwargs = mock_client.create_workflow.call_args.kwargs
            assert call_kwargs.get("task_title") == "Add logout button"
```

Also add `from unittest.mock import MagicMock` to imports.

**Step 4: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_cli_start.py::TestStartCommandTaskFlags::test_title_flag_passed_to_client -v`
Expected: FAIL (option not recognized)

**Step 5: Add --title and --description options to start_command**

```python
# In amelia/client/cli.py, update start_command signature (around line 90):

def start_command(
    issue_id: Annotated[str, typer.Argument(help="Issue ID to work on (e.g., ISSUE-123)")],
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Profile name for configuration"),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option("--title", help="Task title for noop tracker (bypasses issue lookup)"),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option("--description", help="Task description (requires --title)"),
    ] = None,
) -> None:
    """Start a new workflow for an issue in the current worktree.

    Detects the current git worktree context and creates a new workflow
    via the Amelia API server. Displays workflow details and dashboard URL.

    Args:
        issue_id: Issue identifier to work on (e.g., ISSUE-123).
        profile: Optional profile name for driver and tracker configuration.
        title: Optional task title for noop tracker (bypasses issue lookup).
        description: Optional task description (requires --title).
    """
    # Client-side validation: --description requires --title
    if description is not None and title is None:
        console.print("[red]Error:[/red] --description requires --title")
        raise typer.Exit(1)

    worktree_path, worktree_name = _get_worktree_context()

    client = AmeliaClient()

    async def _create() -> CreateWorkflowResponse:
        return await client.create_workflow(
            issue_id=issue_id,
            worktree_path=worktree_path,
            worktree_name=worktree_name,
            profile=profile,
            task_title=title,
            task_description=description,
        )

    # ... rest of function unchanged
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/client/test_cli_start.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add amelia/client/cli.py tests/unit/client/test_cli_start.py
git commit -m "$(cat <<'EOF'
feat(cli): add --title and --description flags to start command

Enable ad-hoc tasks with noop tracker by specifying task details
directly. --description requires --title to be set.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add --title/--description to CLI plan_command

**Files:**
- Modify: `amelia/client/cli.py:357-434` (plan_command)
- Test: Add to `tests/unit/client/test_cli_start.py`

**Step 1: Write failing test for plan command with --title**

```python
# Add to tests/unit/client/test_cli_start.py

class TestPlanCommandTaskFlags:
    """Tests for --title and --description flags on plan command."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    def test_description_without_title_errors(self, runner):
        """--description without --title should error at client side."""
        result = runner.invoke(
            app,
            ["plan", "TASK-1", "--description", "Some description"],
        )
        assert result.exit_code != 0
        assert "requires" in result.stdout.lower() or "title" in result.stdout.lower()

    def test_title_flag_constructs_issue_directly(self, runner, tmp_path):
        """--title should construct Issue directly, bypassing tracker."""
        # Create mock git worktree with settings
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").touch()
        settings_content = """
active_profile: noop
profiles:
  noop:
    name: noop
    driver: cli:claude
    model: sonnet
    tracker: noop
    strategy: single
"""
        (worktree / "settings.amelia.yaml").write_text(settings_content)

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.Architect") as mock_architect_class, \
             patch("amelia.client.cli.DriverFactory") as mock_driver_factory, \
             patch("amelia.client.cli.create_tracker") as mock_create_tracker:
            mock_ctx.return_value = (str(worktree), "repo")

            # Mock architect to capture the state
            mock_architect = mock_architect_class.return_value
            captured_state = None

            async def capture_plan(*args, **kwargs):
                nonlocal captured_state
                captured_state = kwargs.get("state") or args[0]
                # Yield a final state
                final_state = captured_state.model_copy(update={"plan_path": "/tmp/plan.md"})
                yield final_state, None

            mock_architect.plan = capture_plan

            result = runner.invoke(
                app,
                ["plan", "TASK-1", "-p", "noop", "--title", "Fix typo", "--description", "Fix README"],
            )

            # Tracker should NOT be called when --title is provided with noop
            mock_create_tracker.assert_not_called()

            # State should have our custom issue
            assert captured_state is not None
            assert captured_state.issue.title == "Fix typo"
            assert captured_state.issue.description == "Fix README"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/client/test_cli_start.py::TestPlanCommandTaskFlags -v`
Expected: FAIL (option not recognized or tracker still called)

**Step 3: Update plan_command to support --title/--description**

```python
# In amelia/client/cli.py, update plan_command signature (around line 357):

def plan_command(
    issue_id: Annotated[str, typer.Argument(help="Issue ID to generate a plan for (e.g., ISSUE-123)")],
    profile_name: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Profile name for configuration"),
    ] = None,
    title: Annotated[
        str | None,
        typer.Option("--title", help="Task title for noop tracker (bypasses issue lookup)"),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option("--description", help="Task description (requires --title)"),
    ] = None,
) -> None:
    """Generate an implementation plan for an issue without executing it.

    Creates a markdown implementation plan in docs/plans/ that can be
    reviewed before execution. Calls the Architect directly without
    going through the full LangGraph orchestration.

    Args:
        issue_id: Issue identifier to generate a plan for (e.g., ISSUE-123).
        profile_name: Optional profile name for driver and tracker configuration.
        title: Optional task title for noop tracker (bypasses issue lookup).
        description: Optional task description (requires --title).
    """
    # Client-side validation: --description requires --title
    if description is not None and title is None:
        console.print("[red]Error:[/red] --description requires --title")
        raise typer.Exit(1)

    worktree_path, _worktree_name = _get_worktree_context()

    async def _generate_plan() -> ExecutionState:
        # Load settings from worktree
        settings_path = Path(worktree_path) / "settings.amelia.yaml"
        settings = load_settings(settings_path)

        # Get profile (use specified or active profile)
        selected_profile = profile_name or settings.active_profile
        if selected_profile not in settings.profiles:
            raise ValueError(f"Profile '{selected_profile}' not found in settings")
        profile = settings.profiles[selected_profile]

        # Update profile with worktree path
        profile = profile.model_copy(update={"working_dir": worktree_path})

        # Construct issue: use --title if provided with noop tracker, else use tracker
        if title is not None:
            if profile.tracker not in ("noop", "none"):
                raise ValueError(
                    f"--title/--description requires noop tracker, not '{profile.tracker}'"
                )
            issue = Issue(
                id=issue_id,
                title=title,
                description=description or title,
            )
        else:
            # Fetch issue using tracker
            tracker = create_tracker(profile)
            issue = tracker.get_issue(issue_id, cwd=worktree_path)

        # Create minimal execution state
        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
        )

        # Create driver and architect
        driver = DriverFactory.get_driver(profile.driver, model=profile.model)
        architect = Architect(driver)

        # Generate plan by consuming the async generator
        final_state = state
        async for new_state, _event in architect.plan(
            state=state,
            profile=profile,
            workflow_id=f"plan-{issue_id}",
        ):
            final_state = new_state

        return final_state

    # ... rest of function unchanged
```

Also add `from amelia.core.types import Issue` to imports if not present.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/client/test_cli_start.py::TestPlanCommandTaskFlags -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/client/cli.py tests/unit/client/test_cli_start.py
git commit -m "$(cat <<'EOF'
feat(cli): add --title and --description flags to plan command

Enable local planning for ad-hoc tasks without issue tracker lookup.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add Issue Construction Logic to Orchestrator

**Files:**
- Modify: `amelia/server/orchestrator/service.py:362-516` (start_workflow method)
- Test: `tests/unit/server/orchestrator/test_service.py`

**Step 1: Write failing test for noop tracker with task_title**

```python
# Add to tests/unit/server/orchestrator/test_service.py

class TestStartWorkflowWithTaskFields:
    """Tests for start_workflow with task_title/task_description."""

    async def test_noop_tracker_with_task_title_constructs_issue(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """start_workflow with task_title and noop tracker constructs Issue directly."""
        # Create valid worktree with noop tracker settings
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").touch()
        settings_content = """
active_profile: noop
profiles:
  noop:
    name: noop
    driver: cli:claude
    model: sonnet
    tracker: noop
    strategy: single
"""
        (worktree / "settings.amelia.yaml").write_text(settings_content)

        with patch.object(orchestrator, "_run_workflow_with_retry", new=AsyncMock()):
            workflow_id = await orchestrator.start_workflow(
                issue_id="TASK-1",
                worktree_path=str(worktree),
                task_title="Add logout button",
                task_description="Add to navbar with confirmation",
            )

            assert workflow_id is not None

            # Verify the execution state has our custom issue
            call_args = mock_repository.create.call_args
            state = call_args[0][0]
            assert state.execution_state.issue.title == "Add logout button"
            assert state.execution_state.issue.description == "Add to navbar with confirmation"

    async def test_task_title_with_non_noop_tracker_errors(
        self,
        orchestrator: OrchestratorService,
        tmp_path: Path,
    ) -> None:
        """start_workflow with task_title and non-noop tracker should error."""
        # Create valid worktree with github tracker settings
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").touch()
        settings_content = """
active_profile: github
profiles:
  github:
    name: github
    driver: cli:claude
    model: sonnet
    tracker: github
    strategy: single
"""
        (worktree / "settings.amelia.yaml").write_text(settings_content)

        with pytest.raises(ValueError) as exc_info:
            await orchestrator.start_workflow(
                issue_id="TASK-1",
                worktree_path=str(worktree),
                task_title="Add logout button",
            )

        assert "noop" in str(exc_info.value).lower()
        assert "tracker" in str(exc_info.value).lower()

    async def test_task_title_defaults_description_to_title(
        self,
        orchestrator: OrchestratorService,
        mock_repository: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """task_description defaults to task_title when not provided."""
        # Create valid worktree with noop tracker
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").touch()
        settings_content = """
active_profile: noop
profiles:
  noop:
    name: noop
    driver: cli:claude
    model: sonnet
    tracker: noop
    strategy: single
"""
        (worktree / "settings.amelia.yaml").write_text(settings_content)

        with patch.object(orchestrator, "_run_workflow_with_retry", new=AsyncMock()):
            await orchestrator.start_workflow(
                issue_id="TASK-1",
                worktree_path=str(worktree),
                task_title="Fix typo in README",
                # No task_description provided
            )

            call_args = mock_repository.create.call_args
            state = call_args[0][0]
            # Description should default to title
            assert state.execution_state.issue.description == "Fix typo in README"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py::TestStartWorkflowWithTaskFields -v`
Expected: FAIL (start_workflow doesn't accept task_title parameter)

**Step 3: Update start_workflow method signature and logic**

```python
# In amelia/server/orchestrator/service.py, update start_workflow (around line 362):

    async def start_workflow(
        self,
        issue_id: str,
        worktree_path: str,
        worktree_name: str | None = None,
        profile: str | None = None,
        driver: str | None = None,
        task_title: str | None = None,
        task_description: str | None = None,
    ) -> str:
        """Start a new workflow.

        Args:
            issue_id: The issue ID to work on.
            worktree_path: Absolute path to the worktree.
            worktree_name: Human-readable worktree name (optional).
            profile: Optional profile name.
            driver: Optional driver override.
            task_title: Optional task title for noop tracker (bypasses issue lookup).
            task_description: Optional task description (requires task_title).

        Returns:
            The workflow ID (UUID).

        Raises:
            InvalidWorktreeError: If worktree path doesn't exist or is not a git repo.
            WorkflowConflictError: If worktree already has active workflow.
            ConcurrencyLimitError: If at max concurrent workflows.
            ValueError: If task_title used with non-noop tracker.
        """
```

Then in the method body, after loading the profile (around line 428), replace the tracker.get_issue call:

```python
            # ... existing code to load profile ...

            # Construct issue: use task_title if provided with noop tracker, else use tracker
            if task_title is not None:
                if loaded_profile.tracker not in ("noop", "none"):
                    raise ValueError(
                        f"--title/--description requires noop tracker, not '{loaded_profile.tracker}'"
                    )
                issue = Issue(
                    id=issue_id,
                    title=task_title,
                    description=task_description or task_title,
                )
            else:
                # Fetch issue from tracker (pass worktree_path so gh CLI uses correct repo)
                tracker = create_tracker(loaded_profile)
                issue = tracker.get_issue(issue_id, cwd=worktree_path)

            # ... rest of method unchanged, using 'issue' variable ...
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py::TestStartWorkflowWithTaskFields -v`
Expected: PASS

**Step 5: Run full orchestrator test suite**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/orchestrator/test_service.py
git commit -m "$(cat <<'EOF'
feat(orchestrator): construct Issue from task_title with noop tracker

When task_title is provided with noop tracker, construct Issue directly
instead of calling tracker.get_issue(). Returns 400 error if used with
non-noop tracker.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Wire up Server API Endpoint

**Files:**
- Modify: `amelia/server/routes/workflows.py` (find create_workflow endpoint)

**Step 1: Find and read the workflows routes file**

Run: `uv run grep -r "create_workflow" amelia/server/routes/`
Then read the file to understand the current endpoint structure.

**Step 2: Update endpoint to pass task fields to orchestrator**

The endpoint should already receive `CreateWorkflowRequest` from the request model. We need to pass the new fields through to `orchestrator.start_workflow()`:

```python
# In the create_workflow endpoint, update the call to orchestrator.start_workflow:

    workflow_id = await orchestrator.start_workflow(
        issue_id=request.issue_id,
        worktree_path=request.worktree_path,
        worktree_name=request.worktree_name,
        profile=request.profile,
        driver=request.driver,
        task_title=request.task_title,
        task_description=request.task_description,
    )
```

**Step 3: Run type checking**

Run: `uv run mypy amelia/server/routes/`
Expected: PASS

**Step 4: Commit**

```bash
git add amelia/server/routes/workflows.py
git commit -m "$(cat <<'EOF'
feat(api): pass task_title/task_description through to orchestrator

Wire up the REST endpoint to forward task fields to start_workflow.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Integration Tests

**Files:**
- Test: `tests/integration/test_cli_task_option.py` (new file)

**Step 1: Write integration test for full flow**

```python
# Create tests/integration/test_cli_task_option.py

"""Integration tests for CLI task option (--title/--description)."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from amelia.main import app


class TestCliTaskOptionIntegration:
    """Integration tests for --title/--description CLI flow."""

    @pytest.fixture
    def runner(self):
        """Typer CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def noop_worktree(self, tmp_path: Path) -> Path:
        """Create a worktree with noop tracker settings."""
        worktree = tmp_path / "noop-repo"
        worktree.mkdir()
        (worktree / ".git").touch()
        settings_content = """
active_profile: noop
profiles:
  noop:
    name: noop
    driver: cli:claude
    model: sonnet
    tracker: noop
    strategy: single
"""
        (worktree / "settings.amelia.yaml").write_text(settings_content)
        return worktree

    @pytest.fixture
    def github_worktree(self, tmp_path: Path) -> Path:
        """Create a worktree with github tracker settings."""
        worktree = tmp_path / "github-repo"
        worktree.mkdir()
        (worktree / ".git").touch()
        settings_content = """
active_profile: github
profiles:
  github:
    name: github
    driver: cli:claude
    model: sonnet
    tracker: github
    strategy: single
"""
        (worktree / "settings.amelia.yaml").write_text(settings_content)
        return worktree

    def test_start_with_title_noop_tracker_succeeds(
        self,
        runner: CliRunner,
        noop_worktree: Path,
    ) -> None:
        """start with --title and noop tracker should succeed."""
        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(noop_worktree), "noop-repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(return_value=type(
                "Response", (), {"id": "wf-123", "status": "pending"}
            )())

            result = runner.invoke(
                app,
                [
                    "start", "TASK-1",
                    "-p", "noop",
                    "--title", "Add logout button",
                    "--description", "Add to navbar",
                ],
            )

            assert result.exit_code == 0
            assert "wf-123" in result.stdout

            # Verify task fields were passed
            call_kwargs = mock_client.create_workflow.call_args.kwargs
            assert call_kwargs["task_title"] == "Add logout button"
            assert call_kwargs["task_description"] == "Add to navbar"

    def test_start_with_title_non_noop_tracker_returns_400(
        self,
        runner: CliRunner,
        github_worktree: Path,
    ) -> None:
        """start with --title and github tracker should return 400 error."""
        from amelia.client.api import InvalidRequestError

        with patch("amelia.client.cli.get_worktree_context") as mock_ctx, \
             patch("amelia.client.cli.AmeliaClient") as mock_client_class:
            mock_ctx.return_value = (str(github_worktree), "github-repo")
            mock_client = mock_client_class.return_value
            mock_client.create_workflow = AsyncMock(
                side_effect=InvalidRequestError("--title requires noop tracker")
            )

            result = runner.invoke(
                app,
                [
                    "start", "TASK-1",
                    "-p", "github",
                    "--title", "Add logout button",
                ],
            )

            assert result.exit_code == 1
            assert "noop" in result.stdout.lower() or "error" in result.stdout.lower()
```

**Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_cli_task_option.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_cli_task_option.py
git commit -m "$(cat <<'EOF'
test: add integration tests for CLI task option

Verify end-to-end flow for --title/--description with both noop
and non-noop trackers.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Final Verification

**Step 1: Run full test suite**

Run: `uv run pytest`
Expected: PASS

**Step 2: Run type checking**

Run: `uv run mypy amelia`
Expected: PASS

**Step 3: Run linting**

Run: `uv run ruff check amelia tests`
Expected: PASS (or fix any issues)

**Step 4: Update design doc status**

```markdown
# In docs/plans/2026-01-07-cli-task-option-design.md, update status:
**Status:** Implemented
```

**Step 5: Final commit**

```bash
git add docs/plans/2026-01-07-cli-task-option-design.md
git commit -m "$(cat <<'EOF'
docs: mark CLI task option design as implemented

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary of Files Changed

| File | Change |
|------|--------|
| `amelia/server/models/requests.py` | Add `task_title`/`task_description` fields with validation |
| `amelia/client/models.py` | Add `task_title`/`task_description` fields |
| `amelia/client/api.py` | Add params to `create_workflow()` |
| `amelia/client/cli.py` | Add `--title`/`--description` to `start_command` and `plan_command` |
| `amelia/server/orchestrator/service.py` | Add Issue construction logic in `start_workflow()` |
| `amelia/server/routes/workflows.py` | Pass task fields to orchestrator |
| `tests/unit/server/models/test_requests.py` | Add validation tests |
| `tests/unit/client/test_cli_start.py` | Add CLI flag tests (new file) |
| `tests/unit/server/orchestrator/test_service.py` | Add orchestrator tests |
| `tests/integration/test_cli_task_option.py` | Add integration tests (new file) |
