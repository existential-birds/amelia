# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for review loop logic in orchestrator."""

import pytest

from amelia.core.orchestrator import should_continue_developer, should_continue_review_loop


class TestReviewLoopLogic:
    """Tests for should_continue_review_loop function."""

    def test_should_end_when_reviewer_disapproves_but_no_ready_tasks(
        self,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory,
        mock_review_result_factory,
    ):
        """
        When reviewer disapproves but no ready tasks exist, should return 'end'.

        Scenario:
        - All tasks are completed
        - Reviewer disapproves the changes
        - No ready tasks to execute
        - Should return "end" to prevent infinite loop
        """
        task1 = mock_task_factory(id="1", status="completed", dependencies=[])
        task2 = mock_task_factory(id="2", status="completed", dependencies=["1"])

        plan = mock_task_dag_factory(tasks=[task1, task2])
        review = mock_review_result_factory(approved=False, severity="high")

        state = mock_execution_state_factory(plan=plan, last_review=review)

        result = should_continue_review_loop(state)

        assert result == "end", (
            "should_continue_review_loop should return 'end' when review is not "
            "approved but no ready tasks exist (prevents infinite loop)"
        )

    def test_should_reevaluate_when_reviewer_disapproves_and_ready_tasks_exist(
        self,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory,
        mock_review_result_factory,
    ):
        """
        When reviewer disapproves and ready tasks exist, should return 're_evaluate'.

        Scenario:
        - Some tasks are pending and ready to execute
        - Reviewer disapproves the changes
        - Should return "re_evaluate" to loop back to developer
        """
        task1 = mock_task_factory(id="1", status="pending", dependencies=[])
        task2 = mock_task_factory(id="2", status="pending", dependencies=[])

        plan = mock_task_dag_factory(tasks=[task1, task2])
        review = mock_review_result_factory(approved=False, severity="medium")

        state = mock_execution_state_factory(plan=plan, last_review=review)

        result = should_continue_review_loop(state)

        assert result == "re_evaluate", (
            "should_continue_review_loop should return 're_evaluate' when review "
            "is not approved and ready tasks exist"
        )

    def test_should_end_when_reviewer_approves(
        self,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory,
        mock_review_result_factory,
    ):
        """
        When reviewer approves, should return 'end'.

        Scenario:
        - Tasks may be pending or completed
        - Reviewer approves the changes
        - Should return "end" to exit the workflow
        """
        task1 = mock_task_factory(id="1", status="completed", dependencies=[])
        task2 = mock_task_factory(id="2", status="pending", dependencies=["1"])

        plan = mock_task_dag_factory(tasks=[task1, task2])
        review = mock_review_result_factory(approved=True, severity="low")

        state = mock_execution_state_factory(plan=plan, last_review=review)

        result = should_continue_review_loop(state)

        assert result == "end", (
            "should_continue_review_loop should return 'end' when review is approved"
        )

    def test_should_end_when_tasks_blocked_by_failure_and_reviewer_disapproves(
        self,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory,
        mock_review_result_factory,
    ):
        """
        When tasks are blocked by failed dependencies and reviewer disapproves,
        should return 'end'.

        Scenario:
        - Task 1 failed
        - Task 2 and 3 depend on Task 1, remain pending but not ready
        - Reviewer disapproves the changes
        - No ready tasks exist (blocked by failed dependency)
        - Should return "end" to prevent infinite loop
        """
        task1 = mock_task_factory(id="1", status="failed", dependencies=[])
        task2 = mock_task_factory(id="2", status="pending", dependencies=["1"])
        task3 = mock_task_factory(id="3", status="pending", dependencies=["1"])

        plan = mock_task_dag_factory(tasks=[task1, task2, task3])
        review = mock_review_result_factory(approved=False, severity="critical")

        state = mock_execution_state_factory(plan=plan, last_review=review)

        result = should_continue_review_loop(state)

        assert result == "end", (
            "should_continue_review_loop should return 'end' when review is not "
            "approved but tasks are blocked by failed dependencies"
        )

    def test_should_end_when_no_review(
        self, mock_execution_state_factory, mock_task_factory, mock_task_dag_factory
    ):
        """
        When no review exists, should return 'end'.

        Scenario:
        - No reviews have been performed yet
        - Should return "end" (default behavior)
        """
        task1 = mock_task_factory(id="1", status="pending", dependencies=[])

        plan = mock_task_dag_factory(tasks=[task1])
        state = mock_execution_state_factory(plan=plan, last_review=None)

        result = should_continue_review_loop(state)

        assert result == "end", (
            "should_continue_review_loop should return 'end' when no review exists"
        )

    def test_should_end_when_no_plan(
        self, mock_execution_state_factory, mock_review_result_factory
    ):
        """
        When no plan exists and reviewer disapproves, should return 'end'.

        Scenario:
        - Reviewer disapproves
        - No plan exists (edge case)
        - Should return "end" to prevent errors
        """
        review = mock_review_result_factory(approved=False, severity="high")
        state = mock_execution_state_factory(plan=None, last_review=review)

        result = should_continue_review_loop(state)

        assert result == "end", (
            "should_continue_review_loop should return 'end' when no plan exists"
        )

    def test_should_reevaluate_when_mixed_task_statuses_with_ready_tasks(
        self,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory,
        mock_review_result_factory,
    ):
        """
        When some tasks are completed, some pending with ready tasks, should 're_evaluate'.

        Scenario:
        - Task 1 completed
        - Task 2 depends on Task 1, now ready
        - Task 3 pending, no dependencies
        - Reviewer disapproves
        - Should return "re_evaluate" because ready tasks exist
        """
        task1 = mock_task_factory(id="1", status="completed", dependencies=[])
        task2 = mock_task_factory(id="2", status="pending", dependencies=["1"])
        task3 = mock_task_factory(id="3", status="pending", dependencies=[])

        plan = mock_task_dag_factory(tasks=[task1, task2, task3])
        review = mock_review_result_factory(approved=False, severity="medium")

        state = mock_execution_state_factory(plan=plan, last_review=review)

        result = should_continue_review_loop(state)

        assert result == "re_evaluate", (
            "should_continue_review_loop should return 're_evaluate' when ready "
            "tasks exist after some completions"
        )

    def test_should_reevaluate_when_review_disapproves_with_ready_tasks(
        self,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory,
        mock_review_result_factory,
    ):
        """
        Should return re_evaluate when review disapproves and ready tasks exist.

        Scenario:
        - Review disapproved with high severity
        - Ready tasks exist (pending task with no dependencies)
        - Should return "re_evaluate" to continue development
        """
        task1 = mock_task_factory(id="1", status="pending", dependencies=[])

        plan = mock_task_dag_factory(tasks=[task1])
        review = mock_review_result_factory(approved=False, severity="high")

        state = mock_execution_state_factory(
            plan=plan, last_review=review
        )

        result = should_continue_review_loop(state)

        assert result == "re_evaluate", (
            "should_continue_review_loop should return 're_evaluate' when review "
            "disapproves and ready tasks exist"
        )


