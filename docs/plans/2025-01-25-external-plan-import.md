# External Plan Import Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable users to provide pre-written implementation plans that bypass the Architect phase while going through the same validation as Architect-generated plans.

**Architecture:** Add `plan_file`/`plan_content` fields to workflow creation, a new `POST /plan` endpoint for queued workflows, and conditional routing in the LangGraph pipeline to skip Architect when an external plan is provided. The existing `plan_validator_node` validates all plans regardless of source.

**Tech Stack:** Python 3.12+, Pydantic models, FastAPI, LangGraph, pytest-asyncio

---

## Task 1: Add `external_plan` Field to ImplementationState

**Files:**
- Modify: `amelia/pipelines/implementation/state.py:24-74`
- Test: `tests/unit/pipelines/test_implementation_state.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/pipelines/test_implementation_state.py`:

```python
"""Unit tests for ImplementationState."""

from datetime import UTC, datetime

from amelia.pipelines.implementation.state import ImplementationState


class TestExternalPlanField:
    """Tests for external_plan field on ImplementationState."""

    def test_external_plan_defaults_to_false(self) -> None:
        """external_plan should default to False."""
        state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
        )
        assert state.external_plan is False

    def test_external_plan_can_be_set_to_true(self) -> None:
        """external_plan can be explicitly set to True."""
        state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
            external_plan=True,
        )
        assert state.external_plan is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_implementation_state.py -v`
Expected: FAIL with "unexpected keyword argument 'external_plan'"

**Step 3: Write minimal implementation**

Add field to `ImplementationState` in `amelia/pipelines/implementation/state.py` after line 72 (after `max_review_passes`):

```python
    # External plan tracking
    external_plan: bool = False
    """True if plan was imported externally (bypasses Architect)."""
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/test_implementation_state.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/state.py tests/unit/pipelines/test_implementation_state.py
git commit -m "feat(state): add external_plan field to ImplementationState"
```

---

## Task 2: Add `route_after_start` Routing Function

**Files:**
- Modify: `amelia/pipelines/implementation/routing.py`
- Test: `tests/unit/pipelines/test_routing.py` (create or add)

**Step 1: Write the failing test**

Create or add to `tests/unit/pipelines/test_routing.py`:

```python
"""Unit tests for pipeline routing functions."""

from datetime import UTC, datetime

import pytest

from amelia.pipelines.implementation.routing import route_after_start
from amelia.pipelines.implementation.state import ImplementationState


class TestRouteAfterStart:
    """Tests for route_after_start routing function."""

    def test_routes_to_architect_when_not_external_plan(self) -> None:
        """Should route to architect when external_plan is False."""
        state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
            external_plan=False,
        )
        assert route_after_start(state) == "architect"

    def test_routes_to_plan_validator_when_external_plan(self) -> None:
        """Should route to plan_validator when external_plan is True."""
        state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
            external_plan=True,
        )
        assert route_after_start(state) == "plan_validator"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_routing.py::TestRouteAfterStart -v`
Expected: FAIL with "cannot import name 'route_after_start'"

**Step 3: Write minimal implementation**

Add to `amelia/pipelines/implementation/routing.py`:

```python
from typing import Literal

from amelia.pipelines.implementation.state import ImplementationState


def route_after_start(state: ImplementationState) -> Literal["architect", "plan_validator"]:
    """Route to architect or directly to validator based on external plan flag.

    Args:
        state: Current execution state with external_plan flag.

    Returns:
        'architect' if plan needs to be generated.
        'plan_validator' if external plan was provided.
    """
    if state.external_plan:
        return "plan_validator"
    return "architect"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/test_routing.py::TestRouteAfterStart -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/routing.py tests/unit/pipelines/test_routing.py
git commit -m "feat(routing): add route_after_start for external plan bypass"
```

---

## Task 3: Update Graph to Use Conditional Entry Routing

**Files:**
- Modify: `amelia/pipelines/implementation/graph.py:52-126`
- Test: `tests/unit/pipelines/test_graph_routing.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/pipelines/test_graph_routing.py`:

```python
"""Unit tests for graph routing with external plans."""

from datetime import UTC, datetime

import pytest

from amelia.core.types import Issue
from amelia.pipelines.implementation.graph import create_implementation_graph
from amelia.pipelines.implementation.state import ImplementationState


class TestGraphExternalPlanRouting:
    """Tests for graph routing when external_plan is set."""

    def test_graph_compiles_successfully(self) -> None:
        """Graph should compile without errors."""
        graph = create_implementation_graph()
        assert graph is not None

    def test_graph_has_architect_and_validator_nodes(self) -> None:
        """Graph should have both architect and plan_validator nodes."""
        graph = create_implementation_graph()
        nodes = list(graph.nodes.keys())
        assert "architect_node" in nodes
        assert "plan_validator_node" in nodes

    def test_external_plan_routing_logic(self) -> None:
        """Verify routing function returns correct values."""
        from amelia.pipelines.implementation.routing import route_after_start

        # External plan should route to validator
        external_state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
            external_plan=True,
        )
        assert route_after_start(external_state) == "plan_validator"

        # Normal plan should route to architect
        normal_state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
            external_plan=False,
        )
        assert route_after_start(normal_state) == "architect"
```

**Step 2: Run test to verify baseline**

Run: `uv run pytest tests/unit/pipelines/test_graph_routing.py -v`
Expected: Some tests pass, routing test passes (from Task 2)

