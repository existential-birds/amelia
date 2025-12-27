# Agentic-Only Execution Migration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all structured execution mode code and migrate to agentic-only execution. At completion, zero lines of code or documentation reference structured execution concepts (PlanStep, ExecutionBatch, batches, blockers, cascade skips, etc.).

**Success Criteria:** `grep -rE "PlanStep|ExecutionBatch|ExecutionPlan|BatchResult|StepResult|BlockerReport|BlockerType|cascade_skip|batch_approval" amelia/ tests/ dashboard/src/ docs/` returns zero results.

**Approach:** Define new model → Delete old → Build new → Update dashboard → Clean docs

---

## Phase 1: Define New Agentic State Model

### Task 1.1: Create AgenticState Model

**Files:**
- Create: `amelia/core/agentic_state.py`
- Test: `tests/unit/test_agentic_state.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_agentic_state.py
"""Tests for agentic execution state model."""
import pytest
from amelia.core.agentic_state import AgenticState, ToolCall, ToolResult


class TestToolCall:
    """Test ToolCall model."""

    def test_create_tool_call(self):
        """Should create tool call with required fields."""
        call = ToolCall(
            id="call-1",
            tool_name="run_shell_command",
            tool_input={"command": "ls -la"},
        )
        assert call.id == "call-1"
        assert call.tool_name == "run_shell_command"
        assert call.tool_input == {"command": "ls -la"}

    def test_tool_call_is_frozen(self):
        """ToolCall should be immutable."""
        call = ToolCall(id="1", tool_name="test", tool_input={})
        with pytest.raises(Exception):  # ValidationError for frozen
            call.id = "2"


class TestToolResult:
    """Test ToolResult model."""

    def test_create_success_result(self):
        """Should create successful tool result."""
        result = ToolResult(
            call_id="call-1",
            tool_name="run_shell_command",
            output="file1.txt\nfile2.txt",
            success=True,
        )
        assert result.success is True
        assert result.error is None

    def test_create_error_result(self):
        """Should create error tool result."""
        result = ToolResult(
            call_id="call-1",
            tool_name="run_shell_command",
            output="",
            success=False,
            error="Command not found",
        )
        assert result.success is False
        assert result.error == "Command not found"


class TestAgenticState:
    """Test AgenticState model."""

    def test_create_initial_state(self):
        """Should create state with conversation history."""
        state = AgenticState(
            workflow_id="wf-123",
            issue_key="ISSUE-1",
            goal="Implement feature X",
        )
        assert state.workflow_id == "wf-123"
        assert state.tool_calls == ()
        assert state.tool_results == ()
        assert state.status == "running"

    def test_state_tracks_tool_history(self):
        """Should track tool call and result history."""
        call = ToolCall(id="1", tool_name="shell", tool_input={"cmd": "ls"})
        result = ToolResult(call_id="1", tool_name="shell", output="ok", success=True)

        state = AgenticState(
            workflow_id="wf-1",
            issue_key="ISSUE-1",
            goal="test",
            tool_calls=(call,),
            tool_results=(result,),
        )
        assert len(state.tool_calls) == 1
        assert len(state.tool_results) == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_agentic_state.py -v`
Expected: FAIL - ModuleNotFoundError

**Step 3: Create agentic_state module**

```python
# amelia/core/agentic_state.py
"""State model for agentic execution.

This module defines the state model for agentic (tool-calling) execution,
replacing the structured batch/step execution model.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


AgenticStatus = Literal["running", "awaiting_approval", "completed", "failed", "cancelled"]


class ToolCall(BaseModel):
    """A tool call made by the LLM.

    Attributes:
        id: Unique identifier for this call.
        tool_name: Name of the tool being called.
        tool_input: Input parameters for the tool.
        timestamp: When the call was made (ISO format).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    tool_name: str
    tool_input: dict[str, Any]
    timestamp: str | None = None


class ToolResult(BaseModel):
    """Result from a tool execution.

    Attributes:
        call_id: ID of the ToolCall this result is for.
        tool_name: Name of the tool that was called.
        output: Output from the tool (stdout, file content, etc.).
        success: Whether the tool executed successfully.
        error: Error message if success is False.
        duration_ms: Execution time in milliseconds.
    """

    model_config = ConfigDict(frozen=True)

    call_id: str
    tool_name: str
    output: str
    success: bool
    error: str | None = None
    duration_ms: int | None = None


class AgenticState(BaseModel):
    """State for agentic workflow execution.

    Tracks the conversation, tool calls, and results for an agentic
    execution session where the LLM autonomously decides actions.

    Attributes:
        workflow_id: Unique workflow identifier.
        issue_key: Issue being worked on.
        goal: High-level goal or task description.
        system_prompt: System prompt for the agent.
        tool_calls: History of tool calls made.
        tool_results: History of tool results received.
        final_response: Final response from the agent when complete.
        status: Current execution status.
        error: Error message if status is 'failed'.
        session_id: Session ID for driver continuity.
    """

    model_config = ConfigDict(frozen=True)

    workflow_id: str
    issue_key: str
    goal: str
    system_prompt: str | None = None

    # Tool execution history
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()

    # Completion state
    final_response: str | None = None
    status: AgenticStatus = "running"
    error: str | None = None

    # Session continuity
    session_id: str | None = None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_agentic_state.py -v`
