from amelia.drivers.api.openai import ApiDriver
from amelia.drivers.base import DriverInterface
from amelia.drivers.cli.claude import ClaudeCliDriver


class DriverFactory:
    """Factory class for creating driver instances based on configuration keys."""

    @staticmethod
    def get_driver(driver_key: str) -> DriverInterface:
        """
        Factory method to get a concrete driver implementation based on a key.
        """
        if driver_key == "cli:claude" or driver_key == "cli":
            return ClaudeCliDriver()
        elif driver_key == "api:openai" or driver_key == "api":
            return ApiDriver()
        else:
            raise ValueError(f"Unknown driver key: {driver_key}")
