"""Unit tests for Developer agent initialization."""
from unittest.mock import MagicMock, patch

from amelia.agents.developer import Developer
from amelia.core.types import AgentConfig, SandboxConfig


def test_developer_init_with_agent_config() -> None:
    """Developer should accept AgentConfig and create its own driver."""
    config = AgentConfig(driver="api", model="anthropic/claude-sonnet-4")

    with patch("amelia.agents.developer.get_driver") as mock_get_driver:
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        developer = Developer(config)

        mock_get_driver.assert_called_once_with(
            "api",
            model="anthropic/claude-sonnet-4",
            sandbox_config=SandboxConfig(),
            profile_name="default",
            options={},
        )
        assert developer.driver is mock_driver
        assert developer.options == {}


def test_developer_init_with_options() -> None:
    """Developer should pass through options from AgentConfig."""
    config = AgentConfig(
        driver="cli",
        model="claude-sonnet-4-20250514",
        options={"max_iterations": 10},
    )

    with patch("amelia.agents.developer.get_driver") as mock_get_driver:
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        developer = Developer(config)

        assert developer.options == {"max_iterations": 10}


def test_developer_init_passes_sandbox_config() -> None:
    """Developer should pass sandbox_config and profile_name to get_driver."""
    sandbox = SandboxConfig(mode="container", image="custom:latest")
    config = AgentConfig(
        driver="api",
        model="test-model",
        sandbox=sandbox,
        profile_name="work",
        options={"max_iterations": 5},
    )

    with patch("amelia.agents.developer.get_driver") as mock_get_driver:
        mock_get_driver.return_value = MagicMock()
        Developer(config)

        mock_get_driver.assert_called_once_with(
            "api",
            model="test-model",
            sandbox_config=sandbox,
            profile_name="work",
            options={"max_iterations": 5},
        )
