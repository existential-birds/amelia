from typing import Any

from amelia.drivers.api import ApiDriver
from amelia.drivers.base import DriverInterface
from amelia.drivers.cli.claude import ClaudeCliDriver


def get_driver(driver_key: str, **kwargs: Any) -> DriverInterface:
    """Get a concrete driver implementation.

    Args:
        driver_key: Driver identifier (e.g., "cli:claude", "api:openrouter").
        **kwargs: Driver-specific configuration passed to constructor.

    Returns:
        Configured driver instance.

    Raises:
        ValueError: If driver_key is not recognized.
    """
    if driver_key in ("cli:claude", "cli"):
        return ClaudeCliDriver(**kwargs)
    elif driver_key in ("api:openrouter", "api"):
        return ApiDriver(provider="openrouter", **kwargs)
    else:
        raise ValueError(f"Unknown driver key: {driver_key}")


class DriverFactory:
    """Factory class for creating driver instances based on configuration keys.

    Note:
        This class is deprecated. Use the module-level `get_driver()` function directly.
        Kept for backward compatibility.
    """

    @staticmethod
    def get_driver(driver_key: str, **kwargs: Any) -> DriverInterface:
        """Factory method to get a concrete driver implementation.

        Args:
            driver_key: Driver identifier (e.g., "cli:claude", "api:openrouter").
            **kwargs: Driver-specific configuration passed to constructor.

        Returns:
            Configured driver instance.

        Raises:
            ValueError: If driver_key is not recognized.
        """
        return get_driver(driver_key, **kwargs)
