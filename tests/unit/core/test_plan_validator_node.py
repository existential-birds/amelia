"""Tests for plan_validator_node function."""

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.agents.architect import MarkdownPlanOutput
from amelia.core.types import Issue, Profile
from amelia.pipelines.implementation.state import ImplementationState


@pytest.fixture
def plan_content() -> str:
    """Sample plan markdown content."""
    return """# Implementation Plan for TEST-123

**Goal:** Add user authentication with JWT tokens

## Overview

This plan implements JWT-based authentication.

## Files to Modify

- `src/auth/handler.py` - Add JWT validation
- `src/models/user.py` - Add token fields
- `tests/test_auth.py` - Add auth tests

## Implementation Steps

1. Add JWT library dependency
2. Create token validation middleware
3. Update user model
"""


@pytest.fixture
def mock_profile(tmp_path: Path) -> Profile:
    """Create a test profile with tmp_path as working_dir."""
    return Profile(
        name="test",
        driver="api:openrouter",
        model="gpt-4",
        tracker="github",
        validator_model="gpt-4o-mini",
        working_dir=str(tmp_path),
        plan_path_pattern="{date}-{issue_key}.md",
    )


@pytest.fixture
def mock_issue() -> Issue:
    """Create a test issue."""
    return Issue(
        id="TEST-123",
        title="Test Issue",
        description="Test description",
    )


@pytest.fixture
def mock_state(mock_issue: Issue) -> ImplementationState:
    """Create a test execution state."""
    return ImplementationState(
        workflow_id="test-workflow-123",
        created_at=datetime.now(UTC),
        status="running",
        profile_id="test",
        issue=mock_issue,
    )


def make_config(profile: Profile) -> RunnableConfig:
    """Create a RunnableConfig for testing."""
    return {
        "configurable": {
            "profile": profile,
            "thread_id": "test-workflow-123",
            "stream_emitter": AsyncMock(),
        }
    }


def create_plan_file(tmp_path: Path, content: str) -> Path:
    """Create a plan file at the expected location."""
    today = date.today().isoformat()
    plan_path = tmp_path / f"{today}-test-123.md"
    plan_path.write_text(content)
    return plan_path


class TestPlanValidatorNode:
    """Tests for plan_validator_node function."""

    async def test_validator_extracts_goal_from_plan(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        plan_content: str,
        tmp_path: Path,
    ) -> None:
        """Happy path - validator extracts goal, markdown, and key_files from plan."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan_path = create_plan_file(tmp_path, plan_content)

        mock_output = MarkdownPlanOutput(
            goal="Add user authentication with JWT tokens",
            plan_markdown=plan_content,
            key_files=["src/auth/handler.py", "src/models/user.py", "tests/test_auth.py"],
        )

        config = make_config(mock_profile)

        with patch(
            "amelia.pipelines.implementation.nodes.extract_structured",
            new_callable=AsyncMock,
            return_value=mock_output,
        ):
            result = await plan_validator_node(mock_state, config)

        assert result["goal"] == "Add user authentication with JWT tokens"
        assert result["plan_markdown"] == plan_content
        assert result["plan_path"] == plan_path
        assert result["key_files"] == [
            "src/auth/handler.py",
            "src/models/user.py",
            "tests/test_auth.py",
        ]

    async def test_validator_raises_for_missing_file(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Validator raises ValueError when plan file doesn't exist."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        # Don't create the plan file - it should be missing
        config = make_config(mock_profile)

        with pytest.raises(ValueError, match="Plan file not found"):
            await plan_validator_node(mock_state, config)

    async def test_validator_raises_for_empty_file(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Validator raises ValueError when plan file is empty."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        create_plan_file(tmp_path, "")  # Create empty file
        config = make_config(mock_profile)

        with pytest.raises(ValueError, match="Plan file is empty"):
            await plan_validator_node(mock_state, config)

    async def test_validator_model_selection(
        self,
        mock_state: ImplementationState,
        plan_content: str,
        tmp_path: Path,
    ) -> None:
        """Validator uses the configured validator_model."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        profile = Profile(
            name="test",
            driver="api:openrouter",
            model="gpt-4",
            tracker="github",
            validator_model="gpt-4o-mini",
            working_dir=str(tmp_path),
            plan_path_pattern="{date}-{issue_key}.md",
        )

        create_plan_file(tmp_path, plan_content)

        mock_output = MarkdownPlanOutput(
            goal="Goal",
            plan_markdown=plan_content,
            key_files=[],
        )

        config = make_config(profile)

        with patch(
            "amelia.pipelines.implementation.nodes.extract_structured",
            new_callable=AsyncMock,
            return_value=mock_output,
        ) as mock_extract:
            await plan_validator_node(mock_state, config)

        # Verify _extract_structured was called with the correct model
        mock_extract.assert_called_once()
        call_kwargs = mock_extract.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["driver_type"] == "api:openrouter"


