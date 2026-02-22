"""Unit tests for implementation pipeline utilities."""

from datetime import UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from amelia.core.types import AgentConfig, Issue, Profile
from amelia.pipelines.implementation.state import ImplementationState
from amelia.pipelines.implementation.utils import _looks_like_plan, commit_task_changes


class TestLooksLikePlan:
    """Tests for _looks_like_plan function."""

    def test_rejects_empty_text(self) -> None:
        """Should reject empty or None-like text."""
        assert _looks_like_plan("") is False
        assert _looks_like_plan("   ") is False

    def test_rejects_short_text(self) -> None:
        """Should reject text shorter than 100 characters."""
        short_text = "# Plan\n### Task 1: Do something"
        assert len(short_text) < 100
        assert _looks_like_plan(short_text) is False

    def test_rejects_text_without_markers(self) -> None:
        """Should reject text without enough plan markers."""
        # No markdown headers, no plan indicators
        plain_text = "x" * 150
        assert _looks_like_plan(plain_text) is False

    def test_rejects_text_with_markers_but_no_tasks(self) -> None:
        """Should reject text with plan markers but no valid task headers."""
        # Has enough markers but no "### Task N:" pattern
        text_without_tasks = """# Implementation Plan

**Goal:** Build something great

## Overview
This is a plan for doing things.

## Architecture
The architecture consists of components.

```python
def hello():
    pass
```
"""
        # Pad to ensure it's long enough
        padded_text = text_without_tasks + "\n" + ("x" * 100)
        assert len(padded_text) >= 100
        assert _looks_like_plan(padded_text) is False

    def test_accepts_valid_plan_with_task(self) -> None:
        """Should accept text with plan markers and at least one task header."""
        valid_plan = """# Implementation Plan

**Goal:** Build the feature

## Phase 1: Implementation

### Task 1: Create the module
- Step 1: Define the interface
- Step 2: Implement the logic

```python
def example():
    pass
```
"""
        # Ensure it's long enough
        assert len(valid_plan) >= 100
        assert _looks_like_plan(valid_plan) is True

    def test_accepts_plan_with_hierarchical_task(self) -> None:
        """Should accept plans with hierarchical task numbering (Task 1.1)."""
        valid_plan = """# Implementation Plan

**Goal:** Build something

## Phase 1

### Task 1.1: First subtask
- Do stuff

### Task 1.2: Second subtask
- Do more stuff

```python
code = True
```
"""
        assert len(valid_plan) >= 100
        assert _looks_like_plan(valid_plan) is True

    def test_task_pattern_requires_colon(self) -> None:
        """Task header must end with colon to be valid."""
        # Has "### Task 1" but no colon
        invalid_task = """# Implementation Plan

**Goal:** Build something

## Phase 1

### Task 1 without colon
- Do stuff

```python
code = True
```
"""
        padded = invalid_task + "\n" + ("x" * 50)
        assert len(padded) >= 100
        assert _looks_like_plan(padded) is False

    def test_task_must_be_at_line_start(self) -> None:
        """Task header pattern must be at start of line."""
        # Task pattern not at line start
        invalid_task = """# Implementation Plan

**Goal:** Build something

## Phase 1

Some text before ### Task 1: This won't match

```python
code = True
```
"""
        padded = invalid_task + "\n" + ("x" * 50)
        assert len(padded) >= 100
        assert _looks_like_plan(padded) is False


