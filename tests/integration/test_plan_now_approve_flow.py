"""Integration tests for plan_now → approve flow.

These tests verify the complete flow when using plan_now=True:
1. queue_and_plan_workflow runs through LangGraph (creating checkpoint)
2. Workflow status becomes "blocked" with plan available
3. approve_workflow resumes from checkpoint successfully

Bug context: Previously, queue_and_plan_workflow called architect.plan()
directly (bypassing LangGraph), so no checkpoint was created. This caused
approve_workflow to fail because there was nothing to resume from.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.orchestrator.service import OrchestratorService


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
    goal: str = "Test goal from architect",
    plan_markdown: str = "## Plan\n\n### Task 1: First task\n- Do something",
) -> MagicMock:
    """Create a mock LangGraph graph that simulates planning.

    The mock graph yields chunks until it reaches an interrupt at human_approval_node.
    """
    mock_graph = MagicMock()

    # Mock aget_state to return checkpoint with plan data
    checkpoint_values = {
        "goal": goal,
        "plan_markdown": plan_markdown,
        "profile_id": "test",
    }
    mock_checkpoint = MagicMock()
    mock_checkpoint.values = checkpoint_values
    mock_checkpoint.next = []
    mock_graph.aget_state = AsyncMock(return_value=mock_checkpoint)

    # Mock astream to yield chunks including interrupt
    astream_items = [
        ("updates", {"architect_node": {"goal": goal, "plan_markdown": plan_markdown}}),
        ("updates", {"plan_validator_node": {}}),
        ("updates", {"__interrupt__": ("Paused for approval",)}),
    ]
    mock_graph.astream = lambda *args, **kwargs: AsyncIteratorMock(astream_items)

    # Mock aupdate_state for approve_workflow
    mock_graph.aupdate_state = AsyncMock()

    return mock_graph


@asynccontextmanager
async def mock_langgraph_for_planning(
    goal: str = "Test goal from architect",
    plan_markdown: str = "## Plan\n\n### Task 1: First task\n- Do something",
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
async def test_db(temp_db_path: Path) -> AsyncGenerator[Database, None]:
    """Create and initialize in-memory SQLite database."""
    db = Database(temp_db_path)
    await db.connect()
    await db.ensure_schema()
    yield db
    await db.close()


@pytest.fixture
def test_repository(test_db: Database) -> WorkflowRepository:
    """Create repository backed by test database."""
    return WorkflowRepository(test_db)


@pytest.fixture
def test_event_bus() -> EventBus:
    """Create event bus for testing."""
    return EventBus()


@pytest.fixture
def temp_checkpoint_db(tmp_path: Path) -> str:
    """Create temporary checkpoint database path."""
    return str(tmp_path / "checkpoints.db")


@pytest.fixture
def test_orchestrator(
    test_event_bus: EventBus,
    test_repository: WorkflowRepository,
    temp_checkpoint_db: str,
) -> OrchestratorService:
    """Create real OrchestratorService with test dependencies."""
    return OrchestratorService(
        event_bus=test_event_bus,
        repository=test_repository,
        checkpoint_path=temp_checkpoint_db,
    )


@pytest.fixture
def valid_worktree(tmp_path: Path) -> str:
    """Create a valid git worktree directory with required settings file."""
    import subprocess

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=worktree, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=worktree,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=worktree,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=worktree,
        capture_output=True,
        check=True,
    )
    (worktree / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=worktree, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=worktree,
        capture_output=True,
        check=True,
    )

    # Worktree settings are required (no fallback to server settings)
    settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: cli:claude
    model: sonnet
    tracker: noop
    strategy: single
"""
    (worktree / "settings.amelia.yaml").write_text(settings_content)
    return str(worktree)