Expected: PASS

**Step 5: Run type checker**

Run: `uv run mypy amelia/core/agentic_state.py`
Expected: Success

**Step 6: Commit**

```bash
git add amelia/core/agentic_state.py tests/unit/test_agentic_state.py
git commit -m "feat(state): add AgenticState model for agentic execution"
```

---

### Task 1.2: Add OpenRouter Provider Support to ApiDriver

**Files:**
- Modify: `amelia/core/types.py`
- Modify: `amelia/drivers/factory.py`
- Modify: `amelia/drivers/api/openai.py`
- Test: `tests/unit/test_api_driver_providers.py` (new)

**Step 1: Write the failing tests**

```python
# tests/unit/test_api_driver_providers.py
"""Tests for ApiDriver provider validation."""
import pytest
from amelia.drivers.api.openai import ApiDriver


class TestProviderValidation:
    """Test provider validation in ApiDriver."""

    def test_accepts_openai_model(self):
        """Should accept openai: prefixed models."""
        driver = ApiDriver(model="openai:gpt-4o")
        assert driver.model_name == "openai:gpt-4o"
        assert driver._provider == "openai"

    def test_accepts_openrouter_model(self):
        """Should accept openrouter: prefixed models."""
        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")
        assert driver.model_name == "openrouter:anthropic/claude-3.5-sonnet"
        assert driver._provider == "openrouter"

    def test_rejects_unsupported_provider(self):
        """Should reject unsupported providers."""
        with pytest.raises(ValueError, match="Unsupported provider"):
            ApiDriver(model="gemini:pro")


class TestApiKeyValidation:
    """Test API key validation per provider."""

    def test_openai_requires_openai_api_key(self, monkeypatch):
        """OpenAI provider should require OPENAI_API_KEY."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        driver = ApiDriver(model="openai:gpt-4o")
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            driver._validate_api_key()

    def test_openrouter_requires_openrouter_api_key(self, monkeypatch):
        """OpenRouter provider should require OPENROUTER_API_KEY."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        driver = ApiDriver(model="openrouter:anthropic/claude-3.5-sonnet")
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            driver._validate_api_key()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_api_driver_providers.py -v`
Expected: FAIL

**Step 3: Update DriverType and ApiDriver**

```python
# amelia/core/types.py - update DriverType
DriverType = Literal["cli:claude", "api:openai", "api:openrouter", "cli", "api"]
```

```python
# amelia/drivers/api/openai.py - update provider handling
SUPPORTED_PROVIDERS = ("openai:", "openrouter:")

class ApiDriver(DriverInterface):
    def __init__(self, model: str = 'openai:gpt-4o'):
        if not any(model.startswith(prefix) for prefix in SUPPORTED_PROVIDERS):
            raise ValueError(
                f"Unsupported provider in model '{model}'. "
                f"Supported: {', '.join(p.rstrip(':') for p in SUPPORTED_PROVIDERS)}"
            )
        self.model_name = model
        self._provider = model.split(":")[0]

    def _validate_api_key(self) -> None:
        key_map = {"openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
        env_var = key_map.get(self._provider)
        if env_var and not os.environ.get(env_var):
            raise ValueError(f"{env_var} environment variable is not set.")
```

**Step 4: Update factory**

```python
# amelia/drivers/factory.py
elif driver_key in ("api:openai", "api:openrouter", "api"):
    return ApiDriver(**kwargs)
```

**Step 5: Run tests**

