"""API driver module using DeepAgents.

Provide a driver implementation that makes direct HTTP calls to LLM APIs
via the DeepAgents library. Support structured output parsing and tool
calling through the pydantic-ai integration.

Exports:
    ApiDriver: Driver implementation for direct API access.
"""
from amelia.drivers.api.deepagents import ApiDriver


__all__ = ["ApiDriver"]