**Step 3: Write implementation**

Modify `amelia/pipelines/implementation/graph.py`:

1. Update imports:

```python
from langgraph.graph import END, START, StateGraph

from amelia.pipelines.implementation.routing import (
    route_after_start,
    route_after_task_review,
    route_approval,
)
```

2. In `create_implementation_graph`, replace `workflow.set_entry_point("architect_node")` with:

```python
    # Conditional entry point: route based on external_plan flag
    workflow.add_conditional_edges(
        START,
        route_after_start,
        {
            "architect": "architect_node",
            "plan_validator": "plan_validator_node",
        }
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/test_graph_routing.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/graph.py tests/unit/pipelines/test_graph_routing.py
git commit -m "feat(graph): add conditional entry routing for external plans"
```

---

## Task 4: Implement `import_external_plan` Helper Function

**Files:**
- Create: `amelia/pipelines/implementation/external_plan.py`
- Test: `tests/unit/pipelines/test_external_plan.py`

**Step 1: Write the failing tests**

Create `tests/unit/pipelines/test_external_plan.py`:

```python
"""Unit tests for external plan import helper."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import Profile


class TestImportExternalPlan:
    """Tests for import_external_plan helper function."""

    @pytest.fixture
    def mock_profile(self) -> Profile:
        """Create mock profile for testing."""
        return Profile(
            name="test",
            driver="cli",
            model="sonnet",
            validator_model="sonnet",
            tracker="none",
            strategy="single",
            working_dir="/tmp/worktree",
        )

    async def test_import_from_file_path(
        self, tmp_path: Path, mock_profile: Profile
    ) -> None:
        """Import plan from file path reads and validates content."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        plan_file = tmp_path / "plan.md"
        plan_content = """# Implementation Plan

**Goal:** Add user authentication

### Task 1: Create auth module

Create the auth module.
"""
        plan_file.write_text(plan_content)

        target_path = tmp_path / "output" / "plan.md"

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = MagicMock(
                goal="Add user authentication",
                plan_markdown=plan_content,
                key_files=["auth.py"],
            )

            result = await import_external_plan(
                plan_file=str(plan_file),
                plan_content=None,
                target_path=target_path,
                profile=mock_profile,
                workflow_id="wf-001",
            )

        assert result["goal"] == "Add user authentication"
        assert result["plan_markdown"] == plan_content
        assert result["key_files"] == ["auth.py"]
        assert result["total_tasks"] == 1
        assert target_path.read_text() == plan_content

    async def test_import_from_inline_content(
        self, tmp_path: Path, mock_profile: Profile
    ) -> None:
        """Import plan from inline content writes and validates."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        plan_content = """# Implementation Plan

**Goal:** Fix bug

### Task 1: Fix the bug

Fix it.
"""
        target_path = tmp_path / "output" / "plan.md"

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = MagicMock(
                goal="Fix bug",
                plan_markdown=plan_content,
                key_files=[],
            )

            result = await import_external_plan(
                plan_file=None,
                plan_content=plan_content,
                target_path=target_path,
                profile=mock_profile,
                workflow_id="wf-001",
            )

        assert result["goal"] == "Fix bug"
        assert target_path.read_text() == plan_content

    async def test_import_file_not_found_raises(
        self, tmp_path: Path, mock_profile: Profile
    ) -> None:
        """Import with non-existent file raises FileNotFoundError."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        target_path = tmp_path / "output" / "plan.md"

        with pytest.raises(FileNotFoundError, match="Plan file not found"):
            await import_external_plan(
                plan_file="/nonexistent/plan.md",
                plan_content=None,
                target_path=target_path,
                profile=mock_profile,
                workflow_id="wf-001",
            )

    async def test_import_empty_content_raises(
        self, tmp_path: Path, mock_profile: Profile
    ) -> None:
        """Import with empty content raises ValueError."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        target_path = tmp_path / "output" / "plan.md"

        with pytest.raises(ValueError, match="Plan content is empty"):
            await import_external_plan(
                plan_file=None,
                plan_content="   ",
                target_path=target_path,
                profile=mock_profile,
                workflow_id="wf-001",
            )

    async def test_import_relative_path_resolved_to_worktree(
        self, tmp_path: Path
    ) -> None:
        """Relative plan_file paths are resolved relative to worktree."""
        from amelia.pipelines.implementation.external_plan import import_external_plan

        worktree = tmp_path / "worktree"
        worktree.mkdir()
        plan_file = worktree / "docs" / "plan.md"
        plan_file.parent.mkdir(parents=True)
        plan_content = "# Plan\n\n### Task 1: Do thing\n\nDo it."
        plan_file.write_text(plan_content)

        profile = Profile(
            name="test",
            driver="cli",
            model="sonnet",
            validator_model="sonnet",
            tracker="none",
            strategy="single",
            working_dir=str(worktree),
        )

        target_path = tmp_path / "output" / "plan.md"

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = MagicMock(
                goal="Do thing",
                plan_markdown=plan_content,
                key_files=[],
            )

            result = await import_external_plan(
                plan_file="docs/plan.md",
                plan_content=None,
                target_path=target_path,
                profile=profile,
                workflow_id="wf-001",
            )

        assert result["goal"] == "Do thing"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/pipelines/test_external_plan.py -v`
Expected: FAIL with "No module named 'amelia.pipelines.implementation.external_plan'"

**Step 3: Write minimal implementation**

