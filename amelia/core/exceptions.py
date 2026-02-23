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

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({self.args[0]!r}, "
            f"provider_name={self.provider_name!r}, "
            f"original_message={self.original_message!r})"
        )


class SchemaValidationError(AmeliaError):
    """Raised when LLM output fails Pydantic schema validation.

    This is a content error, not a transient provider error.
    Should NOT trigger full workflow restart — the graph-level
    feedback loop handles it instead.
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
