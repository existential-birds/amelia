"""Core types, exceptions, and utilities for Amelia.

Provide foundational types and shared utilities used throughout the Amelia
codebase. Include constants for tool names, custom exceptions, and utility
functions.

Exports:
    ToolName: Enum of recognized tool names for agents.
    AmeliaError: Base exception for all Amelia errors.
    ConfigurationError: Invalid or missing configuration.
    PathTraversalError: Attempted path traversal outside allowed directory.
    strip_ansi: Remove ANSI escape codes from strings.
"""

from amelia.core.constants import ToolName as ToolName
from amelia.core.exceptions import (
    AmeliaError as AmeliaError,
    ConfigurationError as ConfigurationError,
    PathTraversalError as PathTraversalError,
)
from amelia.core.utils import strip_ansi as strip_ansi
