"""Tests for plan_validator_node function.

Verifies that plan_validator_node uses regex-only extraction (no LLM calls).
"""

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.types import AgentConfig, Issue, Profile
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
    """Create a test profile with tmp_path as repo_root."""
    return Profile(
        name="test",
        tracker="github",
        repo_root=str(tmp_path),
        plan_path_pattern="{date}-{issue_key}.md",
        agents={
            "architect": AgentConfig(driver="api", model="gpt-4"),
            "developer": AgentConfig(driver="api", model="gpt-4"),
            "reviewer": AgentConfig(driver="api", model="gpt-4"),
            "plan_validator": AgentConfig(driver="api", model="gpt-4o-mini"),
            "evaluator": AgentConfig(driver="api", model="gpt-4"),
            "task_reviewer": AgentConfig(driver="api", model="gpt-4o-mini"),
        },
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
        workflow_id=uuid4(),
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
    """Tests for plan_validator_node regex-only extraction."""

    async def test_reads_plan_from_disk_and_extracts_fields(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Validator reads plan file and extracts goal, key_files via regex."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        # Plan uses Create:/Modify: format that the regex expects
        plan_with_files = """# Implementation Plan for TEST-123

**Goal:** Add user authentication with JWT tokens

## Overview

This plan implements JWT-based authentication.

### Task 1: Setup auth module
- Create: `src/auth/handler.py`
- Modify: `src/models/user.py`
- Create: `tests/test_auth.py`

Deliverable: Working auth module
"""
        plan_path = create_plan_file(tmp_path, plan_with_files)
        config = make_config(mock_profile)

        result = await plan_validator_node(mock_state, config)

        assert result["goal"] == "Add user authentication with JWT tokens"
        assert result["plan_markdown"] == plan_with_files
        assert result["plan_path"] == plan_path
        assert "src/auth/handler.py" in result["key_files"]
        assert "src/models/user.py" in result["key_files"]
        assert "tests/test_auth.py" in result["key_files"]

    async def test_no_llm_calls(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        plan_content: str,
        tmp_path: Path,
    ) -> None:
        """Validator must NOT use extract_structured (no LLM dependency)."""
        import amelia.pipelines.implementation.nodes as nodes_module
        from amelia.pipelines.implementation.nodes import plan_validator_node

        # Verify extract_structured is not even imported in the module
        assert not hasattr(nodes_module, "extract_structured"), (
            "extract_structured should not be imported in nodes module"
        )

        create_plan_file(tmp_path, plan_content)
        config = make_config(mock_profile)

        # Should succeed purely with regex, no LLM needed
        result = await plan_validator_node(mock_state, config)

        assert result["goal"] is not None
        assert result["plan_markdown"] is not None

    async def test_raises_for_missing_file(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Validator raises ValueError when plan file doesn't exist."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        config = make_config(mock_profile)

        with pytest.raises(ValueError, match="Plan file not found"):
            await plan_validator_node(mock_state, config)

    async def test_raises_for_empty_file(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Validator raises ValueError when plan file is empty."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        create_plan_file(tmp_path, "")
        config = make_config(mock_profile)

        with pytest.raises(ValueError, match="Plan file is empty"):
            await plan_validator_node(mock_state, config)

    async def test_raises_for_missing_issue(
        self,
        mock_profile: Profile,
    ) -> None:
        """Validator raises ValueError when issue is missing from state."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            issue=None,
        )
        config = make_config(mock_profile)

        with pytest.raises(ValueError, match="Issue is required"):
            await plan_validator_node(state, config)

    async def test_returns_expected_state_dict_keys(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        plan_content: str,
        tmp_path: Path,
    ) -> None:
        """Validator returns all expected keys in state dict."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        create_plan_file(tmp_path, plan_content)
        config = make_config(mock_profile)

        result = await plan_validator_node(mock_state, config)

        expected_keys = {
            "goal",
            "plan_markdown",
            "plan_path",
            "key_files",
            "total_tasks",
            "plan_validation_result",
            "plan_revision_count",
            "plan_structured",
        }
        assert set(result.keys()) == expected_keys


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

    def test_extract_task_count_returns_one_for_no_tasks(self) -> None:
        """Should return 1 when no ### Task N: patterns found (single-task default)."""
        from amelia.pipelines.implementation.utils import extract_task_count

        plan = """
# Implementation Plan

Some content without task markers.

## Section 1

More content.
"""
        assert extract_task_count(plan) == 1

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

    async def test_plan_validator_sets_total_tasks(
        self, tmp_path: Path
    ) -> None:
        """plan_validator_node should extract and return total_tasks from plan."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan_content = """
# Test Plan

**Goal:** Test goal

### Task 1: First task

Do first thing.

### Task 2: Second task

Do second thing.
"""
        plan_path = tmp_path / "docs" / "plans" / "test-plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(plan_content)

        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            issue=Issue(id="TEST-123", title="Test", description="Test"),
        )

        profile = Profile(
            name="test",
            tracker="noop",
            repo_root=str(tmp_path),
            plan_path_pattern="docs/plans/test-plan.md",
            agents={
                "architect": AgentConfig(driver="api", model="anthropic/claude-3.5-sonnet"),
                "developer": AgentConfig(driver="api", model="anthropic/claude-3.5-sonnet"),
                "reviewer": AgentConfig(driver="api", model="anthropic/claude-3.5-sonnet"),
                "plan_validator": AgentConfig(driver="api", model="anthropic/claude-3.5-sonnet"),
                "evaluator": AgentConfig(driver="api", model="anthropic/claude-3.5-sonnet"),
                "task_reviewer": AgentConfig(driver="api", model="anthropic/claude-3.5-sonnet"),
            },
        )
        config: RunnableConfig = {
            "configurable": {
                "profile": profile,
                "thread_id": "test-workflow-123",
            }
        }

        result = await plan_validator_node(state, config)

        assert result["total_tasks"] == 2

    async def test_plan_validator_defaults_total_tasks_to_one_for_simple_plans(
        self, tmp_path: Path
    ) -> None:
        """plan_validator_node should set total_tasks=1 for plans without task markers."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan_content = """
# Simple Plan

**Goal:** Simple goal

No task markers here, just freeform instructions.

## Setup

Do setup.

## Implementation

Do implementation.
"""
        plan_path = tmp_path / "docs" / "plans" / "simple-plan.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(plan_content)

        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            issue=Issue(id="TEST-456", title="Simple", description="Simple test"),
        )

        profile = Profile(
            name="test",
            tracker="noop",
            repo_root=str(tmp_path),
            plan_path_pattern="docs/plans/simple-plan.md",
            agents={
                "architect": AgentConfig(driver="api", model="anthropic/claude-3.5-sonnet"),
                "developer": AgentConfig(driver="api", model="anthropic/claude-3.5-sonnet"),
                "reviewer": AgentConfig(driver="api", model="anthropic/claude-3.5-sonnet"),
                "plan_validator": AgentConfig(driver="api", model="anthropic/claude-3.5-sonnet"),
                "evaluator": AgentConfig(driver="api", model="anthropic/claude-3.5-sonnet"),
                "task_reviewer": AgentConfig(driver="api", model="anthropic/claude-3.5-sonnet"),
            },
        )
        config: RunnableConfig = {
            "configurable": {
                "profile": profile,
                "thread_id": "test-workflow-456",
            }
        }

        result = await plan_validator_node(state, config)

        assert result["total_tasks"] == 1


class TestPlanValidatorNodeValidation:
    """Tests for plan validation within plan_validator_node."""

    async def test_returns_valid_result_for_good_plan(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """A well-structured plan should pass validation."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan = """# Feature Implementation Plan

**Goal:** Add user auth

### Task 1: Add login endpoint
- Create: `src/auth.py`
- Deliverable: Working /login route

### Task 2: Add tests
- Create: `tests/test_auth.py`
- Deliverable: Passing test suite

This plan has enough content to pass the minimum length check.
It describes the implementation in reasonable detail.
"""
        create_plan_file(tmp_path, plan)
        config = make_config(mock_profile)

        result = await plan_validator_node(mock_state, config)

        assert result["plan_validation_result"].valid is True
        assert result["plan_validation_result"].issues == []
        assert result["plan_revision_count"] == 0

    async def test_returns_invalid_for_no_tasks(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """A plan with no ### Task headers should fail structural validation."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan = """# Some Plan

**Goal:** Do something

Just some text with no task structure.
This plan does not have any task headers at all.
It is long enough to pass minimum length but
lacks the required ### Task N: formatting that
the downstream task processor expects.
"""
        create_plan_file(tmp_path, plan)
        config = make_config(mock_profile)

        result = await plan_validator_node(mock_state, config)

        assert result["plan_validation_result"].valid is False
        assert any("Task" in i for i in result["plan_validation_result"].issues)

    async def test_increments_revision_count_on_invalid(
        self,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Revision count should increment when validation fails."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan = "short"  # Will fail validation
        create_plan_file(tmp_path, plan)

        state = ImplementationState(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            status="running",
            profile_id="test",
            issue=Issue(id="TEST-123", title="Test", description="Test"),
            plan_revision_count=1,
        )

        config = make_config(mock_profile)

        result = await plan_validator_node(state, config)

        assert result["plan_revision_count"] == 2

    async def test_does_not_increment_revision_count_on_valid(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Revision count should NOT increment when validation passes."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan = """# Feature Plan

**Goal:** Add feature

### Task 1: Implement feature
Detailed implementation steps with enough content to pass validation.
Create the necessary files and write comprehensive tests.

### Task 2: Add tests
Write tests covering all edge cases and error paths.
"""
        create_plan_file(tmp_path, plan)
        config = make_config(mock_profile)

        result = await plan_validator_node(mock_state, config)

        assert result["plan_revision_count"] == 0

    async def test_runs_validate_plan_structure(
        self,
        mock_state: ImplementationState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Validator runs validate_plan_structure and returns its result."""
        from amelia.pipelines.implementation.nodes import plan_validator_node

        plan = """# Feature Plan

**Goal:** Add feature

### Task 1: Do the work
Implementation details here with enough text.
"""
        create_plan_file(tmp_path, plan)
        config = make_config(mock_profile)

        result = await plan_validator_node(mock_state, config)

        # Should have a validation result object
        vr = result["plan_validation_result"]
        assert hasattr(vr, "valid")
        assert hasattr(vr, "issues")
        assert hasattr(vr, "severity")
