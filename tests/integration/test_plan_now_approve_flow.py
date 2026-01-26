"""Integration tests for plan_now → approve flow.

These tests verify the complete flow when using plan_now=True:
1. queue_and_plan_workflow runs through LangGraph (creating checkpoint)
2. Workflow status becomes "blocked" with plan available
3. approve_workflow resumes from checkpoint successfully

Bug context: Previously, queue_and_plan_workflow called architect.plan()
directly (bypassing LangGraph), so no checkpoint was created. This caused
approve_workflow to fail because there was nothing to resume from.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from amelia.core.types import AgentConfig, Profile
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.database.repository import WorkflowRepository
from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.orchestrator.service import OrchestratorService
from tests.conftest import init_git_repo
from tests.integration.conftest import mock_langgraph_for_planning


@pytest.fixture
def valid_worktree(tmp_path: Path) -> str:
    """Create a valid git worktree directory with required settings file."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    init_git_repo(worktree)

    # Worktree settings are required (no fallback to server settings)
    settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: cli
    model: sonnet
    validator_model: sonnet
    tracker: noop
    strategy: single
"""
    (worktree / "settings.amelia.yaml").write_text(settings_content)
    return str(worktree)


@pytest.fixture
async def active_test_profile(
    test_profile_repository: ProfileRepository,
    valid_worktree: str,
) -> Profile:
    """Create and activate a test profile in the database."""
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
        active_test_profile: Profile,
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
            extra_stream_items=[("updates", {"plan_validator_node": {}})],
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
        active_test_profile: Profile,
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
            extra_stream_items=[("updates", {"plan_validator_node": {}})],
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
                "amelia.server.orchestrator.service.create_implementation_graph"
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
        active_test_profile: Profile,
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
            extra_stream_items=[("updates", {"plan_validator_node": {}})],
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
