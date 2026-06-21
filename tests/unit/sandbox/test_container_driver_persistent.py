"""Tests for ContainerDriver's long-lived persistent-worker path.

These assert the lifecycle the long-lived worker guarantees, with the
transport faked at the WorkerProcess boundary:
  - the worker is spawned ONCE even across many agent calls (no per-call
    cold-start);
  - each call gets its own framed result stream, terminated by ``done``;
  - a worker error frame surfaces as a RuntimeError;
  - a worker that exits mid-command is detected and reset (next call respawns);
  - concurrent calls are serialized on the shared pipe.
"""

from __future__ import annotations

import asyncio

import pytest

from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage
from amelia.sandbox.driver import ContainerDriver
from amelia.sandbox.protocol import (
    WorkerRequest,
    done_frame,
    error_frame,
    msg_frame,
    read_request,
)


class FakeWorkerProcess:
    """In-memory duplex worker that replies per request from a script.

    ``responder`` maps a received WorkerRequest to the list of response-frame
    lines to emit (the test supplies msg/done/error frames). Tracks how many
    requests it served so tests can assert single-spawn reuse.
    """

    def __init__(self, responder, *, on_request=None) -> None:
        self._responder = responder
        self._on_request = on_request
        self._outbox: list[str] = []
        self.requests: list[WorkerRequest] = []
        self.alive = True
        self.closed = False

    async def write(self, data: bytes) -> None:
        import io

        request = read_request(io.BytesIO(data))
        assert request is not None
        self.requests.append(request)
        if self._on_request is not None:
            await self._on_request(self, request)
        if self.alive:
            self._outbox.extend(self._responder(request))

    async def readline(self) -> str:
        if self._outbox:
            return self._outbox.pop(0).rstrip("\n")
        # No buffered output: simulate EOF (worker exited).
        return ""

    async def close(self) -> None:
        self.closed = True
        self.alive = False


class FakeProvider:
    """Provider that hands out a single FakeWorkerProcess and counts spawns."""

    def __init__(self, worker: FakeWorkerProcess) -> None:
        self._worker = worker
        self.spawn_count = 0
        self.supports_persistent_worker = True

    async def ensure_running(self) -> None:
        return None

    def resolve_cwd(self, cwd: str) -> str:
        return cwd

    async def spawn_worker(self, cwd=None, env=None) -> FakeWorkerProcess:
        self.spawn_count += 1
        return self._worker


def _result_then_usage(content: str) -> list[str]:
    return [
        msg_frame(AgenticMessage(type=AgenticMessageType.RESULT, content=content)),
        msg_frame(
            AgenticMessage(
                type=AgenticMessageType.USAGE,
                usage=DriverUsage(input_tokens=1, output_tokens=2),
            )
        ),
        done_frame(),
    ]


class TestSpawnOnce:
    async def test_worker_spawned_once_across_many_calls(self) -> None:
        worker = FakeWorkerProcess(lambda req: _result_then_usage(f"r:{req.prompt}"))
        provider = FakeProvider(worker)
        driver = ContainerDriver(model="m", provider=provider)

        for prompt in ("a", "b", "c"):
            out, _ = await driver.generate(prompt=prompt)
            assert out == f"r:{prompt}"

        # One agentic call too — still the same worker.
        msgs: list[AgenticMessage] = []
        async for msg in driver.execute_agentic(prompt="d", cwd="/w"):
            msgs.append(msg)
        assert [m.content for m in msgs] == ["r:d"]

        # The expensive spawn (and its one-time import) happened exactly once.
        assert provider.spawn_count == 1
        assert worker.requests[0].mode == "generate"
        assert worker.requests[-1].mode == "agentic"
        assert worker.requests[-1].cwd == "/w"

    async def test_usage_captured_from_persistent_worker(self) -> None:
        worker = FakeWorkerProcess(lambda req: _result_then_usage("x"))
        provider = FakeProvider(worker)
        driver = ContainerDriver(model="m", provider=provider)

        await driver.generate(prompt="hello")
        usage = driver.get_usage()
        assert usage is not None
        assert usage.input_tokens == 1
        assert usage.output_tokens == 2

    async def test_agentic_excludes_usage_from_stream(self) -> None:
        worker = FakeWorkerProcess(lambda req: _result_then_usage("done"))
        provider = FakeProvider(worker)
        driver = ContainerDriver(model="m", provider=provider)

        types = [m.type async for m in driver.execute_agentic(prompt="go", cwd="/w")]
        assert AgenticMessageType.USAGE not in types
        assert AgenticMessageType.RESULT in types


