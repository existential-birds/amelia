"""Tests for ApiDriver chat-model / HTTP-client caching (issue #642).

These exercise the observable consequence: the chat model (and its underlying
HTTP client) is built once per (provider, model, base_url, api_key_env_var) and
reused across back-to-back calls, rather than rebuilt on every request. The
key-missing error path must still raise clearly.
"""
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from amelia.drivers.api.deepagents import ApiDriver


class TestChatModelInstanceCache:
    """Cached chat model is reused across same-config generate() calls."""

    async def test_generate_builds_chat_model_once_for_repeated_calls(
        self, mock_deepagents_filesystem: MagicMock
    ) -> None:
        """_create_chat_model is invoked once across N same-config generate calls."""
        driver = ApiDriver(model="test/model", cwd="/test", provider="openrouter")
        mock_deepagents_filesystem.agent_result["messages"] = [
            AIMessage(content="response")
        ]

        with patch(
            "amelia.drivers.api.deepagents._create_chat_model"
        ) as mock_create:
            sentinel_model = MagicMock(name="chat_model")
            mock_create.return_value = sentinel_model

            await driver.generate(prompt="one")
            await driver.generate(prompt="two")
            await driver.generate(prompt="three")

            assert mock_create.call_count == 1

    async def test_distinct_configs_build_agents_with_their_cached_models(
        self, mock_deepagents_filesystem: MagicMock
    ) -> None:
        """Each distinct generate config receives the driver's cached chat model."""
        driver = ApiDriver(model="test/model", cwd="/test", provider="openrouter")
        mock_deepagents_filesystem.agent_result["messages"] = [
            AIMessage(content="response")
        ]

        with patch(
            "amelia.drivers.api.deepagents._create_chat_model"
        ) as mock_create:
            sentinel_model = MagicMock(name="chat_model")
            mock_create.return_value = sentinel_model

            # Two distinct system prompts -> two agent builds, one cached model.
            await driver.generate(prompt="one", system_prompt="sys-a")
            await driver.generate(prompt="two", system_prompt="sys-b")

            models_passed = [
                call.kwargs["model"]
                for call in mock_deepagents_filesystem.create_deep_agent.call_args_list
            ]
            assert mock_create.call_count == 1
            assert len(models_passed) == 2
            assert models_passed[0] is sentinel_model
            assert models_passed[1] is sentinel_model

    async def test_generate_and_execute_agentic_share_cached_model(
        self, mock_deepagents_both: MagicMock
    ) -> None:
        """generate() and execute_agentic() reuse the same cached chat model."""
        driver = ApiDriver(model="test/model", cwd="/test", provider="openrouter")
        mock_deepagents_both.agent_result["messages"] = [AIMessage(content="ok")]
        mock_deepagents_both.stream_chunks = [
            {"messages": [AIMessage(content="done")]},
        ]

        with patch(
            "amelia.drivers.api.deepagents._create_chat_model"
        ) as mock_create:
            mock_create.return_value = MagicMock(name="chat_model")

            await driver.generate(prompt="one")
            async for _ in driver.execute_agentic(prompt="two", cwd="/test"):
                pass

            assert mock_create.call_count == 1


class TestGenerateAgentMemoized:
    """Non-agentic generate() agent (fixed tool set) is built once and reused."""

    async def test_repeated_generate_builds_agent_once(
        self, mock_deepagents_filesystem: MagicMock
    ) -> None:
        """create_deep_agent runs once across repeated same-config generate calls."""
        driver = ApiDriver(model="test/model", cwd="/test", provider="openrouter")
        mock_deepagents_filesystem.agent_result["messages"] = [
            AIMessage(content="response")
        ]

        await driver.generate(prompt="one", system_prompt="sys")
        await driver.generate(prompt="two", system_prompt="sys")
        await driver.generate(prompt="three", system_prompt="sys")

        assert mock_deepagents_filesystem.create_deep_agent.call_count == 1

    async def test_generate_rebuilds_agent_when_system_prompt_changes(
        self, mock_deepagents_filesystem: MagicMock
    ) -> None:
        """A different system prompt yields a distinct memoized agent."""
        driver = ApiDriver(model="test/model", cwd="/test", provider="openrouter")
        mock_deepagents_filesystem.agent_result["messages"] = [
            AIMessage(content="response")
        ]

        await driver.generate(prompt="one", system_prompt="sys-a")
        await driver.generate(prompt="two", system_prompt="sys-b")

        assert mock_deepagents_filesystem.create_deep_agent.call_count == 2

    async def test_generate_rebuilds_agent_when_driver_cwd_changes(
        self, mock_deepagents_filesystem: MagicMock
    ) -> None:
        """A different backend root yields a distinct memoized agent."""
        driver = ApiDriver(model="test/model", cwd="/test-a", provider="openrouter")
        mock_deepagents_filesystem.agent_result["messages"] = [
            AIMessage(content="response")
        ]

        await driver.generate(prompt="one", system_prompt="sys")
        driver.cwd = "/test-b"
        await driver.generate(prompt="two", system_prompt="sys")

        assert mock_deepagents_filesystem.create_deep_agent.call_count == 2
        roots = [
            call.kwargs["root_dir"]
            for call in mock_deepagents_filesystem.backend_class.call_args_list
        ]
        assert roots == ["/test-a", "/test-b"]


class TestKeyMissingStillRaises:
    """The cached path must not swallow the missing-API-key error."""

    async def test_generate_raises_when_key_missing(
        self, mock_deepagents_filesystem: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """generate() surfaces a clear error when the API key env var is unset."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        driver = ApiDriver(model="deepseek-chat", cwd="/test", provider="deepseek")

        with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
            await driver.generate(prompt="hi")
