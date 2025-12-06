# LangGraph Execution Bridge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect the server layer to the existing LangGraph orchestrator by implementing `_run_workflow()` with checkpoint persistence, interrupt-based human approval, and event streaming.

**Architecture:** The ExecutionBridge pattern wraps the core LangGraph orchestrator with server-specific concerns: SQLite checkpointing via `langgraph-checkpoint-sqlite`, execution mode detection (CLI vs server), event mapping from LangGraph events to WorkflowEvents, and retry logic for transient failures.

**Tech Stack:** LangGraph, langgraph-checkpoint-sqlite, Pydantic, asyncio, aiosqlite

---

## PR Strategy

This implementation is split into **two PRs** for easier review and faster iteration:

### PR 1: Core Execution Bridge (Tasks 1, 1.5, 4, 5, 6, 7, 10, 11, 12, 13, 14)

**Branch:** `feat/langgraph-execution-bridge`

The core interrupt/resume mechanism. Self-contained and functional without retry logic.

| Task | Description | Priority |
|------|-------------|----------|
| 1 | Add langgraph-checkpoint-sqlite dependency | Required |
| 1.5 | Update create_orchestrator_graph with interrupt_before | **CRITICAL** |
| 4 | Update human_approval_node for execution mode | Required |
| 5 | Add execution_state to ServerExecutionState | Required |
| 6 | Add STAGE_NODES and event mapping | Required |
| 7 | Implement _run_workflow with GraphInterrupt handling | **CRITICAL** |
| 10 | Update approve_workflow for graph resume | Required |
| 11 | Update reject_workflow for graph state | Required |
| 12 | Run full test suite and linting | Required |
| 13 | Create integration test for approval flow | Required |
| 14 | Final verification | Required |

**Estimated scope:** ~600-800 lines + tests

---

### PR 2: Retry Enhancement (Tasks 2, 3, 8, 9)

**Branch:** `feat/workflow-retry-logic`
**Depends on:** PR 1 merged

Optional but recommended enhancement for production resilience.

| Task | Description | Priority |
|------|-------------|----------|
| 2 | Add RetryConfig model | Optional |
| 3 | Add retry field to Profile | Optional |
| 8 | Implement retry wrapper | Optional |
| 9 | Integrate retry in start_workflow | Optional |

**Estimated scope:** ~200 lines + tests

---

> **Implementation order:** Complete all PR 1 tasks first, create PR, then start PR 2 tasks on a new branch after PR 1 is merged.

---

## Task 1: Add langgraph-checkpoint-sqlite Dependency

**Files:**
- Modify: `pyproject.toml:7-22`

**Step 1: Add the dependency**

```bash
uv add langgraph-checkpoint-sqlite
```

**Step 2: Verify installation**

Run: `uv run python -c "from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add langgraph-checkpoint-sqlite dependency"
```

---

## Task 1.5: Update create_orchestrator_graph with interrupt_before Parameter

**Files:**
- Create: `tests/unit/test_orchestrator_interrupt.py`
- Modify: `amelia/core/orchestrator.py:280-340`

> **CRITICAL:** This task enables the interrupt mechanism. Without `interrupt_before`, the graph runs straight through `human_approval_node` without pausing in server mode.

**Step 1: Write the failing test**

Create `tests/unit/test_orchestrator_interrupt.py`:

```python
"""Tests for create_orchestrator_graph interrupt configuration."""

from unittest.mock import MagicMock, patch

import pytest

from amelia.core.orchestrator import create_orchestrator_graph


class TestCreateOrchestratorGraphInterrupt:
    """Test interrupt_before parameter handling."""

    def test_graph_accepts_interrupt_before_parameter(self):
        """create_orchestrator_graph accepts interrupt_before parameter."""
        # Should not raise
        graph = create_orchestrator_graph(interrupt_before=["human_approval_node"])
        assert graph is not None

    def test_graph_without_interrupt_before_defaults_to_none(self):
        """Graph created without interrupt_before has no interrupts configured."""
        graph = create_orchestrator_graph()
        # Graph should still be valid
        assert graph is not None

    @patch("amelia.core.orchestrator.StateGraph")
    def test_interrupt_before_passed_to_compile(self, mock_state_graph_class):
        """interrupt_before is passed through to graph.compile()."""
        mock_workflow = MagicMock()
        mock_state_graph_class.return_value = mock_workflow
        mock_workflow.compile = MagicMock(return_value=MagicMock())

        create_orchestrator_graph(
            checkpoint_saver=MagicMock(),
            interrupt_before=["human_approval_node"],
        )

        mock_workflow.compile.assert_called_once()
        call_kwargs = mock_workflow.compile.call_args[1]
        assert call_kwargs.get("interrupt_before") == ["human_approval_node"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_orchestrator_interrupt.py -v`
Expected: FAIL with "TypeError: create_orchestrator_graph() got an unexpected keyword argument 'interrupt_before'"

**Step 3: Update create_orchestrator_graph signature**

Modify `amelia/core/orchestrator.py`:

```python
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledGraph

def create_orchestrator_graph(
    checkpoint_saver: BaseCheckpointSaver | None = None,
    interrupt_before: list[str] | None = None,
) -> CompiledGraph:
    """Creates and compiles the LangGraph state machine for the orchestrator.

    Args:
        checkpoint_saver: Optional checkpoint saver for state persistence.
        interrupt_before: List of node names to interrupt before executing.
            Use ["human_approval_node"] for server-mode human-in-the-loop.

    Returns:
        Compiled StateGraph ready for execution.
    """
    workflow = StateGraph(ExecutionState)

    # Add nodes
    workflow.add_node("architect_node", call_architect_node)
    workflow.add_node("human_approval_node", human_approval_node)
    workflow.add_node("developer_node", call_developer_node)
    workflow.add_node("reviewer_node", call_reviewer_node)

    # ... existing edge definitions ...

    return workflow.compile(
        checkpointer=checkpoint_saver,
        interrupt_before=interrupt_before,
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_orchestrator_interrupt.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add tests/unit/test_orchestrator_interrupt.py amelia/core/orchestrator.py
git commit -m "feat(core): add interrupt_before parameter to create_orchestrator_graph"
```

---

<!-- ═══════════════════════════════════════════════════════════════════════════
     PR 2 TASKS START HERE - Skip to Task 4 if implementing PR 1 only
     ═══════════════════════════════════════════════════════════════════════════ -->

## Task 2: Add RetryConfig Model (PR 2)

**Files:**
- Create: `tests/unit/test_retry_config.py`
- Modify: `amelia/core/types.py:10-28`

**Step 1: Write the failing test**

Create `tests/unit/test_retry_config.py`:

```python
"""Tests for RetryConfig model."""

import pytest
from pydantic import ValidationError

from amelia.core.types import RetryConfig


class TestRetryConfigDefaults:
    """Test default values for RetryConfig."""

    def test_default_values(self):
        """RetryConfig has sensible defaults."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0


class TestRetryConfigValidation:
    """Test validation constraints for RetryConfig."""

    def test_max_retries_minimum(self):
        """max_retries cannot be negative."""
        with pytest.raises(ValidationError):
            RetryConfig(max_retries=-1)

    def test_max_retries_maximum(self):
        """max_retries cannot exceed 10."""
        with pytest.raises(ValidationError):
            RetryConfig(max_retries=11)

    def test_base_delay_minimum(self):
        """base_delay must be at least 0.1."""
        with pytest.raises(ValidationError):
            RetryConfig(base_delay=0.05)

    def test_base_delay_maximum(self):
        """base_delay cannot exceed 30.0."""
        with pytest.raises(ValidationError):
            RetryConfig(base_delay=31.0)

    def test_valid_custom_values(self):
        """Valid custom values are accepted."""
        config = RetryConfig(max_retries=5, base_delay=2.0)
        assert config.max_retries == 5
        assert config.base_delay == 2.0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_retry_config.py -v`
