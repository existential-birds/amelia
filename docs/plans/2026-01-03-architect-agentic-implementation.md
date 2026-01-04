# Architect Agentic Execution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert the Architect agent from `driver.generate()` to `execute_agentic()`, enabling real-time streaming and autonomous codebase exploration.

**Architecture:** The Architect becomes an async generator like the Developer, yielding `(state, StreamEvent)` tuples during execution. It explores the codebase with read-only tools before producing a reference-based implementation plan. The orchestrator node is updated to consume the generator and emit stream events.

**Tech Stack:** Python 3.12, pydantic, loguru, LangGraph, pytest

---

## Phase 1: State Schema Changes

### Task 1.1: Add `raw_architect_output` Field to ExecutionState

**Files:**
- Modify: `amelia/core/state.py` (the `ExecutionState` class around line 38)
- Test: `tests/unit/core/test_state.py` (create if not exists)

**Step 1: Write the failing test**

```python
# tests/unit/core/test_state.py
"""Tests for ExecutionState model."""
import pytest

from amelia.core.state import ExecutionState


class TestExecutionStateRawArchitectOutput:
    """Tests for raw_architect_output field."""

    def test_raw_architect_output_defaults_to_none(self) -> None:
        """raw_architect_output should default to None."""
        state = ExecutionState(profile_id="test")
        assert state.raw_architect_output is None

    def test_raw_architect_output_stores_string(self) -> None:
        """raw_architect_output should store markdown string."""
        markdown = "# Plan\n\n**Goal:** Do something"
        state = ExecutionState(profile_id="test", raw_architect_output=markdown)
        assert state.raw_architect_output == markdown

    def test_raw_architect_output_in_model_copy(self) -> None:
        """raw_architect_output should work with model_copy."""
        state = ExecutionState(profile_id="test")
        new_state = state.model_copy(update={"raw_architect_output": "# Updated"})
        assert new_state.raw_architect_output == "# Updated"
        assert state.raw_architect_output is None  # Original unchanged
```

**Run:** `uv run pytest tests/unit/core/test_state.py -v`

**Expected:** FAIL with "raw_architect_output" not a valid field

**Step 2: Implement the field**

Add to `amelia/core/state.py` in the `ExecutionState` class, after line 84 (`plan_markdown`):

```python
    raw_architect_output: str | None = None  # Raw output from agentic architect
```

Update the docstring to include this field (around line 53):

```python
        raw_architect_output: Raw markdown output from agentic architect execution.
            Temporary field until #199 validator parses into structured fields.
```

**Run:** `uv run pytest tests/unit/core/test_state.py -v`

**Expected:** PASS

**Step 3: Commit**

```bash
git add amelia/core/state.py tests/unit/core/test_state.py
git commit -m "feat(state): add raw_architect_output field for agentic architect"
```

---

## Phase 2: Architect Agent Conversion

### Task 2.1: Update Architect System Prompt

**Files:**
- Modify: `amelia/agents/architect.py` (the `SYSTEM_PROMPT_PLAN` constant around line 111)

**Step 1: Write the failing test**

```python
# tests/unit/agents/test_architect_agentic.py
"""Tests for Architect agent agentic execution."""
import pytest

from amelia.agents.architect import Architect


class TestArchitectAgenticPrompt:
    """Tests for agentic architect system prompt."""

    def test_plan_prompt_includes_exploration_guidance(self, mock_driver) -> None:
        """System prompt should guide exploration before planning."""
        architect = Architect(mock_driver)
        prompt = architect.plan_prompt

        assert "read-only" in prompt.lower() or "exploration" in prompt.lower()
        assert "DO NOT modify" in prompt or "do not modify" in prompt.lower()

    def test_plan_prompt_emphasizes_references_over_code(self, mock_driver) -> None:
        """System prompt should emphasize file references over code examples."""
        architect = Architect(mock_driver)
        prompt = architect.plan_prompt

        assert "reference" in prompt.lower()
        assert "NOT to Include" in prompt or "What NOT" in prompt
```

