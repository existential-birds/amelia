"""Tests for WorkflowRepository."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from amelia.server.database.repository import WorkflowRepository
from amelia.server.exceptions import WorkflowNotFoundError
from amelia.server.models import EventType
from amelia.server.models.events import EventLevel, WorkflowEvent
from amelia.server.models.state import (
    InvalidStateTransitionError,
    PlanCache,
    ServerExecutionState,
    WorkflowStatus,
)


pytestmark = pytest.mark.integration


class TestWorkflowRepository:
    """Tests for WorkflowRepository CRUD operations."""

    @pytest.fixture
    async def repository(self, test_db):
        """WorkflowRepository instance."""
        return WorkflowRepository(test_db)

    async def test_create_workflow(self, repository) -> None:
        """Can create a workflow."""
        state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
        )

        await repository.create(state)

        # Verify it was created
        retrieved = await repository.get(state.id)
        assert retrieved is not None
        assert retrieved.issue_id == "ISSUE-123"

    async def test_get_by_worktree(self, repository) -> None:
        """Can get active workflow by worktree path."""
        state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            workflow_status="in_progress",
        )
        await repository.create(state)

        retrieved = await repository.get_by_worktree("/path/to/repo")
        assert retrieved is not None
        assert retrieved.id == state.id

    async def test_get_by_worktree_only_active(self, repository) -> None:
        """get_by_worktree only returns active workflows."""
        # Create completed workflow
        completed = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-1",
            worktree_path="/path/to/repo",
            workflow_status="completed",
        )
        await repository.create(completed)

        # No active workflow should be found
        result = await repository.get_by_worktree("/path/to/repo")
        assert result is None

    async def test_get_by_worktree_excludes_pending_by_default(self, repository) -> None:
        """get_by_worktree excludes pending workflows by default.

        This is important for start_pending_workflow: multiple pending workflows
        on the same worktree are allowed, so we should only block if there's an
        in_progress or blocked workflow.
        """
        # Create a pending workflow
        pending = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-PENDING",
            worktree_path="/path/to/repo",
            workflow_status="pending",
        )
        await repository.create(pending)

        # get_by_worktree should NOT find pending workflows
        result = await repository.get_by_worktree("/path/to/repo")
        assert result is None

    async def test_get_by_worktree_finds_in_progress(self, repository) -> None:
        """get_by_worktree finds in_progress workflows."""
        in_progress = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-IP",
            worktree_path="/path/to/repo",
            workflow_status="in_progress",
        )
        await repository.create(in_progress)

        result = await repository.get_by_worktree("/path/to/repo")
        assert result is not None
        assert result.id == in_progress.id

    async def test_get_by_worktree_finds_blocked(self, repository) -> None:
        """get_by_worktree finds blocked workflows."""
        blocked = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-BLOCKED",
            worktree_path="/path/to/repo",
            workflow_status="blocked",
        )
        await repository.create(blocked)

        result = await repository.get_by_worktree("/path/to/repo")
        assert result is not None
        assert result.id == blocked.id

    async def test_get_by_worktree_with_custom_statuses(self, repository) -> None:
        """get_by_worktree can accept custom statuses parameter."""
        # Create a pending workflow
        pending = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-PENDING",
            worktree_path="/path/to/repo",
            workflow_status="pending",
        )
        await repository.create(pending)

        # With custom statuses including pending, it should find the workflow
        result = await repository.get_by_worktree(
            "/path/to/repo",
            statuses=("pending", "in_progress", "blocked"),
        )
        assert result is not None
        assert result.id == pending.id

    async def test_update_workflow(self, repository) -> None:
        """Can update workflow state."""
        state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
        )
        await repository.create(state)

        # Update status
        state.workflow_status = "in_progress"
        state.started_at = datetime.now(UTC)
        await repository.update(state)

        retrieved = await repository.get(state.id)
        assert retrieved.workflow_status == "in_progress"
        assert retrieved.started_at is not None

    async def test_set_status_validates_transition(self, repository) -> None:
        """set_status validates state machine transitions."""
        state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            workflow_status="pending",
        )
        await repository.create(state)

        # Invalid: pending -> completed (must go through in_progress)
        with pytest.raises(InvalidStateTransitionError):
            await repository.set_status(state.id, "completed")

    async def test_set_status_with_failure_reason(self, repository) -> None:
        """set_status can set failure reason."""
        state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            workflow_status="in_progress",
        )
        await repository.create(state)

        await repository.set_status(state.id, "failed", failure_reason="Something went wrong")

        retrieved = await repository.get(state.id)
        assert retrieved.workflow_status == "failed"
        assert retrieved.failure_reason == "Something went wrong"

    async def test_set_status_failed_workflow_persists_failure_reason(
        self, repository
    ) -> None:
        """set_status(in_progress→FAILED, failure_reason=...) persists reason and timestamp.

        Pins the contract exercised by service.py lines 1376, 1414, 1801, 1830, 1871.
        The failure_reason must be written to the DB row and completed_at must be set.
        """
        state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-FAIL",
            worktree_path="/path/to/repo",
            workflow_status="in_progress",
        )
        await repository.create(state)

        await repository.set_status(
            state.id,
            WorkflowStatus.FAILED,
            failure_reason="Failed after 3 attempts: ConnectionError",
        )

        retrieved = await repository.get(state.id)
        assert retrieved.workflow_status == WorkflowStatus.FAILED
        assert retrieved.failure_reason == "Failed after 3 attempts: ConnectionError"
        assert retrieved.completed_at is not None

    async def test_set_status_already_failed_workflow_raises(self, repository) -> None:
        """set_status(already-FAILED, FAILED, failure_reason=...) raises InvalidStateTransitionError.

        FAILED is not in the COMPLETED/CANCELLED terminal-absorption guard, so a
        duplicate FAILED call goes through validate_transition(FAILED, FAILED) and
        is rejected — the state machine forbids it (VALID_TRANSITIONS[FAILED] = {IN_PROGRESS}).
        Pins the contract as "state-machine error", not "log-the-drop" or "silent noop".
        """
        state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-ALREADY-FAILED",
            worktree_path="/path/to/repo",
            workflow_status="in_progress",
        )
        await repository.create(state)
        await repository.set_status(
            state.id,
            WorkflowStatus.FAILED,
            failure_reason="first failure",
        )

        with pytest.raises(InvalidStateTransitionError):
            await repository.set_status(
                state.id,
                WorkflowStatus.FAILED,
                failure_reason="second failure attempt",
            )

        # Row must be unchanged — first failure_reason is preserved
        final = await repository.get(state.id)
        assert final.workflow_status == WorkflowStatus.FAILED
        assert final.failure_reason == "first failure"

    async def test_set_status_failed_workflow_resumes_to_in_progress(
        self, repository
    ) -> None:
        """set_status(FAILED -> IN_PROGRESS) recovers the workflow, not a no-op.

        FAILED is resumable (VALID_TRANSITIONS[FAILED] = {IN_PROGRESS}) and must
        NOT be in the immutable-terminal absorption set. This pins the recovery
        path used by orchestrator service.py (set_status(..., IN_PROGRESS) when a
        previously-failed workflow is resumed). If FAILED were treated as an
        immutable terminal state, this transition would be silently swallowed and
        the workflow could never be resumed — observe the persisted row, not the
        call return.
        """
        state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-RESUME-FROM-FAILED",
            worktree_path="/path/to/repo",
            workflow_status="in_progress",
        )
        await repository.create(state)
        await repository.set_status(
            state.id,
            WorkflowStatus.FAILED,
            failure_reason="transient failure",
        )

        # Recovery: resume the failed workflow back to in_progress.
        await repository.set_status(state.id, WorkflowStatus.IN_PROGRESS)

        resumed = await repository.get(state.id)
        assert resumed.workflow_status == WorkflowStatus.IN_PROGRESS

    async def test_set_status_noop_on_terminal_workflow(self, repository) -> None:
        """A completed row absorbs a lower-precedence transition as a no-op."""
        state = ServerExecutionState(
            id=uuid4(), issue_id="ISSUE-DONE",
            worktree_path="/p", workflow_status="in_progress",
        )
        await repository.create(state)
        await repository.set_status(state.id, "completed")
        snapshot = await repository.get(state.id)

        # cancelled (rank 1) cannot override completed (rank 2): no-op.
        await repository.set_status(state.id, "cancelled")

        final = await repository.get(state.id)
        assert final.workflow_status == WorkflowStatus.COMPLETED
        assert final.completed_at == snapshot.completed_at

    async def test_set_status_completion_overrides_cancellation(self, repository) -> None:
        """COMPLETED (rank 2) overrides a CANCELLED (rank 1) row (terminal precedence)."""
        state = ServerExecutionState(
            id=uuid4(), issue_id="ISSUE-OVERRIDE",
            worktree_path="/p", workflow_status="in_progress",
        )
        await repository.create(state)
        await repository.set_status(state.id, "cancelled")

        # Pre-fix this raises InvalidStateTransitionError; post-fix completion wins.
        await repository.set_status(state.id, "completed")

        final = await repository.get(state.id)
        assert final.workflow_status == WorkflowStatus.COMPLETED
        assert final.completed_at is not None

    async def test_set_status_concurrent_complete_vs_cancel(self, repository) -> None:
        """Precedence logic is order-independent: completed always beats cancelled.

        NOTE: asyncio.gather on a single-threaded event loop does NOT guarantee
        true FOR UPDATE lock contention — one transaction typically completes
        before the other acquires its connection.  What this test actually
        verifies is that the precedence/state-machine logic produces the correct
        result regardless of which call runs first (A-then-B or B-then-A).
        See test_set_status_for_update_blocks_concurrent_writer for the lock
        contention proof.

        Pre-fix (non-atomic read+validate+write) the last UPDATE wins, so the row
        can silently end 'cancelled', losing the completion. Atomic FOR UPDATE +
        terminal precedence (COMPLETED rank 2 > CANCELLED rank 1) make 'completed'
        win regardless of scheduling order. Neither call raises (cancel from
        in_progress is legal; the losing call is absorbed/overridden).
        """
        for _ in range(20):
            state = ServerExecutionState(
                id=uuid4(), issue_id="ISSUE-RACE",
                worktree_path="/p", workflow_status="in_progress",
            )
            await repository.create(state)

            await asyncio.gather(
                repository.set_status(state.id, "completed"),
                repository.set_status(state.id, "cancelled"),
            )

            final = await repository.get(state.id)
            assert final.workflow_status == WorkflowStatus.COMPLETED
            assert final.completed_at is not None

    async def test_set_status_concurrent_cancel_vs_blocked(self, repository) -> None:
        """Precedence logic is order-independent: cancelled always beats blocked.

        NOTE: asyncio.gather on a single-threaded event loop does NOT guarantee
        true FOR UPDATE lock contention — one transaction typically completes
        before the other acquires its connection.  What this test actually
        verifies is that the precedence/state-machine logic produces the correct
        result regardless of which call runs first (A-then-B or B-then-A).
        See test_set_status_for_update_blocks_concurrent_writer for the lock
        contention proof.

        If cancel locks first the row is terminal and absorbs the block (rank 0);
        if block locks first, cancel is a legal BLOCKED->CANCELLED transition.
        Either scheduling order -> cancelled, deterministically (spec should-have
        #5, the 'ideally cancel-vs-blocked' shape).
        """
        for _ in range(20):
            state = ServerExecutionState(
                id=uuid4(), issue_id="ISSUE-RACE-CB",
                worktree_path="/p", workflow_status="in_progress",
            )
            await repository.create(state)

            await asyncio.gather(
                repository.set_status(state.id, "cancelled"),
                repository.set_status(state.id, "blocked"),
            )

            final = await repository.get(state.id)
            assert final.workflow_status == WorkflowStatus.CANCELLED

    async def test_set_status_for_update_blocks_concurrent_writer(
        self, repository
    ) -> None:
        """SELECT … FOR UPDATE actually serializes two overlapping transactions.

        Uses asyncio.Event barriers to force true lock contention: Transaction A
        holds the FOR UPDATE row lock while Transaction B is blocked waiting for
        it.  This proves the locking path works end-to-end, not just that the
        precedence logic is correct for sequential calls.

        Sequence:
          1. Tx-A: BEGIN, SELECT … FOR UPDATE (acquires lock), signals B.
          2. Tx-B: BEGIN, SELECT … FOR UPDATE (blocks on lock held by A).
          2a. Test verifies via pg_stat_activity that Tx-B is genuinely
              blocked on the lock before releasing Tx-A.
          3. Tx-A: UPDATE status='completed', COMMIT (releases lock).
          4. Tx-B: unblocks, reads status='completed' (terminal), no-ops, COMMIT.
          5. Final row must be 'completed'.
        """
        state = ServerExecutionState(
            id=uuid4(), issue_id="ISSUE-LOCK",
            worktree_path="/p", workflow_status="in_progress",
        )
        await repository.create(state)

        # Event that Tx-A signals once it holds the FOR UPDATE lock.
        lock_held = asyncio.Event()
        # Event that the test signals to let Tx-A proceed with its UPDATE/COMMIT.
        proceed = asyncio.Event()

        async def tx_a_hold_then_complete() -> None:
            """Acquires FOR UPDATE, pauses until proceed is set, then commits."""
            async with repository.db.pool.acquire() as conn, conn.transaction():
                await conn.fetchrow(
                    "SELECT status FROM workflows WHERE id = $1 FOR UPDATE",
                    state.id,
                )
                lock_held.set()          # signal: lock is now held
                await proceed.wait()     # hold the lock until the test says go
                await conn.execute(
                    "UPDATE workflows SET status = $1 WHERE id = $2",
                    "completed",
                    state.id,
                )

        async def tx_b_attempt_cancel() -> None:
            """Waits until Tx-A holds the lock, then tries set_status('cancelled').

            set_status opens its own transaction and will block on FOR UPDATE
            until Tx-A commits.  After unblocking it reads status='completed'
            (terminal) and absorbs the call as a no-op.
            """
            await lock_held.wait()           # wait until A holds the lock
            # This call blocks inside DB until Tx-A commits, then reads
            # status='completed' and silently no-ops (terminal absorption).
            await repository.set_status(state.id, "cancelled")

        async def wait_until_tx_b_blocks_on_lock() -> None:
            """Poll pg_stat_activity until a backend is blocked on a row lock.

            Proves Tx-B has actually issued its FOR UPDATE and is waiting on the
            lock held by Tx-A — not merely that Tx-A committed first. Without
            this, proceed.set() could release Tx-A before Tx-B ever contends,
            and the test would no-op via terminal absorption without exercising
            the blocking path. Fails loudly if Tx-B never reaches its lock wait.
            """
            async with repository.db.pool.acquire() as conn:
                for _ in range(200):  # ~2s at 10ms intervals
                    blocked = await conn.fetchval(
                        """
                        SELECT count(*) FROM pg_stat_activity
                        WHERE wait_event_type = 'Lock'
                          AND state = 'active'
                          AND query ILIKE '%FOR UPDATE%'
                          AND pid <> pg_backend_pid()
                        """,
                    )
                    if blocked:
                        return
                    await asyncio.sleep(0.01)
            raise AssertionError(
                "Tx-B never blocked on the row lock; "
                "the FOR UPDATE contention path was not exercised."
            )

        async def orchestrate() -> None:
            task_a = asyncio.create_task(tx_a_hold_then_complete())
            task_b = asyncio.create_task(tx_b_attempt_cancel())
            await lock_held.wait()             # A has the lock
            await wait_until_tx_b_blocks_on_lock()  # B is provably blocked on it
            assert not task_b.done()           # B is still waiting, not no-op'd
            proceed.set()                      # release A → commits → B unblocks
            await asyncio.gather(task_a, task_b)

        await orchestrate()

        final = await repository.get(state.id)
        assert final.workflow_status == WorkflowStatus.COMPLETED

    async def test_list_active_workflows(self, repository) -> None:
        """Can list all active workflows."""
        # Create various workflows
        active1 = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-1",
            worktree_path="/repo1",
            workflow_status="in_progress",
        )
        active2 = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-2",
            worktree_path="/repo2",
            workflow_status="blocked",
        )
        completed = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-3",
            worktree_path="/repo3",
            workflow_status="completed",
        )

        await repository.create(active1)
        await repository.create(active2)
        await repository.create(completed)

        active = await repository.list_active()
        assert len(active) == 2
        ids = {w.id for w in active}
        assert active1.id in ids
        assert active2.id in ids

    # =========================================================================
    # Event Persistence Tests
    # =========================================================================

    async def test_save_event(self, repository, event_factory) -> None:
        """Should persist event to database."""
        # First create a workflow (required for foreign key)
        wf_id = uuid4()
        state = ServerExecutionState(
            id=wf_id,
            issue_id="TEST-100",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        event = event_factory(
            id=uuid4(),
            workflow_id=wf_id,
            timestamp=datetime.now(UTC),
            agent="architect",
            event_type=EventType.STAGE_STARTED,
            message="Planning started",
        )

        await repository.save_event(event)

        # Verify in DB via get_max_event_sequence
        max_seq = await repository.get_max_event_sequence(wf_id)
        assert max_seq == 1

    async def test_get_max_event_sequence_with_events(self, repository, event_factory) -> None:
        """Should return max sequence number."""
        # First create a workflow
        wf_id = uuid4()
        state = ServerExecutionState(
            id=wf_id,
            issue_id="TEST-200",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        # Create events with sequences 1, 2, 3
        for seq in [1, 2, 3]:
            event = event_factory(
                id=uuid4(),
                workflow_id=wf_id,
                sequence=seq,
                timestamp=datetime.now(UTC),
                message=f"Event {seq}",
            )
            await repository.save_event(event)

        max_seq = await repository.get_max_event_sequence(wf_id)
        assert max_seq == 3

    async def test_save_event_with_pydantic_model_in_data(self, repository, event_factory) -> None:
        """Should serialize Pydantic models in event data.

        Regression test for: TypeError: Object of type Profile is not JSON serializable
        """
        from amelia.core.types import Profile

        # First create a workflow
        wf_id = uuid4()
        state = ServerExecutionState(
            id=wf_id,
            issue_id="TEST-300",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        # Create event with Pydantic model in data
        from amelia.core.types import AgentConfig
        profile = Profile(
            name="test",
            tracker="noop",
            repo_root="/tmp/test",
            agents={
                "architect": AgentConfig(driver="claude", model="sonnet"),
                "developer": AgentConfig(driver="claude", model="sonnet"),
                "reviewer": AgentConfig(driver="claude", model="sonnet"),
            },
        )
        event = event_factory(
            id=uuid4(),
            workflow_id=wf_id,
            timestamp=datetime.now(UTC),
            agent="architect",
            event_type=EventType.STAGE_COMPLETED,
            message="Stage completed",
            data={
                "stage": "architect_node",
                "output": {
                    "profile": profile,  # Pydantic model, should be serialized
                    "nested": {"another_profile": profile},
                },
            },
        )

        # Should not raise TypeError
        await repository.save_event(event)

        # Verify event was saved
        max_seq = await repository.get_max_event_sequence(wf_id)
        assert max_seq == 1

    async def test_save_event_with_path_in_data(self, repository, event_factory) -> None:
        """Should serialize Path objects in event data.

        Regression test for: TypeError: Object of type PosixPath is not JSON serializable
        """
        from pathlib import Path

        # First create a workflow
        wf_id = uuid4()
        state = ServerExecutionState(
            id=wf_id,
            issue_id="TEST-400",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        # Create event with Path object in data
        event = event_factory(
            id=uuid4(),
            workflow_id=wf_id,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.STAGE_COMPLETED,
            message="Stage completed",
            data={
                "stage": "developer_node",
                "output": {
                    "worktree_path": Path("/foo/bar"),  # PosixPath, should be serialized
                    "nested": {"another_path": Path("/baz/qux")},
                },
            },
        )

        # Should not raise TypeError
        await repository.save_event(event)

        # Verify event was saved
        max_seq = await repository.get_max_event_sequence(wf_id)
        assert max_seq == 1

    async def test_get_recent_events(self, repository, event_factory) -> None:
        """Should return recent events for a workflow in chronological order."""
        # Create a workflow
        wf_id = uuid4()
        state = ServerExecutionState(
            id=wf_id,
            issue_id="TEST-500",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        # Create events with sequences 1, 2, 3
        event_ids = []
        for seq in [1, 2, 3]:
            evt_id = uuid4()
            event_ids.append(evt_id)
            event = event_factory(
                id=evt_id,
                workflow_id=wf_id,
                sequence=seq,
                timestamp=datetime.now(UTC),
                message=f"Event {seq}",
            )
            await repository.save_event(event)

        # Get recent events
        events = await repository.get_recent_events(wf_id)

        assert len(events) == 3
        # Should be in chronological order (oldest first)
        assert events[0].id == event_ids[0]
        assert events[1].id == event_ids[1]
        assert events[2].id == event_ids[2]

    async def test_get_recent_events_with_limit(self, repository, event_factory) -> None:
        """Should respect limit parameter."""
        # Create a workflow
        wf_id = uuid4()
        state = ServerExecutionState(
            id=wf_id,
            issue_id="TEST-600",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        # Create 5 events
        event_ids = []
        for seq in range(1, 6):
            evt_id = uuid4()
            event_ids.append(evt_id)
            event = event_factory(
                id=evt_id,
                workflow_id=wf_id,
                sequence=seq,
                timestamp=datetime.now(UTC),
                message=f"Event {seq}",
            )
            await repository.save_event(event)

        # Get only 2 most recent events
        events = await repository.get_recent_events(wf_id, limit=2)

        assert len(events) == 2
        # Should return most recent 2, in chronological order
        assert events[0].id == event_ids[3]
        assert events[1].id == event_ids[4]

    async def test_get_recent_events_empty(self, repository) -> None:
        """Should return empty list for workflow with no events."""
        # Create a workflow
        wf_id = uuid4()
        state = ServerExecutionState(
            id=wf_id,
            issue_id="TEST-700",
            worktree_path="/path/to/worktree",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)

        # Get recent events for workflow with no events
        events = await repository.get_recent_events(wf_id)

        assert len(events) == 0

    @pytest.mark.parametrize("limit", [0, -1, -100])
    async def test_get_recent_events_non_positive_limit(self, repository, limit) -> None:
        """Should return empty list for non-positive limit values."""
        # No need to create workflow - should return early before DB query
        events = await repository.get_recent_events(uuid4(), limit=limit)

        assert events == []

    async def test_update_plan_cache(self, repository) -> None:
        """Can update plan_cache column directly."""
        from amelia.server.models.state import PlanCache

        state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            workflow_status="in_progress",
        )
        await repository.create(state)

        # Update plan cache
        plan_cache = PlanCache(
            goal="Test goal",
            plan_markdown="# Test Plan",
            total_tasks=5,
            current_task_index=2,
        )
        await repository.update_plan_cache(state.id, plan_cache)

        # Verify by querying the column directly
        row = await repository._db.fetch_one(
            "SELECT plan_cache FROM workflows WHERE id = $1", state.id
        )
        assert row is not None
        restored = PlanCache.model_validate(row["plan_cache"])
        assert restored.goal == "Test goal"
        assert restored.plan_markdown == "# Test Plan"
        assert restored.total_tasks == 5
        assert restored.current_task_index == 2

    async def test_update_plan_cache_workflow_not_found(self, repository) -> None:
        """update_plan_cache raises WorkflowNotFoundError for missing workflow."""
        from amelia.server.exceptions import WorkflowNotFoundError
        from amelia.server.models.state import PlanCache

        plan_cache = PlanCache(goal="Test goal")

        with pytest.raises(WorkflowNotFoundError):
            await repository.update_plan_cache(uuid4(), plan_cache)

    async def test_update_plan_cache_persists(self, repository) -> None:
        """update_plan_cache writes the cache for an existing workflow."""
        state = ServerExecutionState(
            id=uuid4(), issue_id="ISSUE-PC", worktree_path="/p",
        )
        await repository.create(state)

        await repository.update_plan_cache(state.id, PlanCache(goal="cache me"))

        final = await repository.get(state.id)
        assert final.plan_cache is not None

    async def test_update_plan_cache_missing_workflow_raises(self, repository) -> None:
        """update_plan_cache raises WorkflowNotFoundError for an unknown id (never a silent no-op)."""
        with pytest.raises(WorkflowNotFoundError):
            await repository.update_plan_cache(uuid4(), PlanCache(goal="cache me"))

    async def test_create_workflow_writes_new_columns(self, repository) -> None:
        """create() dual-writes to new columns (workflow_type, profile_id, plan_cache)."""
        from amelia.server.models.state import PlanCache

        plan_cache = PlanCache(goal="Test goal", plan_markdown="# Plan")
        state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
            profile_id="test-profile",
            plan_cache=plan_cache,
            issue_cache={"key": "TEST-1"},
        )
        await repository.create(state)

        # Verify columns directly
        row = await repository._db.fetch_one(
            "SELECT workflow_type, profile_id, plan_cache, issue_cache FROM workflows WHERE id = $1",
            state.id,
        )
        assert row is not None
        assert row["workflow_type"] == "full"
        assert row["profile_id"] == "test-profile"
        assert row["plan_cache"] is not None
        assert row["issue_cache"] == {"key": "TEST-1"}  # JSONB returns dict

        # Verify plan_cache deserialization
        restored = PlanCache.model_validate(row["plan_cache"])
        assert restored.goal == "Test goal"

    async def test_update_workflow_writes_new_columns(self, repository) -> None:
        """update() dual-writes to new columns."""
        from amelia.server.models.state import PlanCache

        # Create workflow
        state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-123",
            worktree_path="/path/to/repo",
        )
        await repository.create(state)

        # Update with new fields
        state.profile_id = "updated-profile"
        state.plan_cache = PlanCache(goal="Updated goal")
        state.issue_cache = {"key": "UPDATED-1"}
        await repository.update(state)

        # Verify columns
        row = await repository._db.fetch_one(
            "SELECT profile_id, plan_cache, issue_cache FROM workflows WHERE id = $1",
            state.id,
        )
        assert row is not None
        assert row["profile_id"] == "updated-profile"
        restored = PlanCache.model_validate(row["plan_cache"])
        assert restored.goal == "Updated goal"
        assert row["issue_cache"] == {"key": "UPDATED-1"}  # JSONB returns dict


class TestRepositoryEvents:
    """Tests for event persistence with level and trace fields."""

    @pytest.fixture
    async def repository(self, test_db):
        """WorkflowRepository instance."""
        return WorkflowRepository(test_db)

    @pytest.fixture
    async def sample_workflow(self, repository):
        """Create a sample workflow for tests."""
        state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-EVENT",
            worktree_path="/path/to/event-test",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)
        return state

    async def test_save_event_with_level(self, repository, sample_workflow) -> None:
        """save_event persists level field."""
        event = WorkflowEvent(
            id=uuid4(),
            workflow_id=sample_workflow.id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            level=EventLevel.INFO,
            message="Started",
        )
        await repository.save_event(event)

        row = await repository._db.fetch_one(
            "SELECT level FROM workflow_log WHERE id = $1", event.id
        )
        assert row["level"] == "info"

    async def test_row_to_event_restores_level(self, repository, sample_workflow) -> None:
        """_row_to_event restores level field from database."""
        event = WorkflowEvent(
            id=uuid4(),
            workflow_id=sample_workflow.id,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            level=EventLevel.INFO,
            message="Workflow started",
        )
        await repository.save_event(event)

        events = await repository.get_recent_events(sample_workflow.id, limit=1)
        restored = events[0]

        assert restored.level == EventLevel.INFO
        assert restored.is_error is False


class TestWorkflowLogFiltering:
    """Tests for event persistence filtering in workflow_log."""

    @pytest.fixture
    async def repository(self, test_db):
        return WorkflowRepository(test_db)

    @pytest.fixture
    async def sample_workflow(self, repository):
        workflow_id = uuid4()
        state = ServerExecutionState(
            id=workflow_id,
            issue_id="TEST-800",
            worktree_path="/tmp/test",
            workflow_status="in_progress",
            started_at=datetime.now(UTC),
        )
        await repository.create(state)
        return workflow_id

    async def test_save_event_persists_lifecycle_event(self, repository, sample_workflow):
        """Lifecycle events should be written to workflow_log."""
        event = WorkflowEvent(
            id=uuid4(),
            workflow_id=sample_workflow,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="system",
            event_type=EventType.WORKFLOW_STARTED,
            message="Workflow started",
        )
        await repository.save_event(event)
        events = await repository.get_recent_events(sample_workflow)
        assert len(events) == 1
        assert events[0].event_type == EventType.WORKFLOW_STARTED

    async def test_save_event_skips_trace_event(self, repository, sample_workflow):
        """Trace events should NOT be written to workflow_log."""
        event = WorkflowEvent(
            id=uuid4(),
            workflow_id=sample_workflow,
            sequence=1,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.CLAUDE_THINKING,
            message="Thinking...",
        )
        await repository.save_event(event)
        events = await repository.get_recent_events(sample_workflow)
        assert len(events) == 0

    async def test_save_event_skips_stream_event(self, repository, sample_workflow):
        """Stream events should NOT be written to workflow_log."""
        event = WorkflowEvent(
            id=uuid4(),
            workflow_id=sample_workflow,
            sequence=0,
            timestamp=datetime.now(UTC),
            agent="developer",
            event_type=EventType.STREAM,
            message="chunk",
        )
        await repository.save_event(event)
        events = await repository.get_recent_events(sample_workflow)
        assert len(events) == 0

