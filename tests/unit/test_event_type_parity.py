"""Parity guard between the backend event enums and the dashboard's
hand-maintained TypeScript event unions.

There is no codegen between the Python models and the dashboard types, so the
two drift silently (see issue #609). This test fails loudly whenever a backend
enum and its TypeScript mirror disagree.

Both sides map 1:1:

* backend ``EventType``          ↔ dashboard ``EventType``           (events.ts)
* backend ``BrainstormEventType`` ↔ dashboard ``BrainstormEventType`` (events.ts)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from amelia.server.models.events import BrainstormEventType, EventType


# dashboard/src/types/events.ts relative to the repo root (this file lives at
# <root>/tests/unit/).
_EVENTS_TS = (
    Path(__file__).resolve().parents[2] / "dashboard" / "src" / "types" / "events.ts"
)


def _extract_union(source: str, type_name: str) -> set[str]:
    """Extract the string-literal members of an exported TS union type.

    Tolerant of inline ``// ...`` comments between union members.
    """
    match = re.search(rf"export type {type_name} =(.*?);", source, re.DOTALL)
    assert match is not None, f"could not find `export type {type_name}` in events.ts"
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


def test_events_ts_exists() -> None:
    assert _EVENTS_TS.is_file(), f"expected dashboard types at {_EVENTS_TS}"


@pytest.mark.parametrize(
    "ts_type_name,backend_enum",
    [
        ("EventType", EventType),
        ("BrainstormEventType", BrainstormEventType),
    ],
)
def test_event_enum_matches_backend(
    ts_type_name: str, backend_enum: type[EventType] | type[BrainstormEventType]
) -> None:
    """Dashboard union must equal the backend enum's values exactly."""
    ts_values = _extract_union(_EVENTS_TS.read_text(), ts_type_name)
    expected = {member.value for member in backend_enum}

    missing_in_ts = expected - ts_values
    extra_in_ts = ts_values - expected
    assert not missing_in_ts, f"{ts_type_name} missing backend values: {sorted(missing_in_ts)}"
    assert not extra_in_ts, f"{ts_type_name} has values not in backend: {sorted(extra_in_ts)}"