**Run:** `uv run pytest tests/unit/agents/test_architect_agentic.py::TestArchitectAgenticPrompt -v`

**Expected:** FAIL - current prompt doesn't include these concepts

**Step 2: Update the SYSTEM_PROMPT_PLAN constant**

Replace `SYSTEM_PROMPT_PLAN` in `amelia/agents/architect.py` (lines 111-161) with:

```python
    SYSTEM_PROMPT_PLAN = """You are a senior software architect creating implementation plans.

## Your Role
Create implementation plans optimized for Claude Code execution. The executor:
- Has full codebase access and can read any file
- Generates code dynamically from understanding
- Doesn't copy-paste from plans

You have read-only access to explore the codebase before planning.

## Exploration Goals
Before planning, discover:
- Existing patterns for similar features
- File structure and naming conventions
- Test patterns and coverage approach
- Dependencies and integration points

## Plan Structure

# [Feature] Implementation Plan

**Goal:** [One sentence]
**Architecture:** [2-3 sentences on approach]
**Key Files:** [Files to create/modify with brief description]

### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py` (the `function_name` function)
- Test: `tests/path/to/test.py`

**Intent:** [What this accomplishes]

**Approach:**
- Follow pattern in `src/similar/feature.py:45-60`
- Interface: `async def function(arg: Type) -> ReturnType`
- Must handle: [edge cases]
- Must NOT: [constraints]

**Test Criteria:**
- Verify [behavior]

## What to Include
- Intent and constraints (what to build, what to avoid)
- File references: "Follow pattern in `file.py:L45-60`"
- Interface signatures (types, function signatures)
- Test criteria and edge cases
- Task dependencies and ordering

## What NOT to Include
- Full code implementations (executor generates these)
- Duplicated file contents (use references)
- Code examples the executor will regenerate anyway

