from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from amelia.agents.architect import Architect
from amelia.agents.architect import PlanOutput
from amelia.core.state import FileOperation
from amelia.core.state import Task
from amelia.core.state import TaskDAG
from amelia.core.state import TaskStep
from amelia.core.types import Design
from amelia.core.types import Issue


@pytest.fixture
def mock_driver_for_architect():
    """Mock driver that returns a TaskListResponse-like object."""
    mock = MagicMock()

    class MockResponse:
        tasks = [
            Task(
                id="1",
                description="Add auth middleware",
                files=[FileOperation(operation="create", path="src/auth.py")],
                steps=[
                    TaskStep(description="Write failing test", code="def test_auth(): pass"),
                    TaskStep(description="Run test", command="pytest", expected_output="FAILED"),
                ],
                commit_message="feat: add auth middleware"
            )
        ]

    mock.generate = AsyncMock(return_value=MockResponse())
    return mock


async def test_architect_plan_returns_plan_output(mock_driver_for_architect, tmp_path):
    architect = Architect(mock_driver_for_architect)
    issue = Issue(id="TEST-1", title="Add auth", description="Add authentication")

    result = await architect.plan(issue, output_dir=str(tmp_path))

    assert isinstance(result, PlanOutput)
    assert isinstance(result.task_dag, TaskDAG)
    assert isinstance(result.markdown_path, Path)
    assert result.markdown_path.exists()


async def test_architect_plan_with_design(mock_driver_for_architect, tmp_path):
    architect = Architect(mock_driver_for_architect)
    issue = Issue(id="TEST-1", title="Add auth", description="Add authentication")
    design = Design(
        title="Auth Feature",
        goal="Add JWT auth",
        architecture="Middleware-based",
        tech_stack=["PyJWT"],
        components=["AuthMiddleware"],
        raw_content="# Design"
    )

    result = await architect.plan(issue, design=design, output_dir=str(tmp_path))

    assert result.task_dag.tasks[0].description == "Add auth middleware"
    # Verify design context was used (check prompt in mock call)
    call_args = mock_driver_for_architect.generate.call_args
    messages = call_args.kwargs.get("messages") or call_args[0][0]
    prompt_content = " ".join(m.content for m in messages)
    assert "Auth Feature" in prompt_content or "JWT auth" in prompt_content


async def test_developer_executes_task(mock_driver):
    """
    Test that the Developer agent can execute a given task.
    """
    from amelia.agents.developer import Developer

    developer = Developer(driver=mock_driver)
    task = Task(id="DEV-1", description="Write a hello world function")

    result = await developer.execute_task(task)

    assert result["status"] == "completed"
    assert "output" in result
    mock_driver.generate.assert_called_once()
