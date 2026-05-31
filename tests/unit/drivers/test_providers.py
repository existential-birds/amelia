import pytest

from amelia.drivers.providers import PROVIDER_PRESETS, resolve_provider


def test_preset_resolves_base_url_and_env_var():
    r = resolve_provider("deepseek")
    assert r.base_url == "https://api.deepseek.com/v1"
    assert r.api_key_env_var == "DEEPSEEK_API_KEY"
    assert r.default_headers == {}


def test_openrouter_preset_carries_site_headers(monkeypatch):
    monkeypatch.delenv("OPENROUTER_SITE_URL", raising=False)
    r = resolve_provider("openrouter")
    assert r.base_url == "https://openrouter.ai/api/v1"
    assert r.api_key_env_var == "OPENROUTER_API_KEY"
    assert r.default_headers["HTTP-Referer"] == "https://github.com/existential-birds/amelia"
    assert r.default_headers["X-Title"] == "Amelia"


def test_base_url_override_wins_over_preset():
    r = resolve_provider("openrouter", base_url="http://proxy.internal/v1")
    assert r.base_url == "http://proxy.internal/v1"


def test_custom_provider_requires_base_url():
    with pytest.raises(ValueError, match="requires a base URL"):
        resolve_provider("vllm", api_key_env_var="VLLM_KEY")


def test_custom_provider_with_base_url_and_env_var_resolves():
    r = resolve_provider("vllm", base_url="http://localhost:8000/v1", api_key_env_var="VLLM_KEY")
    assert r.base_url == "http://localhost:8000/v1"
    assert r.api_key_env_var == "VLLM_KEY"


def test_unknown_provider_without_custom_config_lists_presets():
    with pytest.raises(ValueError, match="Unsupported provider 'anthropic'.*deepseek"):
        resolve_provider("anthropic")


def test_all_six_presets_present():
    assert set(PROVIDER_PRESETS) == {"openrouter", "openai", "deepseek", "groq", "together", "fireworks"}
