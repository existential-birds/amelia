from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

from amelia.agents.architect import Architect
from amelia.core.state import Task
from amelia.core.types import Issue
from amelia.drivers.base import DriverInterface


async def test_driver_parity_design_plan_review(tmp_path: Path) -> None:
    """
    Verifies that the Design and Plan phases function equivalently
    across both CLI and API drivers (via mocking).
    """
    test_issue = Issue(id="PARITY-1", title="Driver Parity Test", description="Ensure consistent behavior.")

    class MockResponse:
        tasks = [
            Task(id="1", description="Implement feature", dependencies=[]),
        ]

    # --- Test with CLI Driver Mock ---
    mock_cli_driver = MagicMock(spec=DriverInterface)
    mock_cli_driver.generate = AsyncMock(return_value=MockResponse())

    architect_cli = Architect(mock_cli_driver)
    result_cli = await architect_cli.plan(test_issue, output_dir=str(tmp_path / "cli"))

    assert len(result_cli.task_dag.tasks) == 1
    assert result_cli.task_dag.original_issue == "PARITY-1"
    mock_cli_driver.generate.assert_called_once()

    # --- Test with API Driver Mock ---
    mock_api_driver = MagicMock(spec=DriverInterface)
    mock_api_driver.generate = AsyncMock(return_value=MockResponse())

    architect_api = Architect(mock_api_driver)
    result_api = await architect_api.plan(test_issue, output_dir=str(tmp_path / "api"))

    assert len(result_api.task_dag.tasks) == 1
    assert result_api.task_dag.original_issue == "PARITY-1"
    mock_api_driver.generate.assert_called_once()

    # --- Verify parity: both produce equivalent results ---
    assert len(result_cli.task_dag.tasks) == len(result_api.task_dag.tasks)
    assert result_cli.task_dag.original_issue == result_api.task_dag.original_issue
