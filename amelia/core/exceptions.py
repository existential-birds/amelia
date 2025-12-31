# amelia/core/exceptions.py
"""Custom exceptions for Amelia."""


class AmeliaError(Exception):
    """Base exception for all Amelia errors."""

    pass


class ConfigurationError(AmeliaError):
    """Raised when required configuration is missing or invalid."""

    pass


class SecurityError(AmeliaError):
    """Raised when a security constraint is violated."""

    pass


class DangerousCommandError(SecurityError):
    """Raised when a command matches a dangerous pattern."""

    pass


class BlockedCommandError(SecurityError):
    """Raised when a command is in the blocklist."""

    pass


class ShellInjectionError(SecurityError):
    """Raised when shell metacharacters are detected in a command."""

    pass


class PathTraversalError(SecurityError):
    """Raised when a path traversal attempt is detected."""

    pass


class CommandNotAllowedError(SecurityError):
    """Raised when in strict mode and command is not in allowlist."""

    pass


class AgenticExecutionError(AmeliaError):
    """Raised when agentic execution fails."""

    pass