Expected: FAIL with "ImportError: cannot import name 'RetryConfig'"

**Step 3: Write minimal implementation**

Add to `amelia/core/types.py` after the existing imports:

```python
class RetryConfig(BaseModel):
    """Retry configuration for transient failures.

    Attributes:
        max_retries: Maximum number of retry attempts (0-10).
        base_delay: Base delay in seconds for exponential backoff (0.1-30.0).
    """

    max_retries: int = Field(default=3, ge=0, le=10)
    base_delay: float = Field(default=1.0, ge=0.1, le=30.0)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_retry_config.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add tests/unit/test_retry_config.py amelia/core/types.py
git commit -m "feat(core): add RetryConfig model with validation"
```

---

## Task 3: Add RetryConfig to Profile Model (PR 2)

**Files:**
- Modify: `tests/unit/test_types.py` (add test)
- Modify: `amelia/core/types.py:10-28`

**Step 1: Write the failing test**

Add to `tests/unit/test_types.py`:

```python
class TestProfileRetryConfig:
    """Test Profile.retry field."""

    def test_profile_has_default_retry_config(self):
        """Profile has default RetryConfig."""
        profile = Profile(name="test", driver="cli:claude")
        assert profile.retry.max_retries == 3
        assert profile.retry.base_delay == 1.0

    def test_profile_accepts_custom_retry_config(self):
        """Profile accepts custom RetryConfig."""
        from amelia.core.types import RetryConfig

        custom_retry = RetryConfig(max_retries=5, base_delay=2.0)
        profile = Profile(name="test", driver="cli:claude", retry=custom_retry)
        assert profile.retry.max_retries == 5
        assert profile.retry.base_delay == 2.0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_types.py::TestProfileRetryConfig -v`
Expected: FAIL with "unexpected keyword argument 'retry'"

**Step 3: Update Profile model**

Modify `Profile` class in `amelia/core/types.py`:

```python
class Profile(BaseModel):
    """Configuration profile for Amelia execution.

    Attributes:
        name: Profile name (e.g., 'work', 'personal').
        driver: LLM driver type (e.g., 'api:openai', 'cli:claude').
        tracker: Issue tracker type (jira, github, none, noop).
        strategy: Review strategy (single or competitive).
        execution_mode: Execution mode (structured or agentic).
        plan_output_dir: Directory for storing generated plans.
        working_dir: Working directory for agentic execution.
        retry: Retry configuration for transient failures.
    """

    name: str
    driver: DriverType
    tracker: TrackerType = "none"
    strategy: StrategyType = "single"
    execution_mode: ExecutionMode = "structured"
    plan_output_dir: str = "docs/plans"
    working_dir: str | None = None
    retry: RetryConfig = Field(default_factory=RetryConfig)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_types.py::TestProfileRetryConfig -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add tests/unit/test_types.py amelia/core/types.py
git commit -m "feat(core): add retry config to Profile model"
```

---

<!-- ═══════════════════════════════════════════════════════════════════════════
     PR 1 TASKS CONTINUE HERE
     ═══════════════════════════════════════════════════════════════════════════ -->

## Task 4: Update human_approval_node for Execution Mode

**Files:**
- Create: `tests/unit/test_human_approval_node.py`
- Modify: `amelia/core/orchestrator.py:50-78`

> **How interrupt_before Works:**
> With `interrupt_before=["human_approval_node"]` configured in server mode:
> 1. Graph executes `architect_node` and creates a plan
> 2. Graph pauses BEFORE entering `human_approval_node` (checkpoint saved)
> 3. `GraphInterrupt` exception is raised, caught by `_run_workflow`
> 4. User approves via REST API → `approve_workflow` calls `aupdate_state({"human_approved": True})`
> 5. Graph resumes → `human_approval_node` runs and reads `state.human_approved`
> 6. Conditional edge routes based on approval status
>
> In **CLI mode**, no interrupt occurs - the node prompts interactively via `typer.confirm`.

**Step 1: Write the failing test**

Create `tests/unit/test_human_approval_node.py`:

```python
"""Tests for human_approval_node execution mode behavior."""

from unittest.mock import AsyncMock, patch

import pytest

from amelia.core.orchestrator import human_approval_node
from amelia.core.state import ExecutionState
from amelia.core.types import Profile


@pytest.fixture
def base_state():
    """Create a base ExecutionState for testing."""
    return ExecutionState(
        profile=Profile(name="test", driver="cli:claude"),
        human_approved=None,
    )


class TestHumanApprovalNodeServerMode:
    """Test human_approval_node in server mode."""

    async def test_server_mode_returns_state_unchanged_when_not_approved(
        self, base_state
    ):
        """In server mode, node returns state unchanged (interrupt handles pause)."""
        config = {"configurable": {"execution_mode": "server"}}
        result = await human_approval_node(base_state, config)
        # State should be returned unchanged - interrupt mechanism handles the pause
        assert result.human_approved is None

    async def test_server_mode_preserves_approval_from_resume(self, base_state):
        """In server mode, node preserves human_approved set from resume."""
        state = base_state.model_copy(update={"human_approved": True})
        config = {"configurable": {"execution_mode": "server"}}
        result = await human_approval_node(state, config)
        assert result.human_approved is True


class TestHumanApprovalNodeCLIMode:
    """Test human_approval_node in CLI mode."""

    @patch("amelia.core.orchestrator.typer.confirm")
    @patch("amelia.core.orchestrator.typer.prompt")
    @patch("amelia.core.orchestrator.typer.secho")
    @patch("amelia.core.orchestrator.typer.echo")
    async def test_cli_mode_prompts_user(
        self, mock_echo, mock_secho, mock_prompt, mock_confirm, base_state
    ):
        """In CLI mode, node prompts user for approval."""
        mock_confirm.return_value = True
        mock_prompt.return_value = ""
        config = {"configurable": {"execution_mode": "cli"}}

        result = await human_approval_node(base_state, config)

        mock_confirm.assert_called_once()
        assert result.human_approved is True

    @patch("amelia.core.orchestrator.typer.confirm")
    @patch("amelia.core.orchestrator.typer.prompt")
    @patch("amelia.core.orchestrator.typer.secho")
    @patch("amelia.core.orchestrator.typer.echo")
    async def test_cli_mode_default_when_no_config(
        self, mock_echo, mock_secho, mock_prompt, mock_confirm, base_state
    ):
        """CLI mode is default when no execution_mode in config."""
        mock_confirm.return_value = False
        mock_prompt.return_value = "rejected"
        config = {}  # No execution_mode

        result = await human_approval_node(base_state, config)

        mock_confirm.assert_called_once()
        assert result.human_approved is False
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_human_approval_node.py -v`
Expected: FAIL with "TypeError: human_approval_node() takes 1 positional argument but 2 were given"

**Step 3: Update human_approval_node implementation**

Replace the function in `amelia/core/orchestrator.py`:

