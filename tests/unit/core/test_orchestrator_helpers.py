"""Tests for orchestrator helper functions.

Note: Plan extraction tests are in test_orchestrator_plan_extraction.py
"""

from unittest.mock import MagicMock

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.types import AgentConfig, Profile
from amelia.pipelines.implementation.utils import (
    extract_task_count,
    extract_task_section,
)
from amelia.pipelines.utils import extract_config_params


SAMPLE_PLAN = """# Model Selection Dropdown Implementation Plan

**Goal:** Add a model selection dropdown to Settings.

**Architecture:** Create a new PreferencesService using the @Observable pattern.

**Tech Stack:** SwiftUI, Swift Observation framework

---

## Phase 1: Data Models

### Task 1.1: Create Model Types

**Files:**
- Create: `Sirona/Models/Preferences.swift`

**Step 1:** Write the failing test
**Step 2:** Run test to verify it fails
**Step 3:** Create the file

### Task 1.2: Add Response Types

**Files:**
- Modify: `Sirona/Models/Preferences.swift`

**Step 1:** Add ModelsListResponse

## Phase 2: Service Layer

### Task 2.1: Create PreferencesService

**Files:**
- Create: `Sirona/Services/PreferencesService.swift`

**Step 1:** Create the service class
"""


class TestExtractTaskCount:
    """Tests for extract_task_count helper."""

    def test_counts_hierarchical_tasks(self) -> None:
        """Should count tasks with N.M numbering."""
        count = extract_task_count(SAMPLE_PLAN)
        assert count == 3  # Task 1.1, 1.2, 2.1

    def test_counts_simple_tasks(self) -> None:
        """Should count tasks with simple numbering."""
        plan = """# Plan
### Task 1: First
Content
### Task 2: Second
More content
"""
        count = extract_task_count(plan)
        assert count == 2

    def test_returns_one_for_no_tasks(self) -> None:
        """Should return 1 if no task patterns found (single-task default)."""
        plan = "# Plan\n\nSome content without tasks"
        count = extract_task_count(plan)
        assert count == 1


class TestExtractTaskSection:
    """Tests for extract_task_section helper."""

    def test_extracts_first_task_with_context(self) -> None:
        """Should extract header + phase + first task."""
        result = extract_task_section(SAMPLE_PLAN, 0)

        # Should include header context
        assert "**Goal:**" in result
        assert "**Architecture:**" in result
        assert "**Tech Stack:**" in result

        # Should include phase header
        assert "## Phase 1: Data Models" in result

        # Should include first task
        assert "### Task 1.1: Create Model Types" in result
        assert "**Step 1:** Write the failing test" in result

        # Should NOT include other tasks
        assert "### Task 1.2:" not in result
        assert "### Task 2.1:" not in result

    def test_extracts_second_task(self) -> None:
        """Should extract header + phase + second task."""
        result = extract_task_section(SAMPLE_PLAN, 1)

        # Should include header
        assert "**Goal:**" in result

        # Should include phase 1 header (task 1.2 is in phase 1)
        assert "## Phase 1: Data Models" in result

        # Should include second task
        assert "### Task 1.2: Add Response Types" in result

        # Should NOT include other tasks
        assert "### Task 1.1:" not in result
        assert "### Task 2.1:" not in result

    def test_extracts_task_from_second_phase(self) -> None:
        """Should extract header + correct phase for task in phase 2."""
        result = extract_task_section(SAMPLE_PLAN, 2)

        # Should include header
        assert "**Goal:**" in result

        # Should include phase 2 header
        assert "## Phase 2: Service Layer" in result

        # Should include task 2.1
        assert "### Task 2.1: Create PreferencesService" in result

        # Should NOT include phase 1 tasks
        assert "### Task 1.1:" not in result
        assert "### Task 1.2:" not in result

    def test_returns_full_plan_for_invalid_index(self) -> None:
        """Should return full plan if task index is out of range."""
        result = extract_task_section(SAMPLE_PLAN, 99)
        assert result == SAMPLE_PLAN

    def test_returns_full_plan_for_no_phase_markers(self) -> None:
        """Should return full plan if no phase/task markers found."""
        simple_plan = "# Simple Plan\n\nJust do the thing."
        result = extract_task_section(simple_plan, 0)
        assert result == simple_plan


class TestExtractConfigParams:
    """Tests for extract_config_params helper."""

    def test_extracts_profile_from_config(self) -> None:
        """Should extract profile from config.configurable.profile."""
        profile = Profile(
            name="test",
            tracker="noop",
            working_dir="/tmp/test",
            agents={
                "architect": AgentConfig(driver="cli:claude", model="sonnet"),
                "developer": AgentConfig(driver="cli:claude", model="sonnet"),
                "reviewer": AgentConfig(driver="cli:claude", model="sonnet"),
            },
        )
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-123",
                "profile": profile,
            }
        }
        event_bus, workflow_id, extracted_profile = extract_config_params(config)
        assert extracted_profile == profile
        assert workflow_id == "wf-123"
        assert event_bus is None

    def test_extracts_event_bus_from_config(self) -> None:
        """Should extract event_bus when provided."""
        mock_event_bus = MagicMock()

        profile = Profile(
            name="test",
            tracker="noop",
            working_dir="/tmp/test",
            agents={
                "architect": AgentConfig(driver="cli:claude", model="sonnet"),
                "developer": AgentConfig(driver="cli:claude", model="sonnet"),
                "reviewer": AgentConfig(driver="cli:claude", model="sonnet"),
            },
        )
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-123",
                "profile": profile,
                "event_bus": mock_event_bus,
            }
        }
        event_bus, wf_id, prof = extract_config_params(config)
        assert event_bus is mock_event_bus
        assert wf_id == "wf-123"
        assert prof == profile

    def test_raises_if_profile_missing(self) -> None:
        """Should raise ValueError if profile not in config."""
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-123",
            }
        }
        with pytest.raises(ValueError, match="profile is required"):
            extract_config_params(config)
