"""Single source of truth for OpenAI-compatible model providers.

Resolves a ``(provider, base_url?, api_key_env_var?)`` triple into a
``ResolvedProvider`` that both execution paths consume: the local path
(``ApiDriver`` → ``_create_chat_model``) and the remote Daytona path
(``create_daytona_provider`` worker_env).

A provider is either a built-in preset (one of :data:`PROVIDER_PRESETS`)
or a fully custom endpoint declared by supplying ``base_url`` and
``api_key_env_var`` explicitly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# Default OpenRouter site-attribution headers, overridable via env vars.
_OPENROUTER_DEFAULT_SITE_URL = "https://github.com/existential-birds/amelia"
_OPENROUTER_DEFAULT_SITE_NAME = "Amelia"


@dataclass(frozen=True)
class ProviderPreset:
    """A built-in OpenAI-compatible provider's base URL and key env var."""

    base_url: str
    api_key_env_var: str


# Starter preset set. URLs/env-vars verified against each provider's docs.
PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "openrouter": ProviderPreset(
        base_url="https://openrouter.ai/api/v1",
        api_key_env_var="OPENROUTER_API_KEY",
    ),
    "openai": ProviderPreset(
        base_url="https://api.openai.com/v1",
        api_key_env_var="OPENAI_API_KEY",
    ),
    "deepseek": ProviderPreset(
        base_url="https://api.deepseek.com/v1",
        api_key_env_var="DEEPSEEK_API_KEY",
    ),
    "groq": ProviderPreset(
        base_url="https://api.groq.com/openai/v1",
        api_key_env_var="GROQ_API_KEY",
    ),
    "together": ProviderPreset(
        base_url="https://api.together.ai/v1",
        api_key_env_var="TOGETHER_API_KEY",
    ),
    "fireworks": ProviderPreset(
        base_url="https://api.fireworks.ai/inference/v1",
        api_key_env_var="FIREWORKS_API_KEY",
    ),
}


@dataclass(frozen=True)
class ResolvedProvider:
    """A fully resolved provider configuration ready for ``init_chat_model``."""

    base_url: str
    api_key_env_var: str
    default_headers: dict[str, str]


def _openrouter_site_headers() -> dict[str, str]:
    """Build OpenRouter site-attribution headers from env (with defaults)."""
    return {
        "HTTP-Referer": os.environ.get(
            "OPENROUTER_SITE_URL", _OPENROUTER_DEFAULT_SITE_URL
        ),
        "X-Title": os.environ.get("OPENROUTER_SITE_NAME", _OPENROUTER_DEFAULT_SITE_NAME),
    }


def resolve_provider(
    provider: str,
    *,
    base_url: str | None = None,
    api_key_env_var: str | None = None,
) -> ResolvedProvider:
    """Resolve a provider name into a concrete base URL, key env var, and headers.

    Args:
        provider: A built-in preset name (see :data:`PROVIDER_PRESETS`) or a
            custom provider name.
        base_url: Overrides the preset base URL when given; required for a
            custom (non-preset) provider.
        api_key_env_var: Required for a custom provider; ignored for presets
            (the preset's own env var is used).

    Returns:
        The resolved provider configuration.

    Raises:
        ValueError: If a custom provider is missing ``base_url`` or
            ``api_key_env_var``, or if an unknown provider is supplied without
            the custom-provider configuration.
    """
    preset = PROVIDER_PRESETS.get(provider)
    if preset is not None:
        default_headers = _openrouter_site_headers() if provider == "openrouter" else {}
        return ResolvedProvider(
            base_url=base_url or preset.base_url,
            api_key_env_var=preset.api_key_env_var,
            default_headers=default_headers,
        )

    # Custom provider: both base_url and api_key_env_var must be supplied.
    if base_url is None:
        if api_key_env_var is not None:
            raise ValueError(
                f"Custom provider {provider!r} requires a base URL "
                "(pass base_url)."
            )
        raise ValueError(
            f"Unsupported provider {provider!r}. "
            f"Known presets: {sorted(PROVIDER_PRESETS)}. "
            "To use a custom provider, supply base_url and api_key_env_var."
        )
    if api_key_env_var is None:
        raise ValueError(
            f"Custom provider {provider!r} requires an API key environment "
            "variable (pass api_key_env_var)."
        )

    return ResolvedProvider(
        base_url=base_url,
        api_key_env_var=api_key_env_var,
        default_headers={},
    )
