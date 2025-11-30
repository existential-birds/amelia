"""Tests for blocked workflow detection in orchestrator."""


from amelia.core.orchestrator import should_continue_developer


class TestBlockedWorkflowDetection:
    """Tests for detecting blocked workflows when tasks fail."""

    def test_should_end_when_task_fails_blocking_dependents(
        self, mock_execution_state_factory, mock_task_factory, mock_task_dag_factory
    ):
        """
        When a task fails and blocks its dependents, should_continue_developer
        should return 'end' to prevent infinite loop.

        Scenario:
        - Task 1 fails (status="failed")
        - Task 2 depends on Task 1, remains pending
        - No ready tasks exist (Task 2's dependency not completed)
        - Should return "end", not "continue"
        """
        task1 = mock_task_factory(id="1", status="failed", dependencies=[])
        task2 = mock_task_factory(id="2", status="pending", dependencies=["1"])

        plan = mock_task_dag_factory(tasks=[task1, task2])
        state = mock_execution_state_factory(plan=plan)

        result = should_continue_developer(state)

        assert result == "end", (
            "should_continue_developer should return 'end' when pending tasks "
            "exist but none are ready (blocked by failed dependencies)"
        )

    def test_should_continue_when_ready_tasks_exist(
        self, mock_execution_state_factory, mock_task_factory, mock_task_dag_factory
    ):
        """Should return 'continue' when there are ready tasks to execute."""
        task1 = mock_task_factory(id="1", status="pending", dependencies=[])

        plan = mock_task_dag_factory(tasks=[task1])
        state = mock_execution_state_factory(plan=plan)

        result = should_continue_developer(state)

        assert result == "continue"

    def test_should_end_when_all_tasks_completed(
        self, mock_execution_state_factory, mock_task_factory, mock_task_dag_factory
    ):
        """Should return 'end' when all tasks are completed."""
        task1 = mock_task_factory(id="1", status="completed", dependencies=[])
        task2 = mock_task_factory(id="2", status="completed", dependencies=["1"])

        plan = mock_task_dag_factory(tasks=[task1, task2])
        state = mock_execution_state_factory(plan=plan)

        result = should_continue_developer(state)

        assert result == "end"

    def test_should_continue_when_some_tasks_ready_after_completion(
        self, mock_execution_state_factory, mock_task_factory, mock_task_dag_factory
    ):
        """Should continue when completed tasks unlock pending dependents."""
        task1 = mock_task_factory(id="1", status="completed", dependencies=[])
        task2 = mock_task_factory(id="2", status="pending", dependencies=["1"])

        plan = mock_task_dag_factory(tasks=[task1, task2])
        state = mock_execution_state_factory(plan=plan)

        result = should_continue_developer(state)

        assert result == "continue"

    def test_should_end_when_multiple_tasks_blocked_by_single_failure(
        self, mock_execution_state_factory, mock_task_factory, mock_task_dag_factory
    ):
        """Multiple pending tasks blocked by a single failed task should end."""
        task1 = mock_task_factory(id="1", status="failed", dependencies=[])
        task2 = mock_task_factory(id="2", status="pending", dependencies=["1"])
        task3 = mock_task_factory(id="3", status="pending", dependencies=["1"])

        plan = mock_task_dag_factory(tasks=[task1, task2, task3])
        state = mock_execution_state_factory(plan=plan)

        result = should_continue_developer(state)

        assert result == "end"

    def test_should_end_when_no_plan(self, mock_execution_state_factory):
        """Should return 'end' when there's no plan."""
        state = mock_execution_state_factory(plan=None)

        result = should_continue_developer(state)

        assert result == "end"
