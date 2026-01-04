"""Tests for token usage extraction from orchestrator agent nodes.

These tests verify that token usage data is correctly extracted from
ResultMessage and saved via the repository when agents complete execution.

The token usage extraction works by:
1. Driver stores last_result_message after each execution
2. Agent stores reference to driver's last_result_message
3. Orchestrator extracts usage from agent after execution
4. Repository saves token usage (if repository is in config)
"""
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig

from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile
from amelia.server.models.tokens import TokenUsage


class TestTokenUsageExtraction:
    """Tests for token usage extraction from agent nodes."""

    @pytest.fixture
    def mock_result_message_with_usage(self) -> MagicMock:
        """Create a mock ResultMessage with usage data."""
        result = MagicMock()
        result.session_id = "session-123"
        result.result = "Execution complete"
        result.is_error = False
        result.duration_ms = 5000
        result.num_turns = 3
        result.total_cost_usd = 0.025
        result.usage = {
            "model": "claude-sonnet-4-20250514",
            "input_tokens": 1500,
            "output_tokens": 500,
            "cache_read_input_tokens": 1000,
            "cache_creation_input_tokens": 200,
        }
        return result

    @pytest.fixture
    def mock_result_message_no_usage(self) -> MagicMock:
        """Create a mock ResultMessage without usage data."""
        result = MagicMock()
        result.session_id = "session-456"
        result.result = "Execution complete"
        result.is_error = False
        result.duration_ms = 3000
        result.num_turns = 2
        result.total_cost_usd = None
        result.usage = None
        return result

    @pytest.fixture
    def base_config(
        self,
        mock_profile_factory: Callable[..., Profile],
    ) -> RunnableConfig:
        """Create base config with required configurable parameters."""
        profile = mock_profile_factory()
        return {
            "configurable": {
                "thread_id": "wf-test-123",
                "profile": profile,
            }
        }

    @pytest.fixture
    def config_with_repository(
        self,
        base_config: RunnableConfig,
    ) -> tuple[RunnableConfig, AsyncMock]:
        """Create config with a mock repository."""
        mock_repository = AsyncMock()
        mock_repository.save_token_usage = AsyncMock()
        base_config["configurable"]["repository"] = mock_repository
        return base_config, mock_repository


