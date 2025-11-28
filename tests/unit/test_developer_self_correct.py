from unittest.mock import AsyncMock

import pytest

from amelia.agents.developer import Developer
from amelia.core.state import Task
from amelia.drivers.base import DriverInterface


async def test_developer_self_correction_on_command_failure():
    """
    Verifies that the Developer agent can detect and react to command failures
    (simulated via stderr or exceptions from the driver).
    """
    mock_driver = AsyncMock(spec=DriverInterface)
    # Simulate a tool execution failure returning an error message
    mock_driver.execute_tool.side_effect = RuntimeError("Mocked command failed: /bin/false returned non-zero exit code.")

    developer = Developer(driver=mock_driver)
    
    # A task that would trigger a tool execution
    failing_task = Task(id="FAIL_T1", description="Run shell command: /bin/false", dependencies=[])
    
    result = await developer.execute_task(failing_task)
    
    # Assert that the task execution is marked as failed and the error message is captured
    assert result["status"] == "failed"
    assert "Mocked command failed" in result["output"]
    mock_driver.execute_tool.assert_called_once_with("run_shell_command", command="/bin/false")

@pytest.mark.skip(reason="Developer agent's self-correction logic not fully implemented yet.")
async def test_developer_reads_stderr_from_driver_for_refinement():
    """
    Tests that the Developer agent, when getting a response from `driver.generate`
    or `driver.execute_tool`, can identify error messages (e.g., from stderr)
    and use them for self-correction.
    """
    # This test would involve mocking `driver.generate` or `driver.execute_tool`
    # to return a structured output that includes error information or an explicit error.
    # The Developer agent would then need logic to parse this and decide on a corrective action.
    pass
