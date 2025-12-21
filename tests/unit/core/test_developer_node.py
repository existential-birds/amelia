# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for call_developer_node using profile from config."""

import pytest


class TestDeveloperNodeProfileFromConfig:
    """Tests for call_developer_node using profile from config."""

    async def test_developer_node_uses_profile_from_config(
        self,
        mock_profile_factory,
        mock_issue_factory,
        mock_execution_plan_factory,
    ) -> None:
        """call_developer_node should get profile from config, not state."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from langchain_core.runnables.config import RunnableConfig

        from amelia.core.orchestrator import call_developer_node
        from amelia.core.state import ExecutionState

        profile = mock_profile_factory()
        issue = mock_issue_factory()
        execution_plan = mock_execution_plan_factory()

        # State has profile_id, not profile object
        state = ExecutionState(
            profile_id=profile.name,
            issue=issue,
            execution_plan=execution_plan,
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
            mock_dev_instance.run = AsyncMock(return_value={})
            mock_dev.return_value = mock_dev_instance

            # Should not raise, should use profile from config
            await call_developer_node(state, config)

            # Verify Developer was created with profile from config
            mock_dev.assert_called_once()
            # Verify run was called
            mock_dev_instance.run.assert_called_once()
