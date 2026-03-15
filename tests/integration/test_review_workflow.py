"""Integration tests for review workflow flows.

Tests the review workflow orchestration with real OrchestratorService,
real WorkflowRepository (PostgreSQL test database), and real profile
management. Only mocks at the LangGraph graph boundary and git subprocess
calls.

Mock boundaries:
- create_review_graph: Returns mock graph for review execution
- get_git_head / asyncio.create_subprocess_exec: Prevents real git calls

Real components:
- OrchestratorService (start_review_workflow, request_review, _run_review_workflow)
- WorkflowRepository with PostgreSQL test database
- ProfileRepository with PostgreSQL test database
- FastAPI route handlers (for HTTP endpoint tests)
- Request/Response model validation
- Exception handlers
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import status

from amelia.core.types import Issue
from amelia.server.database.repository import WorkflowRepository
from amelia.server.dependencies import get_orchestrator, get_repository
from amelia.server.exceptions import (
    ConcurrencyLimitError,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from amelia.server.main import create_app
from amelia.server.models.state import (
    ServerExecutionState,
    WorkflowStatus,
    WorkflowType,
)
from amelia.server.orchestrator.service import OrchestratorService
from tests.integration.server.conftest import noop_lifespan


# =============================================================================
# Helpers
# =============================================================================

def _make_blocking_astream(event: asyncio.Event) -> Any:
    async def blocking_astream(*args: Any, **kwargs: Any) -> Any:
        await event.wait()
        return
        yield  # make it an async generator
    return blocking_astream


def _make_git_mocks() -> dict[str, Any]:
    """Create mock context managers for git subprocess calls.

    Returns:
        Dict with 'get_git_head' and 'create_subprocess_exec' patches.
    """
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"diff --git a/f.py b/f.py\n+hello", b""))
    mock_proc.returncode = 0

    return {
        "get_git_head": patch(
            "amelia.server.orchestrator.service.get_git_head",
            return_value="abc123",
        ),
        "create_subprocess_exec": patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ),
    }


async def _create_completed_workflow(
    repository: WorkflowRepository,
    worktree_path: str,
    issue_id: str = "TEST-001",
    profile_id: str = "test",
    workflow_id: uuid.UUID | None = None,
) -> ServerExecutionState:
    """Create a completed workflow with issue_cache populated.

    This is the standard source workflow for request_review tests.
    """
    if workflow_id is None:
        workflow_id = uuid4()

    issue = Issue(
        id=issue_id,
        title="Test Issue",
        description="Test issue for review",
    )

    state = ServerExecutionState(
        id=workflow_id,
        issue_id=issue_id,
        worktree_path=worktree_path,
        workflow_type=WorkflowType.FULL,
        profile_id=profile_id,
        issue_cache=issue.model_dump(mode="json"),
        workflow_status=WorkflowStatus.COMPLETED,
        started_at=datetime.now(UTC),
    )
    await repository.create(state)
    return state


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def test_client(
    test_orchestrator: OrchestratorService,
    test_repository: WorkflowRepository,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create async test client with real dependencies."""
    app = create_app()

    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_orchestrator] = lambda: test_orchestrator
    app.dependency_overrides[get_repository] = lambda: test_repository

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.integration
class TestRequestReview:
    """Tests for request_review() orchestrator method.

    Validates on-demand review of past runs: creates a new review workflow
    from an existing completed workflow.
    """

    async def test_happy_path_creates_review_workflow(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Any,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """Existing completed workflow → request_review creates new review workflow."""
        source = await _create_completed_workflow(
            test_repository, worktree_path=valid_worktree,
        )

        mocks = langgraph_mock_factory(astream_items=[])
        git_mocks = _make_git_mocks()

        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            git_mocks["get_git_head"],
            git_mocks["create_subprocess_exec"],
        ):
            mock_create.return_value = mocks.graph
            review_id = await test_orchestrator.request_review(source.id)

        assert review_id != source.id
        assert isinstance(review_id, uuid.UUID)

        # Verify persisted in DB with REVIEW type
        review_state = await test_repository.get(review_id)
        assert review_state is not None
        assert review_state.workflow_type == WorkflowType.REVIEW
        assert review_state.issue_id == source.issue_id
        assert review_state.worktree_path == valid_worktree

    @pytest.mark.parametrize(
        ("review_kwargs", "config_key", "expected_value"),
        [
            pytest.param(
                {"mode": "review_only"},
                "review_mode",
                "review_only",
                id="review_only_mode",
            ),
            pytest.param(
                {"mode": "review_fix"},
                "review_mode",
                "review_fix",
                id="review_fix_mode",
            ),
            pytest.param(
                {"review_types": ["security", "performance"]},
                "review_types",
                ["security", "performance"],
                id="custom_review_types",
            ),
        ],
    )
    async def test_review_config_propagated(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Any,
        valid_worktree: str,
        langgraph_mock_factory: Any,
        review_kwargs: dict[str, Any],
        config_key: str,
        expected_value: Any,
    ) -> None:
        """Review kwargs (mode, review_types) are propagated through graph config."""
        source = await _create_completed_workflow(
            test_repository, worktree_path=valid_worktree,
        )

        mocks = langgraph_mock_factory(astream_items=[])
        git_mocks = _make_git_mocks()
        captured_config: dict[str, Any] = {}

        def capture_astream(initial_state: Any, *, config: Any, **kwargs: Any) -> Any:
            captured_config.update(config)
            from tests.conftest import AsyncIteratorMock
            return AsyncIteratorMock([])

        mocks.graph.astream = capture_astream

        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            git_mocks["get_git_head"],
            git_mocks["create_subprocess_exec"],
        ):
            mock_create.return_value = mocks.graph
            await test_orchestrator.request_review(
                source.id, **review_kwargs,
            )

            # Wait for background task to execute (must be inside patch context)
            await asyncio.sleep(0.2)

        assert captured_config["configurable"][config_key] == expected_value

    async def test_workflow_not_found_error(
        self,
        test_orchestrator: OrchestratorService,
        active_test_profile: Any,
    ) -> None:
        """WorkflowNotFoundError when source workflow doesn't exist."""
        fake_id = uuid4()

        with pytest.raises(WorkflowNotFoundError):
            await test_orchestrator.request_review(fake_id)

    async def test_workflow_conflict_error(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Any,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """WorkflowConflictError when worktree already has active task."""
        source = await _create_completed_workflow(
            test_repository, worktree_path=valid_worktree,
        )

        mocks = langgraph_mock_factory(astream_items=[])
        git_mocks = _make_git_mocks()

        # Occupy the worktree with a long-running task
        long_event = asyncio.Event()
        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            git_mocks["get_git_head"],
            git_mocks["create_subprocess_exec"],
        ):
            mocks.graph.astream = _make_blocking_astream(long_event)
            mock_create.return_value = mocks.graph

            # First request occupies the worktree
            await test_orchestrator.request_review(source.id)

            # Second request should conflict
            # Need a second source workflow with same worktree
            source2 = await _create_completed_workflow(
                test_repository,
                worktree_path=valid_worktree,
                issue_id="TEST-002",
                workflow_id=uuid4(),
            )
            with pytest.raises(WorkflowConflictError):
                await test_orchestrator.request_review(source2.id)

            # Cleanup: unblock the task
            long_event.set()
            await asyncio.sleep(0.05)

    async def test_concurrency_limit_error(
        self,
        test_event_bus: Any,
        test_repository: WorkflowRepository,
        test_profile_repository: Any,
        active_test_profile: Any,
        valid_worktree: str,
        tmp_path: Any,
        langgraph_mock_factory: Any,
    ) -> None:
        """ConcurrencyLimitError when at max concurrent workflows."""
        # Create orchestrator with max_concurrent=1
        orchestrator = OrchestratorService(
            event_bus=test_event_bus,
            repository=test_repository,
            profile_repo=test_profile_repository,
            checkpointer=AsyncMock(),
            max_concurrent=1,
        )

        source = await _create_completed_workflow(
            test_repository, worktree_path=valid_worktree,
        )

        mocks = langgraph_mock_factory(astream_items=[])
        git_mocks = _make_git_mocks()

        long_event = asyncio.Event()
        mocks.graph.astream = _make_blocking_astream(long_event)

        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            git_mocks["get_git_head"],
            git_mocks["create_subprocess_exec"],
        ):
            mock_create.return_value = mocks.graph

            # First request uses the only slot
            await orchestrator.request_review(source.id)

            # Create a source on a different worktree
            worktree2 = tmp_path / "worktree2"
            worktree2.mkdir()
            (worktree2 / ".git").mkdir()
            (worktree2 / "settings.amelia.yaml").write_text(
                "active_profile: test\nprofiles:\n  test:\n    name: test\n"
                "    driver: claude\n    model: sonnet\n    tracker: noop\n"
                "    strategy: single\n"
            )
            source2 = await _create_completed_workflow(
                test_repository,
                worktree_path=str(worktree2),
                issue_id="TEST-002",
            )

            with pytest.raises(ConcurrencyLimitError):
                await orchestrator.request_review(source2.id)

            long_event.set()
            await asyncio.sleep(0.05)


