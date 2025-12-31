"""Shared fixtures and helpers for integration tests.

This module provides:
- Factory functions for creating test data (make_issue, make_profile, etc.)
- Fixtures for common test dependencies
"""

import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from amelia.core.orchestrator import create_orchestrator_graph
from amelia.core.state import ExecutionState
from amelia.core.types import Issue, Profile
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.events.connection_manager import ConnectionManager


# =============================================================================
# Constants
# =============================================================================

# Free model for OpenRouter integration tests (incurs no costs)
# Must support tool use - see https://openrouter.ai/models?q=:free
OPENROUTER_FREE_MODEL = "openrouter:meta-llama/llama-3.3-70b-instruct:free"


# =============================================================================
# Factory Functions (module-level, not fixtures)
# =============================================================================


def make_issue(
    id: str = "TEST-123",
    title: str = "Test Issue",
    description: str = "Test issue description",
    status: str = "open",
) -> Issue:
    """Create an Issue with sensible defaults."""
    return Issue(
        id=id,
        title=title,
        description=description,
        status=status,
    )


def make_profile(
    name: str = "test",
    driver: str = "api:openrouter",
    model: str = "openrouter:anthropic/claude-sonnet-4-20250514",
    tracker: str = "noop",
    strategy: str = "single",
    plan_output_dir: str | None = None,
    **kwargs: Any,
) -> Profile:
    """Create a Profile with sensible defaults for testing."""
    return Profile(
        name=name,
        driver=driver,  # type: ignore[arg-type]
        model=model,
        tracker=tracker,  # type: ignore[arg-type]
        strategy=strategy,  # type: ignore[arg-type]
        plan_output_dir=plan_output_dir or "/tmp/test-plans",
        **kwargs,
    )


def make_execution_state(
    issue: Issue | None = None,
    profile: Profile | None = None,
    goal: str | None = None,
    **kwargs: Any,
) -> ExecutionState:
    """Create an ExecutionState with sensible defaults."""
    if profile is None:
        profile = make_profile()
    return ExecutionState(
        issue=issue or make_issue(),
        profile_id=profile.name,
        goal=goal,
        **kwargs,
    )


def make_config(
    thread_id: str,
    profile: Profile | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Create a RunnableConfig with thread_id and profile.

    Args:
        thread_id: The thread ID for the workflow.
        profile: Optional profile (defaults to test profile if not provided).
        **kwargs: Additional configurable parameters.

    Returns:
        RunnableConfig dict with configurable parameters.
    """
    if profile is None:
        profile = make_profile()

    return {
        "configurable": {
            "thread_id": thread_id,
            "profile": profile,
            **kwargs,
        }
    }


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def find_free_port() -> Callable[[], int]:
    """Fixture that returns a function to find an available port for testing.

    Returns:
        A callable that returns an available port number.
    """
    def _find_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port: int = s.getsockname()[1]
            return port
    return _find_port


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Create a mock EventBus with emit_stream tracking."""
    bus = MagicMock(spec=EventBus)
    bus.emit_stream = MagicMock()
    bus.emit = MagicMock()
    bus.set_connection_manager = MagicMock()
    return bus


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create a mock WorkflowRepository."""
    repo = AsyncMock(spec=WorkflowRepository)
    repo.create = AsyncMock()
    repo.get = AsyncMock()
    repo.update = AsyncMock()
    repo.set_status = AsyncMock()
    repo.save_event = AsyncMock()
    repo.get_max_event_sequence = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def test_profile(tmp_path: Path) -> Profile:
    """Create a test profile with temp plan output directory."""
    return make_profile(plan_output_dir=str(tmp_path / "plans"))


@pytest.fixture
def test_issue() -> Issue:
    """Create a test issue."""
    return make_issue()


@pytest.fixture
def test_settings(test_profile: Profile) -> MagicMock:
    """Create mock settings with test profile."""
    settings = MagicMock()
    settings.active_profile = "test_profile"
    settings.profiles = {"test_profile": test_profile}
    return settings


@pytest.fixture
def connection_manager() -> ConnectionManager:
    """Create a ConnectionManager instance."""
    return ConnectionManager()


@pytest.fixture
def event_bus(connection_manager: ConnectionManager) -> EventBus:
    """Create an EventBus with ConnectionManager attached."""
    bus = EventBus()
    bus.set_connection_manager(connection_manager)
    return bus


@pytest.fixture
def memory_checkpointer() -> MemorySaver:
    """Create an in-memory checkpoint saver for integration tests."""
    return MemorySaver()


@pytest.fixture
def orchestrator_graph() -> CompiledStateGraph[Any]:
    """Create orchestrator graph with in-memory checkpointer.

    The graph is configured with interrupts before approval nodes
    for testing human-in-the-loop flows.
    """
    return create_orchestrator_graph(
        checkpoint_saver=MemorySaver(),
        interrupt_before=["human_approval_node"],
    )
