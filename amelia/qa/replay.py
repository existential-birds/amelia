"""Replay cassette format + recorder.

A :class:`Cassette` is the deterministic, JSON-serializable snapshot of one
(scenario, driver) run: an ordered list of :class:`InvocationScript` entries,
each carrying the per-invocation ``AgenticMessage`` stream and the resolved
:class:`DriverUsage` (with ``duration_ms``) captured by the recording seam.

Phase B consumes cassettes in two directions:

* **Record** (``amelia qa record``, Task 12): run the suite once live, then
  build a :class:`Cassette` from each workflow's finalized
  :class:`~amelia.trajectory.recorder.WorkflowTrajectoryRecorder` via
  :func:`record_cassette_from_recorder`.
* **Replay** (``amelia qa run --mode replay``, Task 11/12): load a cassette
  and feed it to a :class:`ReplayDriver` that yields the recorded messages
  with their recorded usage — no live LLM calls, deterministic metrics.

The cassette file format is plain JSON (Pydantic ``model_dump_json`` with
``mode="json"``), so it diffs cleanly in code review and survives schema
evolution via Pydantic's validation-on-load.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from pydantic import BaseModel, ValidationError

from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverUsage,
)


if TYPE_CHECKING:
    from amelia.trajectory.recorder import WorkflowTrajectoryRecorder


class InvocationScript(TypedDict):
    """One recorded ``execute_agentic`` invocation.

    Attributes:
        messages: The ordered ``AgenticMessage`` stream yielded by the
            driver for this invocation, verbatim. A replay driver re-yields
            these in order.
        usage: The per-invocation ``DriverUsage`` captured when the stream
            closed (includes ``duration_ms``). A replay driver sets this as
            its own usage so the recording seam reads deterministic
            token/cost/duration values.
    """

    messages: list[AgenticMessage]
    usage: DriverUsage


class Cassette(BaseModel):
    """A deterministic replay cassette for one (scenario, driver) cell."""

    scenario_id: str
    driver: str
    invocations: list[InvocationScript]


def _atomic_write_text(path: Path, text: str) -> None:
    """Write *text* to *path* atomically (temp file + ``os.replace``).

    Mirrors the atomic-write discipline of
    :func:`amelia.trajectory.store.write_atomic` so a partially written
    cassette never appears on disk (e.g. process killed mid-write).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        # Clean up the temp file if anything went wrong before the rename.
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def cassette_filename(scenario_id: str, driver: str) -> str:
    """Return the canonical cassette filename for a cell.

    Mirrors :func:`amelia.qa.baseline._baseline_filename` so a scenario's
    baseline and cassette share a stable on-disk key.
    """
    return f"{scenario_id}__{driver}.json"


def save_cassette(directory: Path, cassette: Cassette) -> Path:
    """Atomically write *cassette* to ``{directory}/{scenario_id}__{driver}.json``.

    Overwrites an existing cassette for the cell (re-recording path).
    Returns the final path of the written file.
    """
    path = directory / cassette_filename(cassette.scenario_id, cassette.driver)
    _atomic_write_text(path, cassette.model_dump_json(indent=2))
    return path