## Constraints
- DO NOT modify any files - exploration only
- DO NOT run tests, builds, or commands
- Focus on understanding before planning"""
```

**Run:** `uv run pytest tests/unit/agents/test_architect_agentic.py::TestArchitectAgenticPrompt -v`

**Expected:** PASS

**Step 3: Commit**

```bash
git add amelia/agents/architect.py tests/unit/agents/test_architect_agentic.py
git commit -m "feat(architect): update system prompt for agentic exploration"
```

---

### Task 2.2: Convert plan() to Async Generator

**Files:**
- Modify: `amelia/agents/architect.py` (the `plan` method around line 344)
- Test: `tests/unit/agents/test_architect_agentic.py`

**Step 1: Write the failing test for async generator signature**

Add to `tests/unit/agents/test_architect_agentic.py`:

```python
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from amelia.agents.architect import Architect
from amelia.core.state import ExecutionState
from amelia.core.types import Profile, StreamEvent
from amelia.drivers.base import AgenticMessage, AgenticMessageType


class TestArchitectPlanAsyncGenerator:
    """Tests for Architect.plan() as async generator."""

    @pytest.fixture
    def mock_agentic_driver(self) -> MagicMock:
        """Driver that supports execute_agentic."""
        driver = MagicMock()
        driver.execute_agentic = AsyncMock()
        return driver

    @pytest.fixture
    def state_with_issue(self, mock_issue_factory, mock_profile_factory) -> tuple[ExecutionState, Profile]:
        """ExecutionState with required issue."""
        issue = mock_issue_factory(title="Add feature", description="Add feature X")
        profile = mock_profile_factory()
        state = ExecutionState(profile_id="test", issue=issue)
        return state, profile

    async def test_plan_returns_async_iterator(
        self,
        mock_agentic_driver: MagicMock,
        state_with_issue: tuple[ExecutionState, Profile],
    ) -> None:
        """plan() should return an async iterator."""
        state, profile = state_with_issue

        # Mock empty stream
        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[AgenticMessage]:
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="# Plan\n\n**Goal:** Test",
            )

        mock_agentic_driver.execute_agentic = mock_stream
        architect = Architect(mock_agentic_driver)

        result = architect.plan(state, profile, workflow_id="wf-1")

        # Should be an async iterator, not a coroutine
        assert hasattr(result, "__aiter__")
        assert hasattr(result, "__anext__")

    async def test_plan_yields_state_and_event_tuples(
        self,
        mock_agentic_driver: MagicMock,
        state_with_issue: tuple[ExecutionState, Profile],
    ) -> None:
        """plan() should yield (ExecutionState, StreamEvent) tuples."""
        state, profile = state_with_issue

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[AgenticMessage]:
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="read_file",
                tool_input={"path": "src/main.py"},
                tool_call_id="call-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="# Plan\n\n**Goal:** Test goal",
            )

        mock_agentic_driver.execute_agentic = mock_stream
        architect = Architect(mock_agentic_driver)

        results = []
        async for new_state, event in architect.plan(state, profile, workflow_id="wf-1"):
            results.append((new_state, event))

        assert len(results) >= 1
        for new_state, event in results:
            assert isinstance(new_state, ExecutionState)
            assert isinstance(event, StreamEvent)
```

**Run:** `uv run pytest tests/unit/agents/test_architect_agentic.py::TestArchitectPlanAsyncGenerator -v`

**Expected:** FAIL - plan() returns PlanOutput, not async iterator

**Step 2: Add new imports to architect.py**

At the top of `amelia/agents/architect.py`, add to imports (around line 6):

```python
from collections.abc import AsyncIterator

from amelia.core.agentic_state import ToolCall, ToolResult
from amelia.drivers.base import AgenticMessageType, DriverInterface
```

**Step 3: Update plan() method signature and implementation**

Replace the entire `plan()` method (lines 344-449) with:

```python
    async def plan(
        self,
        state: ExecutionState,
        profile: Profile,
        output_dir: str | None = None,
        *,
        workflow_id: str,
    ) -> AsyncIterator[tuple[ExecutionState, StreamEvent]]:
        """Generate a markdown implementation plan from an issue using agentic execution.

        Creates a rich markdown plan by exploring the codebase with read-only tools,
        then producing a reference-based plan. Yields state/event tuples as execution
        progresses for real-time streaming.

        Args:
            state: The execution state containing the issue and optional design.
            profile: The profile containing working directory settings.
            output_dir: Directory path where the markdown plan will be saved.
                If None, uses profile's plan_output_dir (defaults to docs/plans).
            workflow_id: Workflow ID for stream events (required).

        Yields:
            Tuples of (updated ExecutionState, StreamEvent) as exploration and
            planning progresses.

        Raises:
            ValueError: If no issue is present in the state.

        """
        if not state.issue:
            raise ValueError("Cannot generate plan: no issue in ExecutionState")

        # Use profile's output directory if not specified
        if output_dir is None:
            output_dir = profile.plan_output_dir

        # Resolve relative paths to working_dir (not server CWD)
        output_path = Path(output_dir)
        if not output_path.is_absolute() and profile.working_dir:
            output_dir = str(Path(profile.working_dir) / output_path)

        # Build user prompt from state (simplified - no codebase scan)
        user_prompt = self._build_agentic_prompt(state)

        cwd = profile.working_dir or "."
        tool_calls: list[ToolCall] = list(state.tool_calls)
        tool_results: list[ToolResult] = list(state.tool_results)
        raw_output = ""
        current_state = state

        async for message in self.driver.execute_agentic(
            prompt=user_prompt,
            cwd=cwd,
            instructions=self.plan_prompt,
        ):
            event: StreamEvent | None = None

            if message.type == AgenticMessageType.THINKING:
                event = message.to_stream_event(agent="architect", workflow_id=workflow_id)

            elif message.type == AgenticMessageType.TOOL_CALL:
                call = ToolCall(
                    id=message.tool_call_id or f"call-{len(tool_calls)}",
                    tool_name=message.tool_name or "unknown",
                    tool_input=message.tool_input or {},
                )
                tool_calls.append(call)
                logger.debug(
                    "Architect tool call recorded",
                    tool_name=message.tool_name,
                    call_id=call.id,
                )
                event = message.to_stream_event(agent="architect", workflow_id=workflow_id)

            elif message.type == AgenticMessageType.TOOL_RESULT:
                result = ToolResult(
                    call_id=message.tool_call_id or f"call-{len(tool_results)}",
                    tool_name=message.tool_name or "unknown",
                    output=message.tool_output or "",
                    success=not message.is_error,
                )
                tool_results.append(result)
                logger.debug(
                    "Architect tool result recorded",
                    call_id=result.call_id,
                )
                event = message.to_stream_event(agent="architect", workflow_id=workflow_id)

            elif message.type == AgenticMessageType.RESULT:
                raw_output = message.content or ""
                event = message.to_stream_event(agent="architect", workflow_id=workflow_id)

                # Save markdown to file
                markdown_path = self._save_markdown(
                    raw_output,
                    state.issue,
                    state.design,
                    output_dir,
                )

                logger.info(
                    "Architect plan generated",
                    agent="architect",
                    markdown_path=str(markdown_path),
                    raw_output_length=len(raw_output),
                )

                # Yield final state with all updates
                current_state = state.model_copy(update={
                    "tool_calls": tool_calls,
                    "tool_results": tool_results,
                    "raw_architect_output": raw_output,
                    "plan_markdown": raw_output,  # Backward compat until #199
                    "plan_path": markdown_path,
                })
                yield current_state, event
                continue  # Result is the final message

            if event:
                current_state = state.model_copy(update={
                    "tool_calls": tool_calls,
                    "tool_results": tool_results,
                })
                yield current_state, event

    def _build_agentic_prompt(self, state: ExecutionState) -> str:
        """Build user prompt for agentic plan generation.

        Simplified prompt that doesn't include codebase scan - the agent
        will explore using tools.

        Args:
            state: The current execution state.

        Returns:
            Formatted prompt string with issue and design context.

        Raises:
            ValueError: If no issue is present in the state.

        """
        if state.issue is None:
            raise ValueError("ExecutionState must have an issue")

        parts = []
        parts.append("## Issue")
        parts.append(f"**Title:** {state.issue.title}")
        parts.append(f"**Description:**\n{state.issue.description}")

        if state.design:
            parts.append("\n## Design Context")
            parts.append(state.design.raw_content)

        parts.append("\n## Your Task")
        parts.append(
            "Explore the codebase to understand relevant patterns and architecture, "
            "then create a detailed implementation plan for this issue."
        )

        return "\n".join(parts)
```

**Run:** `uv run pytest tests/unit/agents/test_architect_agentic.py::TestArchitectPlanAsyncGenerator -v`

**Expected:** PASS

**Step 4: Commit**

```bash
git add amelia/agents/architect.py tests/unit/agents/test_architect_agentic.py
git commit -m "feat(architect): convert plan() to async generator for streaming"
```

---

### Task 2.3: Remove _scan_codebase Method

**Files:**
- Modify: `amelia/agents/architect.py`
- Modify: `tests/unit/agents/test_architect_agentic.py`

**Step 1: Write test verifying no codebase scan in prompt**

Add to `tests/unit/agents/test_architect_agentic.py`:

```python
class TestArchitectAgenticPromptBuilding:
    """Tests for _build_agentic_prompt method."""

    def test_agentic_prompt_does_not_include_file_structure(
        self,
        mock_driver,
        mock_issue_factory,
    ) -> None:
        """Agentic prompt should not include pre-scanned file structure."""
        issue = mock_issue_factory(title="Test", description="Test description")
        state = ExecutionState(profile_id="test", issue=issue)

        architect = Architect(mock_driver)
        prompt = architect._build_agentic_prompt(state)

        # Should NOT contain file structure section
        assert "### File Structure" not in prompt
        assert "files)" not in prompt  # From "(N files)" in _scan_codebase

    def test_agentic_prompt_includes_issue(
        self,
        mock_driver,
        mock_issue_factory,
    ) -> None:
        """Agentic prompt should include issue details."""
        issue = mock_issue_factory(title="Add feature X", description="Detailed description")
        state = ExecutionState(profile_id="test", issue=issue)

        architect = Architect(mock_driver)
        prompt = architect._build_agentic_prompt(state)

        assert "Add feature X" in prompt
        assert "Detailed description" in prompt
        assert "## Issue" in prompt
```

**Run:** `uv run pytest tests/unit/agents/test_architect_agentic.py::TestArchitectAgenticPromptBuilding -v`

**Expected:** PASS (we already implemented _build_agentic_prompt correctly)

**Step 2: Remove _scan_codebase method**

Delete the `_scan_codebase` method (lines 282-342 in architect.py). Keep `_build_prompt` for the legacy `analyze()` method.

**Step 3: Run all architect tests to ensure nothing broke**

**Run:** `uv run pytest tests/unit/agents/test_architect*.py -v`

**Expected:** PASS

**Step 4: Commit**

```bash
git add amelia/agents/architect.py tests/unit/agents/test_architect_agentic.py
git commit -m "refactor(architect): remove _scan_codebase, agent explores via tools"
```

---

## Phase 3: Orchestrator Integration

### Task 3.1: Update call_architect_node to Consume Async Generator

**Files:**
- Modify: `amelia/core/orchestrator.py` (the `call_architect_node` function around line 125)
- Modify: `amelia/core/orchestrator.py` (add `_extract_goal_from_markdown` helper)
- Test: `tests/integration/test_agentic_workflow.py`

**Step 1: Write the failing integration test**

Add to `tests/integration/test_agentic_workflow.py`:

```python
@pytest.mark.integration
class TestArchitectNodeAgenticIntegration:
    """Test architect node with agentic execution (async generator)."""

    async def test_architect_node_consumes_async_generator(self, tmp_path: Path) -> None:
        """Architect node should consume async generator and emit events.

        Real components: DriverFactory, ApiDriver, Architect
        Mock boundary: ApiDriver.execute_agentic (yields AgenticMessage)
        """
        from amelia.drivers.base import AgenticMessage, AgenticMessageType

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        profile = make_profile(
            plan_output_dir=str(plans_dir),
            working_dir=str(tmp_path),
        )
        issue = make_issue(id="TEST-2", title="Add feature Y", description="Add a new feature Y")
        state = make_execution_state(issue=issue, profile=profile)

        # Track emitted events
        emitted_events = []
        async def capture_events(event):
            emitted_events.append(event)

        config = make_config(
            thread_id="test-agentic-1",
            profile=profile,
            stream_emitter=capture_events,
        )

        # Mock AgenticMessage stream from execute_agentic
        mock_messages = [
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="read_file",
                tool_input={"path": "src/main.py"},
                tool_call_id="call-1",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="read_file",
                tool_output="def main(): pass",
                tool_call_id="call-1",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="# Implementation Plan\n\n**Goal:** Implement feature Y\n\n## Task 1",
            ),
        ]

        async def mock_execute_agentic(*_args, **_kwargs):
            for msg in mock_messages:
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            result = await call_architect_node(state, cast(RunnableConfig, config))

        # Verify goal was extracted
        assert result["goal"] == "Implement feature Y"
        # Verify raw output stored
        assert result["raw_architect_output"] is not None
        assert "## Task 1" in result["raw_architect_output"]
        # Verify plan file created
        assert result["plan_path"] is not None
        assert Path(result["plan_path"]).exists()
        # Verify tool calls were recorded
        assert len(result["tool_calls"]) >= 1
        assert result["tool_calls"][0].tool_name == "read_file"
        # Verify events were emitted
        assert len(emitted_events) >= 1
```

**Run:** `uv run pytest tests/integration/test_agentic_workflow.py::TestArchitectNodeAgenticIntegration -v`

**Expected:** FAIL - call_architect_node still uses PlanOutput, not async generator

**Step 2: Add _extract_goal_from_markdown helper**

Add after `_save_token_usage` function (around line 123):

```python
def _extract_goal_from_markdown(markdown: str | None) -> str | None:
    """Temporary: Extract goal from plan markdown. Remove in #199.

    Looks for **Goal:** line in markdown and extracts the goal text.

    Args:
        markdown: Raw markdown plan content.

    Returns:
        Extracted goal string or None if not found.
    """
    if not markdown:
        return None
    for line in markdown.split("\n"):
        if line.strip().startswith("**Goal:**"):
            return line.replace("**Goal:**", "").strip()
    return None
```

**Step 3: Update call_architect_node to consume async generator**

Replace the `call_architect_node` function (lines 125-191) with:

```python
async def call_architect_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Architect agent to generate an implementation plan.

    Consumes the Architect's async generator, streaming events and collecting
    the final state with the generated plan.

    Args:
        state: Current execution state containing the issue and profile.
        config: Optional RunnableConfig with stream_emitter in configurable.

    Returns:
        Partial state dict with goal, plan_markdown, plan_path, raw_architect_output,
        tool_calls, and tool_results.

    Raises:
        ValueError: If no issue is provided in the state.
    """
    issue_id_for_log = state.issue.id if state.issue else "No Issue Provided"
    logger.info(f"Orchestrator: Calling Architect for issue {issue_id_for_log}")

    if state.issue is None:
        raise ValueError("Cannot call Architect: no issue provided in state.")

    # Extract stream_emitter, workflow_id, and profile from config
    stream_emitter, workflow_id, profile = _extract_config_params(config)

    # Get optional repository for token usage tracking
    config = config or {}
    configurable = config.get("configurable", {})
    repository = configurable.get("repository")

    # Extract prompts from config for agent injection
    prompts = configurable.get("prompts", {})

    driver = DriverFactory.get_driver(profile.driver, model=profile.model)
    architect = Architect(driver, stream_emitter=stream_emitter, prompts=prompts)

    # Consume async generator, emitting events and collecting final state
    final_state = state
    async for new_state, event in architect.plan(
        state=state,
        profile=profile,
        workflow_id=workflow_id,
    ):
        final_state = new_state
        if stream_emitter:
            await stream_emitter(event)

    # Save token usage from driver (best-effort)
    await _save_token_usage(driver, workflow_id, "architect", repository)

    # Temporary goal extraction until #199 validator
    goal = _extract_goal_from_markdown(final_state.raw_architect_output)

    # Log the architect plan generation
    logger.info(
        "Agent action completed",
        agent="architect",
        action="generated_plan",
        details={
            "goal_length": len(goal) if goal else 0,
            "tool_calls_count": len(final_state.tool_calls),
            "plan_path": str(final_state.plan_path) if final_state.plan_path else None,
        },
    )

    # Return partial state update
    return {
        "goal": goal,
        "raw_architect_output": final_state.raw_architect_output,
        "plan_markdown": final_state.raw_architect_output,  # Backward compat
        "plan_path": str(final_state.plan_path) if final_state.plan_path else None,
        "tool_calls": list(final_state.tool_calls),
        "tool_results": list(final_state.tool_results),
    }