@pytest.mark.integration
class TestStartReviewWorkflow:
    """Tests for start_review_workflow() orchestrator method.

    Validates direct review workflow creation (not from an existing workflow).
    """

    async def test_creates_workflow_in_db(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Any,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """Creates workflow in DB with correct state (REVIEW type, PENDING status)."""
        mocks = langgraph_mock_factory(astream_items=[])

        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            patch("amelia.server.orchestrator.service.get_git_head", return_value="def456"),
        ):
            mock_create.return_value = mocks.graph
            workflow_id = await test_orchestrator.start_review_workflow(
                diff_content="diff --git a/test.py\n+hello",
                worktree_path=valid_worktree,
            )

        assert isinstance(workflow_id, uuid.UUID)

        state = await test_repository.get(workflow_id)
        assert state is not None
        assert state.workflow_type == WorkflowType.REVIEW
        assert state.issue_id == "LOCAL-REVIEW"
        assert state.profile_id == "test"
        assert state.worktree_path == valid_worktree

    async def test_populates_issue_cache(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Any,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """issue_cache is populated on ServerExecutionState."""
        mocks = langgraph_mock_factory(astream_items=[])

        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            patch("amelia.server.orchestrator.service.get_git_head", return_value="abc123"),
        ):
            mock_create.return_value = mocks.graph
            workflow_id = await test_orchestrator.start_review_workflow(
                diff_content="diff content",
                worktree_path=valid_worktree,
            )

        state = await test_repository.get(workflow_id)
        assert state is not None
        assert state.issue_cache is not None
        assert state.issue_cache["id"] == "LOCAL-REVIEW"
        assert state.issue_cache["title"] == "Local Code Review"

    async def test_spawns_async_task(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Any,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """Spawns async task that transitions to IN_PROGRESS then COMPLETED."""
        mocks = langgraph_mock_factory(astream_items=[])

        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            patch("amelia.server.orchestrator.service.get_git_head", return_value="abc123"),
        ):
            mock_create.return_value = mocks.graph
            workflow_id = await test_orchestrator.start_review_workflow(
                diff_content="diff content",
                worktree_path=valid_worktree,
            )

            # Let the background task run
            await asyncio.sleep(0.2)

        state = await test_repository.get(workflow_id)
        assert state is not None
        assert state.workflow_status == WorkflowStatus.COMPLETED


