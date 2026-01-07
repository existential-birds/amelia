"""Core types, exceptions, and utilities for Amelia.

Provide foundational types and shared utilities used throughout the Amelia
codebase. Include constants for tool names, custom exceptions, stream event
types for real-time feedback, and utility functions.

Exports:
    ToolName: Enum of recognized tool names for agents.
    AmeliaError: Base exception for all Amelia errors.
    ConfigurationError: Invalid or missing configuration.
    PathTraversalError: Attempted path traversal outside allowed directory.
    StageEventEmitter: Callback for emitting STAGE_STARTED events from nodes.
    StreamEmitter: Protocol for emitting stream events.
    StreamEvent: Event payload for streaming updates.
    StreamEventType: Enum of stream event categories.
    strip_ansi: Remove ANSI escape codes from strings.
"""

from amelia.core.constants import ToolName as ToolName
from amelia.core.exceptions import (
    AmeliaError as AmeliaError,
    ConfigurationError as ConfigurationError,
    PathTraversalError as PathTraversalError,
)
from amelia.core.types import (
    StageEventEmitter as StageEventEmitter,
    StreamEmitter as StreamEmitter,
    StreamEvent as StreamEvent,
    StreamEventType as StreamEventType,
)
from amelia.core.utils import strip_ansi as strip_ansi