Create `amelia/pipelines/implementation/external_plan.py`:

```python
"""External plan import helper.

Provides shared logic for importing external plans from files or inline content,
used by both workflow creation and the POST /plan endpoint.
"""

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from amelia.core.types import Profile
from amelia.drivers.extraction import extract_structured
from amelia.pipelines.implementation.schemas import MarkdownPlanOutput
from amelia.pipelines.implementation.utils import extract_task_count


async def import_external_plan(
    plan_file: str | None,
    plan_content: str | None,
    target_path: Path,
    profile: Profile,
    workflow_id: str,
) -> dict[str, Any]:
    """Import and validate an external plan.

    Args:
        plan_file: Path to plan file (relative to worktree or absolute).
        plan_content: Inline plan markdown content.
        target_path: Where to write the plan (standard plan location).
        profile: Profile for LLM extraction config.
        workflow_id: For logging.

    Returns:
        Dict with goal, plan_markdown, plan_path, key_files, total_tasks.

    Raises:
        FileNotFoundError: If plan_file doesn't exist.
        ValueError: If validation fails or content is empty.
    """
    # Resolve content from file or use inline
    if plan_file is not None:
        plan_path = Path(plan_file)
        if not plan_path.is_absolute():
            working_dir = Path(profile.working_dir) if profile.working_dir else Path(".")
            plan_path = working_dir / plan_file

        if not plan_path.exists():
            raise FileNotFoundError(f"Plan file not found: {plan_path}")

        content = await asyncio.to_thread(plan_path.read_text)
    else:
        content = plan_content or ""

    # Validate content is not empty
    if not content.strip():
        raise ValueError("Plan content is empty")

    # Write to target path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(target_path.write_text, content)

    logger.info(
        "External plan written",
        target_path=str(target_path),
        content_length=len(content),
        workflow_id=workflow_id,
    )

    # Extract structured fields using LLM
    agent_config = profile.get_agent_config("plan_validator")
    prompt = f"""Extract the implementation plan structure from the following markdown plan.

<plan>
{content}
</plan>

Return:
- goal: 1-2 sentence summary of what this plan accomplishes
- plan_markdown: The full plan content (preserve as-is)
- key_files: List of files that will be created or modified"""

    try:
        output = await extract_structured(
            prompt=prompt,
            schema=MarkdownPlanOutput,
            model=agent_config.model,
            driver_type=agent_config.driver,
        )
        goal = output.goal
        plan_markdown = output.plan_markdown
        key_files = output.key_files
    except RuntimeError as e:
        # Fallback extraction without LLM
        logger.warning(
            "Structured extraction failed, using fallback",
            error=str(e),
            workflow_id=workflow_id,
        )
        from amelia.pipelines.implementation.utils import (
            _extract_goal_from_plan,
            _extract_key_files_from_plan,
        )

        goal = _extract_goal_from_plan(content)
        plan_markdown = content
        key_files = _extract_key_files_from_plan(content)

    # Extract task count
    total_tasks = extract_task_count(content)

    logger.info(
        "External plan validated",
        goal=goal,
        key_files_count=len(key_files),
        total_tasks=total_tasks,
        workflow_id=workflow_id,
    )

    return {
        "goal": goal,
        "plan_markdown": plan_markdown,
        "plan_path": target_path,
        "key_files": key_files,
        "total_tasks": total_tasks,
    }
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/pipelines/test_external_plan.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/pipelines/implementation/external_plan.py tests/unit/pipelines/test_external_plan.py
git commit -m "feat(pipelines): add import_external_plan helper function"
```

---

## Task 5: Add Plan Fields to CreateWorkflowRequest

**Files:**
- Modify: `amelia/server/models/requests.py:66-234`
- Modify: `amelia/client/models.py:6-25`
- Modify: `dashboard/src/types/index.ts:427-449`
- Test: `tests/unit/server/test_request_models.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/server/test_request_models.py`:

```python
"""Unit tests for server request models."""

import pytest
from pydantic import ValidationError

from amelia.server.models.requests import CreateWorkflowRequest


class TestCreateWorkflowRequestPlanFields:
    """Tests for plan_file and plan_content fields."""

    def test_plan_file_is_optional(self, tmp_path) -> None:
        """plan_file should be optional and default to None."""
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").mkdir()

        request = CreateWorkflowRequest(
            issue_id="TEST-001",
            worktree_path=str(worktree),
        )
        assert request.plan_file is None

    def test_plan_content_is_optional(self, tmp_path) -> None:
        """plan_content should be optional and default to None."""
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").mkdir()

        request = CreateWorkflowRequest(
            issue_id="TEST-001",
            worktree_path=str(worktree),
        )
        assert request.plan_content is None

    def test_plan_file_and_plan_content_mutually_exclusive(self, tmp_path) -> None:
        """Cannot provide both plan_file and plan_content."""
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").mkdir()

        with pytest.raises(ValidationError, match="mutually exclusive"):
            CreateWorkflowRequest(
                issue_id="TEST-001",
                worktree_path=str(worktree),
                plan_file="plan.md",
                plan_content="# Plan content",
            )

    def test_plan_file_accepted_alone(self, tmp_path) -> None:
        """plan_file can be provided without plan_content."""
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").mkdir()

        request = CreateWorkflowRequest(
            issue_id="TEST-001",
            worktree_path=str(worktree),
            plan_file="docs/plan.md",
        )
        assert request.plan_file == "docs/plan.md"
        assert request.plan_content is None

    def test_plan_content_accepted_alone(self, tmp_path) -> None:
        """plan_content can be provided without plan_file."""
        worktree = tmp_path / "repo"
        worktree.mkdir()
        (worktree / ".git").mkdir()

        request = CreateWorkflowRequest(
            issue_id="TEST-001",
            worktree_path=str(worktree),
            plan_content="# My Plan\n\n### Task 1: Do thing",
        )
        assert request.plan_content == "# My Plan\n\n### Task 1: Do thing"
        assert request.plan_file is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_request_models.py -v`
