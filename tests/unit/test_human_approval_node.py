"""Tests for human_approval_node execution mode behavior."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from amelia.core.types import AgentConfig, Profile
from amelia.pipelines.implementation.nodes import human_approval_node
from amelia.pipelines.implementation.state import ImplementationState


@pytest.fixture
def base_state():
    """Create a base ImplementationState for testing."""
    profile = Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "architect": AgentConfig(driver="cli", model="sonnet"),
            "developer": AgentConfig(driver="cli", model="sonnet"),
            "reviewer": AgentConfig(driver="cli", model="sonnet"),
        },
    )
    return ImplementationState(
        workflow_id="wf-test-123",
        created_at=datetime.now(UTC),
        status="running",
        profile_id=profile.name,
        human_approved=None,
    )


class TestHumanApprovalNodeServerMode:
    """Test human_approval_node in server mode."""

    async def test_server_mode_returns_state_unchanged_when_not_approved(
        self, base_state
    ) -> None:
        """In server mode, node returns empty dict (interrupt handles pause)."""
        config = {"configurable": {"execution_mode": "server"}}
        result = await human_approval_node(base_state, config)
        # Should return empty dict - interrupt mechanism handles the pause
        assert result == {}

    async def test_server_mode_preserves_approval_from_resume(self, base_state) -> None:
        """In server mode, node returns empty dict (approval preserved by state)."""
        state = base_state.model_copy(update={"human_approved": True})
        config = {"configurable": {"execution_mode": "server"}}
        result = await human_approval_node(state, config)
        # Should return empty dict - human_approved is already in state
        assert result == {}


class TestHumanApprovalNodeCLIMode:
    """Test human_approval_node in CLI mode."""

    @patch("amelia.pipelines.implementation.nodes.typer.confirm")
    @patch("amelia.pipelines.implementation.nodes.typer.prompt")
    @patch("amelia.pipelines.implementation.nodes.typer.secho")
    @patch("amelia.pipelines.implementation.nodes.typer.echo")
    async def test_cli_mode_prompts_user(
        self, mock_echo, mock_secho, mock_prompt, mock_confirm, base_state
    ) -> None:
        """In CLI mode, node prompts user for approval."""
        mock_confirm.return_value = True
        mock_prompt.return_value = ""
        config = {"configurable": {"execution_mode": "cli"}}

        result = await human_approval_node(base_state, config)

        mock_confirm.assert_called_once()
        assert result["human_approved"] is True
        assert result.get("human_feedback") is None

    @patch("amelia.pipelines.implementation.nodes.typer.confirm")
    @patch("amelia.pipelines.implementation.nodes.typer.prompt")
    @patch("amelia.pipelines.implementation.nodes.typer.secho")
    @patch("amelia.pipelines.implementation.nodes.typer.echo")
    async def test_cli_mode_default_when_no_config(
        self, mock_echo, mock_secho, mock_prompt, mock_confirm, base_state
    ) -> None:
        """CLI mode is default when no execution_mode in config."""
        mock_confirm.return_value = False
        mock_prompt.return_value = "rejected"
        config = {}  # No execution_mode

        result = await human_approval_node(base_state, config)

        mock_confirm.assert_called_once()
        assert result["human_approved"] is False
        assert result["human_feedback"] == "rejected"
