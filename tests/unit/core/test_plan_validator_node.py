"""Tests for plan_validator_node function."""

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
def mock_profile_with_validator_model(tmp_path: Path) -> Profile:
    """Create a test profile with validator_model set."""
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
def mock_state(mock_issue: Issue) -> ExecutionState:
    """Create a test execution state."""
    return ExecutionState(profile_id="test", issue=mock_issue)


def make_config(profile: Profile) -> RunnableConfig:
    """Create a RunnableConfig for testing."""
    return {
        "configurable": {
            "profile": profile,
            "thread_id": "test-workflow-123",  # _extract_config_params expects thread_id
            "stream_emitter": AsyncMock(),
        }
    }


class TestPlanValidatorNode:
    """Tests for plan_validator_node function."""

    @pytest.mark.asyncio
    async def test_validator_extracts_goal_from_plan(
        self,
        mock_state: ExecutionState,
        mock_profile: Profile,
        plan_content: str,
        tmp_path: Path,
    ) -> None:
        """Happy path - validator extracts goal, markdown, and key_files from plan."""
        # Setup: Create plan file at expected location (working_dir / pattern)
        from datetime import date

        from amelia.core.orchestrator import plan_validator_node
        today = date.today().isoformat()
        plan_path = tmp_path / f"{today}-test-123.md"
        plan_path.write_text(plan_content)

        # Mock the driver to return structured output
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

    @pytest.mark.asyncio
    async def test_validator_fails_when_plan_file_missing(
        self,
        mock_state: ExecutionState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Validator raises ValueError when plan file doesn't exist."""
        from amelia.core.orchestrator import plan_validator_node

        # Don't create the plan file
        config = make_config(mock_profile)

        with pytest.raises(ValueError, match="Plan file not found"):
            await plan_validator_node(mock_state, config)

    @pytest.mark.asyncio
    async def test_validator_fails_when_plan_file_empty(
        self,
        mock_state: ExecutionState,
        mock_profile: Profile,
        tmp_path: Path,
    ) -> None:
        """Validator raises ValueError when plan file is empty."""
        # Create empty plan file at working_dir / pattern
        from datetime import date

        from amelia.core.orchestrator import plan_validator_node
        today = date.today().isoformat()
        plan_path = tmp_path / f"{today}-test-123.md"
        plan_path.write_text("")

        config = make_config(mock_profile)

        with pytest.raises(ValueError, match="Plan file is empty"):
            await plan_validator_node(mock_state, config)

    @pytest.mark.asyncio
    async def test_validator_uses_validator_model_when_set(
        self,
        mock_state: ExecutionState,
        mock_profile_with_validator_model: Profile,
        plan_content: str,
        tmp_path: Path,
    ) -> None:
        """Validator uses profile.validator_model when it's set."""
        # Setup: Create plan file at working_dir / pattern
        from datetime import date

        from amelia.core.orchestrator import plan_validator_node
        today = date.today().isoformat()
        plan_path = tmp_path / f"{today}-test-123.md"
        plan_path.write_text(plan_content)

        mock_output = MarkdownPlanOutput(
            goal="Goal",
            plan_markdown=plan_content,
            key_files=[],
        )
        mock_driver = MagicMock()
        mock_driver.generate = AsyncMock(return_value=(mock_output, "session-123"))

        config = make_config(mock_profile_with_validator_model)

        with patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_factory.get_driver.return_value = mock_driver

            await plan_validator_node(mock_state, config)

        # Verify driver was created with validator_model, not profile.model
        mock_factory.get_driver.assert_called_once_with(
            "api:openrouter",
            model="gpt-4o-mini",  # validator_model, not "gpt-4"
        )

    @pytest.mark.asyncio
    async def test_validator_falls_back_to_profile_model(
        self,
        mock_state: ExecutionState,
        mock_profile: Profile,  # No validator_model set
        plan_content: str,
        tmp_path: Path,
    ) -> None:
        """Validator falls back to profile.model when validator_model is None."""
        # Setup: Create plan file at working_dir / pattern
        from datetime import date

        from amelia.core.orchestrator import plan_validator_node
        today = date.today().isoformat()
        plan_path = tmp_path / f"{today}-test-123.md"
        plan_path.write_text(plan_content)

        mock_output = MarkdownPlanOutput(
            goal="Goal",
            plan_markdown=plan_content,
            key_files=[],
        )
        mock_driver = MagicMock()
        mock_driver.generate = AsyncMock(return_value=(mock_output, "session-123"))

        config = make_config(mock_profile)

        with patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_factory.get_driver.return_value = mock_driver

            await plan_validator_node(mock_state, config)

        # Verify driver was created with profile.model as fallback
        mock_factory.get_driver.assert_called_once_with(
            "api:openrouter",
            model="gpt-4",  # Falls back to profile.model
        )
