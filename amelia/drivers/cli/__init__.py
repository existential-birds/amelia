"""CLI-based drivers for LLM interactions.

Provide CLI-wrapper drivers that delegate to external CLI tools rather than
making direct API calls. Enable enterprise compliance where direct API calls
may be prohibited by routing through approved CLI binaries.

Exports:
    ClaudeCliDriver: Driver wrapping the Claude CLI for LLM interactions.
"""
from amelia.drivers.cli.claude import ClaudeCliDriver


__all__ = ["ClaudeCliDriver"]
