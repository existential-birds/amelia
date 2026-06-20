"""Tracker fetches must not block the event loop (issue #644).

``GithubTracker.get_issue`` shells out via blocking ``subprocess.run`` and
``JiraTracker.get_issue`` does a blocking sync ``httpx.get``. When called
directly from an ``async def`` they freeze the event loop for the entire
fetch duration, stalling every other in-flight coroutine (other workflows,
the PR poller, the event bus).

The fix off-loads each blocking call via ``asyncio.to_thread``. These tests
assert the *observable consequence*: while a slow ``get_issue`` is in flight,
a concurrent coroutine still makes progress. They fail if the call runs on
the loop because the concurrent coroutine never advances (timeout).
"""

import asyncio
import threading
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from amelia.core.types import AgentConfig, DriverType, Issue, Profile, TrackerType
from amelia.pipelines.implementation.state import rebuild_implementation_state


rebuild_implementation_state()

from amelia.server.database.repository import WorkflowRepository  # noqa: E402
from amelia.server.events.bus import EventBus  # noqa: E402
from amelia.server.models import ServerExecutionState  # noqa: E402
from amelia.server.models.state import WorkflowStatus  # noqa: E402
from amelia.server.orchestrator.event_emitter import StreamEventEmitter  # noqa: E402
from amelia.server.orchestrator.runner import GraphRunner  # noqa: E402


def _profile() -> Profile:
    agent = AgentConfig(driver=DriverType.CLAUDE, model="sonnet")
    return Profile(
        name="test",
        tracker=TrackerType.NOOP,
        repo_root="/tmp/test",
        agents={"architect": agent, "developer": agent, "reviewer": agent},
    )


class _SlowBlockingTracker:
    """A tracker whose ``get_issue`` blocks the calling thread.

    ``started`` is set (from whatever thread runs the call) the instant the
    blocking begins; the call then waits on ``release`` before returning. If
    the call runs on the event loop, the loop cannot service other coroutines
    while it waits — so a concurrent coroutine cannot set ``release`` and the
    call times out at the 5s wait. If it runs in a worker thread, the loop
    keeps spinning, the concurrent coroutine advances, sets ``release``, and
    the fetch returns.
    """

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def get_issue(self, issue_id: str, *, cwd: str | None = None) -> Issue:
        self.started.set()
        if not self.release.wait(timeout=5.0):
            raise AssertionError(
                "get_issue was never released by a concurrent coroutine"
            )
        return Issue(id=issue_id, title="slow", description="slow", status="open")


@pytest.fixture
def runner() -> GraphRunner:
    repo = AsyncMock(spec=WorkflowRepository)
    bus = EventBus()
    return GraphRunner(
        repository=repo,
        events=StreamEventEmitter(bus),
        event_bus=bus,
        checkpointer=None,
        profile_repo=AsyncMock(),
    )


async def test_slow_tracker_fetch_does_not_stall_concurrent_coroutine(
    runner: GraphRunner,
) -> None:
    """A slow get_issue must not freeze a concurrent coroutine.

    Drives the real ``_reconstruct_initial_state`` (runner.py call site). The
    concurrent coroutine only advances if the loop keeps spinning while the
    blocking fetch runs — which requires the fetch to be off-loaded.
    """
    tracker = _SlowBlockingTracker()
    state = ServerExecutionState(
        id=uuid.uuid4(),
        issue_id="ISSUE-644",
        worktree_path="/tmp/wt",
        workflow_status=WorkflowStatus.IN_PROGRESS,
        started_at=datetime.now(UTC),
        profile_id="test",
    )

    progressed = False

    async def concurrent_work() -> None:
        nonlocal progressed
        # Wait until the blocking fetch has actually started in its thread.
        while not tracker.started.is_set():
            await asyncio.sleep(0.005)
        progressed = True
        tracker.release.set()

    with (
        patch(
            "amelia.server.orchestrator.runner.create_tracker",
            return_value=tracker,
        ),
        patch(
            "amelia.server.orchestrator.runner.get_git_head",
            new=AsyncMock(return_value="abc123"),
        ),
    ):
        result, _ = await asyncio.wait_for(
            asyncio.gather(
                runner._reconstruct_initial_state(state, _profile()),
                concurrent_work(),
            ),
            timeout=10.0,
        )

    assert progressed, "concurrent coroutine never advanced — fetch blocked the loop"
    assert result["issue"]["id"] == "ISSUE-644"