class TestErrorPropagation:
    async def test_error_frame_raises(self) -> None:
        worker = FakeWorkerProcess(
            lambda req: [error_frame("worker blew up"), done_frame()]
        )
        provider = FakeProvider(worker)
        driver = ContainerDriver(model="m", provider=provider)

        with pytest.raises(RuntimeError, match="worker blew up"):
            await driver.generate(prompt="x")

    async def test_error_then_success_on_same_worker_not_corrupted(self) -> None:
        """After an error command, the trailing ``done`` must not corrupt the next.

        Regression: the protocol emits ``error`` then ``done``. If the driver
        raised on ``error`` without consuming the ``done``, the next command
        would read that stale ``done`` first and return an empty stream.
        """

        def responder(req: WorkerRequest) -> list[str]:
            if req.prompt == "bad":
                return [error_frame("boom"), done_frame()]
            return _result_then_usage(f"ok:{req.prompt}")

        worker = FakeWorkerProcess(responder)
        provider = FakeProvider(worker)
        driver = ContainerDriver(model="m", provider=provider)

        with pytest.raises(RuntimeError, match="boom"):
            await driver.generate(prompt="bad")

        # Same worker (no respawn), next command returns its real result.
        out, _ = await driver.generate(prompt="good")
        assert out == "ok:good"
        assert provider.spawn_count == 1

    async def test_worker_crash_midcommand_detected_and_resets(self) -> None:
        """A worker that exits before ``done`` raises, then the next call respawns."""
        # First request: responder yields NOTHING (no done) -> readline EOF.
        # Second request: a fresh worker that responds normally.
        crashing = FakeWorkerProcess(lambda req: [])  # no frames -> EOF
        healthy = FakeWorkerProcess(lambda req: _result_then_usage("recovered"))

        class TwoWorkerProvider(FakeProvider):
            def __init__(self) -> None:
                super().__init__(crashing)
                self._workers = [crashing, healthy]

            async def spawn_worker(self, cwd=None, env=None):
                self.spawn_count += 1
                return self._workers.pop(0)

        provider = TwoWorkerProvider()
        driver = ContainerDriver(model="m", provider=provider)

        with pytest.raises(RuntimeError, match="exited unexpectedly"):
            await driver.generate(prompt="first")

        # The crashed worker is dropped and closed so it cannot serve stale frames.
        assert crashing.closed is True

        # Next call respawns a fresh worker and succeeds.
        out, _ = await driver.generate(prompt="second")
        assert out == "recovered"
        assert provider.spawn_count == 2


class TestEarlyExitResetsWorker:
    """A dispatch that unwinds before ``done`` must close the worker.

    Otherwise unread frames from the abandoned command stay buffered on the
    shared pipe and the next command reads them as its own output.
    """

    async def test_caller_cancellation_midstream_resets_worker(self) -> None:
        # First command streams two messages then ``done``; the caller stops
        # consuming after the first, leaving the second msg + done unread.
        def responder(req: WorkerRequest) -> list[str]:
            if req.prompt == "partial":
                return [
                    msg_frame(AgenticMessage(type=AgenticMessageType.RESULT, content="a")),
                    msg_frame(AgenticMessage(type=AgenticMessageType.RESULT, content="b")),
                    done_frame(),
                ]
            return _result_then_usage(f"r:{req.prompt}")

        leaky = FakeWorkerProcess(responder)
        healthy = FakeWorkerProcess(responder)

        class TwoWorkerProvider(FakeProvider):
            def __init__(self) -> None:
                super().__init__(leaky)
                self._workers = [leaky, healthy]

            async def spawn_worker(self, cwd=None, env=None):
                self.spawn_count += 1
                return self._workers.pop(0)

        provider = TwoWorkerProvider()
        driver = ContainerDriver(model="m", provider=provider)

        # Drive the production entrypoint and cancel mid-stream, exactly as a
        # caller that stops consuming would. ``aclosing`` in execute_agentic must
        # propagate the close down to dispatch so the worker is reset.
        stream = driver.execute_agentic(prompt="partial", cwd="/w")
        first = await stream.__anext__()
        assert first.content == "a"
        await stream.aclose()  # caller stops consuming mid-command

        # The abandoned worker was closed; the next call respawns a clean one
        # and gets its own result rather than the leaked "b"/done frames.
        assert leaky.closed is True
        out, _ = await driver.generate(prompt="next")
        assert out == "r:next"
        assert provider.spawn_count == 2

    async def test_parse_failure_midcommand_resets_worker(self) -> None:
        # First command emits a structurally valid frame whose payload is not a
        # valid AgenticMessage, so model_validate_json raises before ``done``.
        def responder(req: WorkerRequest) -> list[str]:
            if req.prompt == "garbage":
                return ['{"frame": "msg", "msg": "not-a-message"}', done_frame()]
            return _result_then_usage(f"r:{req.prompt}")

        leaky = FakeWorkerProcess(responder)
        healthy = FakeWorkerProcess(responder)

        class TwoWorkerProvider(FakeProvider):
            def __init__(self) -> None:
                super().__init__(leaky)
                self._workers = [leaky, healthy]

            async def spawn_worker(self, cwd=None, env=None):
                self.spawn_count += 1
                return self._workers.pop(0)

        provider = TwoWorkerProvider()
        driver = ContainerDriver(model="m", provider=provider)

        with pytest.raises(RuntimeError, match="Failed to parse worker output"):
            await driver.generate(prompt="garbage")

        assert leaky.closed is True
        out, _ = await driver.generate(prompt="next")
        assert out == "r:next"
        assert provider.spawn_count == 2


class TestSerialization:
    async def test_concurrent_calls_are_serialized(self) -> None:
        """Two concurrent dispatches never interleave their request frames."""
        active = {"n": 0, "max": 0}

        async def gate(worker: FakeWorkerProcess, req: WorkerRequest) -> None:
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
            await asyncio.sleep(0.01)  # hold the "command" open
            active["n"] -= 1

        worker = FakeWorkerProcess(
            lambda req: _result_then_usage(req.prompt), on_request=gate,
        )
        provider = FakeProvider(worker)
        driver = ContainerDriver(model="m", provider=provider)

        results = await asyncio.gather(
            driver.generate(prompt="one"),
            driver.generate(prompt="two"),
            driver.generate(prompt="three"),
        )

        assert {r[0] for r in results} == {"one", "two", "three"}
        # The lock guarantees at most one command in flight at a time.
        assert active["max"] == 1
        assert provider.spawn_count == 1
