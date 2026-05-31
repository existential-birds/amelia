"""Chat-model construction and model-provider error parsing.

Provider plumbing for the DeepAgents API driver: resolves an
OpenAI-compatible provider into a configured LangChain chat model and
classifies ``ValueError``s that originate from the model provider (rather
than Amelia's own validation) so they can be surfaced as
:class:`~amelia.core.exceptions.ModelProviderError`.
"""
import functools
import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from loguru import logger

from amelia.drivers.providers import resolve_provider


# Patterns in ValueError messages that indicate a model provider error (not Amelia's fault).
#
# These patterns are matched case-insensitively against the exception message.
# When a ValueError contains any of these patterns, it's wrapped in ModelProviderError
# instead of being raised directly, providing better error UX for transient LLM issues.
#
# To add a new pattern:
# 1. Identify the error message substring from the LLM provider SDK (usually langchain_openai)
# 2. Add a lowercase pattern that uniquely identifies the provider error
# 3. Test by triggering the error and verifying ModelProviderError is raised
#
# Configurable via AMELIA_PROVIDER_ERROR_PATTERNS env var (comma-separated, lowercase).
_DEFAULT_PROVIDER_ERROR_PATTERNS = (
    "midstream error",  # OpenRouter/provider streaming failures
    "invalid function arguments",  # Bad tool call JSON from provider
    "provider returned error",  # Generic provider-side errors
)


@functools.lru_cache(maxsize=1)
def _get_provider_error_patterns() -> tuple[str, ...]:
    """Get provider error patterns from environment or defaults.

    Reads AMELIA_PROVIDER_ERROR_PATTERNS environment variable dynamically
    to support runtime configuration and testing with mocked environments.

    Returns:
        Tuple of lowercase pattern strings to match against error messages.
    """
    patterns_str = os.environ.get(
        "AMELIA_PROVIDER_ERROR_PATTERNS",
        ",".join(_DEFAULT_PROVIDER_ERROR_PATTERNS),
    )
    return tuple(p.strip().lower() for p in patterns_str.split(",") if p.strip())


def _is_model_provider_error(exc: ValueError) -> bool:
    """Check if a ValueError originates from a model provider rather than Amelia validation.

    langchain_openai raises ValueError with a dict arg when the provider returns
    an error (e.g. bad JSON from Minimax). Amelia's own validation uses string args.

    Args:
        exc: The ValueError to inspect.

    Returns:
        True if this looks like a model provider error.
    """
    # langchain_openai pattern: ValueError({"error": {...}, "provider": "..."})
    if exc.args and isinstance(exc.args[0], dict):
        return True
    # String-based detection for known provider error patterns
    msg = str(exc).lower()
    return any(pattern in msg for pattern in _get_provider_error_patterns())


def _extract_provider_info(exc: ValueError) -> tuple[str | None, str]:
    """Extract provider name and error message from a model provider ValueError.

    Args:
        exc: The ValueError to extract info from.

    Returns:
        Tuple of (provider_name, error_message). provider_name may be None.
    """
    if exc.args and isinstance(exc.args[0], dict):
        err_dict = exc.args[0]
        error_obj = err_dict.get("error", {})
        provider = err_dict.get("provider")

        # Handle unexpected dict structures with explicit logging
        if not isinstance(error_obj, dict):
            logger.debug(
                "Unexpected error_obj type in provider error",
                error_obj_type=type(error_obj).__name__,
                error_obj_value=str(error_obj)[:200],
                err_dict_keys=list(err_dict.keys()),
            )

        message = (
            error_obj.get("message", str(err_dict))
            if isinstance(error_obj, dict)
            else str(error_obj)
        )
        return provider, message
    return None, str(exc)


def _create_chat_model(
    model: str,
    provider: str,
    base_url: str | None = None,
    api_key_env_var: str | None = None,
) -> BaseChatModel:
    """Create a LangChain chat model for any OpenAI-compatible provider.

    Resolves the provider (built-in preset or fully custom endpoint) via
    :func:`amelia.drivers.providers.resolve_provider`, then routes the model
    through ``init_chat_model(model_provider="openai", ...)`` with the
    resolved base URL, API key, and default headers.

    Args:
        model: Bare model identifier (e.g., 'minimax/minimax-m2',
            'deepseek-chat'). Must NOT carry a ``provider:`` prefix —
            langchain's model parser splits on ``:`` and would misparse it.
        provider: Provider name. A built-in preset (openrouter, openai,
            deepseek, groq, together, fireworks) or a custom name paired with
            ``base_url`` + ``api_key_env_var``.
        base_url: Overrides the preset base URL when given; required for a
            custom (non-preset) provider. Also used for proxy routing in
            sandboxed environments.
        api_key_env_var: Name of the environment variable holding the API key;
            required for a custom (non-preset) provider, ignored for presets.

    Returns:
        Configured BaseChatModel instance.

    Raises:
        ValueError: If ``model`` carries the legacy ``openrouter:`` prefix.
        ValueError: If a custom provider omits ``base_url`` or
            ``api_key_env_var``, or an unknown provider is supplied without
            custom configuration (propagated from ``resolve_provider``).
        ValueError: If the resolved API key environment variable is unset.
    """
    if model.startswith("openrouter:"):
        raise ValueError(
            "The 'openrouter:' prefix in model names is no longer supported. "
            "Use driver='api' with the model name directly "
            f"(e.g., model='{model[len('openrouter:'):]}')."
        )

    resolved = resolve_provider(
        provider, base_url=base_url, api_key_env_var=api_key_env_var
    )
    api_key = os.environ.get(resolved.api_key_env_var)
    if not api_key:
        raise ValueError(
            f"{resolved.api_key_env_var} environment variable is required "
            f"for provider {provider!r}"
        )

    return init_chat_model(
        model=model,
        model_provider="openai",
        base_url=resolved.base_url,
        api_key=api_key,
        default_headers=resolved.default_headers,
    )
