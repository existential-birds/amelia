"""Unit tests for the driver factory."""
from unittest.mock import MagicMock, patch

import pytest

from amelia.core.types import SandboxConfig
from amelia.drivers.factory import cleanup_driver_session, get_driver


class TestGetDriverExistingBehavior:
    """Existing behavior must be preserved with the new signature."""

    def test_cli_driver(self) -> None:
        with patch("amelia.drivers.factory.ClaudeCliDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            _driver = get_driver("cli", model="sonnet")
            mock_cls.assert_called_once()
            kwargs = mock_cls.call_args.kwargs
            assert kwargs["model"] == "sonnet"
            assert kwargs.get("cwd") is None
            assert set(kwargs).issubset({"model", "cwd"})

    def test_api_driver(self) -> None:
        with patch("amelia.drivers.factory.ApiDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            _driver = get_driver("api", model="test-model")
            mock_cls.assert_called_once_with(provider="openrouter", model="test-model")

    def test_unknown_driver_raises(self) -> None:
        with pytest.raises(ValueError, match=r"Unknown driver key: 'unknown'\."):
            get_driver("unknown")


class TestGetDriverContainerBranch:
    """Container sandbox driver creation."""

    def test_container_mode_returns_container_driver(self) -> None:
        sandbox = SandboxConfig(mode="container", image="test:latest")
        with patch("amelia.sandbox.docker.DockerSandboxProvider") as mock_provider_cls, \
             patch("amelia.sandbox.driver.ContainerDriver") as mock_driver_cls:
            mock_driver_cls.return_value = MagicMock()
            _driver = get_driver(
                "api", model="test-model",
                sandbox_config=sandbox, profile_name="work",
            )
            mock_provider_cls.assert_called_once_with(
                profile_name="work",
                image="test:latest",
                network_allowlist_enabled=False,
                network_allowed_hosts=sandbox.network_allowed_hosts,
            )
            mock_driver_cls.assert_called_once_with(
                model="test-model",
                provider=mock_provider_cls.return_value,
            )

    def test_container_mode_cli_raises(self) -> None:
        sandbox = SandboxConfig(mode="container")
        with pytest.raises(ValueError, match="Container sandbox requires API driver"):
            get_driver("cli", sandbox_config=sandbox, profile_name="test")

    def test_container_mode_cli_colon_raises(self) -> None:
        sandbox = SandboxConfig(mode="container")
        with pytest.raises(ValueError, match="Container sandbox requires API driver"):
            get_driver("cli:claude", sandbox_config=sandbox, profile_name="test")

    def test_none_mode_returns_normal_driver(self) -> None:
        sandbox = SandboxConfig(mode="none")
        with patch("amelia.drivers.factory.ApiDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            _driver = get_driver("api", model="test-model", sandbox_config=sandbox)
            mock_cls.assert_called_once_with(provider="openrouter", model="test-model")

    def test_no_sandbox_config_returns_normal_driver(self) -> None:
        with patch("amelia.drivers.factory.ApiDriver") as mock_cls:
            mock_cls.return_value = MagicMock()
            _driver = get_driver("api", model="test-model")
            mock_cls.assert_called_once_with(provider="openrouter", model="test-model")


class TestLegacyDriverRejection:
    """Legacy driver forms should be rejected with clear errors."""

    def test_legacy_cli_driver_rejected(self) -> None:
        """Legacy cli:claude driver form should raise clear error."""
        with pytest.raises(
            ValueError,
            match=r"Unknown driver key: 'cli:claude'.*Legacy forms.*no longer supported",
        ):
            get_driver("cli:claude", model="test-model")

    def test_legacy_api_driver_rejected(self) -> None:
        """Legacy api:openrouter driver form should raise clear error."""
        with pytest.raises(
            ValueError,
            match=r"Unknown driver key: 'api:openrouter'.*Legacy forms.*no longer supported",
        ):
            get_driver("api:openrouter", model="test-model")

    @pytest.mark.asyncio
    async def test_legacy_cleanup_driver_rejected(self) -> None:
        """Legacy driver values should be rejected in cleanup."""
        with pytest.raises(
            ValueError,
            match=r"Unknown driver key: 'cli:claude'",
        ):
            await cleanup_driver_session("cli:claude", "test-session-id")

        with pytest.raises(
            ValueError,
            match=r"Unknown driver key: 'api:openrouter'",
        ):
            await cleanup_driver_session("api:openrouter", "test-session-id")
