"""Tests for _create_chat_model base_url parameter."""

from unittest.mock import patch

from amelia.drivers.api.deepagents import _create_chat_model


class TestCreateChatModelBaseUrl:
    @patch("amelia.drivers.api.deepagents.init_chat_model")
    def test_openrouter_uses_default_base_url(self, mock_init, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        _create_chat_model("test-model", provider="openrouter")
        _, kwargs = mock_init.call_args
        assert kwargs["base_url"] == "https://openrouter.ai/api/v1"

    @patch("amelia.drivers.api.deepagents.init_chat_model")
    def test_openrouter_accepts_custom_base_url(self, mock_init, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        _create_chat_model(
            "test-model",
            provider="openrouter",
            base_url="http://host.docker.internal:8430/proxy/v1",
        )
        _, kwargs = mock_init.call_args
        assert kwargs["base_url"] == "http://host.docker.internal:8430/proxy/v1"

    @patch("amelia.drivers.api.deepagents.init_chat_model")
    def test_non_openrouter_ignores_base_url(self, mock_init):
        _create_chat_model("gpt-4")
        mock_init.assert_called_once_with("gpt-4")
