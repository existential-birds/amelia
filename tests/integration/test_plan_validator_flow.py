"""Integration tests for architect → plan_validator flow."""

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.agents.architect import MarkdownPlanOutput
from amelia.core.orchestrator import (
    plan_validator_node,
)
from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile


@pytest.fixture
def integration_profile(tmp_path: Path) -> Profile:
    """Profile for integration testing."""
    return Profile(
        name="integration-test",
        driver="api:openrouter",
        model="gpt-4",
        validator_model="gpt-4o-mini",
        tracker="github",
        plan_output_dir=str(tmp_path / "plans"),
        plan_path_pattern="{date}-{issue_key}.md",
    )


@pytest.fixture
def integration_issue() -> Issue:
    """Issue for integration testing."""
    return Issue(
        id="INT-456",
        title="Integration Test Issue",
        description="Test the full flow",
        labels=[],
    )


class TestArchitectToValidatorFlow:
    """Integration tests for architect → validator flow."""

    @pytest.mark.asyncio
    async def test_architect_to_validator_flow(
        self,
        integration_profile: Profile,
        integration_issue: Issue,
        tmp_path: Path,
    ) -> None:
        """Full flow: architect writes plan → validator extracts structure."""
        state = ExecutionState(
            issue=integration_issue,
            profile_id=integration_profile.name,
        )
        plan_content = """# Implementation Plan for INT-456

**Goal:** Implement feature X with Y integration

## Files to Modify

- `src/feature.py` - Main implementation
- `tests/test_feature.py` - Tests
"""
        # Setup: Create plan file (simulating architect output)
        plan_dir = tmp_path / "plans"
        plan_dir.mkdir(parents=True)
        today = date.today().isoformat()
        plan_path = plan_dir / f"{today}-int-456.md"
        plan_path.write_text(plan_content)

        # Mock validator driver
        mock_validator_output = MarkdownPlanOutput(
            goal="Implement feature X with Y integration",
            plan_markdown=plan_content,
            key_files=["src/feature.py", "tests/test_feature.py"],
        )
        mock_driver = MagicMock()
        mock_driver.generate = AsyncMock(return_value=(mock_validator_output, "sess"))

        config: dict[str, Any] = {
            "configurable": {
                "profile": integration_profile,
                "thread_id": "int-test-789",
                "stream_emitter": AsyncMock(),
            }
        }

        with patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_factory.get_driver.return_value = mock_driver

            # Run validator node
            result = await plan_validator_node(state, config)

        # Verify extracted structure
        assert result["goal"] == "Implement feature X with Y integration"
        assert result["plan_markdown"] == plan_content
        assert result["plan_path"] == plan_path
        assert "src/feature.py" in result["key_files"]
        assert "tests/test_feature.py" in result["key_files"]