Run: `uv run pytest tests/unit/test_api_driver_providers.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/core/types.py amelia/drivers/factory.py amelia/drivers/api/openai.py tests/unit/test_api_driver_providers.py
git commit -m "feat(driver): add OpenRouter provider support"
```

---

### Task 1.3: Implement execute_agentic in ApiDriver

**Files:**
- Create: `amelia/drivers/api/events.py`
- Create: `amelia/drivers/api/tools.py`
- Modify: `amelia/drivers/api/openai.py`
- Test: `tests/unit/test_api_driver_agentic.py`

**Step 1: Create events module**

```python
# amelia/drivers/api/events.py
"""Stream event types for API driver agentic execution."""
from typing import Any, Literal
from pydantic import BaseModel

ApiStreamEventType = Literal["thinking", "tool_use", "tool_result", "result", "error"]


class ApiStreamEvent(BaseModel):
    """Event from API driver agentic execution."""
    type: ApiStreamEventType
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_result: str | None = None
    session_id: str | None = None
    result_text: str | None = None
```

**Step 2: Create tools module**

```python
# amelia/drivers/api/tools.py
"""Tool definitions for pydantic-ai agentic execution."""
from dataclasses import dataclass
from pydantic_ai import RunContext
from amelia.tools.shell_executor import run_shell_command as shell_exec
from amelia.tools.shell_executor import write_file as file_write


@dataclass
class AgenticContext:
    """Context for agentic tool execution."""
    cwd: str
    allowed_dirs: list[str] | None = None


async def run_shell_command(
    ctx: RunContext[AgenticContext],
    command: str,
    timeout: int = 30,
) -> str:
    """Execute a shell command safely."""
    return await shell_exec(command=command, timeout=timeout, cwd=ctx.deps.cwd)


async def write_file(
    ctx: RunContext[AgenticContext],
    file_path: str,
    content: str,
) -> str:
    """Write content to a file safely."""
    allowed = ctx.deps.allowed_dirs or [ctx.deps.cwd]
    return await file_write(file_path=file_path, content=content, cwd=ctx.deps.cwd)
```

**Step 3: Write failing test for execute_agentic**

```python
# tests/unit/test_api_driver_agentic.py
"""Tests for ApiDriver agentic execution."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from amelia.core.state import AgentMessage
from amelia.drivers.api.openai import ApiDriver


class TestExecuteAgentic:
    """Test execute_agentic method."""

    async def test_yields_result_event(self, monkeypatch):
        """Should yield result event at end of execution."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        driver = ApiDriver(model="openai:gpt-4o")

        with patch("amelia.drivers.api.openai.Agent") as mock_agent_class:
            mock_run = AsyncMock()
            mock_run.result = MagicMock(output="Done")
            mock_run.__aenter__ = AsyncMock(return_value=mock_run)
            mock_run.__aexit__ = AsyncMock(return_value=None)
            mock_run.__aiter__ = lambda self: iter([])

            mock_agent = MagicMock()
            mock_agent.iter = MagicMock(return_value=mock_run)
            mock_agent_class.return_value = mock_agent

            events = []
            async for event in driver.execute_agentic(
                messages=[AgentMessage(role="user", content="test")],
                cwd="/tmp",
            ):
                events.append(event)

            assert len(events) >= 1
            assert events[-1].type == "result"
```

**Step 4: Implement execute_agentic**

See original plan Task 8 for full implementation.

**Step 5: Run tests**

Run: `uv run pytest tests/unit/test_api_driver_agentic.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/drivers/api/events.py amelia/drivers/api/tools.py amelia/drivers/api/openai.py tests/unit/test_api_driver_agentic.py
git commit -m "feat(driver): implement execute_agentic with pydantic-ai"
```

---

## Phase 2: Delete Structured Execution Code

### Task 2.1: Delete Structured Execution Tests

**Files to DELETE:**
- `tests/integration/test_batch_execution.py`
- `tests/integration/test_batch_execution_e2e.py`
- `tests/integration/test_cascade_skip_propagation.py`
- `tests/integration/test_blocker_recovery.py`

**Step 1: Delete test files**

```bash
rm -f tests/integration/test_batch_execution.py
rm -f tests/integration/test_batch_execution_e2e.py
rm -f tests/integration/test_cascade_skip_propagation.py
rm -f tests/integration/test_blocker_recovery.py
```

**Step 2: Remove structured execution test factories from conftest**

