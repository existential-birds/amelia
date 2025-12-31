"""CLI-based drivers for LLM interactions.

This module provides CLI-wrapper drivers that delegate to external CLI tools
rather than making direct API calls. This enables enterprise compliance where
direct API calls may be prohibited.
"""
from amelia.drivers.cli.claude import ClaudeCliDriver


__all__ = ["ClaudeCliDriver"]
