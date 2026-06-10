"""Unit tests for GraphRunner — the LangGraph execution-driver collaborator.

GraphRunner owns the workflow execution drivers (run_workflow,
run_workflow_with_retry, run_review_workflow, run_planning_task) and the
LangGraph setup helpers they depend on. These tests construct GraphRunner
directly and assert observable behavior (astream inputs, status transitions,
backoff delays) — not bookkeeping between components.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from amelia.core.types import AgentConfig, DriverType, Profile, TrackerType
from amelia.pipelines.implementation.state import rebuild_implementation_state


# Rebuild models to resolve forward references before module-level usage.
rebuild_implementation_state()

from amelia.core.exceptions import ModelProviderError  # noqa: E402
from amelia.core.types import RetryConfig  # noqa: E402
from amelia.server.database.repository import WorkflowRepository  # noqa: E402
from amelia.server.events.bus import EventBus  # noqa: E402
from amelia.server.models import ServerExecutionState  # noqa: E402
from amelia.server.models.events import EventType  # noqa: E402
from amelia.server.models.state import WorkflowStatus  # noqa: E402
from amelia.server.orchestrator.event_emitter import StreamEventEmitter  # noqa: E402
from amelia.server.orchestrator.runner import GraphRunner  # noqa: E402


@pytest.fixture
def mock_event_bus() -> EventBus:
    """Create a real EventBus (lightweight, no external deps)."""
    return EventBus()


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create mock workflow repository."""
    repo = AsyncMock(spec=WorkflowRepository)
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.update_plan_cache = AsyncMock()
    repo.set_status = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_profile_repo() -> AsyncMock:
    """Create mock profile repository returning a default profile."""
    repo = AsyncMock()
    agent_config = AgentConfig(driver=DriverType.CLAUDE, model="sonnet")
    default_profile = Profile(
        name="test",
        tracker=TrackerType.NOOP,
        repo_root="/default/repo",
        agents={
            "architect": agent_config,
            "developer": agent_config,
            "reviewer": agent_config,
        },
    )
    repo.get_profile.return_value = default_profile
    repo.get_active_profile.return_value = default_profile
    return repo


@pytest.fixture
def runner(
    mock_event_bus: EventBus,
    mock_repository: AsyncMock,
    mock_profile_repo: AsyncMock,
) -> GraphRunner:
    """Construct a GraphRunner with a real EventBus-backed emitter and real repo seam.

    Only the external graph/sandbox boundary is mocked per-test; the runner
    itself is wired exactly as production wires it.
    """
    events = StreamEventEmitter(mock_event_bus)
    return GraphRunner(
        repository=mock_repository,
        events=events,
        event_bus=mock_event_bus,
        checkpointer=None,
        profile_repo=mock_profile_repo,
    )


# =============================================================================
# Checkpoint Resume Tests (Bug #199: Infinite Loop) — relocated from test_service
# =============================================================================