```

**Step 4: Update imports in orchestrator.py**

Remove `PlanOutput` from imports (line 18), it's no longer needed.

**Run:** `uv run pytest tests/integration/test_agentic_workflow.py::TestArchitectNodeAgenticIntegration -v`

**Expected:** PASS

**Step 5: Run all integration tests**

**Run:** `uv run pytest tests/integration/test_agentic_workflow.py -v`

**Expected:** PASS (existing tests may need updates - see Task 3.2)

**Step 6: Commit**

```bash
git add amelia/core/orchestrator.py tests/integration/test_agentic_workflow.py
git commit -m "feat(orchestrator): consume architect async generator with streaming"
```

---

### Task 3.2: Update Existing Architect Integration Tests

**Files:**
- Modify: `tests/integration/test_agentic_workflow.py`

**Step 1: Update test_architect_node_sets_goal_and_plan**

The existing test mocks `driver.generate()` but now architect uses `execute_agentic()`. Update:

```python
async def test_architect_node_sets_goal_and_plan(self, tmp_path: Path) -> None:
    """Architect node should populate goal and plan_markdown.

    Real components: DriverFactory, ApiDriver, Architect
    Mock boundary: ApiDriver.execute_agentic (yields AgenticMessage)
    """
    from amelia.drivers.base import AgenticMessage, AgenticMessageType

    plans_dir = tmp_path / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)

    profile = make_profile(
        plan_output_dir=str(plans_dir),
        working_dir=str(tmp_path),
    )
    issue = make_issue(id="TEST-1", title="Add feature X", description="Add a new feature X to the system")
    state = make_execution_state(issue=issue, profile=profile)
    config = make_config(thread_id="test-wf-1", profile=profile)

    # Mock AgenticMessage stream with plan result
    mock_messages = [
        AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="# Plan\n\n**Goal:** Implement feature X by modifying component Y\n\n1. Do thing A\n2. Do thing B",
        ),
    ]

    async def mock_execute_agentic(*_args, **_kwargs):
        for msg in mock_messages:
            yield msg

    with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
        result = await call_architect_node(state, cast(RunnableConfig, config))

    assert result["goal"] == "Implement feature X by modifying component Y"
    assert result["plan_markdown"] is not None
    assert "Do thing A" in result["plan_markdown"]
    # Verify plan file was created
    assert result["plan_path"] is not None
    assert Path(result["plan_path"]).exists()
