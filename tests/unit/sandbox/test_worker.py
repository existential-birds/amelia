"""Tests for the sandbox worker entrypoint."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from amelia.sandbox.worker import (
    AgenticMessage,
    AgenticMessageType,
    DriverUsage,
    _create_worker_chat_model,
    _emit_line,
    _emit_usage,
    _import_schema,
    _parse_args,
)


class TestWorkerEmitLine:
    """Tests for the JSON-line emission helper."""

    def test_emit_line_writes_json_to_stdout(self) -> None:
        buf = StringIO()
        msg = AgenticMessage(type=AgenticMessageType.RESULT, content="done")
        _emit_line(msg, file=buf)

        line = buf.getvalue().strip()
        parsed = json.loads(line)
        assert parsed["type"] == "result"
        assert parsed["content"] == "done"

    def test_emit_line_one_line_per_message(self) -> None:
        buf = StringIO()
        _emit_line(AgenticMessage(type=AgenticMessageType.THINKING, content="hmm"), file=buf)
        _emit_line(AgenticMessage(type=AgenticMessageType.RESULT, content="ok"), file=buf)

        lines = buf.getvalue().strip().split("\n")
        assert len(lines) == 2


class TestWorkerParseArgs:
    """Tests for CLI argument parsing."""

    def test_agentic_mode(self) -> None:
        args = _parse_args([
            "agentic",
            "--prompt-file", "/tmp/prompt.txt",
            "--cwd", "/workspace/worktrees/issue-1",
            "--model", "anthropic/claude-sonnet-4-5",
        ])
        assert args.mode == "agentic"
        assert args.prompt_file == "/tmp/prompt.txt"
        assert args.cwd == "/workspace/worktrees/issue-1"
        assert args.model == "anthropic/claude-sonnet-4-5"

    def test_generate_mode_with_schema(self) -> None:
        args = _parse_args([
            "generate",
            "--prompt-file", "/tmp/prompt.txt",
            "--model", "anthropic/claude-sonnet-4-5",
            "--schema", "amelia.agents.schemas.evaluator:EvaluationOutput",
        ])
        assert args.mode == "generate"
        assert args.schema == "amelia.agents.schemas.evaluator:EvaluationOutput"

    def test_agentic_mode_with_instructions(self) -> None:
        args = _parse_args([
            "agentic",
            "--prompt-file", "/tmp/prompt.txt",
            "--cwd", "/workspace",
            "--model", "test-model",
            "--instructions", "Be concise.",
        ])
        assert args.instructions == "Be concise."


class TestWorkerSchemaImport:
    """Tests for dynamic schema class import."""

    def test_import_known_schema(self) -> None:
        cls = _import_schema("amelia.agents.schemas.evaluator:EvaluationOutput")
        from amelia.agents.schemas.evaluator import EvaluationOutput

        assert cls is EvaluationOutput

    def test_import_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="must be 'module:ClassName'"):
            _import_schema("no_colon_here")

    def test_import_nonexistent_module_raises(self) -> None:
        with pytest.raises(ImportError):
            _import_schema("nonexistent.module:Foo")


class TestWorkerUsageEmission:
    """Tests for final USAGE message emission."""

    def test_emit_usage(self) -> None:
        buf = StringIO()
        usage = DriverUsage(input_tokens=100, output_tokens=50)
        _emit_usage(usage, file=buf)

        line = buf.getvalue().strip()
        parsed = AgenticMessage.model_validate_json(line)
        assert parsed.type == AgenticMessageType.USAGE
        assert parsed.usage is not None
        assert parsed.usage.input_tokens == 100


class TestCreateWorkerChatModel:
    """Tests for _create_worker_chat_model()."""

    def test_proxy_token_added_to_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When AMELIA_PROXY_TOKEN is set, it should be included in default_headers."""
        monkeypatch.setenv("AMELIA_PROXY_TOKEN", "test-secret-token")
        monkeypatch.setenv("AMELIA_PROFILE", "work")

        mock_init = MagicMock(return_value="mock-model")
        with patch("langchain.chat_models.init_chat_model", mock_init):
            _create_worker_chat_model(model="test-model", base_url="http://localhost:8430/proxy/v1")

        call_kwargs = mock_init.call_args[1]
        assert call_kwargs["default_headers"]["X-Amelia-Proxy-Token"] == "test-secret-token"

    def test_no_proxy_token_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When AMELIA_PROXY_TOKEN is not set, header should not be present."""
        monkeypatch.delenv("AMELIA_PROXY_TOKEN", raising=False)
        monkeypatch.setenv("AMELIA_PROFILE", "work")

        mock_init = MagicMock(return_value="mock-model")
        with patch("langchain.chat_models.init_chat_model", mock_init):
            _create_worker_chat_model(model="test-model", base_url="http://localhost:8430/proxy/v1")

        call_kwargs = mock_init.call_args[1]
        assert "X-Amelia-Proxy-Token" not in call_kwargs["default_headers"]
