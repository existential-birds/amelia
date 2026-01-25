"""Unit tests for Developer agent initialization."""
from unittest.mock import MagicMock, patch

from amelia.agents.developer import Developer
from amelia.core.types import AgentConfig


def test_developer_init_with_agent_config() -> None:
    """Developer should accept AgentConfig and create its own driver."""
    config = AgentConfig(driver="api", model="anthropic/claude-sonnet-4")

    with patch("amelia.agents.developer.get_driver") as mock_get_driver:
        mock_driver = MagicMock()
        mock_get_driver.return_value = mock_driver

        developer = Developer(config)

        mock_get_driver.assert_called_once_with("api", model="anthropic/claude-sonnet-4")
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
