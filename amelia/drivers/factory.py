from typing import Any

from amelia.drivers.api.openai import ApiDriver
from amelia.drivers.base import DriverInterface
from amelia.drivers.cli.agentic import ClaudeAgenticCliDriver
from amelia.drivers.cli.claude import ClaudeCliDriver


class DriverFactory:
    """Factory class for creating driver instances based on configuration keys."""

    @staticmethod
    def get_driver(driver_key: str, **kwargs: Any) -> DriverInterface:
        """Factory method to get a concrete driver implementation.

        Args:
            driver_key: Driver identifier (e.g., "cli:claude", "api:openai").
            **kwargs: Driver-specific configuration passed to constructor.

        Returns:
            Configured driver instance.

        Raises:
            ValueError: If driver_key is not recognized.
        """
        if driver_key == "cli:claude" or driver_key == "cli":
            return ClaudeCliDriver(**kwargs)
        elif driver_key == "cli:claude:agentic":
            return ClaudeAgenticCliDriver(**kwargs)
        elif driver_key == "api:openai" or driver_key == "api":
            return ApiDriver(**kwargs)
        else:
            raise ValueError(f"Unknown driver key: {driver_key}")
