"""Tests for _create_chat_model base_url parameter."""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from amelia.drivers.api.deepagents import ApiDriver, _create_chat_model


class TestCreateChatModelBaseUrl:
    @patch("amelia.drivers.api.chat_model.init_chat_model")
    def test_openrouter_uses_default_base_url(self, mock_init, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        _create_chat_model("test-model", provider="openrouter")
        _, kwargs = mock_init.call_args
        assert kwargs["base_url"] == "https://openrouter.ai/api/v1"

    @patch("amelia.drivers.api.chat_model.init_chat_model")
    def test_openrouter_accepts_custom_base_url(self, mock_init, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        _create_chat_model(
            "test-model",
            provider="openrouter",
            base_url="http://host.docker.internal:8430/proxy/v1",
        )
        _, kwargs = mock_init.call_args
        assert kwargs["base_url"] == "http://host.docker.internal:8430/proxy/v1"

    @patch("amelia.drivers.api.chat_model.init_chat_model")
    def test_preset_provider_uses_registry_url_and_key(self, mock_init, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
        _create_chat_model("deepseek-chat", provider="deepseek")
        _, kwargs = mock_init.call_args
        assert kwargs["base_url"] == "https://api.deepseek.com/v1"
        assert kwargs["api_key"] == "sk-ds"
        assert kwargs["model_provider"] == "openai"

    @patch("amelia.drivers.api.chat_model.init_chat_model")
    def test_custom_provider_resolves(self, mock_init, monkeypatch):
        monkeypatch.setenv("VLLM_KEY", "local-key")
        _create_chat_model(
            "my-model",
            provider="vllm",
            base_url="http://localhost:8000/v1",
            api_key_env_var="VLLM_KEY",
        )
        _, kwargs = mock_init.call_args
        assert kwargs["base_url"] == "http://localhost:8000/v1"
        assert kwargs["api_key"] == "local-key"

    def test_missing_key_env_var_raises_naming_provider_and_var(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with pytest.raises(ValueError, match="DEEPSEEK_API_KEY.*deepseek"):
            _create_chat_model("deepseek-chat", provider="deepseek")


@patch("amelia.drivers.api.deepagents._create_chat_model")
async def test_apidriver_threads_provider_config_to_chat_model(
    mock_ccm, monkeypatch, mock_deepagents_filesystem
):
    monkeypatch.setenv("VLLM_KEY", "k")
    mock_deepagents_filesystem.agent_result["messages"] = [AIMessage(content="ok")]
    driver = ApiDriver(
        model="m",
        provider="vllm",
        base_url="http://localhost:8000/v1",
        api_key_env_var="VLLM_KEY",
    )
    await driver.generate(prompt="hi")
    mock_ccm.assert_called_with(
        "m",
        provider="vllm",
        base_url="http://localhost:8000/v1",
        api_key_env_var="VLLM_KEY",
    )
