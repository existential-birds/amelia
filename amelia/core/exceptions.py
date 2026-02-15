# amelia/core/exceptions.py
"""Custom exceptions for Amelia."""


class AmeliaError(Exception):
    """Base exception for all Amelia errors."""

    pass


class ConfigurationError(AmeliaError):
    """Raised when required configuration is missing or invalid."""

    pass


class ModelProviderError(AmeliaError):
    """Raised when a model provider returns a transient error.

    Wraps upstream LLM provider errors (bad JSON, provider 400s) that may
    succeed on retry. Not caused by Amelia.
    """

    def __init__(
        self,
        message: str,
        provider_name: str | None = None,
        original_message: str | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.original_message = original_message
        super().__init__(message)