```

**Run:** `uv run pytest tests/integration/test_agentic_workflow.py::TestArchitectNodeIntegration -v`

**Expected:** PASS

**Step 2: Commit**

```bash
git add tests/integration/test_agentic_workflow.py
git commit -m "test(integration): update architect tests for agentic execution"
```

---

## Phase 4: Unit Tests

### Task 4.1: Test Goal Extraction Helper

**Files:**
- Test: `tests/unit/core/test_orchestrator_helpers.py` (create)

**Step 1: Write tests for _extract_goal_from_markdown**

```python
# tests/unit/core/test_orchestrator_helpers.py
"""Tests for orchestrator helper functions."""
import pytest

from amelia.core.orchestrator import _extract_goal_from_markdown


class TestExtractGoalFromMarkdown:
    """Tests for temporary goal extraction helper."""

    def test_extracts_goal_from_markdown(self) -> None:
        """Should extract goal from **Goal:** line."""
        markdown = "# Plan\n\n**Goal:** Implement the feature\n\n## Tasks"
        result = _extract_goal_from_markdown(markdown)
        assert result == "Implement the feature"

    def test_returns_none_for_empty_input(self) -> None:
        """Should return None for empty/None input."""
        assert _extract_goal_from_markdown(None) is None
        assert _extract_goal_from_markdown("") is None

    def test_returns_none_when_no_goal_line(self) -> None:
        """Should return None when no Goal line present."""
        markdown = "# Plan\n\nSome content without goal"
        assert _extract_goal_from_markdown(markdown) is None

    def test_handles_goal_with_colon_in_content(self) -> None:
        """Should handle goal text that contains colons."""
        markdown = "**Goal:** Fix bug: handle edge case"
        result = _extract_goal_from_markdown(markdown)
        assert result == "Fix bug: handle edge case"

    def test_handles_multiline_document(self) -> None:
        """Should find goal anywhere in document."""
        markdown = """# Implementation Plan

Some preamble text.

**Goal:** The actual goal here

## Task 1
Content
"""
        result = _extract_goal_from_markdown(markdown)
        assert result == "The actual goal here"