Expected: FAIL - fields don't exist yet

**Step 3: Write implementation**

Modify `amelia/server/models/requests.py` - add fields after `artifact_path`:

```python
    plan_file: Annotated[
        str | None,
        Field(
            default=None,
            description="Path to external plan file (relative to worktree or absolute)",
        ),
    ] = None

    plan_content: Annotated[
        str | None,
        Field(
            default=None,
            description="Inline plan markdown content",
        ),
    ] = None
```

Add validator after `validate_task_fields`:

```python
    @model_validator(mode="after")
    def validate_plan_fields(self) -> "CreateWorkflowRequest":
        """Validate plan_file and plan_content are mutually exclusive."""
        if self.plan_file is not None and self.plan_content is not None:
            raise ValueError("plan_file and plan_content are mutually exclusive")
        return self
```

Update `amelia/client/models.py`:

```python
    plan_file: str | None = Field(default=None, max_length=4096)
    plan_content: str | None = Field(default=None)
```

Update `dashboard/src/types/index.ts` - add to `CreateWorkflowRequest`:

```typescript
  /** Path to external plan file (relative to worktree or absolute). */
  plan_file?: string;

  /** Inline plan markdown content. */
  plan_content?: string;
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_request_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/requests.py amelia/client/models.py dashboard/src/types/index.ts tests/unit/server/test_request_models.py
git commit -m "feat(api): add plan_file and plan_content to CreateWorkflowRequest"
```

---

## Task 6: Add SetPlanRequest Model

**Files:**
- Modify: `amelia/server/models/requests.py`
- Modify: `dashboard/src/types/index.ts`
- Test: `tests/unit/server/test_request_models.py` (extend)

**Step 1: Write the failing test**

Add to `tests/unit/server/test_request_models.py`:

```python
from amelia.server.models.requests import SetPlanRequest


class TestSetPlanRequest:
    """Tests for SetPlanRequest model."""

    def test_requires_either_plan_file_or_plan_content(self) -> None:
        """Must provide either plan_file or plan_content."""
        with pytest.raises(ValidationError, match="Either plan_file or plan_content"):
            SetPlanRequest()

    def test_plan_file_and_plan_content_mutually_exclusive(self) -> None:
        """Cannot provide both plan_file and plan_content."""
        with pytest.raises(ValidationError, match="mutually exclusive"):
            SetPlanRequest(
                plan_file="plan.md",
                plan_content="# Plan",
            )

    def test_force_defaults_to_false(self) -> None:
        """force should default to False."""
        request = SetPlanRequest(plan_file="plan.md")
        assert request.force is False

    def test_force_can_be_set_true(self) -> None:
        """force can be explicitly set to True."""
        request = SetPlanRequest(plan_content="# Plan", force=True)
        assert request.force is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_request_models.py::TestSetPlanRequest -v`
Expected: FAIL - SetPlanRequest doesn't exist

**Step 3: Write implementation**

Add to `amelia/server/models/requests.py`:

```python
class SetPlanRequest(BaseModel):
    """Request to set or replace the plan for a queued workflow.

    Attributes:
        plan_file: Path to external plan file (relative to worktree or absolute).
        plan_content: Inline plan markdown content.
        force: If True, overwrite existing plan.
    """

    plan_file: Annotated[
        str | None,
        Field(
            default=None,
            description="Path to external plan file (relative to worktree or absolute)",
        ),
    ] = None

    plan_content: Annotated[
        str | None,
        Field(
            default=None,
            description="Inline plan markdown content",
        ),
    ] = None

    force: bool = False
    """If True, overwrite existing plan."""

    @model_validator(mode="after")
    def validate_plan_fields(self) -> "SetPlanRequest":
        """Validate plan_file and plan_content constraints."""
        if self.plan_file is not None and self.plan_content is not None:
            raise ValueError("plan_file and plan_content are mutually exclusive")
        if self.plan_file is None and self.plan_content is None:
            raise ValueError("Either plan_file or plan_content must be provided")
        return self
```

Add to `dashboard/src/types/index.ts`:

```typescript
export interface SetPlanRequest {
  /** Path to external plan file (relative to worktree or absolute). */
  plan_file?: string;

  /** Inline plan markdown content. */
  plan_content?: string;

  /** If true, overwrite existing plan. */
  force?: boolean;
}

export interface SetPlanResponse {
  /** Extracted goal from the plan. */
  goal: string;

  /** List of key files from the plan. */
  key_files: string[];

  /** Number of tasks in the plan. */
  total_tasks: number;
}
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_request_models.py::TestSetPlanRequest -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/models/requests.py dashboard/src/types/index.ts tests/unit/server/test_request_models.py
git commit -m "feat(api): add SetPlanRequest and SetPlanResponse models"
```

---

## Task 7: Update `queue_workflow` to Handle External Plans