Edit `tests/integration/conftest.py`:
- Remove `make_step()` factory
- Remove `make_batch()` factory
- Remove imports: `PlanStep`, `ExecutionBatch`, `ExecutionPlan`

Edit `tests/conftest.py`:
- Remove any batch/step related fixtures

**Step 3: Run remaining tests to verify no breakage**

Run: `uv run pytest tests/ -v --ignore=tests/unit/test_state.py`
Expected: Tests that don't depend on deleted code should pass

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: delete structured execution tests"
```

---

### Task 2.2: Delete Structured Models from state.py

**Files:**
- Modify: `amelia/core/state.py`

**Step 1: Delete these classes/types from state.py**

Delete in order (bottom-up to avoid reference errors):
1. `BatchApproval` class
2. `GitSnapshot` class
3. `BatchResult` class
4. `StepResult` class
5. `BlockerReport` class
6. `ExecutionPlan` class
7. `ExecutionBatch` class
8. `PlanStep` class
9. Type aliases: `RiskLevel`, `ActionType`, `BlockerType`, `StepStatus`, `BatchStatus`
10. Helper: `truncate_output()` (if only used by above)

**Step 2: Remove structured fields from ExecutionState**

Remove these fields from `ExecutionState`:
- `execution_plan`
- `current_batch_index`
- `batch_results`
- `developer_status`
- `current_blocker`
- `blocker_resolution`
- `batch_approvals`
- `skipped_step_ids`
- `git_snapshot_before_batch`
- `review_iteration`

**Step 3: Update ExecutionState to use AgenticState fields**

```python
# amelia/core/state.py - simplified ExecutionState
from amelia.core.agentic_state import AgenticState, ToolCall, ToolResult, AgenticStatus

class ExecutionState(BaseModel):
    """State for workflow execution."""

    model_config = ConfigDict(frozen=True)

    # Identity
    workflow_id: str
    issue: Issue | None = None
    profile: Profile | None = None

    # Conversation
    messages: tuple[AgentMessage, ...] = ()

    # Agentic execution
    goal: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()

    # Status
    status: AgenticStatus = "running"
    final_response: str | None = None
    error: str | None = None
    session_id: str | None = None
```

**Step 4: Run type checker**

Run: `uv run mypy amelia/core/state.py`
Expected: Many errors from files still importing deleted types

**Step 5: Commit (partial - will have broken imports)**

```bash
git add amelia/core/state.py
git commit -m "refactor(state): remove structured execution models"
```

---

### Task 2.3: Delete Developer Agent Batch Logic

**Files:**
- Rewrite: `amelia/agents/developer.py`

**Step 1: Delete these functions entirely**

- `validate_command_result()`
- `get_cascade_skips()`
- `_filesystem_checks()`
- `_pre_validate_step()`
- `_resolve_working_dir()`
- `_resolve_file_path()`
- `_execute_step_with_fallbacks()`
- `_execute_code_action()`
- `_execute_command_action()`
- `_execute_validation_action()`
- `_execute_batch()`
- `_recover_from_blocker()`

**Step 2: Create new agentic Developer**

```python
# amelia/agents/developer.py
"""Developer agent for agentic code execution."""
from collections.abc import AsyncIterator
from loguru import logger

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.core.state import ExecutionState
from amelia.core.types import Profile
from amelia.drivers.api.events import ApiStreamEvent
from amelia.drivers.base import DriverInterface


