# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Shared fixtures and helpers for integration tests.

This module provides:
- Factory functions for creating test data (make_step, make_batch, make_blocker, etc.)
- Assertion helpers (assert_workflow_status, assert_step_skipped, assert_step_not_skipped)
"""

import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from amelia.core.orchestrator import create_orchestrator_graph
from amelia.core.state import (
    BlockerReport,
    BlockerType,
    ExecutionBatch,
    ExecutionPlan,
    ExecutionState,
    GitSnapshot,
    PlanStep,
)
from amelia.core.types import (
    DeveloperStatus,
    Issue,
    Profile,
    TrustLevel,
)
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.events.connection_manager import ConnectionManager


# =============================================================================
# Factory Functions (module-level, not fixtures)
# =============================================================================


def make_step(
    id: str = "step-1",
    description: str = "Test step",
    action_type: Literal["code", "command", "validation", "manual"] = "command",
    command: str = "echo test",
    depends_on: tuple[str, ...] = (),
    risk_level: Literal["low", "medium", "high"] = "low",
    **kwargs: Any,
) -> PlanStep:
    """Create a PlanStep with sensible defaults."""
    return PlanStep(
        id=id,
        description=description,
        action_type=action_type,
        command=command,
        depends_on=depends_on,
        risk_level=risk_level,
        **kwargs,
    )


def make_batch(
    batch_number: int = 1,
    steps: tuple[PlanStep, ...] | None = None,
    risk_summary: Literal["low", "medium", "high"] = "low",
    description: str = "Test batch",
) -> ExecutionBatch:
    """Create an ExecutionBatch with sensible defaults."""
    if steps is None:
        steps = (make_step(id=f"step-{batch_number}-1"),)
    return ExecutionBatch(
        batch_number=batch_number,
        steps=steps,
        risk_summary=risk_summary,
        description=description,
    )


def make_plan(
    goal: str = "Test goal",
    batches: tuple[ExecutionBatch, ...] | None = None,
    num_batches: int = 1,
    steps_per_batch: int = 1,
    tdd_approach: bool = False,
) -> ExecutionPlan:
    """Create an ExecutionPlan with sensible defaults.

    Args:
        goal: Plan goal description.
        batches: Pre-created batches (overrides num_batches/steps_per_batch).
        num_batches: Number of batches to create if batches not provided.
        steps_per_batch: Number of steps per batch if batches not provided.
        tdd_approach: Whether TDD is used.

    Returns:
        ExecutionPlan with specified or auto-generated batches.
    """
    if batches is None:
        batches_list = []
        step_counter = 1
        for batch_num in range(1, num_batches + 1):
            steps = []
            for _ in range(steps_per_batch):
                steps.append(
                    make_step(
                        id=f"step-{step_counter}",
                        description=f"Test step {step_counter}",
                        command=f"echo step-{step_counter}",
                    )
                )
                step_counter += 1
            batches_list.append(
                make_batch(
                    batch_number=batch_num,
                    steps=tuple(steps),
                    description=f"Test batch {batch_num}",
                )
            )
        batches = tuple(batches_list)

    return ExecutionPlan(
        goal=goal,
        batches=batches,
        total_estimated_minutes=len(batches) * steps_per_batch * 2,
        tdd_approach=tdd_approach,
    )


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
    tracker: str = "noop",
    strategy: str = "single",
    trust_level: TrustLevel = TrustLevel.STANDARD,
    batch_checkpoint_enabled: bool = True,
    plan_output_dir: str | None = None,
    **kwargs: Any,
) -> Profile:
    """Create a Profile with sensible defaults for testing."""
    return Profile(
        name=name,
        driver=driver,  # type: ignore[arg-type]
        tracker=tracker,  # type: ignore[arg-type]
        strategy=strategy,  # type: ignore[arg-type]
        trust_level=trust_level,
        batch_checkpoint_enabled=batch_checkpoint_enabled,
        plan_output_dir=plan_output_dir or "/tmp/test-plans",
        **kwargs,
    )


def make_execution_state(
    issue: Issue | None = None,
    profile: Profile | None = None,
    execution_plan: ExecutionPlan | None = None,
    current_batch_index: int = 0,
    developer_status: DeveloperStatus = DeveloperStatus.EXECUTING,
    human_approved: bool | None = None,
    **kwargs: Any,
) -> ExecutionState:
    """Create an ExecutionState with sensible defaults."""
    if profile is None:
        profile = make_profile()
    return ExecutionState(
        issue=issue or make_issue(),
        profile_id=profile.name,
        execution_plan=execution_plan,
        current_batch_index=current_batch_index,
        developer_status=developer_status,
        human_approved=human_approved,
        **kwargs,
    )


def make_blocker(
    step_id: str = "step-a",
    step_description: str | None = None,
    blocker_type: BlockerType = "command_failed",
    error_message: str = "Command failed",
    attempted_actions: tuple[str, ...] = (),
    suggested_resolutions: tuple[str, ...] = (),
) -> BlockerReport:
    """Create a BlockerReport with sensible defaults."""
    return BlockerReport(
        step_id=step_id,
        step_description=step_description or f"{step_id} (blocked)",
        blocker_type=blocker_type,
        error_message=error_message,
        attempted_actions=attempted_actions,
        suggested_resolutions=suggested_resolutions,
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
# Assertion Helpers
# =============================================================================


def _get_skipped_set(state: ExecutionState | dict[str, Any]) -> set[str]:
    """Extract skipped_step_ids as a set from state (ExecutionState or dict).

    Args:
        state: ExecutionState or dict with skipped_step_ids key.

    Returns:
        Set of skipped step IDs (empty set if none).
    """
    if isinstance(state, dict):
        skipped = state.get("skipped_step_ids", frozenset())
    else:
        skipped = state.skipped_step_ids or frozenset()

    # Handle both set and frozenset
    return set(skipped) if skipped else set()


def assert_workflow_status(
    state: ExecutionState | dict[str, Any],
    expected_status: str,
    msg: str = "",
) -> None:
    """Assert the workflow has a specific status.

    Args:
        state: ExecutionState or dict with workflow_status key.
        expected_status: Expected workflow_status value.
        msg: Optional message to include on assertion failure.
    """
    actual = state.get("workflow_status") if isinstance(state, dict) else state.workflow_status

    if msg:
        assert actual == expected_status, f"{msg}: expected {expected_status}, got {actual}"
    else:
        assert actual == expected_status, f"Expected workflow_status={expected_status}, got {actual}"


def assert_step_skipped(
    state: ExecutionState | dict[str, Any],
    step_id: str,
    msg: str = "",
) -> None:
    """Assert that a specific step was skipped.

    Args:
        state: ExecutionState or dict with skipped_step_ids key.
        step_id: The step ID that should be in skipped_step_ids.
        msg: Optional message to include on assertion failure.
    """
    skipped_set = _get_skipped_set(state)

    if msg:
        assert step_id in skipped_set, f"{msg}: step {step_id} not in skipped_step_ids={skipped_set}"
    else:
        assert step_id in skipped_set, f"Expected step {step_id} to be skipped, skipped_step_ids={skipped_set}"


def assert_step_not_skipped(
    state: ExecutionState | dict[str, Any],
    step_id: str,
    msg: str = "",
) -> None:
    """Assert that a specific step was NOT skipped.

    Args:
        state: ExecutionState or dict with skipped_step_ids key.
        step_id: The step ID that should NOT be in skipped_step_ids.
        msg: Optional message to include on assertion failure.
    """
    skipped_set = _get_skipped_set(state)

    if msg:
        assert step_id not in skipped_set, f"{msg}: step {step_id} should not be skipped, skipped_step_ids={skipped_set}"
    else:
        assert step_id not in skipped_set, f"Expected step {step_id} NOT to be skipped, skipped_step_ids={skipped_set}"


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
def mock_git_snapshot() -> GitSnapshot:
    """Create a mock GitSnapshot for testing."""
    return GitSnapshot(
        head_commit="abc123def456",
        dirty_files=(),
        stash_ref=None,
    )


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
        interrupt_before=["human_approval_node", "batch_approval_node", "blocker_resolution_node"],
    )


