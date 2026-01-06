"""Tests for plan_validator_node function."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.agents.architect import MarkdownPlanOutput
from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile


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
def mock_state(mock_issue: Issue) -> ExecutionState:
    """Create a test execution state."""
    return ExecutionState(profile_id="test", issue=mock_issue)


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
        mock_state: ExecutionState,
        mock_profile: Profile,
        plan_content: str,
        tmp_path: Path,
    ) -> None:
        """Happy path - validator extracts goal, markdown, and key_files from plan."""
        from amelia.core.orchestrator import plan_validator_node

        plan_path = create_plan_file(tmp_path, plan_content)

        mock_output = MarkdownPlanOutput(
            goal="Add user authentication with JWT tokens",
            plan_markdown=plan_content,
            key_files=["src/auth/handler.py", "src/models/user.py", "tests/test_auth.py"],
        )
        mock_driver = MagicMock()
        mock_driver.generate = AsyncMock(return_value=(mock_output, "session-123"))

        config = make_config(mock_profile)

        with patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_factory.get_driver.return_value = mock_driver
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
        mock_state: ExecutionState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Validator raises ValueError when plan file doesn't exist."""
        from amelia.core.orchestrator import plan_validator_node

        # Don't create the plan file - it should be missing
        config = make_config(mock_profile)

        with pytest.raises(ValueError, match="Plan file not found"):
            await plan_validator_node(mock_state, config)

    async def test_validator_raises_for_empty_file(
        self,
        mock_state: ExecutionState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Validator raises ValueError when plan file is empty."""
        from amelia.core.orchestrator import plan_validator_node

        create_plan_file(tmp_path, "")  # Create empty file
        config = make_config(mock_profile)

        with pytest.raises(ValueError, match="Plan file is empty"):
            await plan_validator_node(mock_state, config)

    @pytest.mark.parametrize(
        "validator_model,expected_model",
        [
            ("gpt-4o-mini", "gpt-4o-mini"),  # Uses validator_model when set
            (None, "gpt-4"),  # Falls back to profile.model
        ],
        ids=["uses_validator_model", "fallback_to_profile_model"],
    )
    async def test_validator_model_selection(
        self,
        mock_state: ExecutionState,
        plan_content: str,
        tmp_path: Path,
        validator_model: str | None,
        expected_model: str,
    ) -> None:
        """Validator uses correct model based on profile configuration."""
        from amelia.core.orchestrator import plan_validator_node

        profile = Profile(
            name="test",
            driver="api:openrouter",
            model="gpt-4",
            tracker="github",
            validator_model=validator_model,
            working_dir=str(tmp_path),
            plan_path_pattern="{date}-{issue_key}.md",
        )

        create_plan_file(tmp_path, plan_content)

        mock_output = MarkdownPlanOutput(
            goal="Goal",
            plan_markdown=plan_content,
            key_files=[],
        )
        mock_driver = MagicMock()
        mock_driver.generate = AsyncMock(return_value=(mock_output, "session-123"))

        config = make_config(profile)

        with patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_factory.get_driver.return_value = mock_driver
            await plan_validator_node(mock_state, config)

        mock_factory.get_driver.assert_called_once_with(
            "api:openrouter",
            model=expected_model,
        )
