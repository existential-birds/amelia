import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from amelia.core.orchestrator import create_orchestrator_graph
from amelia.core.state import ExecutionState, Profile, Issue, Task, TaskDAG, TaskStatus
from amelia.agents.architect import Architect # For mocking plan

@pytest.fixture
def mock_delay_developer():
    """Mocks developer to simulate a delay for task execution."""
    async def delayed_execute_task(self, task: Task):
        await asyncio.sleep(0.1) # Simulate task taking 100ms
        return {"status": "completed", "output": f"Task {task.id} finished after delay"}
    with patch('amelia.agents.developer.Developer.execute_task', new=delayed_execute_task):
        yield

@pytest.mark.skip(reason="Orchestrator parallel execution (T034) and proper task scheduling not yet implemented.")
async def test_api_driver_parallel_speedup(mock_delay_developer):
    """
    Asserts that API driver with parallel tasks achieves a speedup over sequential execution.
    """
    profile_api = Profile(name="api_perf", driver="api:openai", tracker="noop", strategy="single")
    test_issue = Issue(id="PERF-API", title="Parallel Performance Test", description="Test API speedup.")

    # Create a plan with two independent parallelizable tasks
    mock_plan = TaskDAG(tasks=[
        Task(id="P1", description="API Task 1", status=TaskStatus.PENDING),
        Task(id="P2", description="API Task 2", status=TaskStatus.PENDING),
    ], original_issue="PERF-API")

    with patch.object(Architect, 'plan', AsyncMock(return_value=mock_plan)):
        initial_state = ExecutionState(profile=profile_api, issue=test_issue)
        app = create_orchestrator_graph()
        
        start_time = asyncio.get_event_loop().time()
        # Mocking human approval to skip the interaction
        with patch('typer.confirm', return_value=True), \
             patch('typer.prompt', return_value=""):
            final_state = await app.ainvoke(initial_state)
        end_time = asyncio.get_event_loop().time()
        
        duration = end_time - start_time
        
        # Expect two tasks to run, each taking 0.1s. In parallel, total time should be ~0.1s
        # (plus overhead). If sequential, ~0.2s.
        assert duration < 0.15 # Expecting near 0.1s for parallel execution (2x speedup)
        assert all(task.status == TaskStatus.COMPLETED for task in final_state.plan.tasks)


@pytest.mark.skip(reason="CLI driver sequential execution (T036) and proper task scheduling not yet implemented.")
async def test_cli_driver_sequential_time(mock_delay_developer):
    """
    Asserts that CLI driver with parallel tasks (which run sequentially) takes expected time.
    """
    profile_cli = Profile(name="cli_perf", driver="cli:claude", tracker="noop", strategy="single")
    test_issue = Issue(id="PERF-CLI", title="Sequential Performance Test", description="Test CLI sequential time.")

    # Create a plan with two independent parallelizable tasks
    mock_plan = TaskDAG(tasks=[
        Task(id="S1", description="CLI Task 1", status=TaskStatus.PENDING),
        Task(id="S2", description="CLI Task 2", status=TaskStatus.PENDING),
    ], original_issue="PERF-CLI")

    with patch.object(Architect, 'plan', AsyncMock(return_value=mock_plan)):
        initial_state = ExecutionState(profile=profile_cli, issue=test_issue)
        app = create_orchestrator_graph()
        
        start_time = asyncio.get_event_loop().time()
        # Mocking human approval to skip the interaction
        with patch('typer.confirm', return_value=True), \
             patch('typer.prompt', return_value=""):
            final_state = await app.ainvoke(initial_state)
        end_time = asyncio.get_event_loop().time()
        
        duration = end_time - start_time
        
        # Expect two tasks to run, each taking 0.1s. In sequential, total time should be ~0.2s.
        assert duration >= 0.19 # Expecting near 0.2s for sequential execution
        assert all(task.status == TaskStatus.COMPLETED for task in final_state.plan.tasks)
