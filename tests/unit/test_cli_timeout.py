import pytest
from unittest.mock import AsyncMock, patch
from amelia.drivers.cli.claude import ClaudeCliDriver
from amelia.core.state import AgentMessage

@pytest.mark.asyncio
async def test_cli_driver_timeout_configuration():
    driver = ClaudeCliDriver(timeout=5, max_retries=2)
    assert driver.timeout == 5
    assert driver.max_retries == 2

@pytest.mark.asyncio
async def test_cli_driver_execute_tool_timeout_retry():
    # Mock run_shell_command to fail with TimeoutError (simulated via RuntimeError from shell_executor) first, then succeed
    # We need to mock amelia.drivers.cli.claude.run_shell_command because that's where it's imported
    
    # NOTE: shell_executor.run_shell_command raises RuntimeError("...timed out...") on timeout.
    
    with patch('amelia.drivers.cli.claude.run_shell_command', new_callable=AsyncMock) as mock_run:
        # Side effect: First call raises RuntimeError (timeout), second call succeeds
        mock_run.side_effect = [
            RuntimeError("Command timed out after 1 seconds."),
            "Success Output"
        ]
        
        driver = ClaudeCliDriver(timeout=1, max_retries=1)
        
        result = await driver.execute_tool("run_shell_command", command="echo test")
        
        assert result == "Success Output"
        assert mock_run.call_count == 2

@pytest.mark.asyncio
async def test_cli_driver_execute_tool_fails_after_max_retries():
    with patch('amelia.drivers.cli.claude.run_shell_command', new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = RuntimeError("Command timed out after 1 seconds.")
        
        driver = ClaudeCliDriver(timeout=1, max_retries=1)
        
        with pytest.raises(RuntimeError, match="timed out"):
            await driver.execute_tool("run_shell_command", command="echo test")
        
        # Should call initial + 1 retry = 2 calls
        assert mock_run.call_count == 2

@pytest.mark.asyncio
async def test_cli_driver_generate_retry():
    # Test generate method retry logic. 
    # ClaudeCliDriver._generate_impl currently doesn't raise Timeout/RuntimeError unless we mock something inside it.
    # Or we can mock _generate_impl itself on the instance.
    
    driver = ClaudeCliDriver(timeout=1, max_retries=1)
    
    # Mock _generate_impl to fail then succeed
    driver._generate_impl = AsyncMock(side_effect=[
        RuntimeError("Command timed out simulation"),
        "Generated Content"
    ])
    
    result = await driver.generate([AgentMessage(role="user", content="hi")])
    
    assert result == "Generated Content"
    assert driver._generate_impl.call_count == 2