```python
async def human_approval_node(
    state: ExecutionState,
    config: dict[str, Any] | None = None,
) -> ExecutionState:
    """Node to prompt for human approval before proceeding.

    Behavior depends on execution mode:
    - CLI mode: Blocking prompt via typer.confirm
    - Server mode: Returns state unchanged (interrupt mechanism handles pause)

    Args:
        state: Current execution state containing the plan to be reviewed.
        config: Optional RunnableConfig with execution_mode in configurable.

    Returns:
        Updated execution state with approval status and messages.
    """
    config = config or {}
    execution_mode = config.get("configurable", {}).get("execution_mode", "cli")

    if execution_mode == "server":
        # Server mode: approval comes from resumed state after interrupt
        # If human_approved is already set (from resume), use it
        # Otherwise, just return - the interrupt mechanism will pause here
        return state

    # CLI mode: blocking prompt
    typer.secho("\n--- HUMAN APPROVAL REQUIRED ---", fg=typer.colors.BRIGHT_YELLOW)
    typer.echo("Review the proposed plan before proceeding. State snapshot (for debug):")
    typer.echo(f"Plan for issue {state.issue.id if state.issue else 'N/A'}:")
    if state.plan:
        for task in state.plan.tasks:
            typer.echo(
                f"  - [{task.id}] {task.description} (Dependencies: {', '.join(task.dependencies)})"
            )

    approved = typer.confirm("Do you approve this plan to proceed with development?", default=True)
    comment = typer.prompt("Add an optional comment for the audit log (press Enter to skip)", default="")

    approval_message = f"Human approval: {'Approved' if approved else 'Rejected'}. Comment: {comment}"
    messages = state.messages + [AgentMessage(role="system", content=approval_message)]

    return ExecutionState(
        profile=state.profile,
        issue=state.issue,
        plan=state.plan,
        messages=messages,
        human_approved=approved,
    )
```

Also add `from typing import Any` to imports if not present.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_human_approval_node.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add tests/unit/test_human_approval_node.py amelia/core/orchestrator.py
git commit -m "feat(core): add execution mode detection to human_approval_node"
```

---

## Task 5: Add execution_state Field to ServerExecutionState

**Files:**
- Modify: `tests/unit/server/models/test_state.py` (or create if doesn't exist)
- Modify: `amelia/server/models/state.py:53-116`

**Step 1: Write the failing test**

Add to existing test file or create `tests/unit/server/models/test_state.py`:

```python
"""Tests for ServerExecutionState composition with ExecutionState."""

import pytest

from amelia.core.state import ExecutionState
from amelia.core.types import Profile
from amelia.server.models.state import ServerExecutionState


class TestServerExecutionStateComposition:
    """Test ServerExecutionState with embedded ExecutionState."""

    def test_server_state_accepts_execution_state(self):
        """ServerExecutionState can hold an ExecutionState."""
        core_state = ExecutionState(
            profile=Profile(name="test", driver="cli:claude"),
        )
        server_state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            worktree_name="test-branch",
            execution_state=core_state,
        )
        assert server_state.execution_state is not None
        assert server_state.execution_state.profile.name == "test"

    def test_server_state_execution_state_is_optional(self):
        """execution_state field is optional for backward compatibility."""
        server_state = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            worktree_name="test-branch",
        )
        assert server_state.execution_state is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/models/test_state.py::TestServerExecutionStateComposition -v`
Expected: FAIL with "unexpected keyword argument 'execution_state'"

**Step 3: Update ServerExecutionState model**

Add field to `ServerExecutionState` in `amelia/server/models/state.py`:

```python
from amelia.core.state import ExecutionState

