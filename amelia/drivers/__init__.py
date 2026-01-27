"""Driver interfaces and factory for LLM interaction.

Provide an abstraction layer between agents and LLM providers. Drivers
implement a common interface, allowing the orchestrator to switch between
direct API calls and CLI-wrapped tools without code changes.
"""
