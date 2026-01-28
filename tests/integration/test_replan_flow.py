"""Integration tests for the replan workflow lifecycle.

Tests the full replan cycle with real OrchestratorService, real repository,
mocking only at the LangGraph boundary.

Flow tested:
1. queue_and_plan_workflow → PENDING → BLOCKED (original plan)
2. replan_workflow → PENDING → BLOCKED (new plan)
3. Verify plan data is updated and events are emitted correctly
"""
from typing import Any

import pytest

from amelia.core.types import Profile
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.models.events import EventType
from amelia.server.models.requests import CreateWorkflowRequest
from amelia.server.models.state import WorkflowStatus
from amelia.server.orchestrator.service import OrchestratorService
from tests.integration.conftest import mock_langgraph_for_planning


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
        """Full cycle: PENDING → BLOCKED → replan → PENDING → BLOCKED."""
        # Track events
        received_events: list[Any] = []
        test_event_bus.subscribe(lambda e: received_events.append(e))

        # Phase 1: queue_and_plan_workflow -> PENDING -> BLOCKED
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
        assert workflow.execution_state is not None
        assert workflow.execution_state.goal == "Original goal from architect"
        assert "Original Plan" in (workflow.execution_state.plan_markdown or "")

        # Phase 2: replan -> PENDING -> BLOCKED (with new plan)
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

        # Create a workflow in PENDING status (not BLOCKED)
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