@pytest.mark.integration
class TestRunReviewWorkflow:
    """Tests for _run_review_workflow() graph execution.

    Validates status transitions and event emission during review graph execution.
    """

    async def test_status_transitions_to_completed(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Any,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """PENDING → IN_PROGRESS → COMPLETED on successful graph execution."""
        mocks = langgraph_mock_factory(astream_items=[])

        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            patch("amelia.server.orchestrator.service.get_git_head", return_value="abc123"),
        ):
            mock_create.return_value = mocks.graph
            workflow_id = await test_orchestrator.start_review_workflow(
                diff_content="diff content",
                worktree_path=valid_worktree,
            )

            # Immediately check pending status
            state = await test_repository.get(workflow_id)
            assert state is not None
            # Status is PENDING at creation, transitions to IN_PROGRESS then COMPLETED in the task.
            # With an empty astream mock the background task can finish before this check.
            assert state.workflow_status in (
                WorkflowStatus.PENDING,
                WorkflowStatus.IN_PROGRESS,
                WorkflowStatus.COMPLETED,
            )

            # Wait for completion
            await asyncio.sleep(0.2)

        state = await test_repository.get(workflow_id)
        assert state is not None
        assert state.workflow_status == WorkflowStatus.COMPLETED

    async def test_status_transitions_to_failed_on_error(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Any,
        valid_worktree: str,
    ) -> None:
        """PENDING → IN_PROGRESS → FAILED when graph raises exception."""
        mock_graph = MagicMock()

        async def failing_astream(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("Graph execution failed")
            yield  # make it an async generator

        mock_graph.astream = failing_astream

        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            patch("amelia.server.orchestrator.service.get_git_head", return_value="abc123"),
        ):
            mock_create.return_value = mock_graph
            workflow_id = await test_orchestrator.start_review_workflow(
                diff_content="diff content",
                worktree_path=valid_worktree,
            )

            # Wait for failure
            await asyncio.sleep(0.2)

        state = await test_repository.get(workflow_id)
        assert state is not None
        assert state.workflow_status == WorkflowStatus.FAILED
        assert state.failure_reason is not None
        assert "Graph execution failed" in state.failure_reason

    async def test_review_mode_and_types_in_graph_config(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Any,
        valid_worktree: str,
    ) -> None:
        """review_mode and review_types are passed in graph config's configurable dict."""
        captured_config: dict[str, Any] = {}
        mock_graph = MagicMock()

        def capture_astream(initial_state: Any, *, config: Any, **kwargs: Any) -> Any:
            captured_config.update(config)
            from tests.conftest import AsyncIteratorMock
            return AsyncIteratorMock([])

        mock_graph.astream = capture_astream

        # Create source workflow and request review with specific mode/types
        source = await _create_completed_workflow(
            test_repository, worktree_path=valid_worktree,
        )

        git_mocks = _make_git_mocks()
        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            git_mocks["get_git_head"],
            git_mocks["create_subprocess_exec"],
        ):
            mock_create.return_value = mock_graph
            await test_orchestrator.request_review(
                source.id,
                mode="review_only",
                review_types=["security", "general"],
            )

            await asyncio.sleep(0.2)

        assert captured_config["configurable"]["review_mode"] == "review_only"
        assert captured_config["configurable"]["review_types"] == ["security", "general"]

    async def test_events_emitted(
        self,
        test_event_bus: Any,
        test_repository: WorkflowRepository,
        test_profile_repository: Any,
        active_test_profile: Any,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """WORKFLOW_STARTED and WORKFLOW_COMPLETED events are emitted."""
        from amelia.server.events.bus import EventBus
        from amelia.server.models.events import EventType

        event_bus = EventBus()
        emitted_events: list[Any] = []
        original_emit = event_bus.emit

        def tracking_emit(event: Any) -> None:
            emitted_events.append(event)
            original_emit(event)

        event_bus.emit = tracking_emit  # type: ignore[assignment]

        orchestrator = OrchestratorService(
            event_bus=event_bus,
            repository=test_repository,
            profile_repo=test_profile_repository,
            checkpointer=AsyncMock(),
        )

        mocks = langgraph_mock_factory(astream_items=[])

        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            patch("amelia.server.orchestrator.service.get_git_head", return_value="abc123"),
        ):
            mock_create.return_value = mocks.graph
            workflow_id = await orchestrator.start_review_workflow(
                diff_content="diff content",
                worktree_path=valid_worktree,
            )

            await asyncio.sleep(0.2)

        event_types = [e.event_type for e in emitted_events if e.workflow_id == workflow_id]
        assert EventType.WORKFLOW_STARTED in event_types
        assert EventType.WORKFLOW_COMPLETED in event_types


