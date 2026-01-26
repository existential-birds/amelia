"""Integration tests for the replan workflow lifecycle.

Tests the full replan cycle with real OrchestratorService, real repository,
mocking only at the LangGraph boundary.

Flow tested:
1. queue_and_plan_workflow → PLANNING → BLOCKED (original plan)
2. replan_workflow → PLANNING → BLOCKED (new plan)
3. Verify plan data is updated and events are emitted correctly
"""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.core.types import AgentConfig, Profile
from amelia.server.database.connection import Database
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType
from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.models.state import WorkflowStatus
from amelia.server.orchestrator.service import OrchestratorService
from tests.conftest import init_git_repo


class AsyncIteratorMock:
    """Mock async iterator for testing async generators."""

    def __init__(self, items: list[Any]) -> None:
        self.items = items
        self.index = 0

    def __aiter__(self) -> "AsyncIteratorMock":
        return self

    async def __anext__(self) -> Any:
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


def create_planning_graph_mock(
    goal: str = "Test goal",
    plan_markdown: str = "## Plan\n\n### Task 1: Do thing\n- Step 1",
) -> MagicMock:
    """Create a mock LangGraph graph that simulates planning with interrupt."""
    mock_graph = MagicMock()

    checkpoint_values = {
        "goal": goal,
        "plan_markdown": plan_markdown,
        "profile_id": "test",
    }
    mock_checkpoint = MagicMock()
    mock_checkpoint.values = checkpoint_values
    mock_checkpoint.next = []
    mock_graph.aget_state = AsyncMock(return_value=mock_checkpoint)

    astream_items = [
        ("updates", {"architect_node": {"goal": goal, "plan_markdown": plan_markdown}}),
        ("updates", {"__interrupt__": ("Paused for approval",)}),
    ]
    mock_graph.astream = lambda *args, **kwargs: AsyncIteratorMock(astream_items)
    mock_graph.aupdate_state = AsyncMock()

    return mock_graph


@asynccontextmanager
async def mock_langgraph_for_planning(
    goal: str = "Test goal",
    plan_markdown: str = "## Plan\n\n### Task 1: Do thing\n- Step 1",
) -> AsyncGenerator[MagicMock, None]:
    """Context manager that mocks LangGraph for planning tests."""
    mock_graph = create_planning_graph_mock(goal=goal, plan_markdown=plan_markdown)

    mock_saver = AsyncMock()
    mock_saver_class = MagicMock()
    mock_saver_class.from_conn_string.return_value.__aenter__ = AsyncMock(
        return_value=mock_saver
    )
    mock_saver_class.from_conn_string.return_value.__aexit__ = AsyncMock()

    with (
        patch(
            "amelia.server.orchestrator.service.AsyncSqliteSaver", mock_saver_class
        ),
        patch.object(
            OrchestratorService, "_create_server_graph", return_value=mock_graph
        ),
    ):
        yield mock_graph


@pytest.fixture
async def test_db(tmp_path: Path) -> AsyncGenerator[Database, None]:
    """Create and initialize test database."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.ensure_schema()
    yield db
    await db.close()


@pytest.fixture
def test_repository(test_db: Database) -> WorkflowRepository:
    """Create repository backed by test database."""
    return WorkflowRepository(test_db)


@pytest.fixture
def test_profile_repository(test_db: Database) -> ProfileRepository:
    """Create profile repository backed by test database."""
    return ProfileRepository(test_db)


@pytest.fixture
def test_event_bus() -> EventBus:
    """Create event bus for testing."""
    return EventBus()


@pytest.fixture
def temp_checkpoint_db(tmp_path: Path) -> str:
    """Temporary checkpoint database path."""
    return str(tmp_path / "checkpoints.db")


@pytest.fixture
def valid_worktree(tmp_path: Path) -> str:
    """Create a valid git worktree for testing."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    init_git_repo(worktree)
    return str(worktree)


@pytest.fixture
async def test_orchestrator(
    test_event_bus: EventBus,
    test_repository: WorkflowRepository,
    test_profile_repository: ProfileRepository,
    temp_checkpoint_db: str,
) -> OrchestratorService:
    """Create real OrchestratorService with test dependencies."""
    return OrchestratorService(
        event_bus=test_event_bus,
        repository=test_repository,
        profile_repo=test_profile_repository,
        checkpoint_path=temp_checkpoint_db,
    )


@pytest.fixture
async def active_test_profile(
    test_profile_repository: ProfileRepository,
    valid_worktree: str,
) -> Profile:
    """Create and activate a test profile for replan tests."""
    agent_config = AgentConfig(driver="cli", model="sonnet")
    profile = Profile(
        name="test",
        tracker="noop",
        working_dir=valid_worktree,
        agents={
            "architect": agent_config,
            "developer": agent_config,
            "reviewer": agent_config,
            "plan_validator": agent_config,
            "evaluator": agent_config,
            "task_reviewer": agent_config,
        },
    )
    await test_profile_repository.create_profile(profile)
    await test_profile_repository.set_active("test")
    return profile