class TestDeveloperNodeTokenUsage(TestTokenUsageExtraction):
    """Tests for token usage extraction in call_developer_node."""

    async def test_developer_node_extracts_token_usage_from_driver(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
        mock_result_message_with_usage: MagicMock,
        config_with_repository: tuple[RunnableConfig, AsyncMock],
    ) -> None:
        """call_developer_node should extract usage from driver and save it."""
        from amelia.core.orchestrator import call_developer_node

        profile = config_with_repository[0]["configurable"]["profile"]
        mock_repository = config_with_repository[1]
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Implement test feature",
            plan_markdown="# Test Plan\n\nImplement feature X",
        )

        # Mock Developer.run to yield events
        async def mock_run(
            *args: Any, **kwargs: Any
        ) -> AsyncGenerator[tuple[ExecutionState, MagicMock], None]:
            final_state = state.model_copy(update={
                "agentic_status": "completed",
                "final_response": "Done",
            })
            mock_event = MagicMock()
            mock_event.type = "output"
            yield final_state, mock_event

        with patch("amelia.core.orchestrator.Developer") as mock_dev_class, \
             patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_dev_instance = MagicMock()
            mock_dev_instance.run = mock_run
            mock_dev_class.return_value = mock_dev_instance

            # Driver stores last_result_message with usage data
            mock_driver = MagicMock()
            mock_driver.last_result_message = mock_result_message_with_usage
            mock_factory.get_driver.return_value = mock_driver

            await call_developer_node(state, config_with_repository[0])

            # Verify save_token_usage was called with correct data
            mock_repository.save_token_usage.assert_called_once()
            saved_usage = mock_repository.save_token_usage.call_args[0][0]

            assert isinstance(saved_usage, TokenUsage)
            assert saved_usage.workflow_id == "wf-test-123"
            assert saved_usage.agent == "developer"
            assert saved_usage.model == "claude-sonnet-4-20250514"
            assert saved_usage.input_tokens == 1500
            assert saved_usage.output_tokens == 500
            assert saved_usage.cache_read_tokens == 1000
            assert saved_usage.cache_creation_tokens == 200
            assert saved_usage.cost_usd == 0.025
            assert saved_usage.duration_ms == 5000
            assert saved_usage.num_turns == 3

    async def test_developer_node_skips_save_when_no_usage(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
        mock_result_message_no_usage: MagicMock,
        config_with_repository: tuple[RunnableConfig, AsyncMock],
    ) -> None:
        """call_developer_node should not call save when no usage data."""
        from amelia.core.orchestrator import call_developer_node

        profile = config_with_repository[0]["configurable"]["profile"]
        mock_repository = config_with_repository[1]
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Implement test feature",
            plan_markdown="# Test Plan",
        )

        async def mock_run(
            *args: Any, **kwargs: Any
        ) -> AsyncGenerator[tuple[ExecutionState, MagicMock], None]:
            final_state = state.model_copy(update={
                "agentic_status": "completed",
            })
            mock_event = MagicMock()
            yield final_state, mock_event

        with patch("amelia.core.orchestrator.Developer") as mock_dev_class, \
             patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_dev_instance = MagicMock()
            mock_dev_instance.run = mock_run
            mock_dev_class.return_value = mock_dev_instance

            mock_driver = MagicMock()
            mock_driver.last_result_message = mock_result_message_no_usage
            mock_factory.get_driver.return_value = mock_driver

            await call_developer_node(state, config_with_repository[0])

            # Verify save_token_usage was NOT called
            mock_repository.save_token_usage.assert_not_called()

    async def test_developer_node_works_without_repository(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
        mock_result_message_with_usage: MagicMock,
        base_config: RunnableConfig,
    ) -> None:
        """call_developer_node should work when repository is not in config."""
        from amelia.core.orchestrator import call_developer_node

        profile = base_config["configurable"]["profile"]
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test goal",
            plan_markdown="# Plan",
        )

        async def mock_run(
            *args: Any, **kwargs: Any
        ) -> AsyncGenerator[tuple[ExecutionState, MagicMock], None]:
            final_state = state.model_copy(update={"agentic_status": "completed"})
            mock_event = MagicMock()
            yield final_state, mock_event

        with patch("amelia.core.orchestrator.Developer") as mock_dev_class, \
             patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_dev_instance = MagicMock()
            mock_dev_instance.run = mock_run
            mock_dev_class.return_value = mock_dev_instance

            mock_driver = MagicMock()
            mock_driver.last_result_message = mock_result_message_with_usage
            mock_factory.get_driver.return_value = mock_driver

            # Should not raise even without repository
            result = await call_developer_node(state, base_config)
            assert result is not None


class TestReviewerNodeTokenUsage(TestTokenUsageExtraction):
    """Tests for token usage extraction in call_reviewer_node."""

    async def test_reviewer_node_extracts_token_usage(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
        mock_result_message_with_usage: MagicMock,
        config_with_repository: tuple[RunnableConfig, AsyncMock],
    ) -> None:
        """call_reviewer_node should extract usage from driver and save it."""
        from amelia.core.orchestrator import call_reviewer_node
        from amelia.core.state import ReviewResult

        profile = config_with_repository[0]["configurable"]["profile"]
        mock_repository = config_with_repository[1]
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Review test feature",
            base_commit="abc123",
        )

        mock_review_result = ReviewResult(
            reviewer_persona="General",
            approved=True,
            comments=["Looks good"],
            severity="low",
        )

        with patch("amelia.core.orchestrator.Reviewer") as mock_reviewer_class, \
             patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_reviewer_instance = MagicMock()
            mock_reviewer_instance.agentic_review = AsyncMock(
                return_value=(mock_review_result, "session-abc")
            )
            mock_reviewer_class.return_value = mock_reviewer_instance

            mock_driver = MagicMock()
            mock_driver.last_result_message = mock_result_message_with_usage
            mock_factory.get_driver.return_value = mock_driver

            await call_reviewer_node(state, config_with_repository[0])

            # Verify save_token_usage was called
            mock_repository.save_token_usage.assert_called_once()
            saved_usage = mock_repository.save_token_usage.call_args[0][0]

            assert saved_usage.agent == "reviewer"
            assert saved_usage.input_tokens == 1500
            assert saved_usage.cost_usd == 0.025