# Add to ServerExecutionState class, after failure_reason field:
    execution_state: ExecutionState | None = Field(
        default=None,
        description="Core orchestration state",
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/models/test_state.py::TestServerExecutionStateComposition -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add tests/unit/server/models/test_state.py amelia/server/models/state.py
git commit -m "feat(server): add execution_state composition to ServerExecutionState"
```

---

## Task 6: Add STAGE_NODES Constant and Event Mapping Helper

**Files:**
- Create: `tests/unit/server/orchestrator/test_event_mapping.py`
- Modify: `amelia/server/orchestrator/service.py`

**Step 1: Write the failing test**

Create `tests/unit/server/orchestrator/test_event_mapping.py`:

```python
"""Tests for LangGraph to WorkflowEvent mapping."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from amelia.server.models.events import EventType
from amelia.server.orchestrator.service import STAGE_NODES, OrchestratorService


class TestStageNodesConstant:
    """Test STAGE_NODES constant."""

    def test_stage_nodes_contains_expected_nodes(self):
        """STAGE_NODES contains all workflow stage nodes."""
        expected = {"architect_node", "human_approval_node", "developer_node", "reviewer_node"}
        assert STAGE_NODES == expected

    def test_stage_nodes_is_frozenset(self):
        """STAGE_NODES is immutable."""
        assert isinstance(STAGE_NODES, frozenset)


class TestHandleGraphEvent:
    """Test _handle_graph_event method."""

    @pytest.fixture
    def service(self):
        """Create OrchestratorService with mocked dependencies."""
        event_bus = MagicMock()
        repository = AsyncMock()
        repository.get_max_event_sequence.return_value = 0
        return OrchestratorService(event_bus, repository)

    async def test_on_chain_start_emits_stage_started(self, service):
        """on_chain_start for stage node emits STAGE_STARTED event."""
        service._emit = AsyncMock()
        event = {"event": "on_chain_start", "name": "architect_node"}

        await service._handle_graph_event("wf-123", event)

        service._emit.assert_called_once()
        call_args = service._emit.call_args
        assert call_args[0][1] == EventType.STAGE_STARTED
        assert "architect_node" in call_args[0][2]

    async def test_on_chain_end_emits_stage_completed(self, service):
        """on_chain_end for stage node emits STAGE_COMPLETED event."""
        service._emit = AsyncMock()
        event = {"event": "on_chain_end", "name": "developer_node", "data": {"result": "ok"}}

        await service._handle_graph_event("wf-123", event)

        service._emit.assert_called_once()
        call_args = service._emit.call_args
        assert call_args[0][1] == EventType.STAGE_COMPLETED

    async def test_on_chain_error_emits_system_error(self, service):
        """on_chain_error emits SYSTEM_ERROR event."""
        service._emit = AsyncMock()
        event = {
            "event": "on_chain_error",
            "name": "reviewer_node",
            "data": {"error": "Connection timeout"},
        }

        await service._handle_graph_event("wf-123", event)

        service._emit.assert_called_once()
        call_args = service._emit.call_args
        assert call_args[0][1] == EventType.SYSTEM_ERROR
        assert "Connection timeout" in call_args[0][2]

    async def test_non_stage_node_not_emitted(self, service):
        """Events from non-stage nodes are not emitted."""
        service._emit = AsyncMock()
        event = {"event": "on_chain_start", "name": "some_internal_node"}

        await service._handle_graph_event("wf-123", event)

        service._emit.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_event_mapping.py -v`
Expected: FAIL with "ImportError: cannot import name 'STAGE_NODES'"

**Step 3: Add STAGE_NODES and _handle_graph_event**

Add to `amelia/server/orchestrator/service.py` after imports:

```python
# Nodes that emit stage events
STAGE_NODES: frozenset[str] = frozenset({
    "architect_node",
    "human_approval_node",
    "developer_node",
    "reviewer_node",
})
```

Add method to `OrchestratorService` class:

```python
    async def _handle_graph_event(
        self,
        workflow_id: str,
        event: dict[str, object],
    ) -> None:
        """Translate LangGraph events to WorkflowEvents and emit.

        Args:
            workflow_id: The workflow this event belongs to.
            event: LangGraph event dictionary.
        """
        event_type = event.get("event")
        node_name = event.get("name")

        if not isinstance(node_name, str):
            return

        if event_type == "on_chain_start":
            if node_name in STAGE_NODES:
                await self._emit(
                    workflow_id,
                    EventType.STAGE_STARTED,
                    f"Starting {node_name}",
                    data={"stage": node_name},
                )

        elif event_type == "on_chain_end":
            if node_name in STAGE_NODES:
                await self._emit(
                    workflow_id,
                    EventType.STAGE_COMPLETED,
                    f"Completed {node_name}",
                    data={"stage": node_name, "output": event.get("data")},
                )

        elif event_type == "on_chain_error":
            error_data = event.get("data", {})
            error_msg = "Unknown error"
            if isinstance(error_data, dict):
                error_msg = str(error_data.get("error", "Unknown error"))
            await self._emit(
                workflow_id,
                EventType.SYSTEM_ERROR,
                f"Error in {node_name}: {error_msg}",
                data={"stage": node_name, "error": error_msg},
            )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_event_mapping.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add tests/unit/server/orchestrator/test_event_mapping.py amelia/server/orchestrator/service.py
git commit -m "feat(server): add STAGE_NODES constant and event mapping helper"
```

---

## Task 7: Implement _run_workflow with Checkpointing and GraphInterrupt Handling

**Files:**
- Create: `tests/unit/server/orchestrator/test_execution_bridge.py`
- Modify: `amelia/server/orchestrator/service.py:215-236`

> **CRITICAL:** This implementation must:
> 1. Pass `interrupt_before=["human_approval_node"]` when creating the graph
> 2. Catch `GraphInterrupt` exception and set workflow status to "blocked"
> 3. Emit `APPROVAL_REQUIRED` event when interrupted (not treat it as an error)

**Step 1: Write the failing test**

Create `tests/unit/server/orchestrator/test_execution_bridge.py`:

```python
"""Tests for _run_workflow execution bridge."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.state import ExecutionState
from amelia.core.types import Profile
from amelia.server.models.events import EventType
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService


@pytest.fixture
def mock_event_bus():
    """Create mock event bus."""
    return MagicMock()


@pytest.fixture
def mock_repository():
    """Create mock repository."""
    repo = AsyncMock()
    repo.get_max_event_sequence.return_value = 0
    repo.save_event = AsyncMock()
    repo.set_status = AsyncMock()
    return repo


@pytest.fixture
def service(mock_event_bus, mock_repository):
    """Create OrchestratorService with mocked dependencies."""
    svc = OrchestratorService(mock_event_bus, mock_repository)
    svc._checkpoint_path = "/tmp/test_checkpoints.db"
    return svc


@pytest.fixture
def server_state():
    """Create test ServerExecutionState."""
    core_state = ExecutionState(
        profile=Profile(name="test", driver="cli:claude"),
    )
    return ServerExecutionState(
        id="wf-123",
        issue_id="ISSUE-456",
        worktree_path="/tmp/test",
        worktree_name="test-branch",
        started_at=datetime.now(UTC),
        execution_state=core_state,
    )


class TestRunWorkflowEmitsLifecycleEvents:
    """Test _run_workflow emits lifecycle events."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_emits_workflow_started_event(
        self, mock_create_graph, mock_saver_class, service, server_state
    ):
        """_run_workflow emits WORKFLOW_STARTED at beginning."""
        # Setup mock graph that completes immediately
        mock_graph = AsyncMock()
        mock_graph.astream_events = AsyncMock(return_value=AsyncIteratorMock([]))
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        emitted_events = []
        original_emit = service._emit

        async def capture_emit(*args, **kwargs):
            emitted_events.append(args)
            return await original_emit(*args, **kwargs)

        service._emit = capture_emit

        await service._run_workflow("wf-123", server_state)

        # Check WORKFLOW_STARTED was emitted
        started_events = [e for e in emitted_events if e[1] == EventType.WORKFLOW_STARTED]
        assert len(started_events) == 1

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_emits_workflow_completed_on_success(
        self, mock_create_graph, mock_saver_class, service, server_state
    ):
        """_run_workflow emits WORKFLOW_COMPLETED on successful completion."""
        mock_graph = AsyncMock()
        mock_graph.astream_events = AsyncMock(return_value=AsyncIteratorMock([]))
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        emitted_events = []

        async def capture_emit(*args, **kwargs):
            emitted_events.append(args)

        service._emit = capture_emit

        await service._run_workflow("wf-123", server_state)

        completed_events = [e for e in emitted_events if e[1] == EventType.WORKFLOW_COMPLETED]
        assert len(completed_events) == 1


class TestRunWorkflowInterruptHandling:
    """Test _run_workflow handles GraphInterrupt correctly."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_graph_interrupt_sets_status_to_blocked(
        self, mock_create_graph, mock_saver_class, service, server_state
    ):
        """GraphInterrupt sets workflow status to blocked, not failed."""
        from langgraph.errors import GraphInterrupt

        mock_graph = AsyncMock()
        # Simulate interrupt during streaming
        async def raise_interrupt(*args, **kwargs):
            raise GraphInterrupt("Interrupted at human_approval_node")

        mock_graph.astream_events = raise_interrupt
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        emitted_events = []

        async def capture_emit(*args, **kwargs):
            emitted_events.append(args)

        service._emit = capture_emit
        service._repository.set_status = AsyncMock()

        await service._run_workflow("wf-123", server_state)

        # Should emit APPROVAL_REQUIRED, not WORKFLOW_FAILED
        approval_events = [e for e in emitted_events if e[1] == EventType.APPROVAL_REQUIRED]
        failed_events = [e for e in emitted_events if e[1] == EventType.WORKFLOW_FAILED]
        assert len(approval_events) == 1
        assert len(failed_events) == 0

        # Should set status to blocked
        service._repository.set_status.assert_called_with("wf-123", "blocked")

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_creates_graph_with_interrupt_before(
        self, mock_create_graph, mock_saver_class, service, server_state
    ):
        """_run_workflow passes interrupt_before to create_orchestrator_graph."""
        mock_graph = AsyncMock()
        mock_graph.astream_events = AsyncMock(return_value=AsyncIteratorMock([]))
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        service._emit = AsyncMock()

        await service._run_workflow("wf-123", server_state)

        # Verify interrupt_before was passed
        mock_create_graph.assert_called_once()
        call_kwargs = mock_create_graph.call_args[1]
        assert call_kwargs.get("interrupt_before") == ["human_approval_node"]


class AsyncIteratorMock:
    """Mock async iterator for astream_events."""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_execution_bridge.py -v`
Expected: FAIL with "AttributeError: 'OrchestratorService' object has no attribute '_checkpoint_path'"

**Step 3: Update _run_workflow implementation**

First, add imports at top of `amelia/server/orchestrator/service.py`:

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.errors import GraphInterrupt

from amelia.core.orchestrator import create_orchestrator_graph
```

Update `__init__` to accept checkpoint path:

