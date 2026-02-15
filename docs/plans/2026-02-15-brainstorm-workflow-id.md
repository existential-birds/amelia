# Brainstorm Workflow ID Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace long brainstorm workflow IDs with short, readable slugified IDs capped at 24 chars.

**Architecture:** Add a `slugify()` utility function in a new `amelia/core/text.py` module (no `amelia/utils/` exists, and this is a core utility). Update `handoff_to_implementation()` to use it when generating the `issue_id`. TDD throughout.

**Tech Stack:** Python 3.12+, pytest, re module for regex

---

### Task 1: Create `slugify()` with tests

**Files:**
- Create: `tests/unit/core/test_text.py`
- Create: `amelia/core/text.py`

**Step 1: Write the failing tests**

```python
"""Tests for amelia.core.text utilities."""

import pytest

from amelia.core.text import slugify


class TestSlugify:
    """Tests for slugify()."""

    def test_simple_title(self) -> None:
        assert slugify("Add dark mode") == "add-dark-mode"

    def test_special_characters_replaced(self) -> None:
        assert slugify("Fix bug #123!") == "fix-bug-123"

    def test_consecutive_dashes_collapsed(self) -> None:
        assert slugify("hello   world") == "hello-world"

    def test_leading_trailing_dashes_stripped(self) -> None:
        assert slugify("--hello--") == "hello"

    def test_truncate_at_dash_boundary(self) -> None:
        # "add-dark-mode-support" is 21 chars; truncating to 15 should break at dash
        result = slugify("Add dark mode support", max_length=15)
        assert result == "add-dark-mode"
        assert len(result) <= 15

    def test_truncate_single_long_word(self) -> None:
        # No dash boundary to break at — hard truncate
        result = slugify("Supercalifragilistic", max_length=10)
        assert result == "supercalif"
        assert len(result) <= 10

    def test_empty_string_returns_empty(self) -> None:
        assert slugify("") == ""

    def test_all_special_chars_returns_empty(self) -> None:
        assert slugify("!!!@@@###") == ""

    def test_short_title_unchanged(self) -> None:
        assert slugify("Fix", max_length=15) == "fix"

    def test_default_max_length(self) -> None:
        # Default max_length is 15
        result = slugify("This is a very long title that exceeds the limit")
        assert len(result) <= 15
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/core/test_text.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 3: Write minimal implementation**

```python
"""Text utilities for generating safe identifiers."""

import re


def slugify(text: str, max_length: int = 15) -> str:
    """Convert text to a URL-safe slug.

    Args:
        text: Input text to slugify.
        max_length: Maximum length of the result.

    Returns:
        Lowercase slug with only alphanumeric chars and dashes.
    """
    # Lowercase and replace non-alphanumeric with dashes
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    # Strip leading/trailing dashes
    slug = slug.strip("-")
    # Truncate at dash boundary if possible
    if len(slug) > max_length:
        truncated = slug[:max_length]
        # Try to break at last dash within limit
        last_dash = truncated.rfind("-")
        if last_dash > 0:
            slug = truncated[:last_dash]
        else:
            slug = truncated
    return slug
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/core/test_text.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add amelia/core/text.py tests/unit/core/test_text.py
git commit -m "feat: add slugify() utility for short workflow IDs (#443)"
```

---

### Task 2: Update `handoff_to_implementation()` with tests

**Files:**
- Modify: `amelia/server/services/brainstorm.py:978-980`
- Modify: `tests/unit/server/services/test_brainstorm_service.py`

**Step 1: Write the failing tests**

Add to `tests/unit/server/services/test_brainstorm_service.py` in the existing handoff test class. Find the class containing `test_handoff_with_orchestrator` and add these tests after the existing ones:

```python
async def test_handoff_generates_short_issue_id_from_title(
    self,
    service: BrainstormService,
    mock_repository: MagicMock,
) -> None:
    """Should generate slugified issue_id from title + session hash."""
    now = datetime.now(UTC)
    mock_session = BrainstormingSession(
        id="d9336c40-4ce9-4b12-81e1-099bb70eaa01",
        profile_id="work",
        status="ready_for_handoff",
        created_at=now,
        updated_at=now,
    )
    mock_repository.get_session.return_value = mock_session
    mock_repository.get_artifacts.return_value = [
        Artifact(
            id="art-1", session_id="d9336c40-4ce9-4b12-81e1-099bb70eaa01",
            type="design", path="docs/plans/design.md", created_at=now,
        )
    ]
    mock_orchestrator = MagicMock()
    mock_orchestrator.queue_workflow = AsyncMock(return_value="wf-123")

    await service.handoff_to_implementation(
        session_id="d9336c40-4ce9-4b12-81e1-099bb70eaa01",
        artifact_path="docs/plans/design.md",
        issue_title="Add dark mode support",
        orchestrator=mock_orchestrator,
        worktree_path="/path/to/worktree",
    )

    request = mock_orchestrator.queue_workflow.call_args[0][0]
    assert request.issue_id == "add-dark-mode-d9336c40"
    assert len(request.issue_id) <= 24

