"""Integration test: reviewer prompt resolution -> parse chain.

Verifies that the prompt from PROMPT_DEFAULTS produces output the parser
can handle, with only the driver boundary mocked.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from amelia.agents.reviewer import REVIEW_OUTPUT_FORMAT, Reviewer
from amelia.core.types import AgentConfig, DriverType, Profile, Severity
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.implementation.routing import route_after_task_review
from amelia.pipelines.implementation.state import ImplementationState
from tests.conftest import AsyncIteratorMock


WELL_FORMED_REVIEW = """## Review Summary

All changes look correct and follow project conventions.

## Issues

### Critical (Blocking)

None

### Major (Should Fix)

None

### Minor (Nice to Have)

None

## Good Patterns

- [src/main.py:10] Clean separation of concerns

## Verdict

Ready: Yes
Rationale: Code is clean and follows conventions."""


MALFORMED_REVIEW = """The code changes implement the feature.

I noticed a few things:
- The error handling could be improved
- Some type hints are missing

Overall the code is acceptable."""


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    """Profile with task_reviewer configured."""
    return Profile(
        name="test",
        working_dir=str(tmp_path),
        agents={
            "task_reviewer": AgentConfig(
                driver=DriverType.CLI, model="sonnet", options={"max_iterations": 2}
            ),
        },
    )


@pytest.fixture
def mock_driver() -> MagicMock:
    """Mock driver for reviewer."""
    return MagicMock()


@pytest.fixture
def create_reviewer_with_defaults(mock_driver: MagicMock) -> Callable[..., Reviewer]:
    """Create Reviewer using PROMPT_DEFAULTS content (server-mode path)."""
    from amelia.agents.prompts.defaults import PROMPT_DEFAULTS

    def _create() -> Reviewer:
        prompts = {pid: pd.content for pid, pd in PROMPT_DEFAULTS.items()}
        with patch("amelia.agents.reviewer.get_driver", return_value=mock_driver):
            config = AgentConfig(driver=DriverType.CLI, model="sonnet", options={})
            return Reviewer(config, prompts=prompts, agent_name="task_reviewer")

    return _create


@pytest.mark.integration
class TestReviewerPromptParserChain:
    """Integration: prompt resolution -> LLM call -> parse -> routing."""

    async def test_well_formed_review_approved(
        self,
        create_reviewer_with_defaults: Callable[..., Reviewer],
        mock_driver: MagicMock,
        profile: Profile,
    ) -> None:
        """Well-formed markdown review with Ready: Yes -> approved=True."""
        reviewer = create_reviewer_with_defaults()

        mock_driver.execute_agentic = MagicMock(
            return_value=AsyncIteratorMock(
                [
                    AgenticMessage(
                        type=AgenticMessageType.RESULT,
                        content=WELL_FORMED_REVIEW,
                        session_id="sess-1",
                    ),
                ]
            )
        )

        state = ImplementationState(
            workflow_id="wf-int-001",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            current_task_index=0,
            total_tasks=3,
        )

        result, session_id = await reviewer.agentic_review(
            state, base_commit="abc123", profile=profile, workflow_id="wf-int-001"
        )

        assert result.approved is True
        assert result.severity == Severity.NONE
        assert session_id == "sess-1"

    async def test_malformed_review_defaults_to_not_approved_and_routing_advances(
        self,
        create_reviewer_with_defaults: Callable[..., Reviewer],
        mock_driver: MagicMock,
        profile: Profile,
    ) -> None:
        """Malformed output (no Ready: pattern) -> approved=False -> routing advances."""
        reviewer = create_reviewer_with_defaults()

        mock_driver.execute_agentic = MagicMock(
            return_value=AsyncIteratorMock(
                [
                    AgenticMessage(
                        type=AgenticMessageType.RESULT,
                        content=MALFORMED_REVIEW,
                        session_id="sess-2",
                    ),
                ]
            )
        )

        state = ImplementationState(
            workflow_id="wf-int-002",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            current_task_index=0,
            total_tasks=3,
            task_review_iteration=2,  # At max iterations
        )

        result, _ = await reviewer.agentic_review(
            state, base_commit="abc123", profile=profile, workflow_id="wf-int-002"
        )

        assert result.approved is False

        # Simulate routing with the result
        state_after = ImplementationState(
            workflow_id="wf-int-002",
            profile_id="test",
            created_at=datetime.now(UTC),
            status="running",
            current_task_index=0,
            total_tasks=3,
            task_review_iteration=2,
            last_review=result,
        )
        route = route_after_task_review(state_after, profile)
        # Non-final task at max iterations -> advance, not abort
        assert route == "next_task_node"

    async def test_prompt_defaults_contain_ready_format(self) -> None:
        """Verify PROMPT_DEFAULTS reviewer prompt has markdown format, not JSON."""
        from amelia.agents.prompts.defaults import PROMPT_DEFAULTS

        content = PROMPT_DEFAULTS["reviewer.agentic"].content
        assert "Ready: Yes" in content
        assert REVIEW_OUTPUT_FORMAT in content