class Developer:
    """Developer agent that executes code changes agentically.

    Uses LLM with tool access to autonomously complete coding tasks.
    """

    def __init__(self, driver: DriverInterface):
        """Initialize developer with a driver."""
        self.driver = driver

    async def run(
        self,
        state: ExecutionState,
        profile: Profile,
    ) -> AsyncIterator[tuple[ExecutionState, ApiStreamEvent]]:
        """Execute development task agentically.

        Args:
            state: Current execution state with goal.
            profile: Execution profile with settings.

        Yields:
            Tuples of (updated_state, event) as execution progresses.
        """
        if not state.goal:
            raise ValueError("ExecutionState must have a goal set")

        cwd = profile.repo_root or "."

        tool_calls: list[ToolCall] = list(state.tool_calls)
        tool_results: list[ToolResult] = list(state.tool_results)

        async for event in self.driver.execute_agentic(
            messages=list(state.messages),
            cwd=cwd,
            session_id=state.session_id,
            system_prompt=self._build_system_prompt(profile),
        ):
            # Track tool calls/results
            if event.type == "tool_use" and event.tool_name:
                call = ToolCall(
                    id=f"call-{len(tool_calls)}",
                    tool_name=event.tool_name,
                    tool_input=event.tool_input or {},
                )
                tool_calls.append(call)

            elif event.type == "tool_result" and event.tool_name:
                result = ToolResult(
                    call_id=f"call-{len(tool_results)}",
                    tool_name=event.tool_name,
                    output=event.tool_result or "",
                    success=True,
                )
                tool_results.append(result)

            # Update state
            new_state = state.model_copy(update={
                "tool_calls": tuple(tool_calls),
                "tool_results": tuple(tool_results),
                "session_id": event.session_id or state.session_id,
                "status": "completed" if event.type == "result" else state.status,
                "final_response": event.result_text if event.type == "result" else state.final_response,
                "error": event.content if event.type == "error" else state.error,
            })

            yield new_state, event

    def _build_system_prompt(self, profile: Profile) -> str:
        """Build system prompt for agentic execution."""
        return f"""You are a skilled developer working on a codebase.
Your task is to complete the requested changes using the available tools.

Working directory: {profile.repo_root or '.'}

Available tools:
- run_shell_command: Execute shell commands (ls, cat, grep, git, npm, python, etc.)
- write_file: Create or overwrite files

Guidelines:
- Read files before modifying them
- Make minimal, focused changes
- Run tests after making changes
- Commit your changes when complete
"""
```

**Step 3: Run type checker**

Run: `uv run mypy amelia/agents/developer.py`
Expected: Success

**Step 4: Commit**

```bash
git add amelia/agents/developer.py
git commit -m "refactor(developer): rewrite for agentic execution"
```

---

### Task 2.4: Delete Architect Plan Generation

**Files:**
- Modify: `amelia/agents/architect.py`

**Step 1: Delete these from architect.py**

- `ExecutionPlanOutput` class
- `get_execution_plan_system_prompt()` method
- `get_execution_plan_user_prompt()` method
- `generate_execution_plan()` method
- `validate_and_split_batches()` function
- `_render_markdown()` batch rendering logic
- All imports of `PlanStep`, `ExecutionBatch`, `ExecutionPlan`

**Step 2: Simplify Architect to generate goal/strategy only**

The Architect should now:
- Analyze the issue
- Generate a high-level goal/strategy string
- NOT generate step-by-step plans

```python
# Simplified Architect output
class ArchitectOutput(BaseModel):
    """Output from Architect analysis."""
    goal: str  # Clear description of what needs to be done
    strategy: str  # High-level approach (not step-by-step)
    key_files: list[str]  # Files likely to be modified
    risks: list[str]  # Potential risks to watch for
```

**Step 3: Update plan() method**

Remove all batch/step generation logic. Return simplified output.

**Step 4: Commit**

```bash
git add amelia/agents/architect.py
git commit -m "refactor(architect): remove plan generation, simplify to goal/strategy"
```

---

### Task 2.5: Delete Orchestrator Batch/Blocker Nodes

**Files:**
- Modify: `amelia/core/orchestrator.py`

**Step 1: Delete these functions**

- `should_checkpoint()`
- `batch_approval_node()`
- `blocker_resolution_node()`
- `route_after_developer()`
- `route_batch_approval()`
- `route_blocker_resolution()`
- `create_synthetic_plan_from_review()`
- `should_continue_review_fix()`
- `call_developer_node_for_review()`
- `create_review_graph()`

**Step 2: Simplify graph structure**

New graph flow:
```
START → architect_node → human_approval → developer_node → reviewer_node → END
                                              ↑                    │
                                              └────────────────────┘
                                              (if changes requested)
