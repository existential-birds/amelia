# Consolidate Reviewer to Agentic-Only Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove dead/legacy review methods and consolidate to `agentic_review()` as the single code path, which correctly separates issues from observations.

**Architecture:** The Reviewer agent currently has 4 review methods but only `agentic_review()` is used in practice (when `base_commit` is set). We'll remove the unused methods and ensure `agentic_review()` is always used by computing `base_commit` when missing. This also fixes the `issue_count` problem since `_parse_review_result()` already correctly filters issues from good patterns.

**Tech Stack:** Python, Pydantic, pytest, LangGraph

---

## Task 1: Remove Dead `structured_review()` Method

**Files:**
- Modify: `amelia/agents/reviewer.py:564-657` (remove method)
- Modify: `amelia/agents/reviewer.py:132-146` (remove `STRUCTURED_SYSTEM_PROMPT`)
- Modify: `amelia/agents/reviewer.py:249-253` (remove `structured_prompt` property)
- Delete tests: `tests/unit/agents/test_reviewer.py:90-335` (TestStructuredReview class)

**Step 1: Delete `TestStructuredReview` test class**

Remove lines 90-335 from `tests/unit/agents/test_reviewer.py` - the entire `TestStructuredReview` class.

**Step 2: Run tests to verify removal doesn't break anything**

Run: `uv run pytest tests/unit/agents/test_reviewer.py -v`
Expected: All remaining tests pass

**Step 3: Remove `STRUCTURED_SYSTEM_PROMPT` constant**

In `amelia/agents/reviewer.py`, remove lines 132-146:
```python
    STRUCTURED_SYSTEM_PROMPT = """You are an expert code reviewer. Review the provided code changes and produce structured feedback.
...
Be specific with file paths and line numbers. Provide actionable feedback."""
```

**Step 4: Remove `structured_prompt` property**

In `amelia/agents/reviewer.py`, remove lines 249-253:
```python
    @property
    def structured_prompt(self) -> str:
        return self._prompts.get("reviewer.structured", self.STRUCTURED_SYSTEM_PROMPT)
```

**Step 5: Remove `structured_review()` method**

Remove lines 564-657 (the entire `structured_review` method).

**Step 6: Run linting and type checking**

Run: `uv run ruff check amelia/agents/reviewer.py && uv run mypy amelia/agents/reviewer.py`
Expected: No errors

**Step 7: Run full test suite**

Run: `uv run pytest tests/unit/agents/test_reviewer.py -v`
Expected: All tests pass

**Step 8: Commit**

```bash
git add amelia/agents/reviewer.py tests/unit/agents/test_reviewer.py
git commit -m "$(cat <<'EOF'
refactor(reviewer): remove dead structured_review method

This method had no callers - it was dead code. The agentic_review
method is the primary path used by the orchestrator.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Remove Legacy `review()`, `_single_review()`, `_competitive_review()` Methods

**Files:**
- Modify: `amelia/agents/reviewer.py` (remove 3 methods + `ReviewResponse` schema + `SYSTEM_PROMPT_TEMPLATE`)
- Modify: `tests/unit/agents/test_reviewer.py` (remove `TestReviewer` class tests for removed methods)

**Step 1: Identify tests to remove**

Remove from `tests/unit/agents/test_reviewer.py`:
- `TestReviewer` class (lines ~337-384) - tests `review()` method

**Step 2: Remove `TestReviewer` class**

Delete the `TestReviewer` class that tests `review()` and related methods.

**Step 3: Run remaining tests**

Run: `uv run pytest tests/unit/agents/test_reviewer.py -v`
Expected: All remaining tests pass (TestAgenticReview, TestParseReviewResult, etc.)

**Step 4: Remove `ReviewResponse` schema**

In `amelia/agents/reviewer.py`, remove lines 98-110:
```python
class ReviewResponse(BaseModel):
    """Schema for LLM-generated review response.
    ...
    """
    approved: bool = Field(description="Whether the changes are acceptable.")
    comments: list[str] = Field(description="Specific feedback items.")
    severity: Severity = Field(description="Overall severity of the review findings.")
```

**Step 5: Remove `SYSTEM_PROMPT_TEMPLATE` constant**

Remove lines 129-130:
```python
    SYSTEM_PROMPT_TEMPLATE = """You are an expert code reviewer with a focus on {persona} aspects.
Analyze the provided code changes and provide a comprehensive review."""
```

**Step 6: Remove `template_prompt` property**

Remove lines 244-246:
```python
    @property
    def template_prompt(self) -> str:
        return self._prompts.get("reviewer.template", self.SYSTEM_PROMPT_TEMPLATE)
```

**Step 7: Remove `review()` method**

Remove the `review()` method (dispatcher to single/competitive).

**Step 8: Remove `_single_review()` method**

Remove the `_single_review()` method.

**Step 9: Remove `_competitive_review()` method**

Remove the `_competitive_review()` method.

**Step 10: Remove `DEFAULT_PERSONAS` constant**

Remove line 219:
```python
    DEFAULT_PERSONAS: list[str] = ["Security", "Performance", "Usability"]
