"""Wire protocol for the long-lived sandbox worker.

The driver runs a single long-lived worker process inside the sandbox that
imports the heavy LangChain/deepagents stack ONCE at startup, then services
many commands over its stdin/stdout. This module defines the framing for
that channel so the cost of importing the stack is paid once per sandbox
lifetime instead of once per agent call.

Request framing (host -> worker, binary stdin):
    A request is a single length-prefixed JSON object:
        [4-byte big-endian unsigned length][UTF-8 JSON payload]
    The length prefix makes the boundary unambiguous and lets the worker
    tolerate partial reads on the pipe.

Response framing (worker -> host, line-oriented stdout):
    The worker streams newline-delimited JSON objects. Each line is a
    ``ResponseFrame``:
      - ``{"frame": "msg", "msg": <AgenticMessage JSON>}`` — one streamed
        message (thinking / tool_call / tool_result / result / usage).
      - ``{"frame": "done"}`` — terminates the current command. The driver
        stops reading for this command when it sees this frame.
      - ``{"frame": "error", "error": "<message>"}`` — the command failed.
        The worker survives and stays ready for the next command; the driver
        raises. ``error`` is always followed by ``done``.

Line orientation (rather than length-prefixing responses too) is deliberate:
the existing parser is line-based, and the worker may emit an unbounded number
of streamed messages per command, so a streaming line protocol is the natural
fit.
"""

from __future__ import annotations

import struct
from typing import IO, Literal

from pydantic import BaseModel


# Number of bytes in the big-endian unsigned request length prefix.
LENGTH_PREFIX_BYTES = 4
_LENGTH_STRUCT = struct.Struct(">I")

# Guard against a corrupt/garbage length prefix asking us to allocate GBs.
MAX_REQUEST_BYTES = 64 * 1024 * 1024


class WorkerRequest(BaseModel):
    """A single command sent to the long-lived worker.

    ``mode`` selects the operation; the remaining fields mirror the CLI
    arguments the per-call worker used to take.
    """

    mode: Literal["agentic", "generate"]
    prompt: str
    model: str
    cwd: str | None = None
    instructions: str | None = None
    schema_path: str | None = None


class ResponseFrame(BaseModel):
    """One line of worker output.

    Exactly one of the optional payloads is set depending on ``frame``.
    """

    frame: Literal["msg", "done", "error"]
    # Raw AgenticMessage JSON string for frame == "msg". Kept as a string so
    # this module does not need to import the (worker-local) AgenticMessage
    # type; the driver re-parses it with its own model.
    msg: str | None = None
    error: str | None = None


def encode_request(request: WorkerRequest) -> bytes:
    """Serialize a request to a length-prefixed frame.

    Args:
        request: The command to send.

    Returns:
        ``[4-byte big-endian length][JSON]`` ready to write to the worker's
        stdin.

    Raises:
        ValueError: If the serialized payload exceeds ``MAX_REQUEST_BYTES``.
            Rejecting here fails locally instead of killing the worker when it
            rejects the oversized frame on the read side.
    """
    payload = request.model_dump_json().encode("utf-8")
    if len(payload) > MAX_REQUEST_BYTES:
        raise ValueError(
            f"Request is too large: {len(payload)} bytes (max {MAX_REQUEST_BYTES})"
        )
    return _LENGTH_STRUCT.pack(len(payload)) + payload


def _read_exactly(stream: IO[bytes], count: int) -> bytes | None:
    """Read exactly ``count`` bytes, tolerating partial reads.

    Args:
        stream: Binary input stream.
        count: Number of bytes required.

    Returns:
        The bytes, or ``None`` if EOF is reached before the first byte arrives
        (clean EOF — no message started).

    Raises:
        EOFError: If EOF arrives after at least one byte has been read
            (truncated frame — a protocol error).
    """
    chunks: list[bytes] = []
    remaining = count
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            if chunks:
                raise EOFError(
                    f"Truncated read: expected {count} bytes, got {count - remaining}"
                )
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_request(stream: IO[bytes]) -> WorkerRequest | None:
    """Read one length-prefixed request from a binary stream.

    Handles partial reads by looping until the full frame is available.

    Args:
        stream: Binary input stream (the worker's stdin buffer).

    Returns:
        The parsed request, or ``None`` on clean EOF (no more commands).

    Raises:
        EOFError: If EOF arrives mid-header (truncated length prefix).
        ValueError: If the length prefix is corrupt or implausibly large,
            or if EOF arrives mid-payload.
    """
    header = _read_exactly(stream, LENGTH_PREFIX_BYTES)
    if header is None:
        return None
    (length,) = _LENGTH_STRUCT.unpack(header)
    if length == 0 or length > MAX_REQUEST_BYTES:
        raise ValueError(f"Invalid request length: {length}")
    try:
        payload = _read_exactly(stream, length)
    except EOFError as exc:
        raise ValueError("Truncated request") from exc
    if payload is None:
        raise ValueError("Truncated request: EOF before payload complete")
    return WorkerRequest.model_validate_json(payload)


def msg_frame(msg: BaseModel) -> str:
    """Build a ``msg`` response line for a streamed message.

    Args:
        msg: An AgenticMessage (or compatible model) to forward.

    Returns:
        A newline-terminated JSON ``ResponseFrame`` line.
    """
    return msg_frame_raw(msg.model_dump_json())


def msg_frame_raw(msg_json: str) -> str:
    """Build a ``msg`` response line from a pre-serialized AgenticMessage.

    Args:
        msg_json: An already-JSON-encoded AgenticMessage.

    Returns:
        A newline-terminated JSON ``ResponseFrame`` line.
    """
    return ResponseFrame(frame="msg", msg=msg_json).model_dump_json() + "\n"


def done_frame() -> str:
    """Build the terminating ``done`` response line for a command."""
    return ResponseFrame(frame="done").model_dump_json() + "\n"


def error_frame(error: str) -> str:
    """Build an ``error`` response line.

    Args:
        error: Human-readable failure description.

    Returns:
        A newline-terminated JSON ``ResponseFrame`` line.
    """
    return ResponseFrame(frame="error", error=error).model_dump_json() + "\n"


def parse_frame(line: str) -> ResponseFrame:
    """Parse one worker output line into a ResponseFrame.

    Args:
        line: A single JSON line emitted by the worker.

    Returns:
        The parsed frame.

    Raises:
        ValueError: If the line is not a valid ResponseFrame.
    """
    try:
        return ResponseFrame.model_validate_json(line)
    except Exception as exc:  # noqa: BLE001 - normalize to ValueError for callers
        raise ValueError(f"Malformed worker frame: {line[:200]}") from exc