**Files:**
- Modify: `amelia/server/orchestrator/service.py:558-622`
- Test: `tests/unit/server/test_orchestrator_external_plan.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/server/test_orchestrator_external_plan.py`:

```python
"""Unit tests for OrchestratorService external plan handling."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.orchestrator.service import OrchestratorService


class TestQueueWorkflowWithExternalPlan:
    """Tests for queue_workflow with external plan parameters."""

    @pytest.fixture
    def mock_orchestrator(self) -> OrchestratorService:
        """Create orchestrator with mocked dependencies."""
        mock_event_bus = MagicMock()
        mock_event_bus.emit = AsyncMock()
        mock_repository = MagicMock()
        mock_repository.create = AsyncMock()
        mock_profile_repo = MagicMock()

        return OrchestratorService(
            event_bus=mock_event_bus,
            repository=mock_repository,
            profile_repo=mock_profile_repo,
            checkpoint_path="/tmp/checkpoints.db",
        )

    async def test_queue_workflow_with_plan_content_sets_external_flag(
        self, mock_orchestrator: OrchestratorService, tmp_path: Path
    ) -> None:
        """queue_workflow should set external_plan=True when plan_content provided."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / ".git").mkdir()

        request = CreateWorkflowRequest(
            issue_id="TEST-001",
            worktree_path=str(worktree),
            plan_content="# Test Plan\n\n### Task 1: Do thing",
            start=False,
            task_title="Test task",
        )

        with (
            patch.object(
                mock_orchestrator, "_validate_worktree_path", return_value=worktree
            ),
            patch.object(
                mock_orchestrator,
                "_prepare_workflow_state",
            ) as mock_prepare,
            patch(
                "amelia.server.orchestrator.service.import_external_plan"
            ) as mock_import,
        ):
            mock_state = MagicMock()
            mock_state.external_plan = False
            mock_state.model_copy = MagicMock(return_value=MagicMock(external_plan=True))
            mock_prepare.return_value = (str(worktree), MagicMock(), mock_state)
            mock_import.return_value = {
                "goal": "Do thing",
                "plan_markdown": "# Test Plan",
                "plan_path": tmp_path / "plan.md",
                "key_files": [],
                "total_tasks": 1,
            }

            await mock_orchestrator.queue_workflow(request)

            mock_import.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_orchestrator_external_plan.py -v`
Expected: FAIL - import_external_plan not called

**Step 3: Write implementation**

Modify `queue_workflow` in `amelia/server/orchestrator/service.py`. Add after `_prepare_workflow_state` call:

```python
    # Handle external plan if provided
    if request.plan_file is not None or request.plan_content is not None:
        from amelia.pipelines.implementation.external_plan import import_external_plan
        from amelia.pipelines.implementation.utils import resolve_plan_path

        # Resolve target plan path
        plan_rel_path = resolve_plan_path(profile.plan_path_pattern, request.issue_id)
        working_dir = Path(profile.working_dir) if profile.working_dir else Path(".")
        target_path = working_dir / plan_rel_path

        # Import and validate external plan
        plan_result = await import_external_plan(
            plan_file=request.plan_file,
            plan_content=request.plan_content,
            target_path=target_path,
            profile=profile,
            workflow_id=workflow_id,
        )

        # Update execution state with plan data and external flag
        execution_state = execution_state.model_copy(
            update={
                "external_plan": True,
                "goal": plan_result["goal"],
                "plan_markdown": plan_result["plan_markdown"],
                "plan_path": plan_result["plan_path"],
                "key_files": plan_result["key_files"],
                "total_tasks": plan_result["total_tasks"],
            }
        )
```

