"""Driver interfaces and factory for LLM interaction.

Provide an abstraction layer between agents and LLM providers. Drivers
implement a common interface, allowing the orchestrator to switch between
direct API calls and CLI-wrapped tools without code changes.

Exports:
    DriverInterface: Protocol defining the LLM driver contract.
    get_driver: Function to create driver instances from configuration keys.
    DriverFactory: Deprecated class wrapper for backward compatibility.
"""

from amelia.drivers.base import DriverInterface
from amelia.drivers.factory import DriverFactory, get_driver


__all__ = [
    "DriverInterface",
    "get_driver",
    "DriverFactory",
]
