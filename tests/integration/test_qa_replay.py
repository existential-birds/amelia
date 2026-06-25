"""Integration tests for the QA replay cassette format + recorder (Task 9).

Covers the cassette round-trip and the recorder-from-recorder seam that
feeds Task 12's ``amelia qa record``. Task 11 adds the ``ReplayDriver``
determinism test to this file.
"""

import pytest


pytestmark = pytest.mark.integration


def test_cassette_round_trips_scripts(tmp_path):
    from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverUsage
    from amelia.qa.replay import Cassette, load_cassette, save_cassette

    cassette = Cassette(
        scenario_id="s1",
        driver="api",
        invocations=[
            {
                "messages": [
                    AgenticMessage(type=AgenticMessageType.RESULT, content="plan")
                ],
                "usage": DriverUsage(
                    input_tokens=100,
                    output_tokens=50,
                    duration_ms=1500,
                    model="m",
                ),
            }
        ],
    )
    p = save_cassette(tmp_path, cassette)
    back = load_cassette(p)
    assert back.scenario_id == "s1"
    assert back.driver == "api"
    assert len(back.invocations) == 1
    assert back.invocations[0]["messages"][0].content == "plan"
    assert back.invocations[0]["usage"].duration_ms == 1500


def test_load_cassette_corrupt_file_raises(tmp_path):
    from amelia.qa.replay import load_cassette

    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ValueError):
        load_cassette(bad)


def test_load_cassette_missing_file_raises(tmp_path):
    """A missing cassette is an explicit error from load_cassette itself.

    The runner wraps this as a cell-level breach in replay mode (Task 12),
    so the loader itself must surface the missing file rather than silently
    return None.
    """
    from amelia.qa.replay import load_cassette

    with pytest.raises(FileNotFoundError):
        load_cassette(tmp_path / "absent.json")