```

**Run:** `uv run pytest tests/unit/core/test_orchestrator_helpers.py -v`

**Expected:** PASS

**Step 2: Commit**

```bash
git add tests/unit/core/test_orchestrator_helpers.py
git commit -m "test(unit): add tests for goal extraction helper"
```

---

### Task 4.2: Test Architect Tool Call Accumulation

**Files:**
- Modify: `tests/unit/agents/test_architect_agentic.py`

**Step 1: Add test for tool call accumulation**

```python
class TestArchitectToolCallAccumulation:
    """Tests for tool call/result accumulation during plan()."""

    async def test_accumulates_tool_calls_in_state(
        self,
        mock_driver,
        mock_issue_factory,
        mock_profile_factory,
    ) -> None:
        """Should accumulate tool calls in yielded state."""
        issue = mock_issue_factory()
        profile = mock_profile_factory()
        state = ExecutionState(profile_id="test", issue=issue)

        async def mock_stream(*args, **kwargs):
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="read_file",
                tool_input={"path": "a.py"},
                tool_call_id="call-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="read_file",
                tool_output="content",
                tool_call_id="call-1",
            )
            yield AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="list_dir",
                tool_input={"path": "."},
                tool_call_id="call-2",
            )
            yield AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="**Goal:** Done",
            )

        mock_driver.execute_agentic = mock_stream
        architect = Architect(mock_driver)

        final_state = None
        async for new_state, _ in architect.plan(state, profile, workflow_id="wf-1"):
            final_state = new_state

        assert final_state is not None
        assert len(final_state.tool_calls) == 2
        assert final_state.tool_calls[0].tool_name == "read_file"
        assert final_state.tool_calls[1].tool_name == "list_dir"
        assert len(final_state.tool_results) == 1
