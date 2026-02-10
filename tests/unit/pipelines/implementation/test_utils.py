"""Unit tests for implementation pipeline utilities."""

from amelia.pipelines.implementation.utils import _looks_like_plan


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
