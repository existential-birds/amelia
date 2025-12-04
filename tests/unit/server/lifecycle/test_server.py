"""Unit tests for ServerLifecycle."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from amelia.server.lifecycle.retention import CleanupResult
from amelia.server.lifecycle.server import ServerLifecycle


@pytest.fixture
def mock_orchestrator() -> AsyncMock:
    """Create mock orchestrator."""
    orch = AsyncMock()
    orch.recover_interrupted_workflows = AsyncMock()
    orch.get_active_workflows = MagicMock(return_value=[])
    orch._active_tasks = {}
    return orch


@pytest.fixture
def mock_retention() -> AsyncMock:
    """Create mock retention service."""
    retention = AsyncMock()
    retention.cleanup_on_shutdown = AsyncMock(
        return_value=CleanupResult(events_deleted=10, workflows_deleted=2)
    )
    return retention


@pytest.fixture
def lifecycle(
    mock_orchestrator: AsyncMock,
    mock_retention: AsyncMock,
) -> ServerLifecycle:
    """Create server lifecycle."""
    return ServerLifecycle(
        orchestrator=mock_orchestrator,
        log_retention=mock_retention,
    )


def test_lifecycle_initialization(lifecycle: ServerLifecycle) -> None:
    """ServerLifecycle should initialize with not shutting down."""
    assert lifecycle.is_shutting_down is False


async def test_startup(
    lifecycle: ServerLifecycle, mock_orchestrator: AsyncMock
) -> None:
    """Startup should call recover_interrupted_workflows."""
    await lifecycle.startup()

    mock_orchestrator.recover_interrupted_workflows.assert_called_once()


async def test_shutdown_no_active_workflows(
    lifecycle: ServerLifecycle,
    mock_orchestrator: AsyncMock,
    mock_retention: AsyncMock,
) -> None:
    """Shutdown with no active workflows should cleanup immediately."""
    mock_orchestrator.get_active_workflows.return_value = []

    await lifecycle.shutdown()

    assert lifecycle.is_shutting_down is True
    mock_retention.cleanup_on_shutdown.assert_called_once()


async def test_shutdown_waits_for_workflows(
    lifecycle: ServerLifecycle,
    mock_orchestrator: AsyncMock,
) -> None:
    """Shutdown should wait for active workflows to complete."""
    # Simulate workflow that completes after 0.1s
    active_paths = ["/path/to/worktree"]
    call_count = 0

    def get_active() -> list[str]:
        nonlocal call_count
        call_count += 1
        if call_count > 2:
            return []
        return active_paths

    mock_orchestrator.get_active_workflows = get_active

    await lifecycle.shutdown()

    assert lifecycle.is_shutting_down is True
    assert call_count > 1  # Should have checked multiple times


async def test_shutdown_timeout_cancels_workflows(
    lifecycle: ServerLifecycle,
    mock_orchestrator: AsyncMock,
) -> None:
    """Shutdown timeout should cancel remaining workflows."""
    # Track if cancel was called
    cancel_called = False

    # Create a real task that blocks until cancelled
    async def blocking_task() -> None:
        try:
            await asyncio.sleep(100)  # Would take forever
        except asyncio.CancelledError:
            nonlocal cancel_called
            cancel_called = True
            raise

    task = asyncio.create_task(blocking_task())

    mock_orchestrator.get_active_workflows.return_value = ["/path/to/worktree"]
    mock_orchestrator._active_tasks = {"/path/to/worktree": task}

    # Use short timeout for test
    lifecycle._shutdown_timeout = 0.1

    await lifecycle.shutdown()

    # Should have cancelled the task
    assert cancel_called is True
    assert task.cancelled()


def test_is_shutting_down_property(lifecycle: ServerLifecycle) -> None:
    """is_shutting_down should reflect internal state."""
    assert lifecycle.is_shutting_down is False

    lifecycle._shutting_down = True
    assert lifecycle.is_shutting_down is True
