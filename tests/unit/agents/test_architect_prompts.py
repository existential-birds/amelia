"""Tests for Architect agent prompt injection."""
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from amelia.agents.architect import Architect, MarkdownPlanOutput
from amelia.core.types import AgentConfig, Profile
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.implementation.state import ImplementationState


class TestArchitectPromptInjection:
    """Tests for Architect agent prompt injection."""

    @pytest.fixture
    def plan_output(self) -> MarkdownPlanOutput:
        """Sample plan output from driver."""
        return MarkdownPlanOutput(
            goal="Test goal",
            plan_markdown="# Test Plan",
            key_files=["test.py"],
        )

    async def test_uses_injected_plan_prompt(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
        plan_output: MarkdownPlanOutput,
    ) -> None:
        """Should use injected plan prompt for plan method.

        The architect.plan() now uses execute_agentic which takes instructions parameter.
        """
        custom_plan_prompt = "Custom plan format..."
        prompts = {"architect.plan": custom_plan_prompt}
        config = AgentConfig(driver="cli", model="sonnet")

        state, profile = mock_execution_state_factory()

        # Mock execute_agentic as async generator
        captured_instructions: list[str | None] = []
        mock_messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="**Goal:** Test goal\n\n# Test Plan",
                session_id="session-1",
            ),
        ]

        async def mock_execute_agentic(*args: Any, **kwargs: Any) -> Any:
            captured_instructions.append(kwargs.get("instructions"))
            for msg in mock_messages:
                yield msg

        mock_driver.execute_agentic = mock_execute_agentic

        with patch("amelia.agents.architect.get_driver", return_value=mock_driver):
            architect = Architect(config, prompts=prompts)
            async for _ in architect.plan(state, profile, workflow_id="wf-1"):
                pass

        assert len(captured_instructions) == 1
        assert captured_instructions[0] == custom_plan_prompt

    async def test_falls_back_to_class_default_for_plan(
        self,
        mock_driver: MagicMock,
        mock_execution_state_factory: Callable[..., tuple[ImplementationState, Profile]],
        plan_output: MarkdownPlanOutput,
    ) -> None:
        """Should use class default when plan prompt not injected.

        The architect.plan() now uses execute_agentic which takes instructions parameter.
        """
        config = AgentConfig(driver="cli", model="sonnet")
        state, profile = mock_execution_state_factory()

        # Mock execute_agentic as async generator
        captured_instructions: list[str | None] = []
        mock_messages = [
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content="**Goal:** Test goal\n\n# Test Plan",
                session_id="session-1",
            ),
        ]

        async def mock_execute_agentic(*args: Any, **kwargs: Any) -> Any:
            captured_instructions.append(kwargs.get("instructions"))
            for msg in mock_messages:
                yield msg

        mock_driver.execute_agentic = mock_execute_agentic

        with patch("amelia.agents.architect.get_driver", return_value=mock_driver):
            architect = Architect(config)  # No prompts injected
            async for _ in architect.plan(state, profile, workflow_id="wf-1"):
                pass

        # Verify a non-empty default plan prompt is used
        assert len(captured_instructions) == 1
        instructions = captured_instructions[0]
        assert instructions is not None
        assert len(instructions) > 50

    async def test_plan_prompt_property(
        self,
        mock_driver: MagicMock,
    ) -> None:
        """Test plan_prompt property returns correct value."""
        custom_prompt = "Custom plan prompt"
        config = AgentConfig(driver="cli", model="sonnet")

        with patch("amelia.agents.architect.get_driver", return_value=mock_driver):
            # With custom prompt
            architect_custom = Architect(config, prompts={"architect.plan": custom_prompt})
            assert architect_custom.plan_prompt == custom_prompt

            # Without custom prompt (default)
            architect_default = Architect(config)
            assert architect_default.plan_prompt
            assert len(architect_default.plan_prompt) > 50
