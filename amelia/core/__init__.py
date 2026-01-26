"""Core types, exceptions, and utilities for Amelia.

Provide foundational types and shared utilities used throughout the Amelia
codebase. Include constants for tool names, custom exceptions, and utility
functions.

Exports:
    ToolName: Enum of recognized tool names for agents.
    CANONICAL_TO_CLI: Mapping from canonical tool names to CLI SDK names.
    READONLY_TOOLS: Preset list of safe read-only tools.
    AmeliaError: Base exception for all Amelia errors.
    ConfigurationError: Invalid or missing configuration.
    strip_ansi: Remove ANSI escape codes from strings.
"""

from amelia.core.constants import (
    CANONICAL_TO_CLI as CANONICAL_TO_CLI,
    READONLY_TOOLS as READONLY_TOOLS,
    ToolName as ToolName,
)
from amelia.core.exceptions import (
    AmeliaError as AmeliaError,
    ConfigurationError as ConfigurationError,
)
from amelia.core.utils import strip_ansi as strip_ansi