```

**Step 3: Remove conditional edges for batch/blocker**

Remove edges to deleted nodes. Simplify routing.

**Step 4: Run type checker**

Run: `uv run mypy amelia/core/orchestrator.py`

**Step 5: Commit**

```bash
git add amelia/core/orchestrator.py
git commit -m "refactor(orchestrator): remove batch/blocker nodes, simplify graph"
```

---

### Task 2.6: Delete Server Batch/Blocker Models and Routes

**Files:**
- Modify: `amelia/server/models/requests.py`
- Modify: `amelia/server/models/responses.py`
- Modify: `amelia/server/models/events.py`
- Modify: `amelia/server/routes/workflows.py`

**Step 1: Delete from requests.py**

- `BlockerResolutionRequest`
- `BatchApprovalRequest`
- `plan_only` field from `CreateWorkflowRequest`

**Step 2: Delete from responses.py**

- Any batch/blocker response models

**Step 3: Delete from events.py**

- Batch/blocker event types

**Step 4: Delete from workflows.py**

- Batch approval endpoint
- Blocker resolution endpoint
- Step cancellation endpoints

**Step 5: Run tests**

Run: `uv run pytest tests/unit/server/ -v`

**Step 6: Commit**

```bash
git add amelia/server/
git commit -m "refactor(server): remove batch/blocker models and routes"
```

---

### Task 2.7: Delete CLI Plan Command

**Files:**
- Modify: `amelia/cli/commands.py` or wherever `amelia plan` is defined

**Step 1: Remove plan command**

Delete the `plan` subcommand that generates execution plans.

**Step 2: Update CLI help**

**Step 3: Commit**

```bash
git add amelia/cli/
git commit -m "refactor(cli): remove plan command"
```

---

### Task 2.8: Clean Up types.py

**Files:**
- Modify: `amelia/core/types.py`

**Step 1: Delete these types**

- `ExecutionMode` (no longer needed - only agentic)
- `TrustLevel` (batch-specific)
- `DeveloperStatus` (batch-specific)

**Step 2: Remove from Profile**

- `execution_mode` field
- `batch_checkpoint_enabled` field
- `trust_level` field

**Step 3: Commit**

```bash
git add amelia/core/types.py
git commit -m "refactor(types): remove structured execution types"
```

---

## Phase 3: Build New Agentic Orchestrator

### Task 3.1: Create Simplified Orchestrator Graph

**Files:**
- Modify: `amelia/core/orchestrator.py`
- Test: `tests/unit/test_orchestrator_agentic.py`

**Step 1: Write failing test**

```python
# tests/unit/test_orchestrator_agentic.py
"""Tests for agentic orchestrator."""
import pytest
from amelia.core.orchestrator import create_workflow_graph


class TestAgenticOrchestrator:
    """Test agentic workflow graph."""

    def test_graph_has_required_nodes(self):
        """Graph should have architect, developer, reviewer nodes."""
        graph = create_workflow_graph()
        # Verify node names
        assert "architect" in str(graph.nodes)
        assert "developer" in str(graph.nodes)
        assert "reviewer" in str(graph.nodes)

    def test_graph_does_not_have_batch_nodes(self):
        """Graph should NOT have batch/blocker nodes."""
        graph = create_workflow_graph()
        graph_str = str(graph.nodes)
        assert "batch_approval" not in graph_str
        assert "blocker" not in graph_str
```

**Step 2: Implement simplified graph**

```python
# amelia/core/orchestrator.py - new simplified version

async def architect_node(state: ExecutionState) -> ExecutionState:
    """Architect analyzes issue and sets goal."""
    # Get goal/strategy from Architect
    # Update state with goal
    pass

async def developer_node(state: ExecutionState) -> ExecutionState:
    """Developer executes changes agentically."""
    # Run Developer.run() which uses execute_agentic
    # Stream events, update state
    pass

async def reviewer_node(state: ExecutionState) -> ExecutionState:
    """Reviewer checks changes."""
    # Review and approve or request changes
    pass

def route_after_review(state: ExecutionState) -> str:
    """Route based on review result."""
    if state.status == "completed":
        return END
    return "developer"  # Loop back for changes