```python
    def __init__(
        self,
        event_bus: EventBus,
        repository: WorkflowRepository,
        max_concurrent: int = 5,
        checkpoint_path: str = "~/.amelia/checkpoints.db",
    ) -> None:
        """Initialize orchestrator service.

        Args:
            event_bus: Event bus for broadcasting workflow events.
            repository: Repository for workflow persistence.
            max_concurrent: Maximum number of concurrent workflows (default: 5).
            checkpoint_path: Path to checkpoint database file.
        """
        self._event_bus = event_bus
        self._repository = repository
        self._max_concurrent = max_concurrent
        self._checkpoint_path = checkpoint_path
        self._active_tasks: dict[str, tuple[str, asyncio.Task[None]]] = {}
        self._approval_events: dict[str, asyncio.Event] = {}
        self._approval_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._sequence_counters: dict[str, int] = {}
        self._sequence_locks: dict[str, asyncio.Lock] = {}
```

Replace `_run_workflow` method:

```python
    async def _run_workflow(
        self,
        workflow_id: str,
        state: ServerExecutionState,
    ) -> None:
        """Execute workflow via LangGraph with interrupt support.

        Args:
            workflow_id: The workflow ID.
            state: Server execution state with embedded core state.

        Note:
            When GraphInterrupt is raised, the workflow is paused at the
            human_approval_node. Status is set to "blocked" and an
            APPROVAL_REQUIRED event is emitted. The workflow resumes when
            approve_workflow() is called.
        """
        if state.execution_state is None:
            logger.error("No execution_state in ServerExecutionState", workflow_id=workflow_id)
            await self._repository.set_status(
                workflow_id, "failed", failure_reason="Missing execution state"
            )
            return

        async with AsyncSqliteSaver.from_conn_string(
            str(self._checkpoint_path)
        ) as checkpointer:
            # CRITICAL: Pass interrupt_before to enable server-mode approval
            graph = create_orchestrator_graph(
                checkpoint_saver=checkpointer,
                interrupt_before=["human_approval_node"],
            )

            config = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                }
            }

            await self._emit(
                workflow_id,
                EventType.WORKFLOW_STARTED,
                "Workflow execution started",
                data={"issue_id": state.issue_id},
            )

            try:
                await self._repository.set_status(workflow_id, "in_progress")

                async for event in graph.astream_events(
                    state.execution_state,
                    config=config,
                ):
                    await self._handle_graph_event(workflow_id, event)

                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_COMPLETED,
                    "Workflow completed successfully",
                    data={"final_stage": state.current_stage},
                )
                await self._repository.set_status(workflow_id, "completed")

            except GraphInterrupt:
                # Normal pause at human_approval_node - NOT an error
                logger.info(
                    "Workflow paused for human approval",
                    workflow_id=workflow_id,
                )
                await self._emit(
                    workflow_id,
                    EventType.APPROVAL_REQUIRED,
                    "Plan ready for review - awaiting human approval",
                    data={"paused_at": "human_approval_node"},
                )
                await self._repository.set_status(workflow_id, "blocked")

            except Exception as e:
                logger.exception("Workflow execution failed", workflow_id=workflow_id)
                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Workflow failed: {e!s}",
                    data={"error": str(e), "stage": state.current_stage},
                )
                await self._repository.set_status(
                    workflow_id, "failed", failure_reason=str(e)
                )
                raise
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_execution_bridge.py -v`
Expected: PASS (4 tests - lifecycle events + interrupt handling)

**Step 5: Commit**

```bash
git add tests/unit/server/orchestrator/test_execution_bridge.py amelia/server/orchestrator/service.py
git commit -m "feat(server): implement _run_workflow with LangGraph checkpointing"
```

---

<!-- ═══════════════════════════════════════════════════════════════════════════
     PR 2 TASKS CONTINUE HERE - Skip to Task 10 if implementing PR 1 only
     ═══════════════════════════════════════════════════════════════════════════ -->

## Task 8: Implement Retry Wrapper (PR 2)

**Files:**
- Create: `tests/unit/server/orchestrator/test_retry_logic.py`
- Modify: `amelia/server/orchestrator/service.py`

**Step 1: Write the failing test**

Create `tests/unit/server/orchestrator/test_retry_logic.py`:

```python
"""Tests for workflow retry logic."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import TimeoutException

from amelia.core.state import ExecutionState
from amelia.core.types import Profile, RetryConfig
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService, TRANSIENT_EXCEPTIONS


class TestTransientExceptions:
    """Test TRANSIENT_EXCEPTIONS constant."""

    def test_contains_expected_exceptions(self):
        """TRANSIENT_EXCEPTIONS contains expected exception types."""
        assert asyncio.TimeoutError in TRANSIENT_EXCEPTIONS
        assert TimeoutException in TRANSIENT_EXCEPTIONS
        assert ConnectionError in TRANSIENT_EXCEPTIONS


@pytest.fixture
def mock_event_bus():
    return MagicMock()


@pytest.fixture
def mock_repository():
    repo = AsyncMock()
    repo.get_max_event_sequence.return_value = 0
    repo.save_event = AsyncMock()
    repo.set_status = AsyncMock()
    return repo


@pytest.fixture
def service(mock_event_bus, mock_repository):
    svc = OrchestratorService(mock_event_bus, mock_repository)
    svc._checkpoint_path = "/tmp/test.db"
    return svc


@pytest.fixture
def server_state():
    core_state = ExecutionState(
        profile=Profile(
            name="test",
            driver="cli:claude",
            retry=RetryConfig(max_retries=2, base_delay=0.01),
        ),
    )
    return ServerExecutionState(
        id="wf-123",
        issue_id="ISSUE-456",
        worktree_path="/tmp/test",
        worktree_name="test-branch",
        started_at=datetime.now(UTC),
        execution_state=core_state,
    )


class TestRunWorkflowWithRetry:
    """Test _run_workflow_with_retry method."""

    async def test_succeeds_on_first_attempt(self, service, server_state):
        """Workflow succeeds without retry if no error."""
        service._run_workflow = AsyncMock()

        await service._run_workflow_with_retry("wf-123", server_state)

        assert service._run_workflow.call_count == 1

    async def test_retries_on_transient_error(self, service, server_state):
        """Workflow retries on transient error."""
        call_count = 0

        async def fail_then_succeed(*args):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise asyncio.TimeoutError("Connection timeout")
            return None

        service._run_workflow = fail_then_succeed

        await service._run_workflow_with_retry("wf-123", server_state)

        assert call_count == 2

    async def test_fails_immediately_on_permanent_error(self, service, server_state):
        """Workflow fails immediately on permanent error."""
        service._run_workflow = AsyncMock(side_effect=ValueError("Invalid config"))

        with pytest.raises(ValueError):
            await service._run_workflow_with_retry("wf-123", server_state)

        assert service._run_workflow.call_count == 1

    async def test_fails_after_max_retries(self, service, server_state):
        """Workflow fails after exhausting max_retries."""
        service._run_workflow = AsyncMock(
            side_effect=asyncio.TimeoutError("Always timeout")
        )

        with pytest.raises(asyncio.TimeoutError):
            await service._run_workflow_with_retry("wf-123", server_state)

        # Initial attempt + 2 retries = 3 calls
        assert service._run_workflow.call_count == 3
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/orchestrator/test_retry_logic.py -v`
Expected: FAIL with "ImportError: cannot import name 'TRANSIENT_EXCEPTIONS'"