def load_cassette(path: Path) -> Cassette:
    """Load and validate a cassette from *path*.

    Args:
        path: Cassette JSON file to load.

    Returns:
        The validated :class:`Cassette`.

    Raises:
        FileNotFoundError: If *path* does not exist (callers that want
            optional behavior can ``path.exists()`` first).
        ValueError: If the file is unreadable as JSON or fails Cassette
            validation (corrupt or schema-mismatched cassette).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    try:
        return Cassette.model_validate_json(text)
    except (ValidationError, ValueError) as exc:
        raise ValueError(f"Corrupt cassette at {path}: {exc}") from exc


def _metrics_to_agentic_message(step: object) -> list[AgenticMessage]:
    """Reverse-map one ATIF Step (from a recorder) back to AgenticMessages.

    The forward map (:func:`amelia.trajectory.mapping.map_messages`) collapses
    some structure (a TOOL_CALL and its TOOL_RESULT become one Step); this
    helper reproduces the canonical THINKING -> TOOL_CALL -> TOOL_RESULT ->
    RESULT sequence for the simple shapes the e2e corpus produces. Complex
    multi-tool spans survive as separate TOOL_CALL / TOOL_RESULT messages
    in stream order, which is the same shape ``_scripted_execute_agentic``
    plays back.
    """
    # Lazy import to keep module import cheap and avoid a hard ATIF dep
    # for callers that only want the cassette I/O.
    from harbor.models.trajectories import Step  # noqa: PLC0415

    if not isinstance(step, Step):  # pragma: no cover - defensive
        return []

    out: list[AgenticMessage] = []
    if getattr(step, "reasoning_content", None):
        out.append(
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content=step.reasoning_content,
                model=getattr(step, "model_name", None),
            )
        )
    for call in step.tool_calls or []:
        out.append(
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name=call.function_name,
                tool_input=call.arguments,
                tool_call_id=call.tool_call_id,
                model=getattr(step, "model_name", None),
            )
        )
    if step.observation:
        for result in step.observation.results:
            out.append(
                AgenticMessage(
                    type=AgenticMessageType.TOOL_RESULT,
                    tool_output=result.content,
                    tool_call_id=result.source_call_id,
                    is_error=bool((result.extra or {}).get("is_error")),
                    model=getattr(step, "model_name", None),
                )
            )
    # A pure RESULT step has tool_calls=[] and observation=None; its message
    # text is the agent's final output.
    if not step.tool_calls and not step.observation and step.message:
        out.append(
            AgenticMessage(
                type=AgenticMessageType.RESULT,
                content=step.message,
                model=getattr(step, "model_name", None),
            )
        )
    return out


def _invocation_to_script(invocation: object) -> InvocationScript:
    """Build an :class:`InvocationScript` from a finalized invocation recorder.

    Reconstructs the ``AgenticMessage`` stream from the invocation's ATIF
    steps and derives a ``DriverUsage`` from its ``final_metrics`` /
    ``duration_ms``. The prompt/system steps are NOT replayed (the replay
    driver ignores the prompt arg), so only ``source="agent"`` steps
    contribute messages.
    """
    # AgentInvocationRecorder is private; read its public-ish fields directly.
    steps = getattr(invocation, "_steps", [])
    final_metrics = getattr(invocation, "_final_metrics", None)
    duration_ms = getattr(invocation, "_duration_ms", None)

    messages: list[AgenticMessage] = []
    for step in steps:
        # Skip the prompt scaffolding (system / user steps) — only the agent
        # stream is replayed. The replay driver ignores the prompt argument.
        source = getattr(step, "source", None)
        if source != "agent":
            continue
        messages.extend(_metrics_to_agentic_message(step))

    input_tokens = (
        getattr(final_metrics, "total_prompt_tokens", None)
        if final_metrics is not None
        else None
    )
    output_tokens = (
        getattr(final_metrics, "total_completion_tokens", None)
        if final_metrics is not None
        else None
    )
    cached_tokens = (
        getattr(final_metrics, "total_cached_tokens", None)
        if final_metrics is not None
        else None
    )
    cost_usd = (
        getattr(final_metrics, "total_cost_usd", None)
        if final_metrics is not None
        else None
    )
    usage = DriverUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cached_tokens,
        cost_usd=cost_usd,
        duration_ms=duration_ms,
    )
    return InvocationScript(messages=messages, usage=usage)


def record_cassette_from_recorder(
    recorder: WorkflowTrajectoryRecorder,
    scenario_id: str,
    driver: str,
) -> Cassette:
    """Build a :class:`Cassette` from a finalized workflow recorder.

    Walks the recorder's per-invocation records, reconstructs each
    invocation's ``AgenticMessage`` stream + usage, and returns a cassette
    ready for :func:`save_cassette`. The recorder must have captured at
    least one invocation — an empty recorder raises ``ValueError`` so the
    caller (``amelia qa record``) can surface "nothing recorded" as a
    real error rather than silently writing an empty cassette.
    """
    invocations = list(getattr(recorder, "_invocations", []))
    if not invocations:
        raise ValueError(
            f"cannot build cassette for {scenario_id}/{driver}: "
            "recorder has no invocations"
        )
    return Cassette(
        scenario_id=scenario_id,
        driver=driver,
        invocations=[_invocation_to_script(inv) for inv in invocations],
    )
