"""Tests for call_developer_node using profile from config."""



class TestDeveloperNodeProfileFromConfig:
    """Tests for call_developer_node using profile from config."""

    async def test_developer_node_uses_profile_from_config(
        self,
        mock_profile_factory,
        mock_issue_factory,
    ) -> None:
        """call_developer_node should get profile from config, not state."""
        from unittest.mock import MagicMock, patch

        from langchain_core.runnables.config import RunnableConfig

        from amelia.core.orchestrator import call_developer_node
        from amelia.core.state import ExecutionState

        profile = mock_profile_factory()
        issue = mock_issue_factory()

        # State has profile_id, not profile object
        # Uses goal and plan_markdown instead of execution_plan
        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            goal="Test goal",
            plan_markdown="# Test Plan\n\n## Phase 1\n\n### Task 1.1\n\nTest step",
        )

        # Profile is in config
        config: RunnableConfig = {
            "configurable": {
                "thread_id": "wf-test",
                "profile": profile,
            }
        }

        # Mock the Developer to avoid actual execution
        with patch("amelia.core.orchestrator.Developer") as mock_dev:
            mock_dev_instance = MagicMock()
            # Developer.run is now an async generator
            async def mock_run(*args, **kwargs):
                yield state, MagicMock(type="thinking", content="test")
            mock_dev_instance.run = mock_run
            mock_dev.return_value = mock_dev_instance

            # Should not raise, should use profile from config
            await call_developer_node(state, config)

            # Verify Developer was created with profile from config
            mock_dev.assert_called_once()