async def test_handoff_falls_back_without_title(
    self,
    service: BrainstormService,
    mock_repository: MagicMock,
) -> None:
    """Should use brainstorm-{hash} when no title provided."""
    now = datetime.now(UTC)
    mock_session = BrainstormingSession(
        id="d9336c40-4ce9-4b12-81e1-099bb70eaa01",
        profile_id="work",
        status="ready_for_handoff",
        created_at=now,
        updated_at=now,
    )
    mock_repository.get_session.return_value = mock_session
    mock_repository.get_artifacts.return_value = [
        Artifact(
            id="art-1", session_id="d9336c40-4ce9-4b12-81e1-099bb70eaa01",
            type="design", path="docs/plans/design.md", created_at=now,
        )
    ]
    mock_orchestrator = MagicMock()
    mock_orchestrator.queue_workflow = AsyncMock(return_value="wf-123")

    await service.handoff_to_implementation(
        session_id="d9336c40-4ce9-4b12-81e1-099bb70eaa01",
        artifact_path="docs/plans/design.md",
        orchestrator=mock_orchestrator,
        worktree_path="/path/to/worktree",
    )

    request = mock_orchestrator.queue_workflow.call_args[0][0]
    assert request.issue_id == "brainstorm-d9336c40"

async def test_handoff_falls_back_for_empty_slug(
    self,
    service: BrainstormService,
    mock_repository: MagicMock,
) -> None:
    """Should use fallback when title produces empty slug."""
    now = datetime.now(UTC)
    mock_session = BrainstormingSession(
        id="d9336c40-4ce9-4b12-81e1-099bb70eaa01",
        profile_id="work",
        status="ready_for_handoff",
        created_at=now,
        updated_at=now,
    )
    mock_repository.get_session.return_value = mock_session
    mock_repository.get_artifacts.return_value = [
        Artifact(
            id="art-1", session_id="d9336c40-4ce9-4b12-81e1-099bb70eaa01",
            type="design", path="docs/plans/design.md", created_at=now,
        )
    ]
    mock_orchestrator = MagicMock()
    mock_orchestrator.queue_workflow = AsyncMock(return_value="wf-123")

    await service.handoff_to_implementation(
        session_id="d9336c40-4ce9-4b12-81e1-099bb70eaa01",
        artifact_path="docs/plans/design.md",
        issue_title="!!!@@@",
        orchestrator=mock_orchestrator,
        worktree_path="/path/to/worktree",
    )

    request = mock_orchestrator.queue_workflow.call_args[0][0]
    assert request.issue_id == "brainstorm-d9336c40"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py -k "test_handoff_generates_short or test_handoff_falls_back" -v`
Expected: FAIL (issue_id still uses old format)

**Step 3: Modify `handoff_to_implementation()`**

In `amelia/server/services/brainstorm.py`, add import at top:

```python
from amelia.core.text import slugify
```

Replace line 980 (`issue_id = f"brainstorm-{session_id}"`):

```python
            # Generate short, readable issue ID
            slug = slugify(issue_title, max_length=15) if issue_title else ""
            if slug:
                issue_id = f"{slug}-{session_id[:8]}"
            else:
                issue_id = f"brainstorm-{session_id[:8]}"
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/services/test_brainstorm_service.py -v`
Expected: All PASS (including existing tests)

**Step 5: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All PASS

**Step 6: Run linting and type checking**

Run: `uv run ruff check amelia/core/text.py amelia/server/services/brainstorm.py && uv run mypy amelia/core/text.py amelia/server/services/brainstorm.py`
Expected: No errors

**Step 7: Commit**

```bash
git add amelia/server/services/brainstorm.py tests/unit/server/services/test_brainstorm_service.py
git commit -m "feat: use slugified IDs for brainstorm handoff (#443)"
```
