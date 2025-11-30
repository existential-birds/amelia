"""Tests for architect node in orchestrator."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from amelia.core.orchestrator import call_architect_node


class TestCallArchitectNode:
    """Tests for call_architect_node function."""

    @pytest.mark.asyncio
    async def test_passes_profile_plan_output_dir_to_architect(
        self, mock_execution_state_factory, mock_profile_factory, mock_task_dag_factory
    ):
        """call_architect_node should pass profile.plan_output_dir to Architect.plan."""
        custom_output_dir = "custom/plans/output"
        profile = mock_profile_factory(plan_output_dir=custom_output_dir)
        state = mock_execution_state_factory(profile=profile)

        mock_plan_output = MagicMock()
        mock_plan_output.task_dag = mock_task_dag_factory()

        with patch("amelia.core.orchestrator.DriverFactory"), \
             patch("amelia.core.orchestrator.Architect") as MockArchitect:
            mock_architect_instance = AsyncMock()
            mock_architect_instance.plan = AsyncMock(return_value=mock_plan_output)
            MockArchitect.return_value = mock_architect_instance

            await call_architect_node(state)

            # Verify plan was called with the profile's output_dir
            mock_architect_instance.plan.assert_called_once()
            call_kwargs = mock_architect_instance.plan.call_args
            assert call_kwargs.kwargs.get("output_dir") == custom_output_dir
