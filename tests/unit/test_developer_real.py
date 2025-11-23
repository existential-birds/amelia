import pytest
from unittest.mock import AsyncMock
from amelia.agents.developer import Developer
from amelia.core.state import Task

@pytest.mark.asyncio
async def test_developer_executes_tool_not_simulation():
    mock_driver = AsyncMock()
    mock_driver.execute_tool.return_value = "File created"
    
    dev = Developer(mock_driver)
    # Using a description that triggers the existing logic path but we want to ensure it calls the driver
    task = Task(id="1", description="write file: test.py with print('hi')", status="pending", dependencies=[])
    
    result = await dev.execute_task(task)
    
    # Verify execute_tool was CALLED, not just printed/simulated
    # The current code has 'write file:' logic but it returns "File write simulated"
    # We want it to call execute_tool("write_file", ...)
    
    # NOTE: The existing code splits by "write file:". 
    # We will update the code to properly parse this or use a better mechanism.
    # For this test, we expect the update to parse "test.py" and "print('hi')" somehow
    # or at least call execute_tool.
    
    # The failing test expects execute_tool to be called.
    mock_driver.execute_tool.assert_called_once()
    assert result["output"] == "File created"