def create_workflow_graph() -> CompiledStateGraph:
    """Create the agentic workflow graph."""
    builder = StateGraph(ExecutionState)

    builder.add_node("architect", architect_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("developer", developer_node)
    builder.add_node("reviewer", reviewer_node)

    builder.add_edge(START, "architect")
    builder.add_edge("architect", "human_approval")
    builder.add_edge("human_approval", "developer")
    builder.add_edge("developer", "reviewer")
    builder.add_conditional_edges("reviewer", route_after_review)

    return builder.compile()
```

**Step 3: Run tests**

Run: `uv run pytest tests/unit/test_orchestrator_agentic.py -v`

**Step 4: Commit**

```bash
git add amelia/core/orchestrator.py tests/unit/test_orchestrator_agentic.py
git commit -m "feat(orchestrator): implement simplified agentic graph"
```

---

### Task 3.2: Integration Test for Agentic Workflow

**Files:**
- Create: `tests/integration/test_agentic_workflow.py`

**Step 1: Create integration test**

```python
# tests/integration/test_agentic_workflow.py
"""Integration tests for agentic workflow."""
import pytest
from amelia.core.orchestrator import create_workflow_graph
from amelia.core.state import ExecutionState


@pytest.mark.integration
class TestAgenticWorkflowIntegration:
    """Integration tests for full agentic workflow."""

    async def test_simple_workflow_completes(self, mock_driver):
        """Workflow should complete a simple task."""
        graph = create_workflow_graph()

        initial_state = ExecutionState(
            workflow_id="test-1",
            goal="Create a hello.txt file with 'Hello World'",
        )

        result = await graph.ainvoke(initial_state)

        assert result.status == "completed"
        assert result.final_response is not None
```

**Step 2: Run integration test**

Run: `uv run pytest tests/integration/test_agentic_workflow.py -v`

**Step 3: Commit**

```bash
git add tests/integration/test_agentic_workflow.py
git commit -m "test: add agentic workflow integration test"
```

---

## Phase 4: Update Dashboard

### Task 4.1: Delete Batch/Step Dashboard Components

**Files to DELETE:**
- `dashboard/src/components/flow/BatchNode.tsx`
- `dashboard/src/components/flow/BatchNode.test.tsx`
- `dashboard/src/components/flow/StepNode.tsx`
- `dashboard/src/components/flow/StepNode.test.tsx`
- `dashboard/src/components/flow/CheckpointMarker.tsx`
- `dashboard/src/components/flow/CheckpointMarker.test.tsx`
- `dashboard/src/components/BatchStepCanvas.tsx`
- `dashboard/src/components/BatchStepCanvas.test.tsx`
- `dashboard/src/components/BlockerResolutionDialog.tsx`
- `dashboard/src/components/BlockerResolutionDialog.test.tsx`
- `dashboard/src/components/CancelStepDialog.tsx`
- `dashboard/src/components/CancelStepDialog.test.tsx`

**Step 1: Delete files**

```bash
rm -f dashboard/src/components/flow/BatchNode.tsx
rm -f dashboard/src/components/flow/BatchNode.test.tsx
rm -f dashboard/src/components/flow/StepNode.tsx
rm -f dashboard/src/components/flow/StepNode.test.tsx
rm -f dashboard/src/components/flow/CheckpointMarker.tsx
rm -f dashboard/src/components/flow/CheckpointMarker.test.tsx
rm -f dashboard/src/components/BatchStepCanvas.tsx
rm -f dashboard/src/components/BatchStepCanvas.test.tsx
rm -f dashboard/src/components/BlockerResolutionDialog.tsx
rm -f dashboard/src/components/BlockerResolutionDialog.test.tsx
rm -f dashboard/src/components/CancelStepDialog.tsx
rm -f dashboard/src/components/CancelStepDialog.test.tsx
```

**Step 2: Commit**

```bash
git add -A
git commit -m "chore(dashboard): delete batch/step components"
```

---

### Task 4.2: Delete Structured Types from Dashboard

**Files:**
- Modify: `dashboard/src/types/index.ts`

**Step 1: Delete these types**

- `RiskLevel`
- `ActionType`
- `StepStatus`, `StepStatusUI`
- `BatchStatus`, `BatchStatusUI`
- `BlockerType`
- `DeveloperStatus`
- `BlockerResolutionAction`
- `PlanStep`
- `ExecutionBatch`
- `ExecutionPlan`
- `BlockerReport`
- `StepResult`
- `BatchResult`
- `GitSnapshot`
- `BatchApproval`
- `BlockerResolutionRequest`
- `BatchApprovalRequest`

**Step 2: Remove from WorkflowDetail interface**

Remove fields:
- `execution_plan`
- `current_batch_index`
- `batch_results`
- `developer_status`
- `current_blocker`
- `batch_approvals`

**Step 3: Add new agentic types**

```typescript
// dashboard/src/types/index.ts

export interface ToolCall {
  id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  timestamp?: string;
}

export interface ToolResult {
  call_id: string;
  tool_name: string;
  output: string;
  success: boolean;
  error?: string;
  duration_ms?: number;
}

export type AgenticStatus = 'running' | 'awaiting_approval' | 'completed' | 'failed' | 'cancelled';

// Update WorkflowDetail
export interface WorkflowDetail {
  workflow_id: string;
  issue_key: string;
  goal?: string;
  tool_calls: ToolCall[];
  tool_results: ToolResult[];
  status: AgenticStatus;
  final_response?: string;
  error?: string;
}
```

**Step 4: Run type check**

```bash
cd dashboard && pnpm type-check
```

**Step 5: Commit**

```bash
git add dashboard/src/types/
git commit -m "refactor(dashboard): replace structured types with agentic types"
```

---

### Task 4.3: Update Dashboard Pages for Agentic Display

**Files:**
- Modify: `dashboard/src/pages/WorkflowDetailPage.tsx`
- Modify: `dashboard/src/components/WorkflowCanvas.tsx`

**Step 1: Replace batch visualization with tool call timeline**

Create a new component that shows:
- Tool calls as they happen
- Tool results
- Final response

**Step 2: Remove batch/blocker UI logic**

**Step 3: Run dashboard tests**

```bash
cd dashboard && pnpm test:run
```

**Step 4: Commit**

```bash
git add dashboard/src/
git commit -m "refactor(dashboard): update UI for agentic execution"
```

---

## Phase 5: Clean Documentation

### Task 5.1: Update Architecture Documentation

**Files:**
- Modify: `docs/site/architecture/overview.md`
- Modify: `docs/site/architecture/data-model.md`
- Modify: `docs/site/architecture/concepts.md`
- Modify: `docs/design/dynamic-orchestration.md`
- Modify: `docs/design/stateless-reducer-pattern.md`

**Step 1: Remove all mentions of:**

- PlanStep, ExecutionBatch, ExecutionPlan
- Batch execution, batch approval
- Step-by-step execution
- Cascade skips
- Blockers, blocker resolution
- Structured execution mode

**Step 2: Document new agentic model:**

- AgenticState
- ToolCall, ToolResult
- Simplified orchestrator graph
- execute_agentic flow

**Step 3: Commit**

```bash
git add docs/
git commit -m "docs: update architecture for agentic-only execution"
```

---

### Task 5.2: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Remove structured execution references**

Update Architecture Overview section to reflect agentic-only execution.

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for agentic-only execution"
```

---

### Task 5.3: Delete Old Plan Files

**Files:**
- Delete: `docs/plans/2025-12-21-openrouter-agentic-driver.md` (superseded by this plan)
- Review and delete any other obsolete plan files

**Step 1: Delete superseded plans**

```bash
rm -f docs/plans/2025-12-21-openrouter-agentic-driver.md
```

**Step 2: Commit**

```bash
git add -A
git commit -m "chore: delete superseded plan files"
```

---

## Phase 6: Final Verification

### Task 6.1: Run Full Test Suite

**Step 1: Run all tests**

```bash
uv run pytest tests/ -v
```

Expected: All tests pass

**Step 2: Run linter**

```bash
uv run ruff check amelia tests
```

Expected: No errors

**Step 3: Run type checker**

```bash
uv run mypy amelia
```

Expected: No errors

**Step 4: Run dashboard tests**

```bash
cd dashboard && pnpm test:run && pnpm type-check && pnpm lint
```

Expected: All pass

---

### Task 6.2: Verify Zero Structured References

**Step 1: Run grep verification**

```bash
grep -rE "PlanStep|ExecutionBatch|ExecutionPlan|BatchResult|StepResult|BlockerReport|BlockerType|cascade_skip|batch_approval|blocker_resolution" amelia/ tests/ dashboard/src/ docs/
```

Expected: **Zero results**

If any results found, go back and delete them.

**Step 2: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup - agentic-only migration complete"
```

---

## Summary

**Files DELETED (~30):**
- 4 integration test files
- 12 dashboard component files
- Old plan file
- Various obsolete docs

**Files CREATED (~5):**
- `amelia/core/agentic_state.py`
- `amelia/drivers/api/events.py`
- `amelia/drivers/api/tools.py`
- New test files

**Files MODIFIED (~25):**
- `amelia/core/state.py` - major reduction
- `amelia/core/types.py` - simplified
- `amelia/core/orchestrator.py` - rewritten
- `amelia/agents/developer.py` - rewritten
- `amelia/agents/architect.py` - simplified
- `amelia/server/models/*` - cleaned
- `amelia/server/routes/*` - cleaned
- `dashboard/src/types/index.ts` - replaced
- `dashboard/src/pages/*` - updated
- Various docs

**Success Criteria Met:**
- Zero references to structured execution concepts
- All tests pass
- Type checking passes
- Dashboard functional with agentic UI