@pytest.mark.integration
class TestReviewEndpointIntegration:
    """Tests for POST /{workflow_id}/review HTTP endpoint.

    Uses real orchestrator + real DB, mocks only graph execution.
    """

    async def test_returns_202_with_review_workflow_id(
        self,
        test_client: httpx.AsyncClient,
        test_repository: WorkflowRepository,
        active_test_profile: Any,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """Returns 202 with new review workflow_id (not the source workflow_id)."""
        source = await _create_completed_workflow(
            test_repository, worktree_path=valid_worktree,
        )

        mocks = langgraph_mock_factory(astream_items=[])
        git_mocks = _make_git_mocks()

        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            git_mocks["get_git_head"],
            git_mocks["create_subprocess_exec"],
        ):
            mock_create.return_value = mocks.graph

            response = await test_client.post(
                f"/api/workflows/{source.id}/review",
                json={"mode": "review_only"},
            )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["status"] == "review_requested"
        # The returned workflow_id should be the NEW review workflow, not the source
        assert data["workflow_id"] != str(source.id)
        # Verify it's a valid UUID
        review_id = uuid.UUID(data["workflow_id"])
        assert review_id != source.id

    async def test_returns_404_when_source_not_found(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Returns 404 when source workflow doesn't exist."""
        fake_id = uuid4()
        response = await test_client.post(
            f"/api/workflows/{fake_id}/review",
            json={"mode": "review_only"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["code"] == "NOT_FOUND"

    async def test_returns_409_on_conflict(
        self,
        test_client: httpx.AsyncClient,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Any,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """Returns 409 when worktree already has active workflow."""
        source = await _create_completed_workflow(
            test_repository, worktree_path=valid_worktree,
        )

        mocks = langgraph_mock_factory(astream_items=[])
        git_mocks = _make_git_mocks()

        long_event = asyncio.Event()
        mocks.graph.astream = _make_blocking_astream(long_event)

        with (
            patch("amelia.server.orchestrator.service.create_review_graph") as mock_create,
            git_mocks["get_git_head"],
            git_mocks["create_subprocess_exec"],
        ):
            mock_create.return_value = mocks.graph

            # First request occupies the worktree
            first_response = await test_client.post(
                f"/api/workflows/{source.id}/review",
                json={"mode": "review_only"},
            )
            assert first_response.status_code == status.HTTP_202_ACCEPTED

            # Create another source with same worktree
            source2 = await _create_completed_workflow(
                test_repository,
                worktree_path=valid_worktree,
                issue_id="TEST-002",
            )

            # Second request should conflict
            second_response = await test_client.post(
                f"/api/workflows/{source2.id}/review",
                json={"mode": "review_only"},
            )

            assert second_response.status_code == status.HTTP_409_CONFLICT
            data = second_response.json()
            assert data["code"] == "WORKFLOW_CONFLICT"

            long_event.set()
            await asyncio.sleep(0.05)
