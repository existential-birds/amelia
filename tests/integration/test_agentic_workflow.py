"""Integration tests for agentic workflow.

Tests the LangGraph orchestrator graph structure, ExecutionState fields,
and workflow invocation with real components (mocking only at HTTP/LLM boundary).
"""
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

from amelia.agents.reviewer import ReviewResponse
from amelia.core.orchestrator import (
    call_architect_node,
    call_developer_node,
    call_reviewer_node,
    create_orchestrator_graph,
    route_after_review,
    route_approval,
)
from amelia.core.state import ExecutionState, ReviewResult
from amelia.drivers.api import ApiDriver
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from tests.integration.conftest import make_config, make_execution_state, make_issue, make_profile


@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set API key env var to allow driver construction."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-for-integration-tests")


@pytest.mark.integration
class TestAgenticOrchestrator:
    """Test agentic workflow graph structure."""

    def test_graph_compiles_with_checkpointer(self) -> None:
        """Graph should compile with a checkpointer for persistence."""
        checkpointer = MemorySaver()
        graph = create_orchestrator_graph(checkpoint_saver=checkpointer)

        assert graph is not None
        # Verify interrupt_before is set when checkpointer is provided
        assert graph.interrupt_before_nodes is not None

    def test_graph_compiles_with_custom_interrupt(self) -> None:
        """Graph should compile with custom interrupt_before nodes."""
        checkpointer = MemorySaver()
        graph = create_orchestrator_graph(
            checkpoint_saver=checkpointer,
            interrupt_before=["developer_node"],
        )

        assert "developer_node" in graph.interrupt_before_nodes


@pytest.mark.integration
class TestArchitectNodeIntegration:
    """Test architect node with real Architect, mock at driver.generate() level."""

    async def test_architect_node_sets_goal_and_plan(self, tmp_path: Path) -> None:
        """Architect node should populate goal and plan_markdown.

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
        # The architect now uses agentic execution and yields AgenticMessage events
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

        assert result["goal"] == "Implement feature X by modifying component Y"
        assert result["plan_markdown"] is not None
        assert "Do thing A" in result["plan_markdown"]
        # Verify plan file was created
        assert result["plan_path"] is not None
        assert Path(result["plan_path"]).exists()

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
        from amelia.drivers.base import AgenticMessage, AgenticMessageType

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

        # Mock response at driver.generate level
        mock_llm_response = ReviewResponse(
            approved=True,
            comments=["LGTM! Good use of standard logging module."],
            severity="low",
        )

        # driver.generate returns (output, session_id) tuple
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

        # Mock rejection response at driver.generate level
        mock_llm_response = ReviewResponse(
            approved=False,
            comments=["Critical: Hardcoded password found. Use environment variables or secure vault."],
            severity="critical",
        )

        # driver.generate returns (output, session_id) tuple
        with patch.object(ApiDriver, "generate", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = (mock_llm_response, "session-456")

            result = await call_reviewer_node(state, cast(RunnableConfig, config))

        assert result["last_review"].approved is False
        assert result["last_review"].severity == "critical"


@pytest.mark.integration
class TestWorkflowRouting:
    """Test routing functions for workflow edges."""

    def test_route_approval_approves(self) -> None:
        """route_approval should return 'approve' when human_approved is True."""
        state = ExecutionState(profile_id="test", human_approved=True)
        assert route_approval(state) == "approve"

    def test_route_approval_rejects(self) -> None:
        """route_approval should return 'reject' when human_approved is False."""
        state = ExecutionState(profile_id="test", human_approved=False)
        assert route_approval(state) == "reject"

    def test_route_after_review_ends_on_approval(self) -> None:
        """route_after_review should end workflow when review is approved."""
        profile = make_profile(max_review_iterations=3)
        config = make_config(thread_id="test", profile=profile)
        review = ReviewResult(reviewer_persona="Test", approved=True, comments=[], severity="low")
        state = ExecutionState(profile_id="test", last_review=review)

        result = route_after_review(state, cast(RunnableConfig, config))
        assert result == "__end__"

    def test_route_after_review_loops_on_rejection(self) -> None:
        """route_after_review should loop to developer when review is rejected."""
        profile = make_profile(max_review_iterations=3)
        config = make_config(thread_id="test", profile=profile)
        review = ReviewResult(reviewer_persona="Test", approved=False, comments=["Fix this"], severity="medium")
        state = ExecutionState(profile_id="test", last_review=review, review_iteration=1)

        result = route_after_review(state, cast(RunnableConfig, config))
        assert result == "developer"

    def test_route_after_review_ends_at_max_iterations(self) -> None:
        """route_after_review should end when max iterations reached."""
        profile = make_profile(max_review_iterations=3)
        config = make_config(thread_id="test", profile=profile)
        review = ReviewResult(reviewer_persona="Test", approved=False, comments=["Still wrong"], severity="high")
        state = ExecutionState(profile_id="test", last_review=review, review_iteration=3)

        result = route_after_review(state, cast(RunnableConfig, config))
        assert result == "__end__"


@pytest.mark.integration
class TestDeveloperReviewerLoop:
    """Test the developer ↔ reviewer loop integration."""

    async def test_reviewer_rejection_triggers_developer_with_feedback(self, tmp_path: Path) -> None:
        """When reviewer rejects, developer should receive feedback on next iteration."""
        profile = make_profile(working_dir=str(tmp_path), max_review_iterations=3)

        # First iteration: developer makes a change
        initial_state = make_execution_state(
            profile=profile,
            goal="Add error handling",
            review_iteration=0,
        )

        # Simulate reviewer rejection
        review = ReviewResult(
            reviewer_persona="General",
            approved=False,
            comments=["Add try/except blocks", "Log errors properly"],
            severity="medium",
        )

        # State after review
        state_after_review = initial_state.model_copy(update={
            "last_review": review,
            "review_iteration": 1,
        })

        # Verify state has feedback for next developer iteration
        assert state_after_review.last_review is not None
        assert state_after_review.last_review.approved is False
        assert len(state_after_review.last_review.comments) == 2
        assert state_after_review.review_iteration == 1

        # route_after_review should send back to developer
        config = make_config(thread_id="test", profile=profile)
        next_node = route_after_review(state_after_review, cast(RunnableConfig, config))
        assert next_node == "developer"
