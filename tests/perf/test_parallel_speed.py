import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from amelia.agents.architect import Architect
from amelia.agents.architect import PlanOutput
from amelia.agents.reviewer import ReviewResponse
from amelia.core.orchestrator import create_orchestrator_graph
from amelia.core.state import ExecutionState
from amelia.core.state import Task
from amelia.core.state import TaskDAG
from amelia.core.types import DriverType
from amelia.core.types import Issue
from amelia.core.types import Profile


@pytest.fixture
def mock_delay_developer() -> Iterator[None]:
    """Mocks developer to simulate a delay for task execution."""
    async def delayed_execute_task(self: Any, task: Task) -> dict[str, str]:
        await asyncio.sleep(0.05)  # Simulate task taking 50ms
        return {"status": "completed", "output": f"Task {task.id} finished after delay"}
    with patch('amelia.agents.developer.Developer.execute_task', new=delayed_execute_task):
        yield


@pytest.fixture
def mock_driver() -> MagicMock:
    """Create a mock driver that can be used for both API and CLI tests."""
    driver = MagicMock()
    driver.generate = AsyncMock(return_value=ReviewResponse(
        approved=True,
        comments=[],
        severity="low"
    ))
    return driver


@pytest.mark.parametrize("driver_spec,profile_name,issue_id,max_duration", [
    pytest.param(
        "api:openai", "home", "PERF-API",
        0.3,  # Parallel: 2 tasks @ 50ms each + overhead
        id="api_parallel_speedup"
    ),
    pytest.param(
        "cli:claude", "personal", "PERF-CLI",
        0.3,  # Both use asyncio.gather
        id="cli_execution_time"
    ),
])
async def test_driver_execution_speed(
    mock_delay_developer: None,
    mock_driver: MagicMock,
    driver_spec: DriverType,
    profile_name: str,
    issue_id: str,
    max_duration: float
) -> None:
    """
    Parametrized test for driver execution speed characteristics.
    Both drivers use asyncio.gather for parallel task execution.
    """
    profile = Profile(name=profile_name, driver=driver_spec, tracker="noop", strategy="single")
    test_issue = Issue(id=issue_id, title="Performance Test", description="Test execution speed.")

    mock_plan_output = PlanOutput(
        task_dag=TaskDAG(tasks=[
            Task(id="T1", description="Task 1", status="pending"),
            Task(id="T2", description="Task 2", status="pending"),
        ], original_issue=issue_id),
        markdown_path=Path("/tmp/test-plan.md")
    )

    with patch.object(Architect, 'plan', AsyncMock(return_value=mock_plan_output)), \
         patch('amelia.drivers.factory.DriverFactory.get_driver', return_value=mock_driver):
        initial_state = ExecutionState(profile=profile, issue=test_issue)
        app = create_orchestrator_graph()

        start_time = asyncio.get_event_loop().time()
        with patch('typer.confirm', return_value=True), \
             patch('typer.prompt', return_value=""):
            final_state = await app.ainvoke(initial_state)
        end_time = asyncio.get_event_loop().time()

        duration = end_time - start_time

        assert duration < max_duration, f"Expected execution < {max_duration}s, got {duration}s"
        assert all(task.status == "completed" for task in final_state["plan"].tasks)
