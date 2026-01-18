"""Integration tests for agentic workflow.

Tests the LangGraph orchestrator graph structure, ImplementationState fields,
and workflow invocation with real components (mocking only at HTTP/LLM boundary).
"""

from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.agents.architect import MarkdownPlanOutput
from amelia.core.constants import ToolName
from amelia.core.orchestrator import (
    call_architect_node,
    call_developer_node,
    call_reviewer_node,
    plan_validator_node,
)
from amelia.drivers.api import ApiDriver
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from tests.integration.conftest import (
    make_agentic_messages,
    make_config,
    make_execution_state,
    make_issue,
    make_profile,
    make_reviewer_agentic_messages,
)


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

    async def test_architect_node_requires_issue(self, tmp_path: Path) -> None:
        """Architect node should raise error if no issue provided."""
        profile = make_profile(working_dir=str(tmp_path))
        state = make_execution_state(issue=None, profile=profile)
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
            plan_markdown="# Plan\n\nCreate hello.txt with content 'Hello World'",
        )
        config = make_config(thread_id="test-wf-2", profile=profile)

        # Mock AgenticMessage stream from the driver's execute_agentic
        mock_messages = make_agentic_messages(
            include_thinking=False,
            final_text="I created hello.txt with the content 'Hello World'",
        )

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
        state = make_execution_state(profile=profile, goal=None)
        config = make_config(thread_id="test-wf-3", profile=profile)

        with pytest.raises(ValueError, match="no goal"):
            await call_developer_node(state, cast(RunnableConfig, config))