class TestShouldContinueDeveloper:
    """Tests for should_continue_developer() blocking logic."""

    @pytest.mark.parametrize(
        "task_statuses,expected",
        [
            # All completed -> end
            (["completed", "completed"], "end"),
            # Has pending with no blockers -> continue
            (["completed", "pending"], "continue"),
            # Failed task blocks dependent -> end
            (["failed", "pending"], "end"),
            # No tasks -> end
            ([], "end"),
            # Single pending task with no deps -> continue
            (["pending"], "continue"),
            # Multiple tasks blocked by single failure -> end
            (["failed", "pending", "pending"], "end"),
        ],
        ids=[
            "all_completed_ends",
            "pending_with_completed_dep_continues",
            "failed_blocks_dependent_ends",
            "no_tasks_ends",
            "single_pending_continues",
            "multiple_blocked_by_failure_ends",
        ],
    )
    def test_should_continue_developer(
        self,
        task_statuses: list[str],
        expected: str,
        mock_execution_state_factory,
        mock_task_factory,
        mock_task_dag_factory,
    ):
        """Parametrized test for developer continuation logic."""
        tasks = []
        for i, status in enumerate(task_statuses):
            task = mock_task_factory(
                id=f"TASK-{i}",
                status=status,
                dependencies=[f"TASK-{i-1}"] if i > 0 else [],
            )
            tasks.append(task)

        plan = mock_task_dag_factory(tasks=tasks) if tasks else None
        state = mock_execution_state_factory(plan=plan)

        result = should_continue_developer(state)
        assert result == expected

    def test_should_end_when_no_plan(self, mock_execution_state_factory):
        """Should return 'end' when there's no plan."""
        state = mock_execution_state_factory(plan=None)

        result = should_continue_developer(state)

        assert result == "end"
