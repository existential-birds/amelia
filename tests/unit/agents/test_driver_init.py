"""Unit tests for _driver_init module.

Tests for init_agent_driver() helper and AgentDriverInit model.
"""
from unittest.mock import MagicMock, patch

from amelia.agents._driver_init import AgentDriverInit, init_agent_driver
from amelia.core.types import AgentConfig, SandboxConfig


class TestAgentDriverInit:
    """Tests for AgentDriverInit model."""

    def test_model_attributes(self) -> None:
        """AgentDriverInit should have driver, options, and prompts attributes."""
        mock_driver = MagicMock()
        options = {"max_iterations": 5}
        prompts = {"system": "custom"}

        result = AgentDriverInit(driver=mock_driver, options=options, prompts=prompts)

        assert result.driver is mock_driver
        assert result.options == options
        assert result.prompts == prompts

    def test_tuple_unpacking(self) -> None:
        """AgentDriverInit should support tuple unpacking."""
        mock_driver = MagicMock()
        options = {"key": "value"}
        prompts = {"prompt_id": "content"}

        result = AgentDriverInit(driver=mock_driver, options=options, prompts=prompts)

        driver, opts, prts = result
        assert driver is mock_driver
        assert opts == options
        assert prts == prompts


class TestInitAgentDriver:
    """Tests for init_agent_driver() function."""

    def test_calls_get_driver_with_config_fields(self) -> None:
        """init_agent_driver should pass config fields to get_driver."""
        sandbox = SandboxConfig(mode="container", image="test:latest")
        config = AgentConfig(
            driver="api",
            model="anthropic/claude-sonnet-4",
            sandbox=sandbox,
            profile_name="work",
            options={"max_iterations": 10},
        )
        mock_sandbox_provider = MagicMock()

        with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_get_driver.return_value = mock_driver

            init_agent_driver(
                config,
                prompts={"system": "custom"},
                sandbox_provider=mock_sandbox_provider,
            )

            mock_get_driver.assert_called_once_with(
                "api",
                model="anthropic/claude-sonnet-4",
                sandbox_config=sandbox,
                sandbox_provider=mock_sandbox_provider,
                profile_name="work",
                options={"max_iterations": 10},
            )

    def test_returns_driver_from_get_driver(self) -> None:
        """init_agent_driver should return the driver from get_driver."""
        config = AgentConfig(driver="claude", model="sonnet")

        with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
            mock_driver = MagicMock()
            mock_get_driver.return_value = mock_driver

            result = init_agent_driver(config)

            assert result.driver is mock_driver

    def test_returns_options_from_config(self) -> None:
        """init_agent_driver should return config.options in the result."""
        options = {"max_iterations": 5, "custom_key": "value"}
        config = AgentConfig(driver="api", model="test", options=options)

        with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
            mock_get_driver.return_value = MagicMock()

            result = init_agent_driver(config)

            assert result.options == options

    def test_normalizes_none_prompts_to_empty_dict(self) -> None:
        """init_agent_driver should convert None prompts to empty dict."""
        config = AgentConfig(driver="api", model="test")

        with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
            mock_get_driver.return_value = MagicMock()

            result = init_agent_driver(config, prompts=None)

            assert result.prompts == {}

    def test_preserves_prompts_when_provided(self) -> None:
        """init_agent_driver should preserve prompts dict when provided."""
        config = AgentConfig(driver="api", model="test")
        prompts = {"system": "custom system prompt", "assistant": "custom assistant"}

        with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
            mock_get_driver.return_value = MagicMock()

            result = init_agent_driver(config, prompts=prompts)

            assert result.prompts == prompts

    def test_sandbox_provider_none_by_default(self) -> None:
        """init_agent_driver should pass sandbox_provider=None when not provided."""
        config = AgentConfig(driver="api", model="test")

        with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
            mock_get_driver.return_value = MagicMock()

            init_agent_driver(config)

            call_kwargs = mock_get_driver.call_args.kwargs
            assert call_kwargs["sandbox_provider"] is None

    def test_default_sandbox_config_passed(self) -> None:
        """init_agent_driver should pass default SandboxConfig when not specified."""
        config = AgentConfig(driver="api", model="test")

        with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
            mock_get_driver.return_value = MagicMock()

            init_agent_driver(config)

            call_kwargs = mock_get_driver.call_args.kwargs
            assert call_kwargs["sandbox_config"] == SandboxConfig()

    def test_default_profile_name_passed(self) -> None:
        """init_agent_driver should pass default profile_name when not specified."""
        config = AgentConfig(driver="api", model="test")

        with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
            mock_get_driver.return_value = MagicMock()

            init_agent_driver(config)

            call_kwargs = mock_get_driver.call_args.kwargs
            assert call_kwargs["profile_name"] == "default"

    def test_empty_options_passed_by_default(self) -> None:
        """init_agent_driver should pass empty options dict when not specified."""
        config = AgentConfig(driver="api", model="test")

        with patch("amelia.agents._driver_init.get_driver") as mock_get_driver:
            mock_get_driver.return_value = MagicMock()

            init_agent_driver(config)

            call_kwargs = mock_get_driver.call_args.kwargs
            assert call_kwargs["options"] == {}
