"""Tests for the long-lived worker wire protocol framing.

These assert observable consequences of the framing: a request round-trips
through encode/read, partial reads on the pipe are tolerated, EOF is a clean
end-of-stream, corrupt prefixes are rejected, and response frames serialize
the way the driver expects to parse them.
"""

from __future__ import annotations

import io
import struct

import pytest

from amelia.sandbox.protocol import (
    LENGTH_PREFIX_BYTES,
    MAX_REQUEST_BYTES,
    ResponseFrame,
    WorkerRequest,
    done_frame,
    encode_request,
    error_frame,
    msg_frame,
    parse_frame,
    read_request,
)
from amelia.sandbox.worker import AgenticMessage, AgenticMessageType


class _PartialStream(io.RawIOBase):
    """Binary stream that yields at most ``chunk`` bytes per read().

    Simulates a pipe that returns short reads, forcing the reader to loop.
    """

    def __init__(self, data: bytes, chunk: int) -> None:
        self._data = data
        self._pos = 0
        self._chunk = chunk

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        if self._pos >= len(self._data):
            return b""
        n = min(size if size > 0 else self._chunk, self._chunk)
        out = self._data[self._pos : self._pos + n]
        self._pos += len(out)
        return out


class TestRequestRoundTrip:
    def test_encode_then_read_round_trips(self) -> None:
        req = WorkerRequest(
            mode="agentic", prompt="do x", model="m", cwd="/work", instructions="be terse",
        )
        stream = io.BytesIO(encode_request(req))
        out = read_request(stream)
        assert out == req

    def test_encode_uses_4_byte_big_endian_prefix(self) -> None:
        req = WorkerRequest(mode="generate", prompt="hi", model="m")
        frame = encode_request(req)
        (length,) = struct.unpack(">I", frame[:LENGTH_PREFIX_BYTES])
        assert length == len(frame) - LENGTH_PREFIX_BYTES

    def test_two_requests_read_sequentially_from_one_stream(self) -> None:
        a = WorkerRequest(mode="generate", prompt="first", model="m")
        b = WorkerRequest(mode="agentic", prompt="second", model="m", cwd="/w")
        stream = io.BytesIO(encode_request(a) + encode_request(b))
        assert read_request(stream) == a
        assert read_request(stream) == b
        assert read_request(stream) is None  # clean EOF after both


class TestPartialReads:
    @pytest.mark.parametrize("chunk", [1, 2, 3, 5, 7])
    def test_request_survives_short_reads(self, chunk: int) -> None:
        req = WorkerRequest(
            mode="agentic", prompt="a longer prompt that spans many bytes", model="model-x", cwd="/w",
        )
        stream = _PartialStream(encode_request(req), chunk=chunk)
        assert read_request(stream) == req


class TestEofAndErrors:
    def test_clean_eof_returns_none(self) -> None:
        assert read_request(io.BytesIO(b"")) is None

    def test_truncated_payload_raises(self) -> None:
        req = WorkerRequest(mode="generate", prompt="hello", model="m")
        frame = encode_request(req)
        # Drop the last 3 bytes of the payload.
        stream = io.BytesIO(frame[:-3])
        with pytest.raises(ValueError, match="Truncated request"):
            read_request(stream)

    def test_zero_length_prefix_raises(self) -> None:
        stream = io.BytesIO(struct.pack(">I", 0))
        with pytest.raises(ValueError, match="Invalid request length"):
            read_request(stream)

    def test_implausibly_large_prefix_raises(self) -> None:
        stream = io.BytesIO(struct.pack(">I", MAX_REQUEST_BYTES + 1))
        with pytest.raises(ValueError, match="Invalid request length"):
            read_request(stream)

    def test_encode_rejects_oversized_request(self) -> None:
        req = WorkerRequest(
            mode="generate", prompt="x" * (MAX_REQUEST_BYTES + 1), model="m",
        )
        with pytest.raises(ValueError, match="Request is too large"):
            encode_request(req)


class TestResponseFrames:
    def test_msg_frame_carries_agentic_message(self) -> None:
        m = AgenticMessage(type=AgenticMessageType.RESULT, content="done")
        line = msg_frame(m)
        assert line.endswith("\n")
        frame = parse_frame(line)
        assert frame.frame == "msg"
        assert frame.msg is not None
        restored = AgenticMessage.model_validate_json(frame.msg)
        assert restored.content == "done"

    def test_done_frame_round_trips(self) -> None:
        frame = parse_frame(done_frame())
        assert frame.frame == "done"

    def test_error_frame_carries_message(self) -> None:
        frame = parse_frame(error_frame("boom"))
        assert frame.frame == "error"
        assert frame.error == "boom"

    def test_parse_rejects_garbage(self) -> None:
        with pytest.raises(ValueError, match="Malformed worker frame"):
            parse_frame("not json at all")

    def test_response_frame_is_pydantic(self) -> None:
        assert issubclass(ResponseFrame, __import__("pydantic").BaseModel)