Add import at top: `from pathlib import Path`

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_orchestrator_external_plan.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/test_orchestrator_external_plan.py
git commit -m "feat(orchestrator): handle external plans in queue_workflow"
```

---

## Task 8: Add `POST /api/workflows/{id}/plan` Endpoint

**Files:**
- Modify: `amelia/server/routes/workflows.py`
- Create: `amelia/server/models/responses.py` (if needed)
- Test: `tests/unit/server/test_set_plan_endpoint.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/server/test_set_plan_endpoint.py`:

```python
"""Unit tests for POST /api/workflows/{id}/plan endpoint."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from amelia.server.dependencies import get_orchestrator
from amelia.server.main import create_app


class TestSetPlanEndpoint:
    """Tests for POST /api/workflows/{id}/plan endpoint."""

    @pytest.fixture
    def mock_orchestrator(self) -> MagicMock:
        """Create mock orchestrator."""
        mock = MagicMock()
        mock.set_workflow_plan = AsyncMock(
            return_value={
                "goal": "Test goal",
                "key_files": ["file.py"],
                "total_tasks": 2,
            }
        )
        return mock

    @pytest.fixture
    def test_client(self, mock_orchestrator: MagicMock) -> TestClient:
        """Create test client with mocked orchestrator."""
        app = create_app()
        app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
        return TestClient(app)

    def test_set_plan_with_inline_content(
        self, test_client: TestClient, mock_orchestrator: MagicMock
    ) -> None:
        """Setting plan with inline content returns 200."""
        response = test_client.post(
            "/api/workflows/wf-001/plan",
            json={"plan_content": "# Plan\n\n### Task 1: Do thing"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["goal"] == "Test goal"
        assert data["key_files"] == ["file.py"]
        assert data["total_tasks"] == 2

    def test_set_plan_requires_either_file_or_content(
        self, test_client: TestClient
    ) -> None:
        """Request without plan_file or plan_content returns 422."""
        response = test_client.post(
            "/api/workflows/wf-001/plan",
            json={},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_set_plan_endpoint.py -v`
Expected: FAIL - endpoint doesn't exist (404)

**Step 3: Write implementation**

Add response model to `amelia/server/models/responses.py` (create if needed):

```python
"""Response models for the server API."""

from pydantic import BaseModel


class SetPlanResponse(BaseModel):
    """Response from setting an external plan on a workflow."""

    goal: str
    key_files: list[str]
    total_tasks: int
```

Add endpoint to `amelia/server/routes/workflows.py`:

```python
from amelia.server.models.requests import SetPlanRequest
from amelia.server.models.responses import SetPlanResponse


@router.post("/{workflow_id}/plan", response_model=SetPlanResponse)
async def set_workflow_plan(
    workflow_id: str,
    request: SetPlanRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
) -> SetPlanResponse:
    """Set or replace the plan for a queued workflow.

    Args:
        workflow_id: The workflow ID.
        request: Plan content or file path.
        orchestrator: Orchestrator service dependency.

    Returns:
        SetPlanResponse with extracted plan summary.
    """
    result = await orchestrator.set_workflow_plan(
        workflow_id=workflow_id,
        plan_file=request.plan_file,
        plan_content=request.plan_content,
        force=request.force,
    )

    return SetPlanResponse(
        goal=result["goal"],
        key_files=result["key_files"],
        total_tasks=result["total_tasks"],
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_set_plan_endpoint.py -v`
Expected: FAIL - orchestrator.set_workflow_plan doesn't exist yet (next task)

**Step 5: Commit**

```bash
git add amelia/server/routes/workflows.py amelia/server/models/responses.py tests/unit/server/test_set_plan_endpoint.py
git commit -m "feat(api): add POST /api/workflows/{id}/plan endpoint"
```

---

## Task 9: Implement `OrchestratorService.set_workflow_plan`

**Files:**
- Modify: `amelia/server/orchestrator/service.py`
- Test: `tests/unit/server/test_orchestrator_set_plan.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/server/test_orchestrator_set_plan.py`:

```python
"""Unit tests for OrchestratorService.set_workflow_plan."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.pipelines.implementation.state import ImplementationState
from amelia.server.database.repository import WorkflowRepository
from amelia.server.exceptions import InvalidStateError, WorkflowConflictError, WorkflowNotFoundError
from amelia.server.models.state import ServerExecutionState, WorkflowStatus
from amelia.server.orchestrator.service import OrchestratorService


