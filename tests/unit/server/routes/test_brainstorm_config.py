"""Tests for brainstorm routes using per-agent driver configuration.

These tests verify that brainstorm routes correctly use profile.get_agent_config('brainstormer')
to get driver configuration instead of the old profile.driver/profile.model fields.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import AgentConfig, Profile


class TestBrainstormDriverConfig:
    """Test that brainstorm routes use profile.get_agent_config('brainstormer')."""

    @pytest.mark.asyncio
    async def test_get_brainstorm_driver_uses_brainstormer_agent_config(self) -> None:
        """get_brainstorm_driver should use profile.get_agent_config('brainstormer')."""
        # Create profile with brainstormer agent config
        profile = Profile(
            name="test",
            tracker="none",
            working_dir="/tmp/test",
            agents={
                "brainstormer": AgentConfig(driver="cli", model="sonnet"),
            },
        )

        # Mock the profile repository to return our profile
        mock_profile_repo = MagicMock()
        mock_profile_repo.get_active_profile = AsyncMock(return_value=profile)

        # Mock the driver factory
        mock_driver = MagicMock()

        with (
            patch(
                "amelia.server.main.get_profile_repository",
                return_value=mock_profile_repo,
            ),
            patch(
                "amelia.server.main.factory_get_driver",
                return_value=mock_driver,
            ) as mock_factory,
        ):
            # Import create_app and extract the dependency override
            from amelia.server.main import create_app

            app = create_app()

            # Get the dependency override for get_driver
            from amelia.server.routes.brainstorm import get_driver

            get_brainstorm_driver = app.dependency_overrides[get_driver]

            # Call the dependency override
            result = await get_brainstorm_driver()

            # Verify factory_get_driver was called with brainstormer config
            mock_factory.assert_called_once_with("cli", model="sonnet")
            assert result is mock_driver

    @pytest.mark.asyncio
    async def test_get_brainstorm_driver_fallback_without_active_profile(self) -> None:
        """get_brainstorm_driver should fallback to cli when no active profile."""
        # Mock the profile repository to return None (no active profile)
        mock_profile_repo = MagicMock()
        mock_profile_repo.get_active_profile = AsyncMock(return_value=None)

        mock_driver = MagicMock()

        with (
            patch(
                "amelia.server.main.get_profile_repository",
                return_value=mock_profile_repo,
            ),
            patch(
                "amelia.server.main.factory_get_driver",
                return_value=mock_driver,
            ) as mock_factory,
        ):
            from amelia.server.main import create_app

            app = create_app()

            from amelia.server.routes.brainstorm import get_driver

            get_brainstorm_driver = app.dependency_overrides[get_driver]

            result = await get_brainstorm_driver()

            # Should fallback to cli without model
            mock_factory.assert_called_once_with("cli")
            assert result is mock_driver


class TestProfileInfoWithAgentConfig:
    """Test that ProfileInfo is correctly populated from new Profile structure."""

    @pytest.mark.asyncio
    async def test_get_profile_info_uses_brainstormer_config(self) -> None:
        """get_profile_info should use brainstormer agent config for driver/model."""
        from amelia.server.routes.brainstorm import get_profile_info

        profile = Profile(
            name="test",
            tracker="none",
            working_dir="/tmp/test",
            agents={
                "brainstormer": AgentConfig(driver="api", model="gpt-4o"),
            },
        )

        mock_profile_repo = MagicMock()
        mock_profile_repo.get_profile = AsyncMock(return_value=profile)

        result = await get_profile_info("test", mock_profile_repo)

        assert result is not None
        assert result.name == "test"
        assert result.driver == "api"
        assert result.model == "gpt-4o"