@pytest.mark.integration
class TestPlanNowApproveFlow:
    """Tests for the complete plan_now → approve workflow flow.

    Verifies that queue_and_plan_workflow runs through LangGraph,
    creating proper checkpoints that approve_workflow can resume from.
    """

    async def test_plan_now_creates_checkpoint_for_approve(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        valid_worktree: str,
    ) -> None:
        """queue_and_plan_workflow should create LangGraph checkpoint.

        When plan_now=True, the planning phase should run through LangGraph
        so that approve_workflow can resume from the checkpoint.
        """
        request = CreateWorkflowRequest(
            issue_id="ISSUE-PLAN-NOW",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
            task_title="Test task for plan_now",
        )

        # Run queue_and_plan_workflow with mocked LangGraph
        async with mock_langgraph_for_planning(
            goal="Implement the test feature",
            plan_markdown="# Plan\n\n## Phase 1\n### Task 1: Do thing",
        ):
            workflow_id = await test_orchestrator.queue_and_plan_workflow(request)

            # Wait for the background planning task to complete
            if workflow_id in test_orchestrator._planning_tasks:
                await test_orchestrator._planning_tasks[workflow_id]

        # Verify workflow is in blocked state (waiting for approval)
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.workflow_status == "blocked", (
            f"Expected 'blocked' but got '{workflow.workflow_status}'"
        )
        assert workflow.planned_at is not None, "planned_at should be set after planning"

    async def test_plan_now_and_approve_completes_successfully(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        valid_worktree: str,
        langgraph_mock_factory: Any,
    ) -> None:
        """Complete flow: plan_now → blocked → approve → completion.

        This tests the full lifecycle:
        1. queue_and_plan_workflow creates checkpoint during planning
        2. Workflow becomes blocked waiting for approval
        3. approve_workflow resumes from checkpoint
        4. Workflow completes successfully
        """
        request = CreateWorkflowRequest(
            issue_id="ISSUE-FULL-FLOW",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
            task_title="Full flow test",
        )

        # Step 1: Run planning with mocked graph
        async with mock_langgraph_for_planning(
            goal="Test goal",
            plan_markdown="## Plan\n\n### Task 1: Test",
        ):
            workflow_id = await test_orchestrator.queue_and_plan_workflow(request)

            # Wait for planning to complete
            if workflow_id in test_orchestrator._planning_tasks:
                await test_orchestrator._planning_tasks[workflow_id]

        # Verify blocked status
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.workflow_status == "blocked"

        # Step 2: Approve and resume with mocked post-approval execution
        mocks = langgraph_mock_factory(
            astream_items=[
                ("updates", {"developer_node": {"agentic_status": "completed"}}),
                ("updates", {"reviewer_node": {}}),
            ],
            aget_state_return=MagicMock(
                values={"goal": "Test goal", "profile_id": "test"},
                next=["developer_node"],
            ),
        )

        with (
            patch(
                "amelia.server.orchestrator.service.AsyncSqliteSaver"
            ) as mock_saver_class,
            patch(
                "amelia.server.orchestrator.service.create_orchestrator_graph"
            ) as mock_create_graph,
        ):
            mock_create_graph.return_value = mocks.graph
            mock_saver_class.from_conn_string.return_value = (
                mocks.saver_class.from_conn_string.return_value
            )

            # This should NOT raise an error
            await test_orchestrator.approve_workflow(workflow_id)

        # Verify workflow progressed past approval
        final_workflow = await test_repository.get(workflow_id)
        assert final_workflow is not None
        assert final_workflow.workflow_status in ("completed", "in_progress"), (
            f"Expected 'completed' or 'in_progress' but got '{final_workflow.workflow_status}'"
        )

    async def test_plan_now_syncs_plan_to_server_state(
        self,
        test_orchestrator: OrchestratorService,
        test_repository: WorkflowRepository,
        valid_worktree: str,
    ) -> None:
        """Plan data should be synced from checkpoint to ServerExecutionState.

        When planning completes, the goal and plan_markdown from the checkpoint
        should be synced to the ServerExecutionState so it's available via REST API.
        """
        request = CreateWorkflowRequest(
            issue_id="ISSUE-SYNC",
            worktree_path=valid_worktree,
            start=False,
            plan_now=True,
            task_title="Test plan sync",
        )

        goal = "Synced goal from checkpoint"
        plan_markdown = "## Synced Plan\n\n### Task 1: Synced task"

        async with mock_langgraph_for_planning(
            goal=goal,
            plan_markdown=plan_markdown,
        ):
            workflow_id = await test_orchestrator.queue_and_plan_workflow(request)

            # Wait for planning to complete
            if workflow_id in test_orchestrator._planning_tasks:
                await test_orchestrator._planning_tasks[workflow_id]

        # Verify plan data was synced to ServerExecutionState
        workflow = await test_repository.get(workflow_id)
        assert workflow is not None
        assert workflow.workflow_status == "blocked"
        assert workflow.execution_state is not None
        assert workflow.execution_state.goal == goal, (
            f"Goal should be synced from checkpoint. Got: {workflow.execution_state.goal}"
        )
        assert plan_markdown in (workflow.execution_state.plan_markdown or ""), (
            f"Plan should be synced from checkpoint. Got: {workflow.execution_state.plan_markdown}"
        )
