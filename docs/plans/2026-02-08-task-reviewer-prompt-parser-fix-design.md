# Task Reviewer Prompt/Parser Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three compounding bugs that cause task-based workflows to abort: prompt/parser mismatch, fragile keyword fallback, and max-iterations killing the workflow.

**Architecture:** Extract review output format as a shared constant so both prompt sources (CLI class constant + server-mode defaults) produce markdown the parser expects. Replace the fragile keyword fallback with a safe `approved=False` default. Change routing to advance to next task on max iterations instead of aborting the entire workflow.

**Tech Stack:** Python 3.12, pytest, Pydantic, Loguru

**Issue:** [#407](https://github.com/existential-birds/amelia-feature/issues/407)

---

### Task 1: Unit tests for `route_after_task_review` max-iterations on non-final task

Tests the new behavior: max iterations on a non-final task routes to `next_task_node` instead of `__end__`.

**Files:**
- Modify: `tests/unit/pipelines/test_routing.py`

**Step 1: Write the failing tests**

Add a new test class `TestRouteAfterTaskReview` to the existing file:

```python
from amelia.core.types import AgentConfig, Profile, ReviewResult, Severity
from amelia.pipelines.implementation.routing import route_after_start, route_after_task_review


class TestRouteAfterTaskReview:
    """Tests for route_after_task_review routing function."""

    @pytest.fixture
    def profile(self) -> Profile:
        """Profile with task_reviewer max_iterations=2."""
        return Profile(
            id="test",
            name="test",
            driver="cli",
            model="sonnet",
            agents={
                "task_reviewer": AgentConfig(
                    driver="cli", model="sonnet", options={"max_iterations": 2}
                ),
            },
        )

    def test_approved_non_final_task_routes_to_next_task(self, profile: Profile) -> None:
        """Approved + more tasks remaining -> next_task_node."""
        state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="in_progress",
            current_task_index=0,
            total_tasks=3,
            last_review=ReviewResult(
                reviewer_persona="Agentic", approved=True, comments=[], severity=Severity.NONE
            ),
        )
        assert route_after_task_review(state, profile) == "next_task_node"

    def test_approved_final_task_routes_to_end(self, profile: Profile) -> None:
        """Approved + last task -> __end__."""
        state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="in_progress",
            current_task_index=2,
            total_tasks=3,
            last_review=ReviewResult(
                reviewer_persona="Agentic", approved=True, comments=[], severity=Severity.NONE
            ),
        )
        assert route_after_task_review(state, profile) == "__end__"

    def test_not_approved_within_iterations_routes_to_developer(self, profile: Profile) -> None:
        """Not approved + iterations remaining -> developer."""
        state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="in_progress",
            current_task_index=0,
            total_tasks=3,
            task_review_iteration=1,
            last_review=ReviewResult(
                reviewer_persona="Agentic", approved=False, comments=["fix X"], severity=Severity.MAJOR
            ),
        )
        assert route_after_task_review(state, profile) == "developer"

    def test_max_iterations_non_final_task_advances_to_next(self, profile: Profile) -> None:
        """Max iterations on non-final task -> next_task_node (NOT __end__)."""
        state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="in_progress",
            current_task_index=0,
            total_tasks=3,
            task_review_iteration=2,  # == max_iterations
            last_review=ReviewResult(
                reviewer_persona="Agentic", approved=False, comments=["fix X"], severity=Severity.MAJOR
            ),
        )
        assert route_after_task_review(state, profile) == "next_task_node"

    def test_max_iterations_final_task_routes_to_end(self, profile: Profile) -> None:
        """Max iterations on final task -> __end__."""
        state = ImplementationState(
            workflow_id="wf-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="in_progress",
            current_task_index=2,
            total_tasks=3,
            task_review_iteration=2,  # == max_iterations
            last_review=ReviewResult(
                reviewer_persona="Agentic", approved=False, comments=["fix X"], severity=Severity.MAJOR
            ),
        )
        assert route_after_task_review(state, profile) == "__end__"
```

Add the missing imports at the top of the file:

```python
import pytest
from amelia.core.types import AgentConfig, Profile, ReviewResult, Severity
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/pipelines/test_routing.py::TestRouteAfterTaskReview -v`
Expected: `test_max_iterations_non_final_task_advances_to_next` FAILS (currently returns `"__end__"`)

**Step 3: Commit**

```bash
git add tests/unit/pipelines/test_routing.py
git commit -m "test: add route_after_task_review tests for max-iterations behavior

Cover all branches: approved final/non-final, not-approved within iterations,
and max-iterations on final vs non-final task. The non-final max-iterations
test expects next_task_node (currently fails, returns __end__)."
```

---

### Task 2: Fix `route_after_task_review` to advance on max iterations

**Files:**
- Modify: `amelia/pipelines/implementation/routing.py:42-103`

**Step 1: Implement the fix**

Replace the `route_after_task_review` function body. When `task_review_iteration >= max_iterations` on a non-final task, route to `"next_task_node"` with a warning log. Only return `"__end__"` for the final task.

```python
def route_after_task_review(
    state: ImplementationState,
    profile: Profile,
) -> Literal["developer", "next_task_node", "__end__"]:
    """Route after task review: next task, retry developer, or end.

    Args:
        state: Current execution state with task tracking fields.
        profile: Profile with agent configs. Uses task_reviewer.options.max_iterations.

    Returns:
        "next_task_node" if approved and more tasks remain.
        "developer" if not approved and iterations remain.
        "next_task_node" if max iterations on a non-final task (advance with warning).
        "__end__" if all tasks complete or max iterations on final task.
    """
    task_number = state.current_task_index + 1
    is_final_task = state.current_task_index + 1 >= state.total_tasks
    approved = state.last_review.approved if state.last_review else False

    if approved:
        if is_final_task:
            logger.debug(
                "Task routing decision",
                task=task_number,
                approved=True,
                route="__end__",
                reason="all_tasks_complete",
            )
            return "__end__"
        logger.debug(
            "Task routing decision",
            task=task_number,
            approved=True,
            route="next_task_node",
        )
        return "next_task_node"

    # Not approved - check iteration limit from task_reviewer options, default to 5
    max_iterations = 5
    if "task_reviewer" in profile.agents:
        max_iterations = profile.agents["task_reviewer"].options.get("max_iterations", 5)
    if state.task_review_iteration >= max_iterations:
        if is_final_task:
            logger.debug(
                "Task routing decision",
                task=task_number,
                approved=False,
                iteration=state.task_review_iteration,
                max_iterations=max_iterations,
                route="__end__",
                reason="max_iterations_on_final_task",
            )
            return "__end__"
        logger.warning(
            "Max review iterations reached on non-final task, advancing to next task",
            task=task_number,
            iteration=state.task_review_iteration,
            max_iterations=max_iterations,
            route="next_task_node",
        )
        return "next_task_node"

    logger.debug(
        "Task routing decision",
        task=task_number,
        approved=False,
        iteration=state.task_review_iteration,
        max_iterations=max_iterations,
        route="developer",
    )
    return "developer"
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/pipelines/test_routing.py -v`
Expected: All tests PASS including `test_max_iterations_non_final_task_advances_to_next`

**Step 3: Commit**

```bash
git add amelia/pipelines/implementation/routing.py
git commit -m "fix: advance to next task on max iterations instead of aborting workflow

When task_review_iteration >= max_iterations on a non-final task, route to
next_task_node with a warning log instead of returning __end__. This prevents
a single stuck task from killing a multi-task workflow.

Fixes #407 (partial)"
```

---

### Task 3: Unit tests for `_parse_review_result` fallback removal

Tests that the parser returns `approved=False` (not keyword-based guessing) when the `Ready:` pattern is missing.

**Files:**
- Modify: `tests/unit/agents/test_reviewer.py`

**Step 1: Write the failing tests**

Add these test methods to the existing `TestParseReviewResult` class:

```python
    def test_no_ready_pattern_defaults_to_not_approved(self, create_reviewer: Callable[..., Reviewer]) -> None:
        """When Ready: pattern is missing, default to approved=False (no keyword guessing)."""
        reviewer = create_reviewer()
        output = """## Review Summary
Code looks good overall with minor issues.

## Issues
### Critical (Blocking)
None

## Good Patterns
- Clean architecture

## Verdict
The code is approved and looks good to merge.
Rationale: All checks pass."""

        result = reviewer._parse_review_result(output, workflow_id="wf-test")
        # Should NOT match "approved" keyword - should default to False
        assert result.approved is False

    def test_json_output_without_ready_pattern_defaults_to_not_approved(
        self, create_reviewer: Callable[..., Reviewer]
    ) -> None:
        """JSON output (from mismatched prompt) should default to not approved."""
        reviewer = create_reviewer()
        output = '{"approved": true, "comments": [], "severity": "none"}'

        result = reviewer._parse_review_result(output, workflow_id="wf-test")
        assert result.approved is False

    def test_truncated_output_without_ready_pattern_defaults_to_not_approved(
        self, create_reviewer: Callable[..., Reviewer]
    ) -> None:
        """Truncated output missing verdict section should default to not approved."""
        reviewer = create_reviewer()
        output = """## Review Summary
Code changes implement the feature correctly.

## Issues
### Minor (Nice to Have)
1. [src/main.py:42] Consider adding type hint"""

        result = reviewer._parse_review_result(output, workflow_id="wf-test")
        assert result.approved is False
        assert len(result.comments) >= 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/agents/test_reviewer.py::TestParseReviewResult::test_no_ready_pattern_defaults_to_not_approved tests/unit/agents/test_reviewer.py::TestParseReviewResult::test_json_output_without_ready_pattern_defaults_to_not_approved -v`
Expected: `test_no_ready_pattern_defaults_to_not_approved` FAILS (keyword fallback currently sets `approved=True` because "approved" is in the text)

**Step 3: Commit**

```bash
git add tests/unit/agents/test_reviewer.py
git commit -m "test: add _parse_review_result tests for fallback removal

Tests that missing Ready: pattern defaults to approved=False instead of
keyword guessing. Covers: text with 'approved' keyword, JSON output from
mismatched prompt, and truncated output."
```

---

### Task 4: Remove keyword fallback in `_parse_review_result`

**Files:**
- Modify: `amelia/agents/reviewer.py:349-497` (the `_parse_review_result` method)

**Step 1: Implement the fix**

Replace the keyword fallback `else` branch (lines ~405-422 in the current code) with a simple `approved=False` default and a warning log. The target code in the `else` branch of `if verdict_match:` should become:

```python
        else:
            # No Ready: pattern found - default to not approved for safety.
            # The prompt instructs the model to produce "Ready: Yes|No";
            # if it doesn't, rejecting is the safe default, and the
            # max-iterations routing fix prevents this from killing the workflow.
            approved = False
            logger.warning(
                "No 'Ready:' verdict found in review output, defaulting to not approved",
                agent=self._agent_name,
                output_preview=output[:200] if output else None,
                workflow_id=workflow_id,
            )
```

This replaces the entire keyword scanning block (the `approval_keywords_found` / `rejection_keywords_found` logic).

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/agents/test_reviewer.py::TestParseReviewResult -v`
Expected: All tests PASS including the new fallback tests

**Step 3: Run the full test suite to check for regressions**

Run: `uv run pytest tests/unit/agents/test_reviewer.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add amelia/agents/reviewer.py
git commit -m "fix: replace fragile keyword fallback with safe approved=False default

Remove the keyword scanner in _parse_review_result() that matched 'approved'
regardless of context. When the Ready: pattern is missing, default to
approved=False with a warning log. Combined with the max-iterations routing
fix, this prevents false positives without killing the workflow.

Fixes #407 (partial)"
```

---

### Task 5: Extract `REVIEW_OUTPUT_FORMAT` constant and fix prompt mismatch

**Files:**
- Modify: `amelia/agents/reviewer.py:1-102` (add constant, update `AGENTIC_REVIEW_PROMPT`)
- Modify: `amelia/agents/prompts/defaults.py:86-128` (update `reviewer.agentic` entry)

**Step 1: Write the failing test**

Add a test to `tests/unit/agents/test_reviewer_prompts.py` that verifies both prompt sources contain the same output format:

```python
    def test_review_output_format_in_both_prompts(self) -> None:
        """REVIEW_OUTPUT_FORMAT must appear in both AGENTIC_REVIEW_PROMPT and PROMPT_DEFAULTS."""
        from amelia.agents.prompts.defaults import PROMPT_DEFAULTS
        from amelia.agents.reviewer import REVIEW_OUTPUT_FORMAT, Reviewer

        assert REVIEW_OUTPUT_FORMAT in Reviewer.AGENTIC_REVIEW_PROMPT, (
            "REVIEW_OUTPUT_FORMAT missing from Reviewer.AGENTIC_REVIEW_PROMPT"
        )
        assert REVIEW_OUTPUT_FORMAT in PROMPT_DEFAULTS["reviewer.agentic"].content, (
            "REVIEW_OUTPUT_FORMAT missing from PROMPT_DEFAULTS['reviewer.agentic']"
        )

    def test_prompt_defaults_reviewer_has_ready_verdict_not_json(self) -> None:
        """PROMPT_DEFAULTS['reviewer.agentic'] must use markdown Ready: format, not JSON."""
        from amelia.agents.prompts.defaults import PROMPT_DEFAULTS

        content = PROMPT_DEFAULTS["reviewer.agentic"].content
        assert "Ready: Yes" in content, "Prompt must instruct Ready: Yes|No verdict"
        assert '"approved"' not in content, "Prompt must not instruct JSON output"
```

Add this test class (`TestReviewOutputFormatConstant`) to the existing file, or add the methods to the existing `TestReviewerPromptInjection` class if appropriate. Since they test a different concern, a new class is better:

```python
class TestReviewOutputFormatConstant:
    """Tests for REVIEW_OUTPUT_FORMAT shared constant."""
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/agents/test_reviewer_prompts.py::TestReviewOutputFormatConstant -v`
Expected: FAIL - `REVIEW_OUTPUT_FORMAT` doesn't exist yet, `PROMPT_DEFAULTS` still has JSON format

**Step 3: Extract the constant and update both prompts**

In `amelia/agents/reviewer.py`, add a module-level constant before the `Reviewer` class (after imports, around line 18):

```python
REVIEW_OUTPUT_FORMAT = """## Review Summary

[1-2 sentence overview of findings]

## Issues

### Critical (Blocking)

1. [FILE:LINE] ISSUE_TITLE
   - Issue: Description of what's wrong
   - Why: Why this matters (bug, type safety, security)
   - Fix: Specific recommended fix

### Major (Should Fix)

2. [FILE:LINE] ISSUE_TITLE
   - Issue: ...
   - Why: ...
   - Fix: ...

### Minor (Nice to Have)

N. [FILE:LINE] ISSUE_TITLE
   - Issue: ...
   - Why: ...
   - Fix: ...

## Good Patterns

- [FILE:LINE] Pattern description (preserve this)

## Verdict

Ready: Yes | No | With fixes 1-N
Rationale: [1-2 sentences]"""
```

Update `Reviewer.AGENTIC_REVIEW_PROMPT` to interpolate the constant. Replace the inline markdown template (lines 56-92) with `{REVIEW_OUTPUT_FORMAT}` using an f-string or string concatenation. The prompt body before "## Rules" should reference the constant:

```python
    AGENTIC_REVIEW_PROMPT = f"""You are an expert code reviewer. Your task is to review code changes using the appropriate review skills.

## Process

1. **Identify Changed Files**: Run `git diff --name-only {{base_commit}}` to see what files changed

2. **Detect Technologies**: Based on file extensions and imports, identify the stack:
   - Python files (.py): Look for FastAPI, Pydantic-AI, SQLAlchemy, pytest
   - Go files (.go): Look for BubbleTea, Wish, Prometheus
   - TypeScript/React (.tsx, .ts): Look for React Router, shadcn/ui, Zustand, React Flow

3. **Load Review Skills**: Use the `Skill` tool to load appropriate review skills:
   - Python: `beagle:review-python` (FastAPI, pytest, Pydantic)
   - Go: `beagle:review-go` (error handling, concurrency, interfaces)
   - Frontend: `beagle:review-frontend` (React, TypeScript, CSS)
   - TUI: `beagle:review-tui` (BubbleTea terminal apps)

4. **Get the Diff**: Run `git diff {{base_commit}}` to get the full diff

5. **Review**: Follow the loaded skill's instructions to review the code

6. **Output**: Provide your review in the following markdown format:

```markdown
{REVIEW_OUTPUT_FORMAT}
```

## Rules

- Load skills BEFORE reviewing (not after)
- Number every issue sequentially (1, 2, 3...)
- Include FILE:LINE for each issue
- Separate Issue/Why/Fix clearly
- Categorize by actual severity (Critical/Major/Minor)
- Only flag real issues - check linters first before flagging style issues
- "Ready: Yes" means approved to merge as-is"""
```

**Important:** Since the prompt uses `.format(base_commit=...)` at call time, literal `{base_commit}` must be escaped as `{{base_commit}}` in the f-string. The constant itself has no format variables, so it interpolates cleanly.

Update `amelia/agents/prompts/defaults.py` to import and use the constant:

At the top of the file, add:
```python
from amelia.agents.reviewer import REVIEW_OUTPUT_FORMAT
```

Replace the `"reviewer.agentic"` entry's content to match the class constant (same structure, same output format). The key change is replacing the JSON output section (lines 111-119) with the markdown format from the constant. The full content should mirror `Reviewer.AGENTIC_REVIEW_PROMPT` exactly (they are the same prompt, just the default for server-mode customization):

```python
    "reviewer.agentic": PromptDefault(
        agent="reviewer",
        name="Reviewer Agentic Prompt",
        description="Instructions for agentic code review with tool calling and skill loading",
        content=f"""You are an expert code reviewer. Your task is to review code changes using the appropriate review skills.

## Process

1. **Identify Changed Files**: Run `git diff --name-only {{base_commit}}` to see what files changed

2. **Detect Technologies**: Based on file extensions and imports, identify the stack:
   - Python files (.py): Look for FastAPI, Pydantic-AI, SQLAlchemy, pytest
   - Go files (.go): Look for BubbleTea, Wish, Prometheus
   - TypeScript/React (.tsx, .ts): Look for React Router, shadcn/ui, Zustand, React Flow

3. **Load Review Skills**: Use the `Skill` tool to load appropriate review skills:
   - Python: `beagle:review-python` (FastAPI, pytest, Pydantic)
   - Go: `beagle:review-go` (error handling, concurrency, interfaces)
   - Frontend: `beagle:review-frontend` (React, TypeScript, CSS)
   - TUI: `beagle:review-tui` (BubbleTea terminal apps)

4. **Get the Diff**: Run `git diff {{base_commit}}` to get the full diff

5. **Review**: Follow the loaded skill's instructions to review the code

6. **Output**: Provide your review in the following markdown format:

```markdown
{REVIEW_OUTPUT_FORMAT}
```

## Rules

- Load skills BEFORE reviewing (not after)
- Number every issue sequentially (1, 2, 3...)
- Include FILE:LINE for each issue
- Separate Issue/Why/Fix clearly
- Categorize by actual severity (Critical/Major/Minor)
- Only flag real issues - check linters first before flagging style issues
- "Ready: Yes" means approved to merge as-is""",
    ),
```

**Note on circular imports:** `defaults.py` importing from `reviewer.py` — `REVIEW_OUTPUT_FORMAT` is a module-level string constant defined before the `Reviewer` class, so it imports cleanly. `reviewer.py` does NOT import from `defaults.py`, so there is no circular dependency.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/agents/test_reviewer_prompts.py -v`
Expected: All tests PASS

**Step 5: Run the full reviewer test suite**

Run: `uv run pytest tests/unit/agents/test_reviewer.py tests/unit/agents/test_reviewer_prompts.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add amelia/agents/reviewer.py amelia/agents/prompts/defaults.py tests/unit/agents/test_reviewer_prompts.py
git commit -m "fix: extract REVIEW_OUTPUT_FORMAT constant to align prompt with parser

Create module-level REVIEW_OUTPUT_FORMAT constant in reviewer.py containing
the markdown review template. Both Reviewer.AGENTIC_REVIEW_PROMPT and
PROMPT_DEFAULTS['reviewer.agentic'] now interpolate this constant, replacing
the JSON output instruction in defaults.py. This ensures server-mode reviews
produce the Ready: Yes|No verdict that _parse_review_result() expects.

Fixes #407"
```

---

### Task 6: Integration test — reviewer prompt-to-parse chain

Tests the full chain from prompt resolution through parsing with only the driver boundary mocked.

**Files:**
- Create: `tests/integration/test_reviewer_prompt_parser.py`

**Step 1: Write the integration test**

```python
"""Integration test: reviewer prompt resolution -> parse chain.

Verifies that the prompt from PROMPT_DEFAULTS produces output the parser
can handle, with only the driver boundary mocked.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from amelia.agents.reviewer import REVIEW_OUTPUT_FORMAT, Reviewer
from amelia.core.types import AgentConfig, Profile, ReviewResult, Severity
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.implementation.routing import route_after_task_review
from amelia.pipelines.implementation.state import ImplementationState
from tests.conftest import AsyncIteratorMock


WELL_FORMED_REVIEW = """## Review Summary

All changes look correct and follow project conventions.

## Issues

### Critical (Blocking)

None

### Major (Should Fix)

None

### Minor (Nice to Have)

None

## Good Patterns

- [src/main.py:10] Clean separation of concerns

## Verdict

Ready: Yes
Rationale: Code is clean and follows conventions."""


MALFORMED_REVIEW = """The code changes implement the feature.

I noticed a few things:
- The error handling could be improved
- Some type hints are missing

Overall the code is acceptable."""


@pytest.fixture
def profile() -> Profile:
    """Profile with task_reviewer configured."""
    return Profile(
        id="test",
        name="test",
        driver="cli",
        model="sonnet",
        agents={
            "task_reviewer": AgentConfig(
                driver="cli", model="sonnet", options={"max_iterations": 2}
            ),
        },
    )


@pytest.fixture
def mock_driver() -> MagicMock:
    """Mock driver for reviewer."""
    return MagicMock()


@pytest.fixture
def create_reviewer_with_defaults(mock_driver: MagicMock) -> Callable[..., Reviewer]:
    """Create Reviewer using PROMPT_DEFAULTS content (server-mode path)."""
    from amelia.agents.prompts.defaults import PROMPT_DEFAULTS

    def _create() -> Reviewer:
        prompts = {pid: pd.content for pid, pd in PROMPT_DEFAULTS.items()}
        with patch("amelia.agents.reviewer.get_driver", return_value=mock_driver):
            config = AgentConfig(driver="cli", model="sonnet", options={})
            return Reviewer(config, prompts=prompts, agent_name="task_reviewer")

    return _create


@pytest.mark.integration
class TestReviewerPromptParserChain:
    """Integration: prompt resolution -> LLM call -> parse -> routing."""

    async def test_well_formed_review_approved(
        self,
        create_reviewer_with_defaults: Callable[..., Reviewer],
        mock_driver: MagicMock,
        profile: Profile,
    ) -> None:
        """Well-formed markdown review with Ready: Yes -> approved=True."""
        reviewer = create_reviewer_with_defaults()

        # Mock driver to return well-formed review
        mock_driver.execute_agentic.return_value = AsyncIteratorMock(
            [
                AgenticMessage(
                    type=AgenticMessageType.RESULT,
                    content=WELL_FORMED_REVIEW,
                    session_id="sess-1",
                    is_error=False,
                ),
            ]
        )

        state = ImplementationState(
            workflow_id="wf-int-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="in_progress",
            current_task_index=0,
            total_tasks=3,
        )

        result, session_id = await reviewer.agentic_review(
            state, base_commit="abc123", profile=profile, workflow_id="wf-int-001"
        )

        assert result.approved is True
        assert result.severity == Severity.NONE
        assert session_id == "sess-1"

    async def test_malformed_review_defaults_to_not_approved_and_routing_advances(
        self,
        create_reviewer_with_defaults: Callable[..., Reviewer],
        mock_driver: MagicMock,
        profile: Profile,
    ) -> None:
        """Malformed output (no Ready: pattern) -> approved=False -> routing advances."""
        reviewer = create_reviewer_with_defaults()

        mock_driver.execute_agentic.return_value = AsyncIteratorMock(
            [
                AgenticMessage(
                    type=AgenticMessageType.RESULT,
                    content=MALFORMED_REVIEW,
                    session_id="sess-2",
                    is_error=False,
                ),
            ]
        )

        state = ImplementationState(
            workflow_id="wf-int-002",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="in_progress",
            current_task_index=0,
            total_tasks=3,
            task_review_iteration=2,  # At max iterations
        )

        result, _ = await reviewer.agentic_review(
            state, base_commit="abc123", profile=profile, workflow_id="wf-int-002"
        )

        assert result.approved is False

        # Simulate routing with the result
        state_after = ImplementationState(
            workflow_id="wf-int-002",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="in_progress",
            current_task_index=0,
            total_tasks=3,
            task_review_iteration=2,
            last_review=result,
        )
        route = route_after_task_review(state_after, profile)
        # Non-final task at max iterations -> advance, not abort
        assert route == "next_task_node"

    async def test_prompt_defaults_contain_ready_format(self) -> None:
        """Verify PROMPT_DEFAULTS reviewer prompt has markdown format, not JSON."""
        from amelia.agents.prompts.defaults import PROMPT_DEFAULTS

        content = PROMPT_DEFAULTS["reviewer.agentic"].content
        assert "Ready: Yes" in content
        assert REVIEW_OUTPUT_FORMAT in content
```

**Step 2: Run the integration test**

Run: `uv run pytest tests/integration/test_reviewer_prompt_parser.py -v -m integration`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/integration/test_reviewer_prompt_parser.py
git commit -m "test: add integration test for reviewer prompt-to-parser chain

Tests the full chain: PROMPT_DEFAULTS resolution -> driver call -> parse ->
ReviewResult -> routing. Verifies well-formed markdown is approved, and
malformed output defaults to not-approved with routing advancing to next task."
```

---

### Task 7: Final verification

**Step 1: Run the full test suite**

Run: `uv run pytest tests/unit/ tests/integration/test_reviewer_prompt_parser.py -v`
Expected: All tests PASS

**Step 2: Run linting and type checking**

Run: `uv run ruff check amelia tests`
Run: `uv run mypy amelia`
Expected: No errors

**Step 3: Verify no regressions in existing reviewer tests**

Run: `uv run pytest tests/unit/agents/test_reviewer.py tests/unit/agents/test_reviewer_prompts.py tests/unit/pipelines/test_routing.py -v`
Expected: All existing + new tests PASS