class TestSetWorkflowPlan:
    """Tests for set_workflow_plan method."""

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock repository."""
        mock = MagicMock(spec=WorkflowRepository)
        mock.get = AsyncMock()
        mock.update = AsyncMock()
        return mock

    @pytest.fixture
    def mock_orchestrator(self, mock_repository: MagicMock) -> OrchestratorService:
        """Create orchestrator with mocked dependencies."""
        mock_event_bus = MagicMock()
        mock_event_bus.emit = AsyncMock()
        mock_profile_repo = MagicMock()
        mock_profile_repo.get_profile = AsyncMock()

        return OrchestratorService(
            event_bus=mock_event_bus,
            repository=mock_repository,
            profile_repo=mock_profile_repo,
            checkpoint_path="/tmp/checkpoints.db",
        )

    def _create_workflow(
        self,
        workflow_id: str = "wf-001",
        workflow_status: WorkflowStatus = WorkflowStatus.PENDING,
        has_plan: bool = False,
    ) -> ServerExecutionState:
        """Create test workflow."""
        execution_state = ImplementationState(
            workflow_id=workflow_id,
            profile_id="test",
            created_at=datetime.now(UTC),
            status="pending",
            goal="Existing goal" if has_plan else None,
            plan_markdown="# Existing plan" if has_plan else None,
        )
        return ServerExecutionState(
            id=workflow_id,
            issue_id="TEST-001",
            worktree_path="/tmp/worktree",
            workflow_status=workflow_status,
            execution_state=execution_state,
        )

    async def test_set_plan_on_pending_workflow(
        self, mock_orchestrator: OrchestratorService, mock_repository: MagicMock, tmp_path: Path
    ) -> None:
        """Setting plan on pending workflow succeeds."""
        workflow = self._create_workflow(workflow_status=WorkflowStatus.PENDING)
        mock_repository.get.return_value = workflow

        with (
            patch(
                "amelia.server.orchestrator.service.import_external_plan"
            ) as mock_import,
            patch.object(mock_orchestrator, "_get_profile_or_fail") as mock_profile,
        ):
            mock_import.return_value = {
                "goal": "New goal",
                "plan_markdown": "# New plan",
                "plan_path": tmp_path / "plan.md",
                "key_files": ["file.py"],
                "total_tasks": 2,
            }
            mock_profile.return_value = MagicMock(
                plan_path_pattern="docs/{issue_key}/plan.md",
                working_dir="/tmp/worktree",
            )

            result = await mock_orchestrator.set_workflow_plan(
                workflow_id="wf-001",
                plan_content="# New plan",
            )

        assert result["goal"] == "New goal"
        assert result["total_tasks"] == 2
        mock_repository.update.assert_called_once()

    async def test_set_plan_on_running_workflow_fails(
        self, mock_orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """Setting plan on running workflow raises InvalidStateError."""
        workflow = self._create_workflow(workflow_status=WorkflowStatus.RUNNING)
        mock_repository.get.return_value = workflow

        with pytest.raises(InvalidStateError, match="pending or planning"):
            await mock_orchestrator.set_workflow_plan(
                workflow_id="wf-001",
                plan_content="# Plan",
            )

    async def test_set_plan_without_force_when_plan_exists_fails(
        self, mock_orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """Setting plan without force when plan exists raises WorkflowConflictError."""
        workflow = self._create_workflow(workflow_status=WorkflowStatus.PENDING, has_plan=True)
        mock_repository.get.return_value = workflow

        with pytest.raises(WorkflowConflictError, match="Plan already exists"):
            await mock_orchestrator.set_workflow_plan(
                workflow_id="wf-001",
                plan_content="# New plan",
                force=False,
            )

    async def test_set_plan_on_nonexistent_workflow_fails(
        self, mock_orchestrator: OrchestratorService, mock_repository: MagicMock
    ) -> None:
        """Setting plan on nonexistent workflow raises WorkflowNotFoundError."""
        mock_repository.get.return_value = None

        with pytest.raises(WorkflowNotFoundError):
            await mock_orchestrator.set_workflow_plan(
                workflow_id="wf-nonexistent",
                plan_content="# Plan",
            )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/test_orchestrator_set_plan.py -v`
Expected: FAIL - set_workflow_plan doesn't exist

**Step 3: Write implementation**

Add method to `OrchestratorService` in `amelia/server/orchestrator/service.py`:

```python
async def set_workflow_plan(
    self,
    workflow_id: str,
    plan_file: str | None = None,
    plan_content: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Set or replace the plan for a queued workflow.

    Args:
        workflow_id: The workflow ID.
        plan_file: Path to plan file (relative to worktree or absolute).
        plan_content: Inline plan markdown content.
        force: If True, overwrite existing plan.

    Returns:
        Dict with goal, key_files, total_tasks.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist.
        InvalidStateError: If workflow not in pending/planning status.
        WorkflowConflictError: If plan exists and force=False.
        FileNotFoundError: If plan_file doesn't exist.
    """
    from amelia.pipelines.implementation.external_plan import import_external_plan
    from amelia.pipelines.implementation.utils import resolve_plan_path

    # Load workflow
    workflow = await self._repository.get(workflow_id)
    if workflow is None:
        raise WorkflowNotFoundError(workflow_id)

    # Check status
    valid_statuses = {WorkflowStatus.PENDING, WorkflowStatus.PLANNING}
    if workflow.workflow_status not in valid_statuses:
        raise InvalidStateError(
            f"Workflow must be in pending or planning status, "
            f"but is in {workflow.workflow_status}"
        )

    # Check for active planning task
    if workflow_id in self._planning_tasks:
        raise WorkflowConflictError(
            f"Architect is currently running for workflow {workflow_id}"
        )

    # Check existing plan
    execution_state = workflow.execution_state
    if execution_state.plan_markdown is not None and not force:
        raise WorkflowConflictError(
            "Plan already exists. Use force=true to overwrite."
        )

    # Get profile for plan path resolution
    profile = await self._get_profile_or_fail(execution_state.profile_id)
    profile = self._update_profile_working_dir(profile, workflow.worktree_path)

    # Resolve target plan path
    plan_rel_path = resolve_plan_path(profile.plan_path_pattern, workflow.issue_id)
    working_dir = Path(profile.working_dir) if profile.working_dir else Path(".")
    target_path = working_dir / plan_rel_path

    # Import and validate external plan
    plan_result = await import_external_plan(
        plan_file=plan_file,
        plan_content=plan_content,
        target_path=target_path,
        profile=profile,
        workflow_id=workflow_id,
    )

    # Update execution state
    updated_execution_state = execution_state.model_copy(
        update={
            "external_plan": True,
            "goal": plan_result["goal"],
            "plan_markdown": plan_result["plan_markdown"],
            "plan_path": plan_result["plan_path"],
            "key_files": plan_result["key_files"],
            "total_tasks": plan_result["total_tasks"],
        }
    )

    # Update workflow in database
    updated_workflow = workflow.model_copy(
        update={
            "execution_state": updated_execution_state,
            "workflow_status": WorkflowStatus.PENDING
            if workflow.workflow_status == WorkflowStatus.PLANNING
            else workflow.workflow_status,
        }
    )
    await self._repository.update(updated_workflow)

    # Emit plan updated event
    await self._emit(
        workflow_id,
        EventType.PLAN_READY,
        f"External plan set for workflow {workflow_id}",
        data={
            "goal": plan_result["goal"],
            "key_files": plan_result["key_files"],
            "total_tasks": plan_result["total_tasks"],
        },
    )

    logger.info(
        "External plan set",
        workflow_id=workflow_id,
        goal=plan_result["goal"],
        total_tasks=plan_result["total_tasks"],
    )

    return {
        "goal": plan_result["goal"],
        "key_files": plan_result["key_files"],
        "total_tasks": plan_result["total_tasks"],
    }
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/test_orchestrator_set_plan.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add amelia/server/orchestrator/service.py tests/unit/server/test_orchestrator_set_plan.py
git commit -m "feat(orchestrator): implement set_workflow_plan method"
```

---

## Task 10: Integration Tests for External Plan Flow

**Files:**
- Create: `tests/integration/test_external_plan_flow.py`

**Step 1: Write the integration test**

Create `tests/integration/test_external_plan_flow.py`:

```python
"""Integration tests for external plan import flow.

Tests the complete external plan lifecycle with real components,
mocking only at the external HTTP boundary (LLM API calls).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository
from amelia.server.dependencies import get_orchestrator, get_repository
from amelia.server.events.bus import EventBus
from amelia.server.main import create_app
from amelia.server.orchestrator.service import OrchestratorService
from tests.conftest import init_git_repo


@pytest.fixture
async def test_db(temp_db_path: Path) -> AsyncGenerator[Database, None]:
    """Create and initialize SQLite database."""
    db = Database(temp_db_path)
    await db.connect()
    await db.ensure_schema()
    yield db
    await db.close()


@pytest.fixture
def test_repository(test_db: Database) -> WorkflowRepository:
    """Create repository backed by test database."""
    return WorkflowRepository(test_db)


@pytest.fixture
def test_orchestrator(
    test_repository: WorkflowRepository,
    tmp_path: Path,
) -> OrchestratorService:
    """Create real OrchestratorService."""
    return OrchestratorService(
        event_bus=EventBus(),
        repository=test_repository,
        checkpoint_path=str(tmp_path / "checkpoints.db"),
    )


@pytest.fixture
def test_client(
    test_orchestrator: OrchestratorService,
    test_repository: WorkflowRepository,
) -> TestClient:
    """Create test client with real dependencies."""
    app = create_app()

    @asynccontextmanager
    async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
        yield

    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_orchestrator] = lambda: test_orchestrator
    app.dependency_overrides[get_repository] = lambda: test_repository

    return TestClient(app)


@pytest.mark.integration
class TestExternalPlanAtCreation:
    """Tests for external plan at workflow creation."""

    async def test_create_workflow_with_plan_content(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        tmp_path: Path,
    ) -> None:
        """Creating workflow with plan_content sets external_plan flag."""
        git_dir = tmp_path / "repo"
        git_dir.mkdir()
        init_git_repo(git_dir)

        plan_content = "# Plan\n\n### Task 1: Do thing\n\nDo it."

        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = MagicMock(
                goal="Do thing",
                plan_markdown=plan_content,
                key_files=[],
            )

            response = test_client.post(
                "/api/workflows",
                json={
                    "issue_id": "TEST-001",
                    "worktree_path": str(git_dir.resolve()),
                    "start": False,
                    "task_title": "Test task",
                    "plan_content": plan_content,
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        workflow_id = response.json()["id"]

        workflow = await test_repository.get(workflow_id)
        assert workflow.execution_state.external_plan is True
        assert workflow.execution_state.goal == "Do thing"


@pytest.mark.integration
class TestSetPlanEndpoint:
    """Tests for POST /api/workflows/{id}/plan endpoint."""

    async def test_set_plan_on_pending_workflow(
        self,
        test_client: TestClient,
        test_repository: WorkflowRepository,
        tmp_path: Path,
    ) -> None:
        """Setting plan on pending workflow succeeds."""
        git_dir = tmp_path / "repo"
        git_dir.mkdir()
        init_git_repo(git_dir)

        # Create workflow without plan
        response = test_client.post(
            "/api/workflows",
            json={
                "issue_id": "TEST-002",
                "worktree_path": str(git_dir.resolve()),
                "start": False,
                "task_title": "Test task",
            },
        )
        workflow_id = response.json()["id"]

        # Set plan
        with patch(
            "amelia.pipelines.implementation.external_plan.extract_structured"
        ) as mock_extract:
            mock_extract.return_value = MagicMock(
                goal="New goal",
                plan_markdown="# Plan",
                key_files=[],
            )

            response = test_client.post(
                f"/api/workflows/{workflow_id}/plan",
                json={"plan_content": "# Plan\n\n### Task 1: Do thing"},
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["goal"] == "New goal"

        workflow = await test_repository.get(workflow_id)
        assert workflow.execution_state.external_plan is True
```

**Step 2: Run tests**

Run: `uv run pytest tests/integration/test_external_plan_flow.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_external_plan_flow.py
git commit -m "test(integration): add external plan import flow tests"
```

---

## Task 11: Final Verification and Cleanup

**Files:**
- All modified files

**Step 1: Run full test suite**

```bash
uv run pytest tests/unit tests/integration -v --tb=short
```

**Step 2: Run type checking**

```bash
uv run mypy amelia
```

**Step 3: Run linting**

```bash
uv run ruff check amelia tests
uv run ruff check --fix amelia tests
```

**Step 4: Run dashboard type check**

```bash
cd dashboard && pnpm type-check
```

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup for external plan import feature"
```

---

## Summary

This plan implements external plan import with:

1. **State Changes:** `external_plan` field on `ImplementationState`
2. **Routing:** `route_after_start()` for conditional Architect bypass
3. **Graph Changes:** Conditional entry point using `add_conditional_edges(START, ...)`
4. **Helper Function:** `import_external_plan()` for shared import logic
5. **API Changes:**
   - `plan_file` and `plan_content` on `CreateWorkflowRequest`
   - `SetPlanRequest` model for POST endpoint
   - `POST /api/workflows/{id}/plan` endpoint
6. **Orchestrator:** `queue_workflow` handles external plans, `set_workflow_plan` method

All tasks follow TDD with unit tests first, then implementation.
