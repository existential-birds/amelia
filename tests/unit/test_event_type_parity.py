"""Parity guard between the backend ``EventType`` enum and the dashboard's
hand-maintained TypeScript event unions.

There is no codegen between the Python models and the dashboard types, so the
two drift silently (see issue #609). This test fails loudly whenever the backend
enum and the TypeScript unions disagree.

The backend defines a single ``EventType`` StrEnum. The dashboard splits it into
two unions because brainstorm events are serialized differently over the
WebSocket (see ``amelia/server/events/connection_manager.py``):

* Non-brainstorm events are sent wrapped with the raw backend value, so the
  dashboard ``EventType`` must equal the backend enum MINUS the ``brainstorm_*``
  members.
* Brainstorm events are sent flat with the ``brainstorm_`` prefix stripped, so
  the dashboard ``BrainstormEventType`` must equal the backend ``brainstorm_*``
  members WITHOUT the prefix.
"""

from __future__ import annotations

import re
from pathlib import Path

from amelia.server.models.events import EventType


_BRAINSTORM_PREFIX = "brainstorm_"

# dashboard/src/types/events.ts relative to the repo root (this file lives at
# <root>/tests/unit/).
_EVENTS_TS = (
    Path(__file__).resolve().parents[2] / "dashboard" / "src" / "types" / "events.ts"
)


def _extract_union(source: str, type_name: str) -> set[str]:
    """Extract the string-literal members of an exported TS union type.

    Tolerant of inline ``// ...`` comments between union members.
    """
    match = re.search(
        rf"export type {type_name} =(.*?);",
        source,
        re.DOTALL,
    )
    assert match is not None, f"could not find `export type {type_name}` in events.ts"
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


def _backend_values() -> set[str]:
    return {member.value for member in EventType}


def _expected_event_type() -> set[str]:
    return {v for v in _backend_values() if not v.startswith(_BRAINSTORM_PREFIX)}


def _expected_brainstorm_event_type() -> set[str]:
    return {
        v.removeprefix(_BRAINSTORM_PREFIX)
        for v in _backend_values()
        if v.startswith(_BRAINSTORM_PREFIX)
    }


def test_events_ts_exists() -> None:
    assert _EVENTS_TS.is_file(), f"expected dashboard types at {_EVENTS_TS}"


def test_event_type_matches_backend() -> None:
    """Dashboard ``EventType`` == backend enum minus ``brainstorm_*``."""
    ts_values = _extract_union(_EVENTS_TS.read_text(), "EventType")
    expected = _expected_event_type()

    missing_in_ts = expected - ts_values
    extra_in_ts = ts_values - expected
    assert not missing_in_ts, f"EventType missing backend values: {sorted(missing_in_ts)}"
    assert not extra_in_ts, f"EventType has values not in backend: {sorted(extra_in_ts)}"


def test_brainstorm_event_type_matches_backend() -> None:
    """Dashboard ``BrainstormEventType`` == backend ``brainstorm_*`` (prefix stripped)."""
    ts_values = _extract_union(_EVENTS_TS.read_text(), "BrainstormEventType")
    expected = _expected_brainstorm_event_type()

    missing_in_ts = expected - ts_values
    extra_in_ts = ts_values - expected
    assert not missing_in_ts, (
        f"BrainstormEventType missing backend values: {sorted(missing_in_ts)}"
    )
    assert not extra_in_ts, (
        f"BrainstormEventType has values not in backend: {sorted(extra_in_ts)}"
    )