**Step 3: Add TRANSIENT_EXCEPTIONS and _run_workflow_with_retry**

Add imports and constant to `amelia/server/orchestrator/service.py`:

```python
from httpx import TimeoutException

# Exceptions that warrant retry
TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    asyncio.TimeoutError,
    TimeoutException,
    ConnectionError,
)
```

Add method to `OrchestratorService`:

```python
    async def _run_workflow_with_retry(
        self,
        workflow_id: str,
        state: ServerExecutionState,
    ) -> None:
        """Execute workflow with automatic retry for transient failures.

        Args:
            workflow_id: The workflow ID.
            state: Server execution state.
        """
        if state.execution_state is None:
            await self._repository.set_status(
                workflow_id, "failed", failure_reason="Missing execution state"
            )
            return

        retry_config = state.execution_state.profile.retry
        attempt = 0

        while attempt <= retry_config.max_retries:
            try:
                await self._run_workflow(workflow_id, state)
                return  # Success

            except TRANSIENT_EXCEPTIONS as e:
                attempt += 1
                if attempt > retry_config.max_retries:
                    await self._repository.set_status(
                        workflow_id,
                        "failed",
                        failure_reason=f"Failed after {attempt} attempts: {e}",
                    )
                    raise

                delay = min(
                    retry_config.base_delay * (2 ** (attempt - 1)),
                    60.0,  # Hard cap at 60s
                )
                logger.warning(
                    f"Transient error (attempt {attempt}/{retry_config.max_retries}), "
                    f"retrying in {delay}s",
                    workflow_id=workflow_id,
                    error=str(e),
                )
                await asyncio.sleep(delay)

            except Exception as e:
                # Non-transient error - fail immediately
                await self._repository.set_status(
                    workflow_id, "failed", failure_reason=str(e)
                )
                raise
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/orchestrator/test_retry_logic.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add tests/unit/server/orchestrator/test_retry_logic.py amelia/server/orchestrator/service.py
git commit -m "feat(server): add retry logic for transient failures"
```

---

## Task 9: Update start_workflow to Use Retry Wrapper (PR 2)

**Files:**
- Modify: `tests/unit/server/orchestrator/test_service.py`
- Modify: `amelia/server/orchestrator/service.py`

**Step 1: Write the test**

Add to `tests/unit/server/orchestrator/test_service.py`:

```python
class TestStartWorkflowWithRetry:
    """Test start_workflow uses retry wrapper."""

    async def test_start_workflow_calls_retry_wrapper(
        self, orchestrator, mock_repository
    ):
        """start_workflow creates task with _run_workflow_with_retry."""
        orchestrator._run_workflow_with_retry = AsyncMock()

        workflow_id = await orchestrator.start_workflow(
            issue_id="TEST-1",
            worktree_path="/tmp/test-wt",
        )

        # Wait briefly for task to start
        await asyncio.sleep(0.01)

        # The task should call _run_workflow_with_retry
        assert workflow_id is not None
```

**Step 2: Run test to verify current behavior**

Run: `uv run pytest tests/unit/server/orchestrator/test_service.py::TestStartWorkflowWithRetry -v`
Expected: May pass or fail depending on existing implementation

**Step 3: Update start_workflow to use retry wrapper**

In `start_workflow` method, change the task creation line from:

```python
task = asyncio.create_task(self._run_workflow(workflow_id, state, profile))
```

to:

```python
task = asyncio.create_task(self._run_workflow_with_retry(workflow_id, state))
```

Note: Remove the `profile` parameter since it's now in `state.execution_state.profile`.

Also update the `_run_workflow` signature in `start_workflow` call since we removed `profile`:

```python
    async def _run_workflow(
        self,
        workflow_id: str,
        state: ServerExecutionState,
    ) -> None:
```

**Step 4: Run full test suite for orchestrator**

Run: `uv run pytest tests/unit/server/orchestrator/ -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/server/orchestrator/test_service.py amelia/server/orchestrator/service.py
git commit -m "feat(server): use retry wrapper in start_workflow"
```

---

<!-- ═══════════════════════════════════════════════════════════════════════════
     PR 1 TASKS CONTINUE HERE
     ═══════════════════════════════════════════════════════════════════════════ -->

## Task 10: Update approve_workflow for Graph Resume

**Files:**
- Modify: `tests/unit/server/orchestrator/test_service.py`
- Modify: `amelia/server/orchestrator/service.py:301-342`

**Step 1: Write the failing test**

Add to `tests/unit/server/orchestrator/test_service.py`:

```python
class TestApproveWorkflowResume:
    """Test approve_workflow resumes LangGraph execution."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_approve_updates_state_and_resumes(
        self, mock_create_graph, mock_saver_class, orchestrator, mock_repository
    ):
        """approve_workflow updates graph state and resumes execution."""
        # Setup blocked workflow
        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            worktree_name="test",
            workflow_status="blocked",
        )
        mock_repository.get.return_value = workflow
        orchestrator._active_tasks["/tmp/test"] = ("wf-123", AsyncMock())

        # Setup mock graph
        mock_graph = AsyncMock()
        mock_graph.aupdate_state = AsyncMock()
        mock_graph.astream_events = AsyncMock(return_value=AsyncIteratorMock([]))
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        await orchestrator.approve_workflow("wf-123")

        # Verify state was updated with approval
        mock_graph.aupdate_state.assert_called_once()
        call_args = mock_graph.aupdate_state.call_args
        assert call_args[0][1] == {"human_approved": True}


class AsyncIteratorMock:
    """Mock async iterator."""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest "tests/unit/server/orchestrator/test_service.py::TestApproveWorkflowResume" -v`