class TestArchitectNodeTokenUsage(TestTokenUsageExtraction):
    """Tests for token usage extraction in call_architect_node."""

    async def test_architect_node_extracts_token_usage(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
        mock_result_message_with_usage: MagicMock,
        config_with_repository: tuple[RunnableConfig, AsyncMock],
    ) -> None:
        """call_architect_node should extract usage from driver and save it."""
        from datetime import UTC, datetime

        from amelia.core.orchestrator import call_architect_node
        from amelia.core.types import StreamEvent, StreamEventType

        profile = config_with_repository[0]["configurable"]["profile"]
        mock_repository = config_with_repository[1]
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
        )

        # The architect.plan() now yields (ExecutionState, StreamEvent) tuples
        mock_final_state = state.model_copy(update={
            "raw_architect_output": "**Goal:** Implement feature X\n\n# Plan\n\nStep 1...",
            "plan_path": Path("/docs/plans/test.md"),
            "tool_calls": [],
            "tool_results": [],
        })
        mock_event = StreamEvent(
            type=StreamEventType.AGENT_OUTPUT,
            content="Plan generated",
            timestamp=datetime.now(UTC),
            agent="architect",
            workflow_id="wf-test-123",
        )

        async def mock_plan_generator(*args, **kwargs):
            """Mock async generator that yields (state, event) tuples."""
            yield (mock_final_state, mock_event)

        with patch("amelia.core.orchestrator.Architect") as mock_architect_class, \
             patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_architect_instance = MagicMock()
            mock_architect_instance.plan = mock_plan_generator
            mock_architect_class.return_value = mock_architect_instance

            mock_driver = MagicMock()
            mock_driver.last_result_message = mock_result_message_with_usage
            mock_factory.get_driver.return_value = mock_driver

            await call_architect_node(state, config_with_repository[0])

            # Verify save_token_usage was called
            mock_repository.save_token_usage.assert_called_once()
            saved_usage = mock_repository.save_token_usage.call_args[0][0]

            assert saved_usage.agent == "architect"
            assert saved_usage.workflow_id == "wf-test-123"


