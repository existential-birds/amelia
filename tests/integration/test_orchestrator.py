# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import asyncio
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from amelia.agents.architect import PlanOutput
from amelia.agents.reviewer import ReviewResponse
from amelia.core.orchestrator import call_reviewer_node, create_orchestrator_graph
from amelia.core.state import ExecutionState, Task, TaskDAG
from amelia.core.types import Issue, Profile


async def test_orchestrator_parallel_review_api() -> None:
    """Verifies concurrent API calls during competitive review with an API driver."""
    profile = Profile(
        name="api_comp_reviewer", driver="api:openai", tracker="noop", strategy="competitive"
    )
    test_issue = Issue(
        id="PAR-API", title="Parallel API Review", description="Test concurrent API calls for review."
    )

    mock_driver = AsyncMock()

    async def slow_generate(*_args: Any, **_kwargs: Any) -> ReviewResponse:
        await asyncio.sleep(0.1)
        return ReviewResponse(approved=True, comments=[], severity="low")

    mock_driver.generate.side_effect = slow_generate

    with patch("amelia.drivers.factory.DriverFactory.get_driver", return_value=mock_driver):
        start_time = time.time()

        initial_state = ExecutionState(
            profile=profile,
            issue=test_issue,
            code_changes_for_review="changes"
        )

        config = {"configurable": {"thread_id": "test-parallel-review"}}
        await call_reviewer_node(initial_state, config)

        duration = time.time() - start_time

        # Sequential: 0.3s, Parallel: ~0.1s
        assert duration < 0.25
        assert mock_driver.generate.call_count == 3


@pytest.mark.parametrize(
    "driver_type,profile_name,task_prefix,issue_id,issue_title",
    [
        ("api:openai", "api_parallel", "P", "PAR-EXEC", "Parallel Execution Test"),
        ("cli:claude", "cli_parallel", "S", "CLI-PAR", "CLI Parallel Test"),
    ],
    ids=["api_driver", "cli_driver"]
)
async def test_orchestrator_parallel_execution(
    driver_type: str,
    profile_name: str,
    task_prefix: str,
    issue_id: str,
    issue_title: str
) -> None:
    """Verifies the orchestrator executes independent tasks in parallel with different drivers."""
    profile = Profile(name=profile_name, driver=driver_type, tracker="noop", strategy="single")
    test_issue = Issue(id=issue_id, title=issue_title, description="Execute tasks in parallel.")

    async def delayed_execute_current_task(_self: Any, state: ExecutionState, workflow_id: str | None = None) -> dict[str, str]:
        await asyncio.sleep(0.05)
        return {"status": "completed", "output": f"Task {state.current_task_id} finished"}

    mock_plan_output = PlanOutput(
        task_dag=TaskDAG(tasks=[
            Task(id=f"{task_prefix}1", description="Task 1", status="pending"),
            Task(id=f"{task_prefix}2", description="Task 2", status="pending"),
        ], original_issue=issue_id),
        markdown_path=Path(f"/tmp/test-plan-{issue_id.lower()}.md")
    )

    mock_driver = AsyncMock()
    mock_driver.generate.return_value = ReviewResponse(approved=True, comments=[], severity="low")

    with patch('amelia.agents.architect.Architect.plan', new_callable=AsyncMock) as mock_plan, \
         patch('amelia.agents.developer.Developer.execute_current_task', new=delayed_execute_current_task), \
         patch('amelia.drivers.factory.DriverFactory.get_driver', return_value=mock_driver), \
         patch('amelia.core.orchestrator.get_code_changes_for_review', new_callable=AsyncMock, return_value="mock code changes"), \
         patch('typer.confirm', return_value=True), \
         patch('typer.prompt', return_value=""):

        mock_plan.return_value = mock_plan_output
        initial_state = ExecutionState(profile=profile, issue=test_issue)
        app = create_orchestrator_graph()

        start_time = time.time()
        config = {"configurable": {"thread_id": f"test-parallel-exec-{issue_id.lower()}"}}
        final_state = await app.ainvoke(initial_state, config)
        duration = time.time() - start_time

        # Sequential: 100ms, Parallel: ~50ms (200ms threshold for CI variability)
        assert duration < 0.2, f"Expected < 0.2s, got {duration:.3f}s"
        assert all(task.status == "completed" for task in final_state["plan"].tasks)