@pytest.mark.integration
class TestReviewerNodeIntegration:
    """Test reviewer node with real Reviewer, mock at driver.execute_agentic() level."""

    async def test_reviewer_node_returns_review_result(self, tmp_path: Path) -> None:
        """Reviewer node should return ReviewResult from driver.

        Real components: DriverFactory, ApiDriver, Reviewer
        Mock boundary: ApiDriver.execute_agentic (LLM call)
        """
        profile = make_profile(working_dir=str(tmp_path))
        state = make_execution_state(
            profile=profile,
            goal="Add logging to the application",
            code_changes_for_review="diff --git a/app.py b/app.py\n+import logging",
        )
        config = make_config(thread_id="test-wf-4", profile=profile)

        mock_messages = make_reviewer_agentic_messages(approved=True)

        async def mock_execute_agentic(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages:
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            result = await call_reviewer_node(state, cast(RunnableConfig, config))

        assert result["last_review"] is not None
        assert result["last_review"].approved is True

    async def test_reviewer_node_rejection(self, tmp_path: Path) -> None:
        """Reviewer node should return rejection with feedback.

        Real components: DriverFactory, ApiDriver, Reviewer
        Mock boundary: ApiDriver.execute_agentic (LLM call)
        """
        profile = make_profile(working_dir=str(tmp_path))
        state = make_execution_state(
            profile=profile,
            goal="Implement secure authentication",
            code_changes_for_review="diff --git a/auth.py\n+password = 'hardcoded'",
        )
        config = make_config(thread_id="test-wf-5", profile=profile)

        mock_messages = make_reviewer_agentic_messages(
            approved=False,
            comments=["Hardcoded password found"],
            severity="critical",
        )

        async def mock_execute_agentic(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages:
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            result = await call_reviewer_node(state, cast(RunnableConfig, config))

        assert result["last_review"].approved is False
        assert result["last_review"].severity == "critical"

    async def test_reviewer_node_increments_review_iteration(self, tmp_path: Path) -> None:
        """Reviewer node should increment review_iteration after each review.

        This prevents infinite loops when review is rejected - the iteration
        counter ensures we eventually hit max_review_iterations and terminate.

        Real components: DriverFactory, ApiDriver, Reviewer
        Mock boundary: ApiDriver.execute_agentic (LLM call)
        """
        profile = make_profile(working_dir=str(tmp_path), max_review_iterations=3)
        state = make_execution_state(
            profile=profile,
            goal="Fix the bug",
            code_changes_for_review="diff --git a/fix.py\n+# partial fix",
            review_iteration=0,
        )
        config = make_config(thread_id="test-wf-iteration", profile=profile)

        mock_messages = make_reviewer_agentic_messages(
            approved=False,
            comments=["Still needs work"],
            severity="high",
        )

        async def mock_execute_agentic(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages:
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            result = await call_reviewer_node(state, cast(RunnableConfig, config))

        # Key assertion: review_iteration should be incremented
        assert "review_iteration" in result, "review_iteration must be returned by reviewer node"
        assert result["review_iteration"] == 1, "review_iteration should increment from 0 to 1"

        # Run again with incremented state to verify it keeps incrementing
        state_round2 = state.model_copy(update={"review_iteration": 1})
        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            result2 = await call_reviewer_node(state_round2, cast(RunnableConfig, config))

        assert result2["review_iteration"] == 2, "review_iteration should increment from 1 to 2"

    async def test_reviewer_node_updates_last_review_each_round(self, tmp_path: Path) -> None:
        """Reviewer node should update last_review with new results each round.

        This verifies that the review results are different after developer
        makes changes, preventing the "same review message" infinite loop bug.

        Real components: DriverFactory, ApiDriver, Reviewer
        Mock boundary: ApiDriver.execute_agentic (LLM call)
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
        mock_messages_round1 = make_reviewer_agentic_messages(
            approved=False,
            comments=["Missing error handling", "No tests"],
            severity="high",
        )

        async def mock_execute_round1(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages_round1:
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_round1):
            result1 = await call_reviewer_node(state, cast(RunnableConfig, config))

        assert result1["last_review"].approved is False
        assert result1["last_review"].severity == "high"
        assert len(result1["last_review"].comments) == 2

        # Round 2: Simulate developer fixed one issue, reviewer now returns different result
        state_round2 = state.model_copy(update={
            "review_iteration": 1,
            "code_changes_for_review": "diff --git a/fix.py\n+# with error handling",
        })
        mock_messages_round2 = make_reviewer_agentic_messages(
            approved=False,
            comments=["Still no tests"],
            severity="medium",
        )

        async def mock_execute_round2(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages_round2:
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_round2):
            result2 = await call_reviewer_node(state_round2, cast(RunnableConfig, config))

        # Verify last_review is UPDATED, not stale
        assert result2["last_review"].approved is False
        # Note: severity mapping: "medium" comments go to Minor section, parsed as "medium"
        assert len(result2["last_review"].comments) == 1, "comment count should change"

        # Round 3: All fixed, approved
        state_round3 = state.model_copy(update={
            "review_iteration": 2,
            "code_changes_for_review": "diff --git a/fix.py\n+# with tests",
        })
        mock_messages_round3 = make_reviewer_agentic_messages(approved=True)

        async def mock_execute_round3(*_args: Any, **_kwargs: Any) -> Any:
            for msg in mock_messages_round3:
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_round3):
            result3 = await call_reviewer_node(state_round3, cast(RunnableConfig, config))

        assert result3["last_review"].approved is True, "should be approved in round 3"
        assert result3["review_iteration"] == 3


@pytest.mark.integration
class TestArchitectValidatorFlowIntegration:
    """Test architect → plan_validator flow with real components, mock at driver level."""

    async def test_architect_to_validator_handoff(self, tmp_path: Path) -> None:
        """Verify architect creates plan file and validator extracts structured data.

        Real components: DriverFactory, ApiDriver, Architect, plan_validator_node
        Mock boundary: ApiDriver.execute_agentic (architect), ApiDriver.generate (validator)

        This tests the complete handoff:
        1. architect_node calls LLM, writes plan file via Write tool, returns raw_architect_output
        2. plan_validator_node reads plan file, extracts goal/plan_markdown/key_files
        """
        from amelia.core.constants import resolve_plan_path

        plans_dir = tmp_path / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        profile = make_profile(
            plan_output_dir=str(plans_dir),
            working_dir=str(tmp_path),
        )
        issue = make_issue(
            id="TEST-FLOW-1",
            title="Add user authentication",
            description="Implement JWT-based authentication for the API",
        )
        state = make_execution_state(issue=issue, profile=profile)
        config = make_config(thread_id="test-flow-1", profile=profile)

        # Compute expected plan path
        plan_rel_path = resolve_plan_path(profile.plan_path_pattern, issue.id)
        expected_plan_path = tmp_path / plan_rel_path

        # --- Phase 1: Architect node ---
        # The architect writes the plan content to disk via Write tool
        plan_content = """# Implementation Plan: Add User Authentication

## Goal
Implement JWT-based authentication for the API endpoints.

## Key Files
- `src/auth/jwt.py` - JWT token handling
- `src/api/middleware.py` - Authentication middleware
- `tests/test_auth.py` - Authentication tests

## Tasks

### Task 1: Create JWT utilities
Create the JWT token generation and validation utilities.

### Task 2: Add authentication middleware
Implement middleware to validate tokens on protected routes.

### Task 3: Write tests
Add comprehensive tests for the authentication flow.
"""
        # Mock messages include Write tool call (how architect saves plan in production)
        mock_architect_messages = [
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Analyzing the authentication requirements...",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name=ToolName.WRITE_FILE,
                tool_input={"file_path": str(expected_plan_path), "content": plan_content},
                tool_call_id="write-plan-1",
            ),
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name=ToolName.WRITE_FILE,
                tool_output=f"File written to {expected_plan_path}",
                tool_call_id="write-plan-1",
            ),
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="I've created an implementation plan for adding user authentication.",
                session_id="architect-session-123",
            ),
        ]

        async def mock_execute_agentic(*_args: Any, **_kwargs: Any) -> Any:
            """Mock async generator for architect's execute_agentic.

            Simulates agentic execution with Write tool call. Since we're mocking,
            we manually write the file to simulate what the tool would do.
            """
            for msg in mock_architect_messages:
                # Simulate Write tool execution when we yield the tool result
                if msg.type == AgenticMessageType.TOOL_RESULT and msg.tool_name == ToolName.WRITE_FILE:
                    expected_plan_path.parent.mkdir(parents=True, exist_ok=True)
                    expected_plan_path.write_text(plan_content)
                yield msg

        with patch.object(ApiDriver, "execute_agentic", mock_execute_agentic):
            architect_result = await call_architect_node(state, cast(RunnableConfig, config))

        # Verify architect returns raw output
        assert "raw_architect_output" in architect_result
        # raw_architect_output is the RESULT message content, not the plan itself
        assert "implementation plan" in architect_result["raw_architect_output"].lower()

        # Verify tool calls were recorded
        assert "tool_calls" in architect_result
        assert len(architect_result["tool_calls"]) >= 1
        write_call = architect_result["tool_calls"][0]
        assert write_call.tool_name == ToolName.WRITE_FILE

        # Verify plan file was written to disk (by our mock simulating the Write tool)
        assert expected_plan_path.exists(), f"Plan file should exist at {expected_plan_path}"
        assert expected_plan_path.read_text() == plan_content

        # --- Phase 2: Plan Validator node ---
        # Update state with architect results (simulating graph transition)
        state_after_architect = state.model_copy(
            update={"raw_architect_output": architect_result["raw_architect_output"]}
        )

        # Mock the validator's generate call to extract structured data
        mock_validator_output = MarkdownPlanOutput(
            goal="Implement JWT-based authentication for the API endpoints",
            plan_markdown=plan_content,
            key_files=["src/auth/jwt.py", "src/api/middleware.py", "tests/test_auth.py"],
        )

        with patch.object(ApiDriver, "generate", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = (mock_validator_output, "validator-session-456")
            validator_result = await plan_validator_node(
                state_after_architect, cast(RunnableConfig, config)
            )

        # Verify validator extracts structured fields
        assert "goal" in validator_result
        assert validator_result["goal"] == "Implement JWT-based authentication for the API endpoints"

        assert "plan_markdown" in validator_result
        assert validator_result["plan_markdown"] == plan_content

        assert "key_files" in validator_result
        assert len(validator_result["key_files"]) == 3
        assert "src/auth/jwt.py" in validator_result["key_files"]

        assert "plan_path" in validator_result
        assert validator_result["plan_path"] == expected_plan_path

    async def test_validator_fails_if_plan_file_missing(self, tmp_path: Path) -> None:
        """Validator should raise error if architect didn't write plan file.

        This ensures the validator fails fast if the plan file is missing,
        rather than silently continuing with invalid state.
        """
        plans_dir = tmp_path / "plans"
        # Don't create the directory - simulate architect failure

        profile = make_profile(
            plan_output_dir=str(plans_dir),
            working_dir=str(tmp_path),
        )
        issue = make_issue(id="TEST-MISSING-1")
        state = make_execution_state(
            issue=issue,
            profile=profile,
            raw_architect_output="Some content that wasn't written to disk",
        )
        config = make_config(thread_id="test-missing-1", profile=profile)

        with pytest.raises(ValueError, match="Plan file not found"):
            await plan_validator_node(state, cast(RunnableConfig, config))

    async def test_validator_fails_if_plan_file_empty(self, tmp_path: Path) -> None:
        """Validator should raise error if plan file exists but is empty.

        This catches edge cases where the file was created but write failed.
        """
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)

        profile = make_profile(
            plan_output_dir=str(plans_dir),
            working_dir=str(tmp_path),
        )
        issue = make_issue(id="TEST-EMPTY-1")
        state = make_execution_state(issue=issue, profile=profile)
        config = make_config(thread_id="test-empty-1", profile=profile)

        # Create empty plan file
        from amelia.core.constants import resolve_plan_path

        plan_rel_path = resolve_plan_path(profile.plan_path_pattern, issue.id)
        plan_path = tmp_path / plan_rel_path
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text("")  # Empty file

        with pytest.raises(ValueError, match="Plan file is empty"):
            await plan_validator_node(state, cast(RunnableConfig, config))