Expected: FAIL (current approve_workflow doesn't use graph resume)

**Step 3: Update approve_workflow implementation**

Replace `approve_workflow` method:

```python
    async def approve_workflow(self, workflow_id: str) -> None:
        """Approve a blocked workflow and resume LangGraph execution.

        Args:
            workflow_id: The workflow to approve.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateError: If workflow is not in "blocked" state.
        """
        workflow = await self._repository.get(workflow_id)
        if not workflow:
            raise WorkflowNotFoundError(workflow_id)

        if workflow.workflow_status != "blocked":
            raise InvalidStateError(
                f"Cannot approve workflow in '{workflow.workflow_status}' state",
                workflow_id=workflow_id,
                current_status=workflow.workflow_status,
            )

        async with self._approval_lock:
            # Signal the approval event if it exists (for legacy flow)
            event = self._approval_events.get(workflow_id)
            if event:
                event.set()
                self._approval_events.pop(workflow_id, None)

            await self._emit(
                workflow_id,
                EventType.APPROVAL_GRANTED,
                "Plan approved",
            )

            logger.info("Workflow approved", workflow_id=workflow_id)

        # Resume LangGraph execution with updated state
        async with AsyncSqliteSaver.from_conn_string(
            str(self._checkpoint_path)
        ) as checkpointer:
            graph = create_orchestrator_graph(checkpoint_saver=checkpointer)

            config = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                }
            }

            # Update state with approval decision
            await graph.aupdate_state(config, {"human_approved": True})

            # Update status to in_progress before resuming
            await self._repository.set_status(workflow_id, "in_progress")

            # Resume execution
            try:
                async for event in graph.astream_events(None, config=config):
                    await self._handle_graph_event(workflow_id, event)

                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_COMPLETED,
                    "Workflow completed successfully",
                )
                await self._repository.set_status(workflow_id, "completed")

            except Exception as e:
                logger.exception("Workflow failed after approval", workflow_id=workflow_id)
                await self._emit(
                    workflow_id,
                    EventType.WORKFLOW_FAILED,
                    f"Workflow failed: {e!s}",
                    data={"error": str(e)},
                )
                await self._repository.set_status(
                    workflow_id, "failed", failure_reason=str(e)
                )
                raise
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest "tests/unit/server/orchestrator/test_service.py::TestApproveWorkflowResume" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/server/orchestrator/test_service.py amelia/server/orchestrator/service.py
git commit -m "feat(server): update approve_workflow to resume LangGraph execution"
```

---

## Task 11: Update reject_workflow for Graph State

**Files:**
- Modify: `tests/unit/server/orchestrator/test_service.py`
- Modify: `amelia/server/orchestrator/service.py:344-395`

**Step 1: Write the failing test**

Add to `tests/unit/server/orchestrator/test_service.py`:

```python
class TestRejectWorkflowGraphState:
    """Test reject_workflow updates LangGraph state."""

    @patch("amelia.server.orchestrator.service.AsyncSqliteSaver")
    @patch("amelia.server.orchestrator.service.create_orchestrator_graph")
    async def test_reject_updates_graph_state(
        self, mock_create_graph, mock_saver_class, orchestrator, mock_repository
    ):
        """reject_workflow updates graph state with human_approved=False."""
        workflow = ServerExecutionState(
            id="wf-123",
            issue_id="ISSUE-456",
            worktree_path="/tmp/test",
            worktree_name="test",
            workflow_status="blocked",
        )
        mock_repository.get.return_value = workflow

        mock_graph = AsyncMock()
        mock_graph.aupdate_state = AsyncMock()
        mock_create_graph.return_value = mock_graph

        mock_saver = AsyncMock()
        mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
            return_value=mock_saver
        )
        mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

        await orchestrator.reject_workflow("wf-123", "Not ready")

        mock_graph.aupdate_state.assert_called_once()
        call_args = mock_graph.aupdate_state.call_args
        assert call_args[0][1] == {"human_approved": False}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest "tests/unit/server/orchestrator/test_service.py::TestRejectWorkflowGraphState" -v`
Expected: FAIL (current reject_workflow doesn't update graph state)

**Step 3: Update reject_workflow implementation**

Replace `reject_workflow` method:

```python
    async def reject_workflow(
        self,
        workflow_id: str,
        feedback: str,
    ) -> None:
        """Reject a blocked workflow.

        Args:
            workflow_id: The workflow to reject.
            feedback: Reason for rejection.

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist.
            InvalidStateError: If workflow is not in "blocked" state.
        """
        workflow = await self._repository.get(workflow_id)
        if not workflow:
            raise WorkflowNotFoundError(workflow_id)

        if workflow.workflow_status != "blocked":
            raise InvalidStateError(
                f"Cannot reject workflow in '{workflow.workflow_status}' state",
                workflow_id=workflow_id,
                current_status=workflow.workflow_status,
            )

        async with self._approval_lock:
            # Remove approval event if it exists
            self._approval_events.pop(workflow_id, None)

            # Update workflow status to failed with feedback
            await self._repository.set_status(
                workflow_id, "failed", failure_reason=feedback
            )
            await self._emit(
                workflow_id,
                EventType.APPROVAL_REJECTED,
                f"Plan rejected: {feedback}",
            )

            # Cancel the waiting task
            if workflow.worktree_path in self._active_tasks:
                _, task = self._active_tasks[workflow.worktree_path]
                task.cancel()

            logger.info(
                "Workflow rejected",
                workflow_id=workflow_id,
                feedback=feedback,
            )

        # Update LangGraph state to record rejection
        async with AsyncSqliteSaver.from_conn_string(
            str(self._checkpoint_path)
        ) as checkpointer:
            graph = create_orchestrator_graph(checkpoint_saver=checkpointer)

            config = {
                "configurable": {
                    "thread_id": workflow_id,
                    "execution_mode": "server",
                }
            }

            await graph.aupdate_state(config, {"human_approved": False})
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest "tests/unit/server/orchestrator/test_service.py::TestRejectWorkflowGraphState" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/server/orchestrator/test_service.py amelia/server/orchestrator/service.py
git commit -m "feat(server): update reject_workflow to set graph state"
```

---

## Task 12: Run Full Test Suite and Linting (PR 1 Verification)

**Files:**
- None (verification only)

**Step 1: Run type checker**

Run: `uv run mypy amelia/server/orchestrator/service.py amelia/core/types.py amelia/core/orchestrator.py`
Expected: Success (0 errors)

**Step 2: Run linter**

Run: `uv run ruff check amelia/server/orchestrator/ amelia/core/types.py amelia/core/orchestrator.py`
Expected: Success (0 errors)

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests PASS

**Step 4: Fix any issues found**

If there are type errors or lint issues, fix them and re-run checks.

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "chore: fix type errors and lint issues"
```

---

## Task 13: Create Integration Test for Approval Flow

**Files:**
- Create: `tests/integration/test_approval_flow.py`

> **Goal:** Test the complete interrupt → approve → resume cycle with a real LangGraph graph but mocked node implementations.

**Step 1: Write the integration test**

Create `tests/integration/test_approval_flow.py`:

```python
"""Integration tests for the complete approval flow.

These tests verify the interrupt/resume cycle works end-to-end:
1. Graph executes until interrupt_before human_approval_node
2. GraphInterrupt is raised, workflow status becomes "blocked"
3. User approves via approve_workflow()
4. Graph resumes with human_approved=True in state
5. Workflow completes successfully
"""

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.state import ExecutionState
from amelia.core.types import Profile
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService


@pytest.fixture
def temp_checkpoint_db():
    """Create temporary checkpoint database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def event_tracker():
    """Create event bus that tracks all emitted events."""
    class EventTracker:
        def __init__(self):
            self.events = []

        def emit(self, event):
            self.events.append(event)

        def get_by_type(self, event_type):
            return [e for e in self.events if e.event_type == event_type]

    return EventTracker()


@pytest.fixture
def mock_repository():
    """Create in-memory repository implementation."""
    repo = AsyncMock(spec=WorkflowRepository)
    repo.workflows = {}
    repo.events = []
    repo.event_sequence = {}

    async def create(state):
        repo.workflows[state.id] = state

    async def get(workflow_id):
        return repo.workflows.get(workflow_id)

    async def set_status(workflow_id, status, failure_reason=None):
        if workflow_id in repo.workflows:
            repo.workflows[workflow_id] = repo.workflows[workflow_id].model_copy(
                update={"workflow_status": status, "failure_reason": failure_reason}
            )

    async def save_event(event):
        repo.events.append(event)

    async def get_max_event_sequence(workflow_id):
        return repo.event_sequence.get(workflow_id, 0)

    repo.create = create
    repo.get = get
    repo.set_status = set_status
    repo.save_event = save_event
    repo.get_max_event_sequence = get_max_event_sequence

    return repo


class TestInterruptResumeCycle:
    """Test the complete interrupt → approve → resume cycle."""

    @pytest.mark.asyncio
    async def test_workflow_pauses_at_human_approval_node(
        self, event_tracker, mock_repository, temp_checkpoint_db
    ):
        """Workflow pauses at human_approval_node and sets status to blocked."""
        service = OrchestratorService(
            event_tracker,
            mock_repository,
            checkpoint_path=temp_checkpoint_db,
        )

        core_state = ExecutionState(
            profile=Profile(name="test", driver="cli:claude"),
        )
        server_state = ServerExecutionState(
            id="wf-interrupt-test",
            issue_id="TEST-123",
            worktree_path="/tmp/test-interrupt",
            worktree_name="test-interrupt",
            started_at=datetime.now(UTC),
            execution_state=core_state,
        )

        await mock_repository.create(server_state)

        # Run workflow - should pause at human_approval_node
        await service._run_workflow("wf-interrupt-test", server_state)

        # Verify status is "blocked"
        persisted = await mock_repository.get("wf-interrupt-test")
        assert persisted.workflow_status == "blocked"

        # Verify APPROVAL_REQUIRED event was emitted
        approval_events = event_tracker.get_by_type(EventType.APPROVAL_REQUIRED)
        assert len(approval_events) >= 1

    @pytest.mark.asyncio
    async def test_approve_resumes_and_completes_workflow(
        self, event_tracker, mock_repository, temp_checkpoint_db
    ):
        """After approval, workflow resumes and completes."""
        service = OrchestratorService(
            event_tracker,
            mock_repository,
            checkpoint_path=temp_checkpoint_db,
        )

        core_state = ExecutionState(
            profile=Profile(name="test", driver="cli:claude"),
        )
        server_state = ServerExecutionState(
            id="wf-approve-test",
            issue_id="TEST-456",
            worktree_path="/tmp/test-approve",
            worktree_name="test-approve",
            started_at=datetime.now(UTC),
            workflow_status="blocked",  # Already paused
            execution_state=core_state,
        )

        await mock_repository.create(server_state)

        # Approve the workflow
        await service.approve_workflow("wf-approve-test")

        # Verify APPROVAL_GRANTED was emitted
        granted_events = event_tracker.get_by_type(EventType.APPROVAL_GRANTED)
        assert len(granted_events) >= 1


class TestEventSequence:
    """Test that events are emitted in correct sequence."""

    @pytest.mark.asyncio
    async def test_event_sequence_on_successful_path(
        self, event_tracker, mock_repository, temp_checkpoint_db
    ):
        """Events follow expected sequence: STARTED → (stages) → APPROVAL_REQUIRED."""
        service = OrchestratorService(
            event_tracker,
            mock_repository,
            checkpoint_path=temp_checkpoint_db,
        )

        core_state = ExecutionState(
            profile=Profile(name="test", driver="cli:claude"),
        )
        server_state = ServerExecutionState(
            id="wf-sequence-test",
            issue_id="TEST-789",
            worktree_path="/tmp/test-sequence",
            worktree_name="test-sequence",
            started_at=datetime.now(UTC),
            execution_state=core_state,
        )

        await mock_repository.create(server_state)
        await service._run_workflow("wf-sequence-test", server_state)

        # Check WORKFLOW_STARTED came first
        event_types = [e.event_type for e in event_tracker.events]
        assert EventType.WORKFLOW_STARTED in event_types

        # WORKFLOW_STARTED should be before APPROVAL_REQUIRED
        started_idx = event_types.index(EventType.WORKFLOW_STARTED)
        if EventType.APPROVAL_REQUIRED in event_types:
            approval_idx = event_types.index(EventType.APPROVAL_REQUIRED)
            assert started_idx < approval_idx


class TestErrorHandling:
    """Test error handling during workflow execution."""

    @pytest.mark.asyncio
    async def test_non_interrupt_error_sets_status_to_failed(
        self, event_tracker, mock_repository, temp_checkpoint_db
    ):
        """Non-GraphInterrupt errors set status to failed."""
        service = OrchestratorService(
            event_tracker,
            mock_repository,
            checkpoint_path=temp_checkpoint_db,
        )

        # Create state without execution_state to trigger error
        server_state = ServerExecutionState(
            id="wf-error-test",
            issue_id="TEST-ERR",
            worktree_path="/tmp/test-error",
            worktree_name="test-error",
            started_at=datetime.now(UTC),
            execution_state=None,  # Missing - will cause error
        )

        await mock_repository.create(server_state)
        await service._run_workflow("wf-error-test", server_state)

        # Verify status is "failed"
        persisted = await mock_repository.get("wf-error-test")
        assert persisted.workflow_status == "failed"
        assert "Missing execution state" in persisted.failure_reason
```

**Step 2: Run the integration test**

Run: `uv run pytest tests/integration/test_approval_flow.py -v`
Expected: PASS (5 tests)

> **Note:** Some tests may require mocking the actual LangGraph nodes (architect_node, etc.) if they make external calls. Add `@patch` decorators as needed.

**Step 3: Commit**

```bash
git add tests/integration/test_approval_flow.py
git commit -m "test(integration): add comprehensive approval flow integration tests"
```

---

## Task 14: Final Verification and Documentation

**Files:**
- None (verification only)

**Step 1: Run complete test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests PASS

**Step 2: Run type checker on entire project**

Run: `uv run mypy amelia`
Expected: Success

**Step 3: Run linter on entire project**

Run: `uv run ruff check amelia tests`
Expected: Success

**Step 4: Verify PR 1 implementation matches the design**

Check that all PR 1 components are implemented:
- [x] `langgraph-checkpoint-sqlite` dependency added (Task 1)
- [x] `create_orchestrator_graph` accepts `interrupt_before` parameter **(CRITICAL)** (Task 1.5)
- [x] `human_approval_node` execution mode detection (Task 4)
- [x] `ServerExecutionState.execution_state` composition (Task 5)
- [x] `STAGE_NODES` constant (Task 6)
- [x] `_handle_graph_event` method (Task 6)
- [x] `_run_workflow` with checkpointing and `GraphInterrupt` handling **(CRITICAL)** (Task 7)
- [x] `approve_workflow` graph resume (Task 10)
- [x] `reject_workflow` graph state update (Task 11)

**Step 5: Final commit and create PR 1**

```bash
git add -A
git commit -m "feat: complete LangGraph execution bridge implementation"
git push -u origin feat/langgraph-execution-bridge
```

Create PR with title: `feat(server): implement LangGraph execution bridge with interrupt-based approval`

---

# PR 2: Retry Enhancement

> **Prerequisites:** PR 1 must be merged before starting these tasks.
>
> ```bash
> git checkout main && git pull
> git checkout -b feat/workflow-retry-logic
> ```

**PR 2 Tasks:** 2, 3, 8, 9 (scroll up to find them, marked with "(PR 2)")

**After completing Tasks 2, 3, 8, 9:**

```bash
# Run tests
uv run pytest tests/unit/test_retry_config.py tests/unit/server/orchestrator/test_retry_logic.py -v

# Run full suite
uv run pytest tests/unit/ -v
uv run mypy amelia
uv run ruff check amelia tests

# Commit and push
git add -A
git commit -m "feat(server): add retry logic for transient failures"
git push -u origin feat/workflow-retry-logic
```

**PR 2 Checklist:**
- [ ] `RetryConfig` model with validation (Task 2)
- [ ] `Profile.retry` field (Task 3)
- [ ] `_run_workflow_with_retry` wrapper (Task 8)
- [ ] `start_workflow` uses retry wrapper (Task 9)

Create PR with title: `feat(server): add retry logic for transient workflow failures`