class TestTokenUsageEdgeCases(TestTokenUsageExtraction):
    """Edge case tests for token usage extraction."""

    async def test_handles_partial_usage_data(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
        config_with_repository: tuple[RunnableConfig, AsyncMock],
    ) -> None:
        """Should handle ResultMessage with partial usage data."""
        from amelia.core.orchestrator import call_developer_node

        profile = config_with_repository[0]["configurable"]["profile"]
        mock_repository = config_with_repository[1]
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test",
            plan_markdown="# Plan",
        )

        # Create result with minimal usage data
        partial_result = MagicMock()
        partial_result.session_id = "session-partial"
        partial_result.is_error = False
        partial_result.duration_ms = 1000
        partial_result.num_turns = 1
        partial_result.total_cost_usd = 0.01
        partial_result.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            # Missing model, cache tokens
        }

        async def mock_run(
            *args: Any, **kwargs: Any
        ) -> AsyncGenerator[tuple[ExecutionState, MagicMock], None]:
            final_state = state.model_copy(update={"agentic_status": "completed"})
            mock_event = MagicMock()
            yield final_state, mock_event

        with patch("amelia.core.orchestrator.Developer") as mock_dev_class, \
             patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_dev_instance = MagicMock()
            mock_dev_instance.run = mock_run
            mock_dev_class.return_value = mock_dev_instance

            mock_driver = MagicMock()
            mock_driver.model = "sonnet"  # Driver has model attribute
            mock_driver.last_result_message = partial_result
            mock_factory.get_driver.return_value = mock_driver

            await call_developer_node(state, config_with_repository[0])

            # Should still save with defaults for missing fields
            mock_repository.save_token_usage.assert_called_once()
            saved_usage = mock_repository.save_token_usage.call_args[0][0]

            assert saved_usage.input_tokens == 100
            assert saved_usage.output_tokens == 50
            assert saved_usage.model == "sonnet"  # Falls back to driver.model
            assert saved_usage.cache_read_tokens == 0  # Default
            assert saved_usage.cache_creation_tokens == 0  # Default

    async def test_handles_missing_model_in_both_usage_and_driver(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
        config_with_repository: tuple[RunnableConfig, AsyncMock],
    ) -> None:
        """Should use 'unknown' when model is missing from both usage and driver."""
        from amelia.core.orchestrator import call_developer_node

        profile = config_with_repository[0]["configurable"]["profile"]
        mock_repository = config_with_repository[1]
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test",
            plan_markdown="# Plan",
        )

        # Create result with usage data missing model
        partial_result = MagicMock()
        partial_result.session_id = "session-no-model"
        partial_result.is_error = False
        partial_result.duration_ms = 1000
        partial_result.num_turns = 1
        partial_result.total_cost_usd = 0.01
        partial_result.usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            # Missing model
        }

        async def mock_run(
            *args: Any, **kwargs: Any
        ) -> AsyncGenerator[tuple[ExecutionState, MagicMock], None]:
            final_state = state.model_copy(update={"agentic_status": "completed"})
            mock_event = MagicMock()
            yield final_state, mock_event

        with patch("amelia.core.orchestrator.Developer") as mock_dev_class, \
             patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_dev_instance = MagicMock()
            mock_dev_instance.run = mock_run
            mock_dev_class.return_value = mock_dev_instance

            # Driver without model attribute (using spec to limit attributes)
            mock_driver = MagicMock(spec=["last_result_message", "generate"])
            mock_driver.last_result_message = partial_result
            mock_factory.get_driver.return_value = mock_driver

            await call_developer_node(state, config_with_repository[0])

            # Should save with "unknown" as last-resort default
            mock_repository.save_token_usage.assert_called_once()
            saved_usage = mock_repository.save_token_usage.call_args[0][0]

            assert saved_usage.model == "unknown"  # Final fallback

    async def test_handles_repository_save_error_gracefully(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
        mock_result_message_with_usage: MagicMock,
        config_with_repository: tuple[RunnableConfig, AsyncMock],
    ) -> None:
        """Should log error but not fail workflow when repository save fails."""
        from amelia.core.orchestrator import call_developer_node

        profile = config_with_repository[0]["configurable"]["profile"]
        mock_repository = config_with_repository[1]
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test",
            plan_markdown="# Plan",
        )

        # Make repository raise an error
        mock_repository.save_token_usage.side_effect = Exception("DB error")

        async def mock_run(
            *args: Any, **kwargs: Any
        ) -> AsyncGenerator[tuple[ExecutionState, MagicMock], None]:
            final_state = state.model_copy(update={"agentic_status": "completed"})
            mock_event = MagicMock()
            yield final_state, mock_event

        with patch("amelia.core.orchestrator.Developer") as mock_dev_class, \
             patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_dev_instance = MagicMock()
            mock_dev_instance.run = mock_run
            mock_dev_class.return_value = mock_dev_instance

            mock_driver = MagicMock()
            mock_driver.last_result_message = mock_result_message_with_usage
            mock_factory.get_driver.return_value = mock_driver

            # Should NOT raise - token usage is best-effort
            result = await call_developer_node(state, config_with_repository[0])
            assert result is not None  # Workflow should still complete

    async def test_handles_driver_without_last_result_message(
        self,
        mock_profile_factory: Callable[..., Profile],
        mock_issue_factory: Callable[..., Issue],
        config_with_repository: tuple[RunnableConfig, AsyncMock],
    ) -> None:
        """Should handle gracefully when driver has no last_result_message attr."""
        from amelia.core.orchestrator import call_developer_node

        profile = config_with_repository[0]["configurable"]["profile"]
        mock_repository = config_with_repository[1]
        issue = mock_issue_factory()

        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test",
            plan_markdown="# Plan",
        )

        async def mock_run(
            *args: Any, **kwargs: Any
        ) -> AsyncGenerator[tuple[ExecutionState, MagicMock], None]:
            final_state = state.model_copy(update={"agentic_status": "completed"})
            mock_event = MagicMock()
            yield final_state, mock_event

        with patch("amelia.core.orchestrator.Developer") as mock_dev_class, \
             patch("amelia.core.orchestrator.DriverFactory") as mock_factory:
            mock_dev_instance = MagicMock()
            mock_dev_instance.run = mock_run
            mock_dev_class.return_value = mock_dev_instance

            # Driver without last_result_message (e.g., API driver)
            mock_driver = MagicMock(spec=["generate"])
            mock_factory.get_driver.return_value = mock_driver

            # Should not raise
            result = await call_developer_node(state, config_with_repository[0])
            assert result is not None
            # Should NOT attempt to save usage
            mock_repository.save_token_usage.assert_not_called()
