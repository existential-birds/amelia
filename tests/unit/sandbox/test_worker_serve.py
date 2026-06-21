"""Tests for the long-lived ``serve`` mode of the sandbox worker.

These assert the lifecycle the long-lived worker exists to guarantee:
  - the heavy import happens exactly ONCE, before any command and not per
    command;
  - a single serve loop dispatches MULTIPLE sequential requests, returning a
    framed result per command;
  - a command that raises mid-flight emits an ``error`` frame but does NOT
    kill the worker — the next command is still served;
  - a clean EOF on stdin stops the loop.

The LLM stack is faked at the dispatch boundary so no network/LLM is needed.
"""

from __future__ import annotations

import io
from typing import Any, TextIO

import pytest

from amelia.sandbox import worker as worker_mod
from amelia.sandbox.protocol import (
    WorkerRequest,
    encode_request,
    parse_frame,
)
from amelia.sandbox.worker import AgenticMessage, AgenticMessageType, _serve


def _requests_stdin(*requests: WorkerRequest) -> io.BytesIO:
    """Build a binary stdin containing the given framed requests, then EOF."""
    return io.BytesIO(b"".join(encode_request(r) for r in requests))


def _frames(stdout: io.StringIO) -> list[Any]:
    """Parse all response frames written to stdout."""
    return [parse_frame(line) for line in stdout.getvalue().splitlines() if line]


@pytest.fixture
def patched_stack(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch import + dispatch; record import count and dispatched requests.

    Returns a dict with ``import_calls`` (int) and ``dispatched`` (list of
    WorkerRequest) populated as the serve loop runs.
    """
    state: dict[str, Any] = {"import_calls": 0, "dispatched": []}

    def fake_import() -> None:
        state["import_calls"] += 1

    async def fake_dispatch(request: WorkerRequest, file: TextIO) -> None:
        state["dispatched"].append(request)
        # Emit one RESULT line the way the real run functions do, so the
        # framing writer wraps it into a ``msg`` frame.
        worker_mod._emit_line(
            AgenticMessage(
                type=AgenticMessageType.RESULT, content=f"ok:{request.prompt}",
            ),
            file=file,
        )

    monkeypatch.setattr(worker_mod, "_import_stack", fake_import)
    monkeypatch.setattr(worker_mod, "_dispatch_request", fake_dispatch)
    return state


class TestServeLifecycle:
    async def test_import_happens_once_across_many_commands(
        self, patched_stack: dict[str, Any],
    ) -> None:
        reqs = [
            WorkerRequest(mode="generate", prompt="a", model="m"),
            WorkerRequest(mode="generate", prompt="b", model="m"),
            WorkerRequest(mode="agentic", prompt="c", model="m", cwd="/w"),
        ]
        stdout = io.StringIO()

        await _serve(stdin=_requests_stdin(*reqs), stdout=stdout)

        # The stack is imported exactly once, regardless of command count.
        assert patched_stack["import_calls"] == 1
        # All three commands were dispatched, in order.
        assert [r.prompt for r in patched_stack["dispatched"]] == ["a", "b", "c"]

    async def test_one_result_and_done_per_command(
        self, patched_stack: dict[str, Any],
    ) -> None:
        reqs = [
            WorkerRequest(mode="generate", prompt="a", model="m"),
            WorkerRequest(mode="generate", prompt="b", model="m"),
        ]
        stdout = io.StringIO()

        await _serve(stdin=_requests_stdin(*reqs), stdout=stdout)

        frames = _frames(stdout)
        # Expect: msg(a), done, msg(b), done
        kinds = [f.frame for f in frames]
        assert kinds == ["msg", "done", "msg", "done"]

        first_result = AgenticMessage.model_validate_json(frames[0].msg)
        second_result = AgenticMessage.model_validate_json(frames[2].msg)
        assert first_result.content == "ok:a"
        assert second_result.content == "ok:b"

    async def test_eof_stops_loop(self, patched_stack: dict[str, Any]) -> None:
        stdout = io.StringIO()
        # Empty stdin → immediate clean EOF, no commands, no output.
        await _serve(stdin=io.BytesIO(b""), stdout=stdout)
        assert patched_stack["dispatched"] == []
        assert stdout.getvalue() == ""


class TestServeCrashRecovery:
    async def test_command_crash_emits_error_but_worker_survives(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import_calls = {"n": 0}

        def fake_import() -> None:
            import_calls["n"] += 1

        dispatched: list[str] = []

        async def flaky_dispatch(request: WorkerRequest, file: TextIO) -> None:
            dispatched.append(request.prompt)
            if request.prompt == "boom":
                raise RuntimeError("kaboom")
            worker_mod._emit_line(
                AgenticMessage(type=AgenticMessageType.RESULT, content="fine"),
                file=file,
            )

        monkeypatch.setattr(worker_mod, "_import_stack", fake_import)
        monkeypatch.setattr(worker_mod, "_dispatch_request", flaky_dispatch)

        reqs = [
            WorkerRequest(mode="generate", prompt="boom", model="m"),
            WorkerRequest(mode="generate", prompt="after", model="m"),
        ]
        stdout = io.StringIO()

        await _serve(stdin=_requests_stdin(*reqs), stdout=stdout)

        # Worker imported once and served BOTH commands despite the first crash.
        assert import_calls["n"] == 1
        assert dispatched == ["boom", "after"]

        frames = _frames(stdout)
        kinds = [f.frame for f in frames]
        # boom: error, done ; after: msg, done
        assert kinds == ["error", "done", "msg", "done"]
        assert "kaboom" in (frames[0].error or "")
        assert AgenticMessage.model_validate_json(frames[2].msg).content == "fine"

    async def test_partial_command_messages_still_framed_before_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Messages emitted before a mid-command crash are flushed, then error."""
        monkeypatch.setattr(worker_mod, "_import_stack", lambda: None)

        async def emit_then_crash(request: WorkerRequest, file: TextIO) -> None:
            worker_mod._emit_line(
                AgenticMessage(type=AgenticMessageType.THINKING, content="step"),
                file=file,
            )
            raise RuntimeError("mid-stream failure")

        monkeypatch.setattr(worker_mod, "_dispatch_request", emit_then_crash)

        req = WorkerRequest(mode="agentic", prompt="x", model="m", cwd="/w")
        stdout = io.StringIO()
        await _serve(stdin=_requests_stdin(req), stdout=stdout)

        frames = _frames(stdout)
        kinds = [f.frame for f in frames]
        assert kinds == ["msg", "error", "done"]
        assert AgenticMessage.model_validate_json(frames[0].msg).type == (
            AgenticMessageType.THINKING
        )
