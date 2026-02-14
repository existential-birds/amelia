"""Unit tests for sandbox container teardown."""
from unittest.mock import AsyncMock, patch


class TestTeardownAllSandboxContainers:
    """Tests for teardown_all_sandbox_containers()."""

    async def test_stops_running_containers(self) -> None:
        """Should find and remove all amelia-sandbox-* containers."""
        from amelia.sandbox.teardown import teardown_all_sandbox_containers

        # Mock docker ps returning two container IDs
        mock_ps = AsyncMock()
        mock_ps.communicate = AsyncMock(return_value=(b"abc123\ndef456\n", b""))
        mock_ps.returncode = 0

        mock_rm = AsyncMock()
        mock_rm.communicate = AsyncMock(return_value=(b"", b""))
        mock_rm.returncode = 0

        call_count = 0

        async def mock_create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_ps
            return mock_rm

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess):
            await teardown_all_sandbox_containers()

        # Should have called docker ps once, then docker rm once
        assert call_count == 2

    async def test_no_containers_is_noop(self) -> None:
        """Should do nothing when no containers are running."""
        from amelia.sandbox.teardown import teardown_all_sandbox_containers

        mock_ps = AsyncMock()
        mock_ps.communicate = AsyncMock(return_value=(b"", b""))
        mock_ps.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_ps):
            await teardown_all_sandbox_containers()

        # Only docker ps was called, no docker rm
        mock_ps.communicate.assert_called_once()

    async def test_handles_docker_not_available(self) -> None:
        """Should handle gracefully when docker is not available."""
        from amelia.sandbox.teardown import teardown_all_sandbox_containers

        mock_ps = AsyncMock()
        mock_ps.communicate = AsyncMock(return_value=(b"", b"Cannot connect"))
        mock_ps.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_ps):
            # Should not raise
            await teardown_all_sandbox_containers()
