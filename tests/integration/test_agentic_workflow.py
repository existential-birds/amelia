"""Integration tests for agentic workflow.

Tests the LangGraph orchestrator graph structure, ExecutionState fields,
and workflow invocation with real components (mocking only at HTTP/LLM boundary).
"""

from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.agents.reviewer import ReviewResponse
from amelia.core.orchestrator import (
    call_architect_node,
    call_developer_node,
    call_reviewer_node,
)
from amelia.core.state import ExecutionState
from amelia.drivers.api import ApiDriver
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from tests.integration.conftest import make_config, make_execution_state, make_issue, make_profile


@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set API key env var to allow driver construction."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-for-integration-tests")


@pytest.mark.integration
class TestArchitectNodeIntegration:
    """Test architect node with real Architect, mock at driver.execute_agentic() level."""

    async def test_architect_node_returns_raw_output(self, tmp_path: Path) -> None:
        """Architect node should return raw output; plan extraction is done by plan_validator_node.

        Real components: DriverFactory, ApiDriver, Architect
        Mock boundary: ApiDriver.execute_agentic (LLM call)
        """
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        profile = make_profile(
            plan_output_dir=str(plans_dir),
            working_dir=str(tmp_path),
        )
        issue = make_issue(id="TEST-1", title="Add feature X", description="Add a new feature X to the system")
        state = make_execution_state(issue=issue, profile=profile)
        config = make_config(thread_id="test-wf-1", profile=profile)

        # Mock at driver.execute_agentic level - this is the HTTP boundary
        plan_markdown = "# Plan\n\n**Goal:** Implement feature X by modifying component Y\n\n1. Do thing A\n2. Do thing B"
        mock_messages = [
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Analyzing the issue...",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content=plan_markdown,
                session_id="session-123",
            ),
        ]

        async def mock_execute_agentic(*_args: Any, **_kwargs: Any) -> Any:
            """Mock async generator that yields AgenticMessage objects."""
            for msg in mock_messages:
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            result = await call_architect_node(state, cast(RunnableConfig, config))

        # Architect node returns raw output - goal/plan extraction is done by plan_validator_node
        assert "raw_architect_output" in result
        assert result["raw_architect_output"] == plan_markdown
        assert "tool_calls" in result
        assert "tool_results" in result
        # These fields are NOT set by architect_node (set by plan_validator_node)
        assert "goal" not in result
        assert "plan_markdown" not in result

    async def test_architect_node_requires_issue(self) -> None:
        """Architect node should raise error if no issue provided."""
        profile = make_profile()
        state = ExecutionState(profile_id="test", issue=None)
        config = make_config(thread_id="test-wf-1", profile=profile)

        with pytest.raises(ValueError, match="no issue provided"):
            await call_architect_node(state, cast(RunnableConfig, config))


@pytest.mark.integration
class TestDeveloperNodeIntegration:
    """Test developer node with real Developer, mock at pydantic-ai Agent level."""

    async def test_developer_node_collects_tool_calls(self, tmp_path: Path) -> None:
        """Developer node should track tool calls/results from driver.

        Real components: DriverFactory, ApiDriver, Developer
        Mock boundary: ApiDriver.execute_agentic (HTTP/LLM call)
        """
        profile = make_profile(working_dir=str(tmp_path))
        state = make_execution_state(
            profile=profile,
            goal="Create a hello.txt file with 'Hello World'",
        )
        config = make_config(thread_id="test-wf-2", profile=profile)

        # Mock AgenticMessage stream from the driver's execute_agentic
        mock_messages = [
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name="write_file",
                tool_input={"file_path": "hello.txt", "content": "Hello World"},
                tool_call_id="call-1",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name="write_file",
                tool_output="File created successfully",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="I created hello.txt with the content 'Hello World'",
                session_id="session-123",
            ),
        ]

        async def mock_execute_agentic(*_args: Any, **_kwargs: Any) -> Any:
            """Mock async generator that yields AgenticMessage objects."""
            for msg in mock_messages:
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            result = await call_developer_node(state, cast(RunnableConfig, config))

        assert len(result["tool_calls"]) >= 1
        assert result["tool_calls"][0].tool_name == "write_file"
        assert result["agentic_status"] == "completed"
        assert "hello.txt" in result["final_response"]

    async def test_developer_node_requires_goal(self, tmp_path: Path) -> None:
        """Developer node should raise error if no goal set."""
        profile = make_profile(working_dir=str(tmp_path))
        state = ExecutionState(profile_id="test", goal=None)
        config = make_config(thread_id="test-wf-3", profile=profile)

        with pytest.raises(ValueError, match="no goal"):
            await call_developer_node(state, cast(RunnableConfig, config))


