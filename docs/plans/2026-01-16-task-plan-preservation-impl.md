# Task Plan Preservation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix bug where `plan_markdown` gets mutated during task transitions, causing Task B to receive wrong plan content.

**Architecture:** Keep `plan_markdown` immutable throughout the workflow. Extract task sections at prompt-building time in Developer and Reviewer agents rather than mutating state in orchestrator.

**Tech Stack:** Python 3.12+, Pydantic, pytest, pytest-asyncio

---

## Task 1: Fix Orchestrator - Remove plan_markdown Mutation

**Files:**
- Modify: `amelia/core/orchestrator.py:756-759`

**Step 1: Read the current buggy code**

Run: Read `call_developer_node` at lines 756-759 to confirm the mutation.

Current buggy code:
```python
state = state.model_copy(update={
    "driver_session_id": None,  # Fresh session for each task
    "plan_markdown": task_plan,  # Only current task, not full plan <-- BUG
})
```

**Step 2: Remove the plan_markdown mutation**

Replace lines 756-759 with:
```python
state = state.model_copy(update={
    "driver_session_id": None,  # Fresh session for each task
    # plan_markdown stays intact - extraction happens in Developer._build_prompt
})
```

**Step 3: Verify tests still pass**

Run: `uv run pytest tests/integration/test_task_based_execution.py -v`
Expected: Existing tests may fail (expected - Developer doesn't extract yet)

**Step 4: Commit**

```bash
git add amelia/core/orchestrator.py
git commit -m "fix(orchestrator): stop mutating plan_markdown in call_developer_node

Removes the buggy plan_markdown mutation that narrowed the plan to the
current task section, breaking subsequent task transitions. Task section
extraction will be handled at prompt-building time in each agent."
```

---

## Task 2: Update Developer - Add Task Extraction to _build_prompt

**Files:**
- Modify: `amelia/agents/developer.py:135-175`

**Step 1: Read current _build_prompt implementation**

Already captured. Current implementation just appends `state.plan_markdown` without extraction.

**Step 2: Write the failing unit test**

Create file: `tests/unit/agents/test_developer_prompt.py`

```python
"""Unit tests for Developer prompt building with task extraction."""

import pytest

from amelia.agents.developer import Developer
from amelia.core.state import ExecutionState


@pytest.fixture
def multi_task_plan() -> str:
    """A plan with header and 3 tasks."""
    return """# Implementation Plan

## Goal
Build a feature with multiple tasks.

## Architecture
Modular design with clear separation.

## Tech Stack
Python, pytest

---

## Phase 1: Foundation

### Task 1: Create module

Create the base module structure.

### Task 2: Add validation

Add input validation logic.

## Phase 2: Testing

### Task 3: Write tests

Add comprehensive test coverage.
"""


class TestDeveloperBuildPrompt:
    """Tests for Developer._build_prompt task extraction."""

    def test_single_task_uses_full_plan(self) -> None:
        """When total_tasks is None or 1, use full plan without extraction."""
        state = ExecutionState(
            profile_id="test",
            goal="Implement feature",
            plan_markdown="# Simple Plan\n\nJust do the thing.",
            total_tasks=None,
            current_task_index=0,
        )
        developer = Developer(driver=None)  # type: ignore[arg-type]
        prompt = developer._build_prompt(state)

        assert "# Simple Plan" in prompt
        assert "Just do the thing." in prompt

    def test_multi_task_extracts_current_section(
        self, multi_task_plan: str
    ) -> None:
        """For multi-task execution, extract only the current task section."""
        state = ExecutionState(
            profile_id="test",
            goal="Implement feature",
            plan_markdown=multi_task_plan,
            total_tasks=3,
            current_task_index=1,  # Task 2 (0-indexed)
        )
        developer = Developer(driver=None)  # type: ignore[arg-type]
        prompt = developer._build_prompt(state)

        # Should contain Task 2 content
        assert "Task 2" in prompt
        assert "Add validation" in prompt
        # Should NOT contain other tasks
        assert "Task 1:" not in prompt or "### Task 1:" not in prompt
        assert "Task 3:" not in prompt or "### Task 3:" not in prompt

    def test_multi_task_includes_breadcrumb(self, multi_task_plan: str) -> None:
        """Breadcrumb shows task progress for context."""
        state = ExecutionState(
            profile_id="test",
            goal="Implement feature",
            plan_markdown=multi_task_plan,
            total_tasks=3,
            current_task_index=2,  # Task 3 (0-indexed)
        )
        developer = Developer(driver=None)  # type: ignore[arg-type]
        prompt = developer._build_prompt(state)

        # Should show progress breadcrumb
        assert "Tasks 1-2 of 3 completed" in prompt
        assert "Task 3" in prompt

    def test_first_task_breadcrumb(self, multi_task_plan: str) -> None:
        """First task shows appropriate breadcrumb."""
        state = ExecutionState(
            profile_id="test",
            goal="Implement feature",
            plan_markdown=multi_task_plan,
            total_tasks=3,
            current_task_index=0,  # Task 1 (0-indexed)
        )
        developer = Developer(driver=None)  # type: ignore[arg-type]
        prompt = developer._build_prompt(state)

        # First task breadcrumb
        assert "Executing Task 1 of 3" in prompt
        # Should NOT say "completed"
        assert "completed" not in prompt.lower()

    def test_missing_plan_raises_error(self) -> None:
        """Developer requires plan_markdown from Architect."""
        state = ExecutionState(
            profile_id="test",
            goal="Implement feature",
            plan_markdown=None,
        )
        developer = Developer(driver=None)  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="requires plan_markdown"):
            developer._build_prompt(state)
```

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_developer_prompt.py -v`
Expected: FAIL - tests will fail because extraction logic doesn't exist yet

**Step 4: Update Developer._build_prompt with task extraction**

Replace `Developer._build_prompt` method (lines 135-175) with:

```python
def _build_prompt(self, state: ExecutionState) -> str:
    """Build prompt combining goal, review feedback, and context.

    For multi-task execution, extracts only the current task section
    from the full plan and includes a progress breadcrumb.
    """
    parts = []

    if not state.plan_markdown:
        raise ValueError(
            "Developer requires plan_markdown. Architect must run first."
        )

    parts.append("""
You have a detailed implementation plan to follow. Execute it using your tools.
Use your judgment to handle unexpected situations - the plan is a guide, not rigid steps.

## CRITICAL: No Summary Files

DO NOT create any of the following files:
- TASK_*_COMPLETION.md, TASK_*_INDEX.md, TASK_*_SUMMARY.md
- IMPLEMENTATION_*.md, EXECUTION_*.md
- CODE_REVIEW*.md, FINAL_SUMMARY.md
- Any markdown file that summarizes progress, completion status, or documents work done

These files waste tokens and provide no value. The code changes ARE the deliverable.
Only create files explicitly listed in the plan's "Create:" directives.

---
IMPLEMENTATION PLAN:
---
""")

    from amelia.core.orchestrator import extract_task_section

    total = state.total_tasks or 1
    current = state.current_task_index

    if total == 1:
        parts.append(state.plan_markdown)
    else:
        task_section = extract_task_section(state.plan_markdown, current)
        task_num = current + 1
        if current > 0:
            parts.append(
                f"Tasks 1-{current} of {total} completed. "
                f"Now executing Task {task_num}:\n\n"
            )
        else:
            parts.append(f"Executing Task 1 of {total}:\n\n")
        parts.append(task_section)

    # Main task
    parts.append(f"\n\nPlease complete the following task:\n\n{state.goal}")

    # Review feedback (if this is a review-fix iteration)
    if state.last_review and not state.last_review.approved:
        feedback = "\n".join(f"- {c}" for c in state.last_review.comments)
        parts.append(f"\n\nThe reviewer requested the following changes:\n{feedback}")

    return "\n".join(parts)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/agents/test_developer_prompt.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/agents/developer.py tests/unit/agents/test_developer_prompt.py
git commit -m "feat(developer): extract task section in _build_prompt

Moves task extraction from orchestrator mutation to prompt-building time.
Adds breadcrumb showing task progress (e.g., 'Tasks 1-2 of 5 completed').
Raises ValueError if plan_markdown is missing."
```

---

## Task 3: Update Reviewer - Add Task Extraction to _extract_task_context

**Files:**
- Modify: `amelia/agents/reviewer.py:207-231`
- Test: `tests/unit/agents/test_reviewer.py`

**Step 1: Write the failing unit test**

Add to `tests/unit/agents/test_reviewer.py`:

```python
class TestExtractTaskContext:
    """Tests for Reviewer._extract_task_context task extraction."""

    @pytest.fixture
    def multi_task_plan(self) -> str:
        """A plan with 3 tasks."""
        return """# Plan

## Goal
Multi-task feature.

---

### Task 1: Create module
First task content.

### Task 2: Add validation
Second task content.

### Task 3: Write tests
Third task content.
"""

    def test_single_task_returns_full_plan(self) -> None:
        """When total_tasks is None or 1, return full plan."""
        state = ExecutionState(
            profile_id="test",
            goal="Implement feature",
            plan_markdown="# Simple Plan\n\nJust do it.",
            total_tasks=None,
            current_task_index=0,
        )
        reviewer = Reviewer(driver=None)  # type: ignore[arg-type]
        context = reviewer._extract_task_context(state)

        assert context is not None
        assert "**Task:**" in context
        assert "Simple Plan" in context

    def test_multi_task_extracts_current_section(
        self, multi_task_plan: str
    ) -> None:
        """For multi-task, extract current task with index label."""
        state = ExecutionState(
            profile_id="test",
            goal="Implement feature",
            plan_markdown=multi_task_plan,
            total_tasks=3,
            current_task_index=1,  # Task 2
        )
        reviewer = Reviewer(driver=None)  # type: ignore[arg-type]
        context = reviewer._extract_task_context(state)

        assert context is not None
        assert "Current Task (2/3)" in context
        assert "Add validation" in context

    def test_no_plan_returns_goal_fallback(self) -> None:
        """Without plan, fall back to goal."""
        state = ExecutionState(
            profile_id="test",
            goal="Just do the thing",
            plan_markdown=None,
        )
        reviewer = Reviewer(driver=None)  # type: ignore[arg-type]
        context = reviewer._extract_task_context(state)

        assert context is not None
        assert "Just do the thing" in context
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_reviewer.py::TestExtractTaskContext -v`
Expected: FAIL - new test class doesn't exist, extraction logic missing

**Step 3: Update Reviewer._extract_task_context**

Replace `Reviewer._extract_task_context` method (lines 207-231) with:

```python
def _extract_task_context(self, state: ExecutionState) -> str | None:
    """Extract task context from execution state.

    For multi-task execution, extracts only the current task section
    from the full plan.

    Args:
        state: Current execution state containing plan or goal.

    Returns:
        Formatted task context string, or None if no context found.
    """
    if state.plan_markdown:
        from amelia.core.orchestrator import extract_task_section

        total = state.total_tasks or 1
        current = state.current_task_index

        if total == 1:
            return f"**Task:**\n\n{state.plan_markdown}"

        task_section = extract_task_section(state.plan_markdown, current)
        return f"**Current Task ({current + 1}/{total}):**\n\n{task_section}"

    if state.goal:
        return f"**Task Goal:**\n\n{state.goal}"

    if state.issue:
        issue_parts = []
        if state.issue.title:
            issue_parts.append(f"**{state.issue.title}**")
        if state.issue.description:
            issue_parts.append(state.issue.description)
        if issue_parts:
            return "\n\n".join(issue_parts)

    return None
```

**Step 4: Add required imports at top of reviewer.py if missing**

Check if `ExecutionState` import exists. It should already be imported.

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/agents/test_reviewer.py::TestExtractTaskContext -v`
Expected: PASS

**Step 6: Commit**

```bash
git add amelia/agents/reviewer.py tests/unit/agents/test_reviewer.py
git commit -m "feat(reviewer): extract task section in _extract_task_context

Mirrors Developer change - extracts current task section from full plan
at prompt-building time. Shows task index (e.g., 'Current Task (2/3)')."
```

---

## Task 4: Integration Test - Verify plan_markdown Preserved Across Tasks

**Files:**
- Modify: `tests/integration/test_task_based_execution.py`

**Step 1: Write integration test for plan preservation**

Add to `tests/integration/test_task_based_execution.py`:

```python
class TestPlanMarkdownPreservation:
    """Tests that plan_markdown stays intact across task transitions."""

    async def test_plan_markdown_unchanged_after_developer_node(
        self,
        tmp_path: Path,
        integration_profile: Profile,
        integration_issue: Issue,
        multi_task_plan_content: str,
    ) -> None:
        """Developer node should NOT mutate plan_markdown in returned state.

        Real components: call_developer_node state handling
        Mock boundary: ApiDriver.execute_agentic
        """
        plan_path = tmp_path / "plans" / "test-plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(multi_task_plan_content)

        original_plan = multi_task_plan_content

        state = ExecutionState(
            profile_id="test-preservation",
            issue=integration_issue,
            goal="Implement feature",
            plan_markdown=original_plan,
            plan_path=plan_path,
            total_tasks=3,
            current_task_index=0,
        )

        config = make_config(
            thread_id="test-preservation",
            profile=integration_profile,
        )

        async def mock_execute_agentic(*args: Any, **kwargs: Any) -> Any:
            for msg in _create_developer_mock_messages(1):
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            result = await call_developer_node(state, cast(RunnableConfig, config))

        # The returned state dict should NOT contain plan_markdown
        # (preserving immutability - orchestrator uses state.plan_markdown directly)
        assert "plan_markdown" not in result, (
            "call_developer_node should not return plan_markdown in updates"
        )

    async def test_developer_prompt_contains_task_section_not_full_plan(
        self,
        tmp_path: Path,
        integration_profile: Profile,
        integration_issue: Issue,
        multi_task_plan_content: str,
    ) -> None:
        """Developer should receive extracted task section, not full plan.

        Real components: Developer._build_prompt, extract_task_section
        Mock boundary: ApiDriver.execute_agentic
        """
        plan_path = tmp_path / "plans" / "test-plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(multi_task_plan_content)

        state = ExecutionState(
            profile_id="test-extraction",
            issue=integration_issue,
            goal="Implement feature",
            plan_markdown=multi_task_plan_content,
            plan_path=plan_path,
            total_tasks=3,
            current_task_index=1,  # Task 2
        )

        config = make_config(
            thread_id="test-extraction",
            profile=integration_profile,
        )

        captured_prompt: list[str] = []

        async def mock_execute_agentic(*args: Any, **kwargs: Any) -> Any:
            prompt = kwargs.get("prompt", "")
            captured_prompt.append(prompt)
            for msg in _create_developer_mock_messages(1):
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            await call_developer_node(state, cast(RunnableConfig, config))

        assert len(captured_prompt) == 1
        prompt = captured_prompt[0]

        # Should have Task 2 content
        assert "Task 2" in prompt
        assert "Add tests" in prompt
        # Should NOT have Task 1 or Task 3 as separate task headers
        # (Task 1 content might appear in extraction header context)
        assert "### Task 3:" not in prompt
```

**Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_task_based_execution.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_task_based_execution.py
git commit -m "test(integration): verify plan_markdown preservation across tasks

Adds tests ensuring:
- call_developer_node doesn't return plan_markdown in updates
- Developer prompt contains extracted task section, not full plan"
```

---

## Task 5: Run Full Test Suite and Fix Any Failures

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

**Step 2: Run type checking**

Run: `uv run mypy amelia`
Expected: No type errors

**Step 3: Run linting**

Run: `uv run ruff check amelia tests`
Expected: No lint errors

**Step 4: Fix any failures found**

If any tests fail, investigate and fix. Common issues:
- Import errors from circular imports (extract_task_section import)
- Existing tests that relied on mutated plan_markdown

**Step 5: Final commit if fixes needed**

```bash
git add -A
git commit -m "fix: address test failures from plan preservation changes"
```

---

## Task 6: Cleanup - Remove Dead Code Paths

**Files:**
- Modify: `amelia/agents/developer.py` (remove issue fallback if present)

**Step 1: Check for dead code in Developer._build_prompt**

The design doc mentions removing `state.goal` and `state.issue` fallback branches. Review if these exist.

Current code has:
```python
# Issue context (fallback if no plan)
if state.issue and not state.plan_markdown:
    parts.append(f"\nIssue: {state.issue.title}\n{state.issue.description}")
```

**Step 2: Remove dead fallback code**

Since we now raise ValueError when plan_markdown is missing, the issue fallback is dead code. Remove it.

**Step 3: Run tests to verify nothing broke**

Run: `uv run pytest tests/unit/agents/test_developer_prompt.py -v`
Expected: PASS

**Step 4: Commit cleanup**

```bash
git add amelia/agents/developer.py
git commit -m "refactor(developer): remove dead issue fallback code

Plan is now the single source of truth. Issue context is captured
in the plan by the Architect."
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `amelia/core/orchestrator.py` | Remove `plan_markdown` mutation in `call_developer_node` |
| `amelia/agents/developer.py` | Task extraction + breadcrumb in `_build_prompt()`, remove issue fallback |
| `amelia/agents/reviewer.py` | Task extraction in `_extract_task_context()` |
| `tests/unit/agents/test_developer_prompt.py` | New file - prompt building tests |
| `tests/unit/agents/test_reviewer.py` | Add `TestExtractTaskContext` class |
| `tests/integration/test_task_based_execution.py` | Add `TestPlanMarkdownPreservation` class |
