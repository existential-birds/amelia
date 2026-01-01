"""Driver interfaces and factory for LLM interaction.

Provide an abstraction layer between agents and LLM providers. Drivers
implement a common interface, allowing the orchestrator to switch between
direct API calls and CLI-wrapped tools without code changes.

Exports:
    DriverInterface: Protocol defining the LLM driver contract.
    DriverFactory: Factory for creating driver instances from configuration.
"""

from amelia.drivers.base import DriverInterface
from amelia.drivers.factory import DriverFactory


__all__ = [
    "DriverInterface",
    "DriverFactory",
]
