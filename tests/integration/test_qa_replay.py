"""Integration tests for the QA replay cassette format + recorder (Task 9).

Covers the cassette round-trip and the recorder-from-recorder seam that
feeds Task 12's ``amelia qa record``. Task 11 adds the ``ReplayDriver``
determinism test to this file.
"""

import pytest

from amelia.core.types import Profile
from amelia.drivers.base import (
    AgenticMessage,
    AgenticMessageType,
    DriverUsage,
)
from amelia.qa.replay import Cassette
from amelia.server.database.connection import Database
from amelia.server.orchestrator.service import OrchestratorService
from tests.integration.conftest import (
    _architect_messages,
    _wait_for_status,
    make_agentic_messages,
    make_reviewer_agentic_messages,
)


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _api_key(mock_api_key: None) -> None:
    """Allow driver construction during this test module."""


def _cassette_from_e2e_scripts() -> Cassette:
    """Build a deterministic cassette matching the e2e scripted-driver shape.

    Three invocations (architect / developer / reviewer), each carrying the
    AgenticMessage stream and the per-invocation usage that the recording
    seam captures. This is the same shape ``_scripted_execute_agentic``
    plays in the e2e test, sourced from a :class:`Cassette` instead.
    """

    def _inv(messages: list[AgenticMessage]) -> dict:
        return {
            "messages": messages,
            "usage": DriverUsage(
                input_tokens=100,
                output_tokens=50,
                duration_ms=1500,
                model="replay",
            ),
        }

    return Cassette(
        scenario_id="s1",
        driver="api",
        invocations=[
            _inv(_architect_messages()),
            _inv(make_agentic_messages()),
            _inv(make_reviewer_agentic_messages(approved=True)),
        ],
    )


def test_cassette_round_trips_scripts(tmp_path):
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


async def test_replay_run_is_deterministic(
    orchestrator: OrchestratorService,
    test_db: Database,
    api_profile: Profile,
    valid_worktree: str,
) -> None:
    """A replay run produces identical metrics across two runs (same cassette).

    Drives ``OrchestratorService.start_workflow(driver_override=...)`` with
    a fresh :class:`ReplayDriver` per run, no ``patch.object`` anywhere.
    The two runs must complete with byte-identical status / tokens / cost.

    The worktree is reset between runs because the developer's TOOL_CALL
    messages translate into real file writes — replay replays the LLM
    stream, not the filesystem side effects, so run 2 starts from a clean
    tree just like run 1.
    """
    import subprocess

    from amelia.qa.replay import ReplayDriver

    cassette = _cassette_from_e2e_scripts()
    seen: list[tuple[str, int | None, float | None]] = []
    for run_idx in range(2):
        # Reset any files the developer wrote in the prior run so the dirty
        # check passes. This mirrors what real CI does between QA runs.
        subprocess.run(
            ["git", "checkout", "--", "."],
            cwd=valid_worktree,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=valid_worktree,
            check=True,
            capture_output=True,
        )
        # A fresh ReplayDriver per run — the script is consumed once through.
        override = ReplayDriver(cassette)
        workflow_id = await orchestrator.start_workflow(
            issue_id=f"REP-{run_idx + 1}",
            worktree_path=valid_worktree,
            task_title="t",
            task_description="d",
            driver="api",
            driver_override=override,
        )
        await _wait_for_status(test_db, workflow_id, "blocked")
        await orchestrator.approve_workflow(workflow_id)
        row = await test_db.fetch_one(
            "SELECT status, total_tokens, total_cost_usd FROM workflows WHERE id = $1",
            workflow_id,
        )
        assert row is not None
        seen.append((row["status"], row["total_tokens"], row["total_cost_usd"]))
    assert seen[0][0] == "completed", f"first run did not complete: {seen[0]}"
    assert seen[0] == seen[1], (
        f"replay not deterministic across runs: first={seen[0]} second={seen[1]}"
    )


def test_replay_driver_empty_cassette_raises_on_first_call() -> None:
    """An empty cassette fails fast at first ``execute_agentic`` (no hang)."""
    from collections.abc import AsyncIterator

    from amelia.qa.replay import ReplayDriver

    empty = Cassette(scenario_id="s", driver="api", invocations=[])
    driver = ReplayDriver(empty)

    async def _drive() -> None:
        gen: AsyncIterator[AgenticMessage] = driver.execute_agentic(
            "p", cwd=".", session_id="s"
        )
        async for _ in gen:
            pass

    import asyncio

    with pytest.raises(ValueError, match="no invocations"):
        asyncio.run(_drive())