@pytest.mark.integration
class TestReplanFlow:
    """Integration tests for the full replan lifecycle."""

    async def test_replan_full_cycle(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Profile,
        valid_worktree: str,
        test_event_bus: EventBus,
    ) -> None:
        """Full cycle: PENDING -> PLANNING -> BLOCKED -> replan -> PLANNING -> BLOCKED."""
        # Track events
        received_events: list[Any] = []
        test_event_bus.subscribe(lambda e: received_events.append(e))

        # Phase 1: queue_and_plan_workflow -> PLANNING -> BLOCKED
        request = CreateWorkflowRequest(
            issue_id="ISSUE-REPLAN-INTEG",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
            task_title="Test replan feature",
        )

        async with mock_langgraph_for_planning(
            goal="Original goal from architect",
            plan_markdown="# Original Plan\n\n### Task 1: Original task",
        ):
            workflow_id = await test_orchestrator.queue_and_plan_workflow(request)

            # Wait for background planning task
            if workflow_id in test_orchestrator._planning_tasks:
                await test_orchestrator._planning_tasks[workflow_id]

        # Verify Phase 1: workflow should be BLOCKED with original plan
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.workflow_status == WorkflowStatus.BLOCKED
        assert workflow.planned_at is not None
        assert workflow.execution_state is not None
        assert workflow.execution_state.goal == "Original goal from architect"
        assert "Original Plan" in (workflow.execution_state.plan_markdown or "")

        original_planned_at = workflow.planned_at

        # Phase 2: replan -> PLANNING -> BLOCKED (with new plan)
        async with mock_langgraph_for_planning(
            goal="New goal after replan",
            plan_markdown="# Revised Plan\n\n### Task 1: Revised task",
        ):
            await test_orchestrator.replan_workflow(workflow_id)

            # Wait for background planning task
            if workflow_id in test_orchestrator._planning_tasks:
                await test_orchestrator._planning_tasks[workflow_id]

        # Verify Phase 2: workflow should be BLOCKED again with NEW plan
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.workflow_status == WorkflowStatus.BLOCKED
        assert workflow.planned_at is not None
        assert workflow.planned_at != original_planned_at  # New timestamp
        assert workflow.execution_state is not None
        assert workflow.execution_state.goal == "New goal after replan"
        assert "Revised Plan" in (workflow.execution_state.plan_markdown or "")

        # Verify events include replanning stage
        stage_events = [
            e for e in received_events if e.event_type == EventType.STAGE_STARTED
        ]
        replan_events = [
            e for e in stage_events if "replan" in (e.message or "").lower()
        ]
        assert len(replan_events) >= 1, (
            f"Expected at least one replan STAGE_STARTED event. "
            f"Stage events: {[(e.message, e.event_type) for e in stage_events]}"
        )

        # Verify approval events for both planning cycles
        approval_events = [
            e for e in received_events if e.event_type == EventType.APPROVAL_REQUIRED
        ]
        assert len(approval_events) == 2, (
            f"Expected 2 APPROVAL_REQUIRED events (one per plan cycle), "
            f"got {len(approval_events)}"
        )

    async def test_replan_rejects_non_blocked_workflow(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Profile,
        valid_worktree: str,
    ) -> None:
        """Replan should raise InvalidStateError for non-blocked workflows."""
        from amelia.server.exceptions import InvalidStateError

        # Create a workflow in PLANNING status (not BLOCKED)
        request = CreateWorkflowRequest(
            issue_id="ISSUE-REPLAN-REJECT",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
            task_title="Test replan rejection",
        )

        async with mock_langgraph_for_planning():
            workflow_id = await test_orchestrator.queue_and_plan_workflow(request)

            # Wait for planning to finish -> BLOCKED
            if workflow_id in test_orchestrator._planning_tasks:
                await test_orchestrator._planning_tasks[workflow_id]

        # Manually set the workflow to PENDING to test rejection
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        workflow.workflow_status = WorkflowStatus.PENDING
        await test_repository.update(workflow)

        # Replan should fail because workflow is PENDING, not BLOCKED
        with pytest.raises(InvalidStateError):
            await test_orchestrator.replan_workflow(workflow_id)

    async def test_replan_clears_old_plan_fields(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        active_test_profile: Profile,
        valid_worktree: str,
    ) -> None:
        """Replan should clear stale plan fields before regenerating."""
        # Phase 1: create initial plan
        request = CreateWorkflowRequest(
            issue_id="ISSUE-REPLAN-CLEAR",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
            task_title="Test replan clears fields",
        )

        async with mock_langgraph_for_planning(
            goal="Old goal",
            plan_markdown="# Old Plan",
        ):
            workflow_id = await test_orchestrator.queue_and_plan_workflow(request)
            if workflow_id in test_orchestrator._planning_tasks:
                await test_orchestrator._planning_tasks[workflow_id]

        # Verify old plan is set
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.execution_state is not None
        assert workflow.execution_state.goal == "Old goal"

        # Phase 2: replan with new plan
        async with mock_langgraph_for_planning(
            goal="Fresh goal",
            plan_markdown="# Fresh Plan",
        ):
            await test_orchestrator.replan_workflow(workflow_id)
            if workflow_id in test_orchestrator._planning_tasks:
                await test_orchestrator._planning_tasks[workflow_id]

        # Verify new plan replaced old one
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.execution_state is not None
        assert workflow.execution_state.goal == "Fresh goal"
        assert "Fresh Plan" in (workflow.execution_state.plan_markdown or "")
        # Old plan should be gone
        assert "Old goal" not in (workflow.execution_state.goal or "")
        assert "Old Plan" not in (workflow.execution_state.plan_markdown or "")