```

**Step 11: Run linting and type checking**

Run: `uv run ruff check amelia/agents/reviewer.py && uv run mypy amelia/agents/reviewer.py`
Expected: No errors (fix any issues)

**Step 12: Run full test suite**

Run: `uv run pytest tests/unit/agents/test_reviewer.py -v`
Expected: All tests pass

**Step 13: Commit**

```bash
git add amelia/agents/reviewer.py tests/unit/agents/test_reviewer.py
git commit -m "$(cat <<'EOF'
refactor(reviewer): remove legacy review methods

Remove review(), _single_review(), _competitive_review() and
supporting code (ReviewResponse, SYSTEM_PROMPT_TEMPLATE, DEFAULT_PERSONAS).

These were fallback paths only used when base_commit was not set.
The agentic_review() method is now the only review path.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Update Orchestrator to Always Use `agentic_review()`

**Files:**
- Modify: `amelia/core/orchestrator.py:653-666` (simplify review node)
- Modify: `amelia/core/orchestrator.py:383-467` (remove or simplify `get_code_changes_for_review`)

**Step 1: Write failing test for base_commit fallback**

Create test in `tests/unit/core/test_orchestrator_review.py`:
```python
"""Tests for reviewer node base_commit handling."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from amelia.core.orchestrator import call_review_node
from amelia.core.state import ExecutionState


class TestReviewNodeBaseCommit:
    """Tests for call_review_node base_commit behavior."""

    async def test_review_node_computes_base_commit_when_missing(
        self,
        mock_execution_state_factory,
        mock_profile_factory,
    ) -> None:
        """Test that review node computes base_commit if not in state."""
        state, profile = mock_execution_state_factory(
            goal="Test goal",
            base_commit=None,  # No base_commit
        )

        config = {
            "configurable": {
                "profile": profile,
                "workflow_id": "wf-123",
            }
        }

        with patch("amelia.core.orchestrator.get_current_commit") as mock_get_commit:
            mock_get_commit.return_value = "abc123"
            with patch("amelia.core.orchestrator.Reviewer") as MockReviewer:
                mock_reviewer = MagicMock()
                mock_reviewer.agentic_review = AsyncMock(
                    return_value=(MagicMock(approved=True, comments=[], severity="low"), None)
                )
                MockReviewer.return_value = mock_reviewer

                result = await call_review_node(state, config)

                # Should have called agentic_review with computed base_commit
                mock_reviewer.agentic_review.assert_called_once()
                call_args = mock_reviewer.agentic_review.call_args
                assert call_args.args[1] == "abc123"  # base_commit argument
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/core/test_orchestrator_review.py -v`
Expected: FAIL (test file doesn't exist yet or logic not implemented)

**Step 3: Add `get_current_commit()` helper function**

In `amelia/tools/git.py`, add:
```python
async def get_current_commit(cwd: str | None = None) -> str | None:
    """Get the current HEAD commit SHA.

    Args:
        cwd: Working directory for git command.

    Returns:
        The current commit SHA, or None if not in a git repo.
    """
    try:
        result = await run_shell_command(
            "git rev-parse HEAD",
            cwd=cwd,
        )
        return result.stdout.strip() if result.stdout else None
    except Exception:
        return None
```

**Step 4: Update `call_review_node()` to always use agentic_review**

In `amelia/core/orchestrator.py`, simplify the review node:
```python
async def call_review_node(
    state: ExecutionState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Orchestrator node for the Reviewer agent to review code changes.

    Always uses agentic review, computing base_commit if not in state.
    """
    # ... setup code unchanged ...

    # Compute base_commit if not in state
    base_commit = state.base_commit
    if not base_commit:
        from amelia.tools.git import get_current_commit
        base_commit = await get_current_commit(profile.working_dir)
        if not base_commit:
            # Fallback: use HEAD~1 or empty tree for initial commit
            base_commit = "HEAD~1"

    logger.info(
        "Using agentic review",
        agent=agent_name,
        base_commit=base_commit,
    )
    review_result, new_session_id = await reviewer.agentic_review(
        state, base_commit, profile, workflow_id=workflow_id
    )

    # ... rest unchanged ...
```

**Step 5: Remove `get_code_changes_for_review()` function**

This function is no longer needed since we always use agentic review (which fetches diff itself).

**Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/core/test_orchestrator_review.py -v`
Expected: PASS

**Step 7: Run full test suite**

Run: `uv run pytest tests/ -v --ignore=tests/e2e --ignore=tests/perf`
Expected: All tests pass (some integration tests may need updates)

**Step 8: Commit**

```bash
git add amelia/core/orchestrator.py amelia/tools/git.py tests/unit/core/test_orchestrator_review.py
git commit -m "$(cat <<'EOF'
refactor(orchestrator): always use agentic_review

- Remove conditional logic between review() and agentic_review()
- Compute base_commit if not in state using get_current_commit()
- Remove get_code_changes_for_review() helper (no longer needed)

The agentic_review method handles fetching the diff itself via git tools,
avoiding "argument list too long" errors with large diffs.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Update Integration Tests

**Files:**
- Modify: `tests/integration/test_agentic_workflow.py`
- Modify: `tests/integration/test_multi_driver_agents.py`
- Modify: `tests/integration/test_orchestrator_prompts.py`

**Step 1: Run integration tests to identify failures**

Run: `uv run pytest tests/integration/ -v`
Expected: Some tests may fail due to removed methods

**Step 2: Update failing tests**

For each failing test:
- If testing removed methods (`review()`, `structured_review()`): delete the test
- If testing orchestrator with reviewer: update to use `agentic_review()` mock

**Step 3: Run integration tests again**

Run: `uv run pytest tests/integration/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/integration/
git commit -m "$(cat <<'EOF'
test(integration): update tests for agentic-only reviewer

Update integration tests to work with consolidated reviewer that
only uses agentic_review(). Remove tests for deleted methods.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Clean Up Exports and Documentation

**Files:**
- Modify: `amelia/agents/reviewer.py` (update docstrings, remove dead references)
- Modify: `amelia/agents/__init__.py` (if exports affected)

**Step 1: Update Reviewer class docstring**

Update the class docstring to reflect single review method:
```python
class Reviewer:
    """Agent responsible for reviewing code changes against requirements.

    Review Method:
        agentic_review(): Agentic review that auto-detects technologies, loads review
            skills, and fetches diff via git. Returns ReviewResult with properly
            separated issues (not including observations or praise).

    Attributes:
        driver: LLM driver interface for generating reviews.
    """
```

**Step 2: Remove unused imports**

Check for and remove any unused imports (asyncio if no longer needed, etc.).

**Step 3: Run linting**

Run: `uv run ruff check amelia/agents/reviewer.py --fix`
Expected: Clean

**Step 4: Run type checking**

Run: `uv run mypy amelia/agents/reviewer.py`
Expected: No errors

**Step 5: Run full test suite**

Run: `uv run pytest tests/ -v --ignore=tests/e2e --ignore=tests/perf`
Expected: All tests pass

**Step 6: Commit**

```bash
git add amelia/agents/reviewer.py amelia/agents/__init__.py
git commit -m "$(cat <<'EOF'
docs(reviewer): update docstrings for agentic-only design

Clean up Reviewer class documentation to reflect the consolidated
single-method design using agentic_review().

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Remove `strategy` Field from Profile

**Files:**
- Modify: `amelia/core/types.py` (remove `StrategyType` and `strategy` field)
- Modify: `tests/conftest.py` (remove `strategy` from fixtures if present)
- Update any settings files or tests that reference `strategy`

**Step 1: Find all usages of strategy**

```bash
grep -rn "strategy" amelia/ tests/ --include="*.py" | grep -v "__pycache__"
```

**Step 2: Remove `StrategyType` enum from types.py**

In `amelia/core/types.py`, remove the `StrategyType` enum:
```python
class StrategyType(str, Enum):
    SINGLE = "single"
    COMPETITIVE = "competitive"
```

**Step 3: Remove `strategy` field from Profile model**

In `amelia/core/types.py`, remove the `strategy` field from the `Profile` model:
```python
strategy: StrategyType = StrategyType.SINGLE
```

**Step 4: Update test fixtures**

Remove `strategy` field from any test fixtures in `tests/conftest.py` and other test files.

**Step 5: Update configuration loading**

If `amelia/core/config.py` or settings loading references `strategy`, remove those references. Settings files with `strategy` should be ignored (backward compatible) or warn.

**Step 6: Run linting and type checking**

Run: `uv run ruff check amelia tests && uv run mypy amelia`
Expected: No errors

**Step 7: Run tests**

Run: `uv run pytest tests/ -v --ignore=tests/e2e --ignore=tests/perf`
Expected: All tests pass

**Step 8: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor(types): remove strategy field from Profile

The strategy field controlled competitive vs single review mode,
which is no longer needed now that agentic_review() is the only
review path.

Removes:
- StrategyType enum
- Profile.strategy field
- Related test fixture updates

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

After completing all tasks:

1. **Removed dead code:** `structured_review()`, never called
2. **Removed legacy paths:** `review()`, `_single_review()`, `_competitive_review()`
3. **Single code path:** `agentic_review()` is now the only review method
4. **issue_count is correct:** `_parse_review_result()` already separates issues from good patterns
5. **Simpler codebase:** One review method instead of four
6. **Removed strategy field:** `StrategyType` enum and `Profile.strategy` field removed

**Verification:**
```bash
uv run ruff check amelia tests
uv run mypy amelia
uv run pytest tests/ -v --ignore=tests/e2e --ignore=tests/perf
```