```

**Run:** `uv run pytest tests/unit/agents/test_architect_agentic.py::TestArchitectToolCallAccumulation -v`

**Expected:** PASS

**Step 2: Commit**

```bash
git add tests/unit/agents/test_architect_agentic.py
git commit -m "test(unit): add architect tool call accumulation tests"
```

---

## Phase 5: Cleanup and Verification

### Task 5.1: Update Type Hints and Imports

**Files:**
- Modify: `amelia/agents/architect.py`
- Modify: `amelia/core/orchestrator.py`

**Step 1: Verify imports are clean**

Check that:
- `MarkdownPlanOutput` is still exported for backward compatibility (keep it)
- `PlanOutput` is still used by other code (check with grep)
- Unused imports are removed

**Run:** `uv run ruff check amelia/agents/architect.py amelia/core/orchestrator.py`

**Expected:** No errors

**Step 2: Commit if changes needed**

```bash
git add amelia/agents/architect.py amelia/core/orchestrator.py
git commit -m "refactor: clean up imports and type hints"
```

---

### Task 5.2: Run Full Test Suite

**Step 1: Run type checking**

**Run:** `uv run mypy amelia`

**Expected:** PASS

**Step 2: Run linter**

**Run:** `uv run ruff check amelia tests`

**Expected:** PASS

**Step 3: Run full test suite**

**Run:** `uv run pytest`

**Expected:** PASS

**Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address type and lint issues"
```

---

## Summary

This implementation:

1. **State Changes:** Adds `raw_architect_output` field for storing raw agentic output
2. **Architect Changes:**
   - Updates system prompt for exploration-focused, reference-based plans
   - Converts `plan()` to async generator yielding `(state, event)` tuples
   - Removes `_scan_codebase()` - agent explores via tools
   - Adds `_build_agentic_prompt()` for simplified prompt building
3. **Orchestrator Changes:**
   - Updates `call_architect_node()` to consume async generator
   - Adds `_extract_goal_from_markdown()` temporary helper
   - Emits stream events during architect execution
4. **Testing:**
   - Unit tests for state field, prompt content, async generator behavior
   - Integration tests for end-to-end agentic execution

**Dependencies:**
- Requires: #198 (unified AgenticMessage) - already merged ✓
- Enables: #199 (validator node) - will consume `raw_architect_output`