class TestExtractTaskCount:
    """Tests for extract_task_count helper function."""

    def test_extract_task_count_returns_count_for_valid_tasks(self) -> None:
        """Should count ### Task N: patterns in plan markdown."""
        from amelia.pipelines.implementation.utils import extract_task_count

        plan = """
# Implementation Plan

### Task 1: Setup

Do the setup.

### Task 2: Implementation

Do the implementation.

### Task 3: Testing

Run tests.
"""
        assert extract_task_count(plan) == 3

    def test_extract_task_count_returns_none_for_no_tasks(self) -> None:
        """Should return None when no ### Task N: patterns found."""
        from amelia.pipelines.implementation.utils import extract_task_count

        plan = """
# Implementation Plan

Some content without task markers.

## Section 1

More content.
"""
        assert extract_task_count(plan) is None

    def test_extract_task_count_ignores_malformed_patterns(self) -> None:
        """Should only match exact ### Task N: pattern."""
        from amelia.pipelines.implementation.utils import extract_task_count

        plan = """
### Task 1: Valid

Content.

#### Task 2: Wrong level (h4)

### Task: Missing number

### Task2: Missing space

### Task 3: Also valid
"""
        assert extract_task_count(plan) == 2  # Only Task 1 and Task 3

    def test_extract_task_count_supports_hierarchical_numbering(self) -> None:
        """Should count ### Task N.M: patterns (hierarchical/phased format)."""
        from amelia.pipelines.implementation.utils import extract_task_count

        plan = """
# Implementation Plan

## Phase 1: Foundation

### Task 1.1: Initialize project

Setup steps.

### Task 1.2: Configure database

Database config.

## Phase 2: Implementation

### Task 2.1: Build API

API work.

### Task 2.2: Add tests

Test work.
"""
        assert extract_task_count(plan) == 4

    def test_extract_task_count_supports_mixed_numbering(self) -> None:
        """Should count both simple and hierarchical task patterns."""
        from amelia.pipelines.implementation.utils import extract_task_count

        plan = """
### Task 1: Simple task

Content.

### Task 1.1: Hierarchical task

Content.

### Task 2: Another simple

Content.
"""
        assert extract_task_count(plan) == 3


class TestPlanValidatorNodeTotalTasks:
    """Tests for plan_validator_node total_tasks extraction."""

    @pytest.fixture
    def mock_profile(self) -> Profile:
        return Profile(
            name="test",
            driver="api:openrouter",
            model="anthropic/claude-3.5-sonnet",
            validator_model="anthropic/claude-3.5-sonnet",
            working_dir="/tmp/test",
        )

    @pytest.fixture
    def state_with_plan(self, tmp_path: Path, mock_profile: Profile) -> tuple[ImplementationState, Path]:
        plan_content = """
# Test Plan

### Task 1: First task

Do first thing.

### Task 2: Second task

Do second thing.
"""
        plan_path = tmp_path / "docs" / "plans" / "test-plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(plan_content)

        state = ImplementationState(
            workflow_id="test-workflow-123",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            raw_architect_output=str(plan_path),
            issue=Issue(id="TEST-123", title="Test", description="Test"),
        )
        return state, plan_path

    async def test_plan_validator_sets_total_tasks(
        self, state_with_plan: tuple[ImplementationState, Path], tmp_path: Path
    ) -> None:
        """plan_validator_node should extract and return total_tasks from plan."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        state, plan_path = state_with_plan

        mock_output = MagicMock()
        mock_output.goal = "Test goal"
        mock_output.key_files = ["file1.py"]
        mock_output.plan_markdown = plan_path.read_text()

        profile = Profile(
            name="test",
            driver="api:openrouter",
            model="anthropic/claude-3.5-sonnet",
            validator_model="anthropic/claude-3.5-sonnet",
            working_dir=str(tmp_path),
            plan_path_pattern="docs/plans/test-plan.md",
        )
        config: RunnableConfig = {
            "configurable": {
                "profile": profile,
                "thread_id": "test-workflow-123",
            }
        }

        with patch(
            "amelia.pipelines.implementation.nodes.extract_structured",
            new_callable=AsyncMock,
            return_value=mock_output,
        ):
            result = await plan_validator_node(state, config)

        assert result["total_tasks"] == 2

    async def test_plan_validator_sets_total_tasks_none_for_legacy_plans(
        self, tmp_path: Path
    ) -> None:
        """plan_validator_node should set total_tasks=None for plans without task markers."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan_content = """
# Legacy Plan

No task markers here, just freeform instructions.

## Setup

Do setup.

## Implementation

Do implementation.
"""
        plan_path = tmp_path / "docs" / "plans" / "legacy-plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(plan_content)

        state = ImplementationState(
            workflow_id="test-workflow-456",
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            raw_architect_output=str(plan_path),
            issue=Issue(id="TEST-456", title="Legacy", description="Legacy test"),
        )

        mock_output = MagicMock()
        mock_output.goal = "Legacy goal"
        mock_output.key_files = []
        mock_output.plan_markdown = plan_content

        profile = Profile(
            name="test",
            driver="api:openrouter",
            model="anthropic/claude-3.5-sonnet",
            validator_model="anthropic/claude-3.5-sonnet",
            working_dir=str(tmp_path),
            plan_path_pattern="docs/plans/legacy-plan.md",
        )
        config: RunnableConfig = {
            "configurable": {
                "profile": profile,
                "thread_id": "test-workflow-456",
            }
        }

        with patch(
            "amelia.pipelines.implementation.nodes.extract_structured",
            new_callable=AsyncMock,
            return_value=mock_output,
        ):
            result = await plan_validator_node(state, config)

        assert result["total_tasks"] is None
