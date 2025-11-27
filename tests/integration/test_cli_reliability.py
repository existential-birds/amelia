import asyncio
import time
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from amelia.core.state import AgentMessage
from amelia.drivers.cli.claude import ClaudeCliDriver


@pytest.mark.asyncio
async def test_cli_driver_reliability_loop():
    """
    Soak test to ensure CLI driver handles multiple concurrent requests gracefully
    by queuing them via semaphore, without crashing or deadlocking.
    """
    driver = ClaudeCliDriver(timeout=5, max_retries=2)

    # We can inject a small delay in _generate_impl to verify serialization if we wanted,
    # but standard stub is fast.

    async def make_request(i):
        messages = [AgentMessage(role="user", content=f"msg {i}")]
        try:
            return await driver.generate(messages)
        except Exception as e:
            return e

    # Mock the internal subprocess call for deterministic output
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        def create_mock_process():
            """Create a fresh mock process for each subprocess call."""
            mock_process = MagicMock()
            # stdin: write() and close() are sync, drain() is async
            mock_process.stdin = MagicMock()
            mock_process.stdin.write = MagicMock()
            mock_process.stdin.drain = AsyncMock()
            mock_process.stdin.close = MagicMock()
            # stdout: readline() is async
            mock_process.stdout = MagicMock()
            mock_process.stdout.readline = AsyncMock(side_effect=[b"Mocked CLI Response\n", b""])
            # stderr: read() is async
            mock_process.stderr = MagicMock()
            mock_process.stderr.read = AsyncMock(return_value=b"")
            mock_process.returncode = 0
            mock_process.wait = AsyncMock(return_value=0)
            return mock_process

        mock_exec.side_effect = lambda *args, **kwargs: create_mock_process()

        # Run 5 requests concurrently
        count = 5
        tasks = [make_request(i) for i in range(count)]

        start_time = time.time()
        results = await asyncio.gather(*tasks)
        duration = time.time() - start_time

        assert len(results) == count

        # Verify all succeeded
        failures = [r for r in results if isinstance(r, Exception)]
        assert len(failures) == 0, f"Some requests failed: {failures}"

        for res in results:
            assert "Mocked CLI Response" in str(res) # Assert for our mocked response

        print(f"Processed {count} requests in {duration:.2f}s")