class TestRunWorkflowCheckpointResume:
    """run_workflow must resume from an existing checkpoint instead of restarting.

    Bug #199: passing initial_state on every attempt restarted execution from
    review_iteration=0, creating an infinite loop. The fix checks for a
    checkpoint and passes None (resume) when one exists.
    """

    @pytest.fixture
    def mock_graph(self) -> MagicMock:
        graph = MagicMock()
        graph.aget_state = AsyncMock()
        graph.astream = MagicMock()
        return graph

    @pytest.fixture
    def mock_state(self) -> ServerExecutionState:
        return ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-123",
            worktree_path="/path/to/worktree",
            workflow_status=WorkflowStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
            profile_id="test",
        )

    @pytest.fixture
    def mock_profile(self) -> Profile:
        return Profile(
            name="test",
            tracker=TrackerType.NOOP,
            repo_root="/tmp/test",
            agents={
                "architect": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
                "developer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
                "reviewer": AgentConfig(driver=DriverType.CLAUDE, model="sonnet"),
            },
        )

    async def test_run_workflow_resumes_when_checkpoint_exists(
        self,
        runner: GraphRunner,
        mock_graph: MagicMock,
        mock_state: ServerExecutionState,
        mock_profile: Profile,
    ) -> None:
        """run_workflow passes None to astream when a checkpoint exists (resume)."""
        mock_checkpoint_state = MagicMock()
        mock_checkpoint_state.values = {"review_iteration": 2, "goal": "test"}
        mock_graph.aget_state.return_value = mock_checkpoint_state

        async def empty_stream() -> AsyncIterator[dict[str, Any]]:
            return
            yield  # makes this an async generator

        mock_graph.astream.return_value = empty_stream()

        with (
            patch.object(runner, "create_server_graph", return_value=mock_graph),
            patch.object(runner, "get_profile_or_fail", return_value=mock_profile),
            patch.object(runner._events, "emit", new=AsyncMock()),
        ):
            await runner.run_workflow(
                UUID("00000000-0000-0000-0000-000000000001"), mock_state
            )

        mock_graph.astream.assert_called_once()
        call_args = mock_graph.astream.call_args
        first_arg = call_args[0][0] if call_args[0] else call_args[1].get("input")
        assert first_arg is None, (
            f"Expected astream called with None to resume from checkpoint, "
            f"got {type(first_arg).__name__}: {first_arg}"
        )

    async def test_run_workflow_starts_fresh_when_no_checkpoint(
        self,
        runner: GraphRunner,
        mock_graph: MagicMock,
        mock_state: ServerExecutionState,
        mock_profile: Profile,
    ) -> None:
        """run_workflow passes reconstructed initial_state when no checkpoint exists."""
        mock_graph.aget_state.return_value = None

        async def empty_stream() -> AsyncIterator[dict[str, Any]]:
            return
            yield

        mock_graph.astream.return_value = empty_stream()

        with (
            patch.object(runner, "create_server_graph", return_value=mock_graph),
            patch.object(runner, "get_profile_or_fail", return_value=mock_profile),
            patch.object(runner._events, "emit", new=AsyncMock()),
        ):
            await runner.run_workflow(
                UUID("00000000-0000-0000-0000-000000000002"), mock_state
            )

        mock_graph.astream.assert_called_once()
        call_args = mock_graph.astream.call_args
        first_arg = call_args[0][0] if call_args[0] else call_args[1].get("input")
        assert first_arg is not None, "Expected astream called with initial_state"
        assert isinstance(first_arg, dict), "Expected initial_state to be a dict"
        assert first_arg.get("profile_id") == "test"


# =============================================================================
# Exponential Backoff / Retry Tests — relocated from test_service
# =============================================================================