class TestCommitTaskChanges:
    """Tests for commit_task_changes function."""

    @pytest.fixture
    def test_state_and_config(self, tmp_path: Path) -> tuple[ImplementationState, dict]:
        """Create test state and config."""
        from datetime import datetime

        # Create profile
        agents = {
            "architect": AgentConfig(driver="claude", model="sonnet"),
            "developer": AgentConfig(driver="claude", model="sonnet"),
            "reviewer": AgentConfig(driver="claude", model="sonnet"),
        }
        profile = Profile(
            name="test",
            tracker="noop",
            repo_root=str(tmp_path),
            agents=agents,
        )

        # Create state
        state = ImplementationState(
            workflow_id=uuid4(),
            pipeline_type="implementation",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            current_task_index=0,
            total_tasks=5,
            issue=Issue(
                id="TEST-123",
                title="Test issue",
                description="Test issue description",
            ),
        )

        config = {"configurable": {"profile": profile}}
        return state, config

    @pytest.mark.asyncio
    async def test_retries_commit_when_hooks_modify_files(
        self,
        test_state_and_config: tuple[ImplementationState, dict],
    ) -> None:
        """Should re-stage and retry commit when hooks modify files."""
        mock_state, mock_config = test_state_and_config
        # Mock process results
        mock_add_proc = MagicMock()
        mock_add_proc.returncode = 0
        mock_add_proc.communicate = AsyncMock(return_value=(b"", b""))

        mock_diff_cached_proc = MagicMock()
        mock_diff_cached_proc.returncode = 1  # Changes exist
        mock_diff_cached_proc.communicate = AsyncMock(return_value=(b"", b""))

        mock_commit_proc_fail = MagicMock()
        mock_commit_proc_fail.returncode = 1  # Commit failed
        mock_commit_proc_fail.communicate = AsyncMock(return_value=(b"", b"hook modified files"))

        mock_diff_unstaged_proc = MagicMock()
        mock_diff_unstaged_proc.returncode = 1  # Unstaged changes exist (hook modified)
        mock_diff_unstaged_proc.communicate = AsyncMock(return_value=(b"", b""))

        mock_restage_proc = MagicMock()
        mock_restage_proc.returncode = 0
        mock_restage_proc.communicate = AsyncMock(return_value=(b"", b""))

        mock_commit_proc_success = MagicMock()
        mock_commit_proc_success.returncode = 0  # Retry succeeds
        mock_commit_proc_success.communicate = AsyncMock(return_value=(b"", b""))

        # Sequence of subprocess calls:
        # 1. git add -A (initial staging)
        # 2. git diff --cached --quiet (check staged)
        # 3. git commit -m ... (fails)
        # 4. git diff --quiet (check for hook modifications)
        # 5. git add -A (re-stage)
        # 6. git commit -m ... (retry succeeds)
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                mock_add_proc,
                mock_diff_cached_proc,
                mock_commit_proc_fail,
                mock_diff_unstaged_proc,
                mock_restage_proc,
                mock_commit_proc_success,
            ]

            result = await commit_task_changes(mock_state, mock_config)

        assert result is True
        assert mock_exec.call_count == 6

    @pytest.mark.asyncio
    async def test_fails_when_hooks_modify_and_retry_fails(
        self,
        test_state_and_config: tuple[ImplementationState, dict],
    ) -> None:
        """Should return False when retry commit also fails."""
        mock_state, mock_config = test_state_and_config
        mock_add_proc = MagicMock()
        mock_add_proc.returncode = 0
        mock_add_proc.communicate = AsyncMock(return_value=(b"", b""))

        mock_diff_cached_proc = MagicMock()
        mock_diff_cached_proc.returncode = 1
        mock_diff_cached_proc.communicate = AsyncMock(return_value=(b"", b""))

        mock_commit_proc_fail = MagicMock()
        mock_commit_proc_fail.returncode = 1
        mock_commit_proc_fail.communicate = AsyncMock(return_value=(b"", b"hook error"))

        mock_diff_unstaged_proc = MagicMock()
        mock_diff_unstaged_proc.returncode = 1  # Hook modified
        mock_diff_unstaged_proc.communicate = AsyncMock(return_value=(b"", b""))

        mock_restage_proc = MagicMock()
        mock_restage_proc.returncode = 0
        mock_restage_proc.communicate = AsyncMock(return_value=(b"", b""))

        mock_commit_proc_retry_fail = MagicMock()
        mock_commit_proc_retry_fail.returncode = 1  # Retry also fails
        mock_commit_proc_retry_fail.communicate = AsyncMock(return_value=(b"", b"still failed"))

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                mock_add_proc,
                mock_diff_cached_proc,
                mock_commit_proc_fail,
                mock_diff_unstaged_proc,
                mock_restage_proc,
                mock_commit_proc_retry_fail,
            ]

            result = await commit_task_changes(mock_state, mock_config)

        assert result is False

    @pytest.mark.asyncio
    async def test_succeeds_on_first_commit_attempt(
        self,
        test_state_and_config: tuple[ImplementationState, dict],
    ) -> None:
        """Should succeed on first attempt when no hook modifications."""
        mock_state, mock_config = test_state_and_config
        mock_add_proc = MagicMock()
        mock_add_proc.returncode = 0
        mock_add_proc.communicate = AsyncMock(return_value=(b"", b""))

        mock_diff_cached_proc = MagicMock()
        mock_diff_cached_proc.returncode = 1
        mock_diff_cached_proc.communicate = AsyncMock(return_value=(b"", b""))

        mock_commit_proc = MagicMock()
        mock_commit_proc.returncode = 0  # Success on first try
        mock_commit_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = [
                mock_add_proc,
                mock_diff_cached_proc,
                mock_commit_proc,
            ]

            result = await commit_task_changes(mock_state, mock_config)

        assert result is True
        assert mock_exec.call_count == 3  # No retry needed
