from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

from amelia.agents.architect import Architect
from amelia.core.state import Task
from amelia.core.state import TaskDAG
from amelia.core.types import Issue


async def test_architect_creates_valid_dag(tmp_path: Path) -> None:
    """
    Verify that the Architect agent can generate a syntactically and semantically valid TaskDAG
    from a given issue ticket.
    """
    mock_driver = MagicMock()

    class MockResponse:
        tasks = [
            Task(id="1", description="Set up project structure", dependencies=[]),
            Task(id="2", description="Implement core logic", dependencies=["1"]),
            Task(id="3", description="Add tests", dependencies=["2"]),
        ]

    mock_driver.generate = AsyncMock(return_value=MockResponse())

    architect = Architect(mock_driver)
    mock_issue = Issue(id="PROJ-123", title="Example Task", description="Implement feature X")

    result = await architect.plan(mock_issue, output_dir=str(tmp_path))

    # 1. generated_dag is an instance of TaskDAG
    assert isinstance(result.task_dag, TaskDAG)

    # 2. The DAG structure is valid (no cycles, all dependencies resolve)
    assert len(result.task_dag.tasks) == 3

    # 3. Tasks have meaningful structure
    assert result.task_dag.tasks[0].dependencies == []
    assert result.task_dag.tasks[1].dependencies == ["1"]
    assert result.task_dag.tasks[2].dependencies == ["2"]

    # 4. Original issue is tracked
    assert result.task_dag.original_issue == "PROJ-123"