@pytest.mark.integration
class TestReviewerNodeIntegration:
    """Test reviewer node with real Reviewer, mock at driver.generate() level."""

    async def test_reviewer_node_returns_review_result(self, tmp_path: Path) -> None:
        """Reviewer node should return ReviewResult from driver.

        Real components: DriverFactory, ApiDriver, Reviewer
        Mock boundary: ApiDriver.generate (LLM call)
        """
        profile = make_profile(working_dir=str(tmp_path))
        state = make_execution_state(
            profile=profile,
            goal="Add logging to the application",
            code_changes_for_review="diff --git a/app.py b/app.py\n+import logging",
        )
        config = make_config(thread_id="test-wf-4", profile=profile)

        mock_llm_response = ReviewResponse(
            approved=True,
            comments=["LGTM! Good use of standard logging module."],
            severity="low",
        )

        with patch.object(ApiDriver, "generate", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = (mock_llm_response, "session-123")
            result = await call_reviewer_node(state, cast(RunnableConfig, config))

        assert result["last_review"] is not None
        assert result["last_review"].approved is True
        assert "LGTM" in result["last_review"].comments[0]

    async def test_reviewer_node_rejection(self, tmp_path: Path) -> None:
        """Reviewer node should return rejection with feedback.

        Real components: DriverFactory, ApiDriver, Reviewer
        Mock boundary: ApiDriver.generate (LLM call)
        """
        profile = make_profile(working_dir=str(tmp_path))
        state = make_execution_state(
            profile=profile,
            goal="Implement secure authentication",
            code_changes_for_review="diff --git a/auth.py\n+password = 'hardcoded'",
        )
        config = make_config(thread_id="test-wf-5", profile=profile)

        mock_llm_response = ReviewResponse(
            approved=False,
            comments=["Critical: Hardcoded password found. Use environment variables or secure vault."],
            severity="critical",
        )

        with patch.object(ApiDriver, "generate", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = (mock_llm_response, "session-456")
            result = await call_reviewer_node(state, cast(RunnableConfig, config))

        assert result["last_review"].approved is False
        assert result["last_review"].severity == "critical"

    async def test_reviewer_node_increments_review_iteration(self, tmp_path: Path) -> None:
        """Reviewer node should increment review_iteration after each review.

        This prevents infinite loops when review is rejected - the iteration
        counter ensures we eventually hit max_review_iterations and terminate.

        Real components: DriverFactory, ApiDriver, Reviewer
        Mock boundary: ApiDriver.generate (LLM call)
        """
        profile = make_profile(working_dir=str(tmp_path), max_review_iterations=3)
        state = make_execution_state(
            profile=profile,
            goal="Fix the bug",
            code_changes_for_review="diff --git a/fix.py\n+# partial fix",
            review_iteration=0,
        )
        config = make_config(thread_id="test-wf-iteration", profile=profile)

        mock_llm_response = ReviewResponse(
            approved=False,
            comments=["Still needs work"],
            severity="high",
        )

        with patch.object(ApiDriver, "generate", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = (mock_llm_response, "session-iter")
            result = await call_reviewer_node(state, cast(RunnableConfig, config))

        # Key assertion: review_iteration should be incremented
        assert "review_iteration" in result, "review_iteration must be returned by reviewer node"
        assert result["review_iteration"] == 1, "review_iteration should increment from 0 to 1"

        # Run again with incremented state to verify it keeps incrementing
        state_round2 = state.model_copy(update={"review_iteration": 1})
        with patch.object(ApiDriver, "generate", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = (mock_llm_response, "session-iter2")
            result2 = await call_reviewer_node(state_round2, cast(RunnableConfig, config))

        assert result2["review_iteration"] == 2, "review_iteration should increment from 1 to 2"

    async def test_reviewer_node_updates_last_review_each_round(self, tmp_path: Path) -> None:
        """Reviewer node should update last_review with new results each round.

        This verifies that the review results are different after developer
        makes changes, preventing the "same review message" infinite loop bug.

        Real components: DriverFactory, ApiDriver, Reviewer
        Mock boundary: ApiDriver.generate (LLM call)
        """
        profile = make_profile(working_dir=str(tmp_path), max_review_iterations=3)
        state = make_execution_state(
            profile=profile,
            goal="Fix the bug",
            code_changes_for_review="diff --git a/fix.py\n+# initial attempt",
            review_iteration=0,
        )
        config = make_config(thread_id="test-wf-review-update", profile=profile)

        # Round 1: Reviewer rejects with severity "high"
        mock_response_round1 = ReviewResponse(
            approved=False,
            comments=["Missing error handling", "No tests"],
            severity="high",
        )

        with patch.object(ApiDriver, "generate", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = (mock_response_round1, "session-r1")
            result1 = await call_reviewer_node(state, cast(RunnableConfig, config))

        assert result1["last_review"].approved is False
        assert result1["last_review"].severity == "high"
        assert len(result1["last_review"].comments) == 2
        assert "Missing error handling" in result1["last_review"].comments

        # Round 2: Simulate developer fixed one issue, reviewer now returns different result
        state_round2 = state.model_copy(update={
            "review_iteration": 1,
            "code_changes_for_review": "diff --git a/fix.py\n+# with error handling",
        })
        mock_response_round2 = ReviewResponse(
            approved=False,
            comments=["Still no tests"],
            severity="medium",
        )

        with patch.object(ApiDriver, "generate", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = (mock_response_round2, "session-r2")
            result2 = await call_reviewer_node(state_round2, cast(RunnableConfig, config))

        # Verify last_review is UPDATED, not stale
        assert result2["last_review"].approved is False
        assert result2["last_review"].severity == "medium", "severity should update from high to medium"
        assert len(result2["last_review"].comments) == 1, "comment count should change"
        assert "Still no tests" in result2["last_review"].comments, "comments should be new"

        # Round 3: All fixed, approved
        state_round3 = state.model_copy(update={
            "review_iteration": 2,
            "code_changes_for_review": "diff --git a/fix.py\n+# with tests",
        })
        mock_response_round3 = ReviewResponse(
            approved=True,
            comments=["LGTM!"],
            severity="low",
        )

        with patch.object(ApiDriver, "generate", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = (mock_response_round3, "session-r3")
            result3 = await call_reviewer_node(state_round3, cast(RunnableConfig, config))

        assert result3["last_review"].approved is True, "should be approved in round 3"
        assert result3["last_review"].severity == "low"
        assert result3["review_iteration"] == 3
