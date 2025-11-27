import asyncio
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from amelia.agents.architect import Architect
from amelia.core.orchestrator import create_orchestrator_graph
from amelia.core.state import ExecutionState
from amelia.core.state import Issue
from amelia.core.state import Profile
from amelia.core.state import Task
from amelia.core.state import TaskDAG
from amelia.core.state import TaskStatus


@pytest.fixture
def mock_delay_developer():
    """Mocks developer to simulate a delay for task execution."""
    async def delayed_execute_task(self, task: Task):
        await asyncio.sleep(0.1)  # Simulate task taking 100ms
        return {"status": "completed", "output": f"Task {task.id} finished after delay"}
    with patch('amelia.agents.developer.Developer.execute_task', new=delayed_execute_task):
        yield


@pytest.mark.skip(reason="Orchestrator parallel execution (T034) and proper task scheduling not yet implemented.")
@pytest.mark.parametrize("driver_spec,profile_name,issue_id,max_duration,min_duration", [
    pytest.param(
        "api:openai", "api_perf", "PERF-API",
        0.15, None,  # Parallel: ~0.1s (2x speedup)
        id="api_parallel_speedup"
    ),
    pytest.param(
        "cli:claude", "cli_perf", "PERF-CLI",
        None, 0.19,  # Sequential: ~0.2s
        id="cli_sequential_time"
    ),
])
async def test_driver_execution_speed(
    mock_delay_developer,
    driver_spec,
    profile_name,
    issue_id,
    max_duration,
    min_duration
):
    """
    Parametrized test for driver execution speed characteristics.
    - API driver should achieve parallel speedup
    - CLI driver should run sequentially
    """
    profile = Profile(name=profile_name, driver=driver_spec, tracker="noop", strategy="single")
    test_issue = Issue(id=issue_id, title="Performance Test", description="Test execution speed.")

    mock_plan = TaskDAG(tasks=[
        Task(id="T1", description="Task 1", status=TaskStatus.PENDING),
        Task(id="T2", description="Task 2", status=TaskStatus.PENDING),
    ], original_issue=issue_id)

    with patch.object(Architect, 'plan', AsyncMock(return_value=mock_plan)):
        initial_state = ExecutionState(profile=profile, issue=test_issue)
        app = create_orchestrator_graph()

        start_time = asyncio.get_event_loop().time()
        with patch('typer.confirm', return_value=True), \
             patch('typer.prompt', return_value=""):
            final_state = await app.ainvoke(initial_state)
        end_time = asyncio.get_event_loop().time()

        duration = end_time - start_time

        if max_duration is not None:
            assert duration < max_duration, f"Expected parallel execution < {max_duration}s, got {duration}s"
        if min_duration is not None:
            assert duration >= min_duration, f"Expected sequential execution >= {min_duration}s, got {duration}s"

        assert all(task.status == TaskStatus.COMPLETED for task in final_state.plan.tasks)
