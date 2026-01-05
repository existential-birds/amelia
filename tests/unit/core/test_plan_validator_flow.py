"""Unit tests for plan_validator_node function."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.agents.architect import MarkdownPlanOutput
from amelia.core.orchestrator import (
    plan_validator_node,
)
from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile


@pytest.fixture
def validator_profile(tmp_path: Path) -> Profile:
    """Profile configured for plan validator testing.

    Uses working_dir to match how plan_validator_node resolves paths.
    """
    return Profile(
        name="validator-test",
        driver="api:openrouter",
        model="gpt-4",
        validator_model="gpt-4o-mini",
        tracker="github",
        working_dir=str(tmp_path),
        plan_path_pattern="{date}-{issue_key}.md",
    )


@pytest.fixture
def validator_issue() -> Issue:
    """Issue for validator testing."""
    return Issue(
        id="VAL-456",
        title="Validator Test Issue",
        description="Test plan validation",
    )


class TestPlanValidatorNode:
    """Unit tests for plan_validator_node."""

    @pytest.mark.asyncio
    async def test_validator_extracts_structured_output(
        self,
        validator_profile: Profile,
        validator_issue: Issue,
        tmp_path: Path,
    ) -> None:
        """Validator reads plan file and extracts structured fields via LLM."""
        state = ExecutionState(
            issue=validator_issue,
            profile_id=validator_profile.name,
        )
        plan_content = """# Implementation Plan for VAL-456

**Goal:** Implement feature X with Y integration

## Files to Modify

- `src/feature.py` - Main implementation
- `tests/test_feature.py` - Tests
"""
        # Setup: Create plan file in working_dir (simulating architect output)
        today = date.today().isoformat()
        plan_path = tmp_path / f"{today}-val-456.md"
        plan_path.write_text(plan_content)

        # Mock validator driver response
        mock_validator_output = MarkdownPlanOutput(
            goal="Implement feature X with Y integration",
            plan_markdown=plan_content,
            key_files=["src/feature.py", "tests/test_feature.py"],
        )
        mock_driver = MagicMock()
        mock_driver.generate = AsyncMock(return_value=(mock_validator_output, "sess"))

        config: RunnableConfig = {
            "configurable": {
                "profile": validator_profile,
                "thread_id": "val-test-789",
                "stream_emitter": AsyncMock(),
            }
        }

        with patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_factory.get_driver.return_value = mock_driver

            result = await plan_validator_node(state, config)

        # Verify extracted structure
        assert result["goal"] == "Implement feature X with Y integration"
        assert result["plan_markdown"] == plan_content
        assert result["plan_path"] == plan_path
        assert "src/feature.py" in result["key_files"]
        assert "tests/test_feature.py" in result["key_files"]
