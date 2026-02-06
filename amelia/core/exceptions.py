# amelia/core/exceptions.py
"""Custom exceptions for Amelia."""


class AmeliaError(Exception):
    """Base exception for all Amelia errors."""

    pass


class ConfigurationError(AmeliaError):
    """Raised when required configuration is missing or invalid."""

    pass