class TestRunWorkflowWithRetry:
    """run_workflow_with_retry drives jittered exponential backoff and failure emission."""

    def _create_test_setup(
        self,
        worktree: str,
        max_retries: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 10.0,
    ) -> tuple[ServerExecutionState, Profile]:
        mock_state = ServerExecutionState(
            id=uuid4(),
            issue_id="ISSUE-BACKOFF",
            worktree_path=worktree,
            workflow_status=WorkflowStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
            profile_id="test",
        )
        agent_config = AgentConfig(driver=DriverType.CLAUDE, model="sonnet")
        mock_profile = Profile(
            name="test",
            tracker=TrackerType.NOOP,
            repo_root=worktree,
            retry=RetryConfig(
                max_retries=max_retries, base_delay=base_delay, max_delay=max_delay
            ),
            agents={
                "architect": agent_config,
                "developer": agent_config,
                "reviewer": agent_config,
            },
        )
        return mock_state, mock_profile

    @pytest.mark.parametrize(
        "max_retries,base_delay,max_delay",
        [
            (3, 0.1, 10.0),
            (5, 1.0, 3.0),
        ],
        ids=["normal_exponential_backoff", "max_delay_cap"],
    )
    async def test_exponential_backoff_delays(
        self,
        runner: GraphRunner,
        tmp_path: Any,
        max_retries: int,
        base_delay: float,
        max_delay: float,
    ) -> None:
        """Jittered backoff delays fall in the expected band and cap at max_delay."""
        mock_state, mock_profile = self._create_test_setup(
            str(tmp_path), max_retries=max_retries, base_delay=base_delay, max_delay=max_delay
        )

        call_count = 0

        async def failing_run_workflow(
            workflow_id: uuid.UUID, state: ServerExecutionState, **kwargs: Any
        ) -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= max_retries:
                raise ModelProviderError("transient failure")

        with (
            patch.object(runner, "get_profile_or_fail", return_value=mock_profile),
            patch.object(runner, "run_workflow", new=failing_run_workflow),
            patch("amelia.core.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await runner.run_workflow_with_retry(mock_state.id, mock_state)

        assert mock_sleep.call_count == max_retries
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        for n, d in enumerate(delays):
            base = base_delay * (2**n)
            lower = min(base, max_delay)
            upper = min(base * 1.25, max_delay)
            assert lower <= d <= upper, f"delay[{n}]={d} not in [{lower}, {upper}]"

    async def test_max_retries_exhausted(
        self,
        runner: GraphRunner,
        mock_repository: AsyncMock,
        tmp_path: Any,
    ) -> None:
        """After max_retries exhausted, run_workflow_with_retry re-raises and records FAILED."""
        mock_state, mock_profile = self._create_test_setup(
            str(tmp_path), max_retries=2, base_delay=0.1, max_delay=10.0
        )

        async def always_fail(
            workflow_id: uuid.UUID, state: ServerExecutionState, **kwargs: Any
        ) -> None:
            raise ModelProviderError("always fails")

        with (
            patch.object(runner, "get_profile_or_fail", return_value=mock_profile),
            patch.object(runner, "run_workflow", new=always_fail),
            patch("amelia.core.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            pytest.raises(ModelProviderError),
        ):
            await runner.run_workflow_with_retry(mock_state.id, mock_state)

        assert mock_sleep.call_count == 2
        failed_calls = [
            c
            for c in mock_repository.set_status.call_args_list
            if len(c[0]) >= 2 and c[0][1] == WorkflowStatus.FAILED
        ]
        assert len(failed_calls) == 1
        assert "Failed after" in failed_calls[0].kwargs.get("failure_reason", "")

    async def test_overflow_prevention(
        self,
        runner: GraphRunner,
        mock_repository: AsyncMock,
        tmp_path: Any,
    ) -> None:
        """Backoff delays never exceed max_delay, even at the largest configured values."""
        mock_state, mock_profile = self._create_test_setup(
            str(tmp_path), max_retries=10, base_delay=30.0, max_delay=300.0
        )

        call_count = 0

        async def failing_run_workflow(
            workflow_id: uuid.UUID, state: ServerExecutionState, **kwargs: Any
        ) -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 10:
                raise ModelProviderError("transient failure")

        with (
            patch.object(runner, "get_profile_or_fail", return_value=mock_profile),
            patch.object(runner, "run_workflow", new=failing_run_workflow),
            patch("amelia.core.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await runner.run_workflow_with_retry(mock_state.id, mock_state)

        assert mock_sleep.call_count == 10
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        for n, d in enumerate(delays):
            base = 30.0 * (2**n)
            lower = min(base, 300.0)
            upper = min(base * 1.25, 300.0)
            assert lower <= d <= upper, f"delay[{n}]={d} not in [{lower}, {upper}]"
            assert d <= 300.0

    async def test_sandbox_bootstrap_failure_emits_and_fails(
        self,
        runner: GraphRunner,
        mock_repository: AsyncMock,
        tmp_path: Any,
    ) -> None:
        """A non-transient sandbox-bootstrap error emits WORKFLOW_FAILED and does NOT retry."""
        mock_state, mock_profile = self._create_test_setup(
            str(tmp_path), max_retries=3, base_delay=0.1, max_delay=10.0
        )

        async def boom(profile: Profile, **kwargs: Any) -> None:
            raise RuntimeError("daytona exploded")

        run_workflow = AsyncMock()
        emit = AsyncMock()
        with (
            patch.object(runner, "get_profile_or_fail", return_value=mock_profile),
            patch.object(runner, "create_sandbox_provider", new=boom),
            patch.object(runner, "run_workflow", new=run_workflow),
            patch.object(runner._events, "emit", new=emit),
            patch("amelia.core.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await runner.run_workflow_with_retry(mock_state.id, mock_state)

        assert mock_sleep.call_count == 0
        run_workflow.assert_not_called()
        emit.assert_awaited_once()
        emit_args = emit.await_args
        assert emit_args.args[1] == EventType.WORKFLOW_FAILED
        assert "Sandbox bootstrap failed" in emit_args.args[2]
        assert emit_args.kwargs["data"]["error_type"] == "sandbox_bootstrap"
        failed_calls = [
            c
            for c in mock_repository.set_status.call_args_list
            if len(c[0]) >= 2 and c[0][1] == WorkflowStatus.FAILED
        ]
        assert len(failed_calls) == 1
        assert "Sandbox bootstrap failed" in failed_calls[0].kwargs.get("failure_reason", "")

    async def test_non_transient_error_emits_and_reraises(
        self,
        runner: GraphRunner,
        mock_repository: AsyncMock,
        tmp_path: Any,
    ) -> None:
        """A non-transient error from run_workflow emits WORKFLOW_FAILED, re-raises, no retry."""
        mock_state, mock_profile = self._create_test_setup(
            str(tmp_path), max_retries=3, base_delay=0.1, max_delay=10.0
        )

        async def boom_workflow(
            workflow_id: uuid.UUID, state: ServerExecutionState, **kwargs: Any
        ) -> None:
            raise RuntimeError("non-transient boom")

        emit = AsyncMock()
        with (
            patch.object(runner, "get_profile_or_fail", return_value=mock_profile),
            patch.object(runner, "run_workflow", new=boom_workflow),
            patch.object(runner._events, "emit", new=emit),
            patch("amelia.core.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            pytest.raises(RuntimeError, match="non-transient boom"),
        ):
            await runner.run_workflow_with_retry(mock_state.id, mock_state)

        assert mock_sleep.call_count == 0
        emit.assert_awaited_once()
        emit_args = emit.await_args
        assert emit_args.args[1] == EventType.WORKFLOW_FAILED
        assert emit_args.kwargs["data"]["error_type"] == "non-transient"
        failed_calls = [
            c
            for c in mock_repository.set_status.call_args_list
            if len(c[0]) >= 2 and c[0][1] == WorkflowStatus.FAILED
        ]
        assert len(failed_calls) == 1


# =============================================================================
# Plan Sync Tests — relocated from test_service (driver-owned helper)
# =============================================================================


class TestSyncPlanFromCheckpoint:
    """_sync_plan_from_checkpoint writes the checkpoint plan to the plan_cache column."""

    async def test_sync_plan_updates_plan_cache(
        self,
        runner: GraphRunner,
        mock_repository: AsyncMock,
    ) -> None:
        mock_graph = MagicMock()
        checkpoint_values = {"goal": "Test goal", "plan_markdown": "# Test Plan"}
        mock_graph.aget_state = AsyncMock(return_value=MagicMock(values=checkpoint_values))

        config: dict[str, Any] = {"configurable": {"thread_id": str(uuid4())}}
        workflow_id = uuid4()

        await runner._sync_plan_from_checkpoint(workflow_id, mock_graph, config)

        mock_repository.update_plan_cache.assert_called_once()
        call_args = mock_repository.update_plan_cache.call_args
        assert call_args[0][0] == workflow_id
        plan_cache = call_args[0][1]
        assert plan_cache.goal == "Test goal"
        assert plan_cache.plan_markdown == "# Test Plan"

    async def test_sync_plan_no_checkpoint_state(
        self,
        runner: GraphRunner,
        mock_repository: AsyncMock,
    ) -> None:
        mock_graph = MagicMock()
        mock_graph.aget_state = AsyncMock(return_value=None)
        config: dict[str, Any] = {"configurable": {"thread_id": str(uuid4())}}

        await runner._sync_plan_from_checkpoint(uuid4(), mock_graph, config)

        mock_repository.update_plan_cache.assert_not_called()
