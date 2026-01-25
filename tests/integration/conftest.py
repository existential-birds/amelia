"""Shared fixtures and helpers for integration tests.

This module provides:
- Factory functions for creating test data (make_issue, make_profile, etc.)
- Fixtures for common test dependencies
"""

import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from amelia.core.types import AgentConfig, DriverType, Issue, Profile, TrackerType
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.implementation import create_implementation_graph
from amelia.pipelines.implementation.state import ImplementationState, rebuild_implementation_state
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.events.connection_manager import ConnectionManager
from amelia.server.models.events import WorkflowEvent
from amelia.server.models.state import (
    ServerExecutionState,
    rebuild_server_execution_state,
)


# Rebuild ImplementationState first (resolves EvaluationResult),
# then ServerExecutionState (resolves ImplementationState union member)
rebuild_implementation_state()
rebuild_server_execution_state()


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
    driver: DriverType = "api",
    model: str = "anthropic/claude-sonnet-4-20250514",
    tracker: TrackerType = "noop",
    plan_output_dir: str | None = None,
    validator_model: str | None = None,
    agents: dict[str, AgentConfig] | None = None,
    **kwargs: Any,
) -> Profile:
    """Create a Profile with sensible defaults for testing.

    Args:
        name: Profile name.
        driver: Default driver for agents (used if agents dict not provided).
        model: Default model for agents (used if agents dict not provided).
        tracker: Issue tracker type.
        plan_output_dir: Directory for plan files.
        validator_model: Model for validation (used if agents dict not provided).
        agents: Explicit agents dict. If not provided, builds from driver/model/validator_model.
        **kwargs: Additional Profile fields.

    Returns:
        Profile with the specified or default agents configuration.
    """
    if agents is None:
        # Build default agents from driver/model for backward compatibility
        effective_validator_model = validator_model or model
        agents = {
            "architect": AgentConfig(driver=driver, model=model),
            "developer": AgentConfig(driver=driver, model=model),
            "reviewer": AgentConfig(driver=driver, model=model),
            "plan_validator": AgentConfig(driver=driver, model=effective_validator_model),
            "evaluator": AgentConfig(driver=driver, model=model),
            "task_reviewer": AgentConfig(driver=driver, model=effective_validator_model),
        }
    return Profile(
        name=name,
        tracker=tracker,
        plan_output_dir=plan_output_dir or "/tmp/test-plans",
        agents=agents,
        **kwargs,
    )


_NOT_PROVIDED: object = object()  # Sentinel for distinguishing explicit None


def make_execution_state(
    issue: Issue | None | object = _NOT_PROVIDED,
    profile: Profile | None = None,
    goal: str | None = None,
    **kwargs: Any,
) -> ImplementationState:
    """Create an ImplementationState with sensible defaults.

    Args:
        issue: Issue to use. If not provided, creates a default issue.
            Pass None explicitly to create state with no issue.
        profile: Profile to use. If None, creates a default profile.
        goal: Goal string.
        **kwargs: Additional fields to pass to ImplementationState.

    Returns:
        ImplementationState with sensible defaults for testing.
    """
    from datetime import UTC, datetime  # noqa: PLC0415
    from uuid import uuid4  # noqa: PLC0415

    if profile is None:
        profile = make_profile()

    # Provide defaults for required BasePipelineState fields
    workflow_id = kwargs.pop("workflow_id", str(uuid4()))
    created_at = kwargs.pop("created_at", datetime.now(UTC))
    status = kwargs.pop("status", "pending")

    # Use sentinel to distinguish between "not provided" and "explicitly None"
    resolved_issue: Issue | None = (
        make_issue() if issue is _NOT_PROVIDED else issue  # type: ignore[assignment]  # Sentinel pattern: _NOT_PROVIDED type not narrowed
    )

    return ImplementationState(
        workflow_id=workflow_id,
        created_at=created_at,
        status=status,
        issue=resolved_issue,
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


def make_agentic_messages(
    *,
    include_thinking: bool = True,
    include_tool_call: bool = True,
    include_tool_result: bool = True,
    tool_name: str = "write_file",
    final_text: str = "Done!",
) -> list[AgenticMessage]:
    """Create standard agentic message sequence for testing.

    Args:
        include_thinking: Include a THINKING message.
        include_tool_call: Include a TOOL_CALL message.
        include_tool_result: Include a TOOL_RESULT message.
        tool_name: Name of tool for TOOL_CALL/RESULT.
        final_text: Final RESULT message content.

    Returns:
        List of AgenticMessage for test mocking.
    """
    messages: list[AgenticMessage] = []

    if include_thinking:
        messages.append(
            AgenticMessage(
                type=AgenticMessageType.THINKING,
                content="Analyzing the task...",
            )
        )

    if include_tool_call:
        messages.append(
            AgenticMessage(
                type=AgenticMessageType.TOOL_CALL,
                tool_name=tool_name,
                tool_input={"path": "test.py", "content": "# test"},
            )
        )

    if include_tool_result:
        messages.append(
            AgenticMessage(
                type=AgenticMessageType.TOOL_RESULT,
                tool_name=tool_name,
                tool_output="File written successfully",
            )
        )

    messages.append(
        AgenticMessage(
            type=AgenticMessageType.RESULT,
            content=final_text,
        )
    )

    return messages


def make_reviewer_agentic_messages(
    *,
    approved: bool = True,
    comments: list[str] | None = None,
    severity: str = "none",
) -> list[AgenticMessage]:
    """Create mock agentic messages that produce reviewer-parseable output.

    The reviewer now uses agentic_review() which calls execute_agentic() and
    parses the beagle markdown format from the RESULT message.

    Args:
        approved: Whether the review should approve the changes.
        comments: List of review comments. If None, defaults based on approval.
        severity: Severity level for issues ("low", "medium", "high", "critical").

    Returns:
        List of AgenticMessage for mocking execute_agentic.
    """
    if comments is None:
        comments = ["LGTM! Good work."] if approved else ["Issue found in code."]

    # Map severity to beagle format section
    severity_map = {
        "low": "Minor",
        "medium": "Minor",
        "high": "Major",
        "critical": "Critical",
    }
    section = severity_map.get(severity, "Minor")

    # Build issues section if not approved
    issues_section = ""
    if not approved:
        issues_section = f"\n### {section} (Should Fix)\n\n"
        for i, comment in enumerate(comments, 1):
            issues_section += f"{i}. [test.py:10] {comment}\n"
            issues_section += f"   - Issue: {comment}\n"
            issues_section += "   - Why: Quality concern\n"
            issues_section += "   - Fix: Address the issue\n\n"

    # Build verdict
    verdict = "Yes" if approved else "No"
    rationale = "All changes look good." if approved else "Issues need to be addressed."

    review_output = f"""## Review Summary

Review of the code changes.

## Issues
{issues_section if not approved else "No issues found."}

## Good Patterns

- Well-structured code

## Verdict

**Ready:** {verdict}
**Rationale:** {rationale}
"""

    return [
        AgenticMessage(
            type=AgenticMessageType.THINKING,
            content="Analyzing the code changes...",
        ),
        AgenticMessage(
            type=AgenticMessageType.RESULT,
            content=review_output,
            session_id="session-review",
        ),
    ]


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
    """Create a mock EventBus for testing."""
    bus = MagicMock(spec=EventBus)
    bus.emit = MagicMock()
    bus.set_connection_manager = MagicMock()
    return bus


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create in-memory repository mock with full CRUD support."""
    repo = AsyncMock(spec=WorkflowRepository)
    repo.workflows = {}
    repo.events = []
    repo.event_sequence = {}

    async def create(state: ServerExecutionState) -> None:
        repo.workflows[state.id] = state

    async def get(workflow_id: str) -> ServerExecutionState | None:
        return cast(ServerExecutionState | None, repo.workflows.get(workflow_id))

    async def set_status(
        workflow_id: str, status: str, failure_reason: str | None = None
    ) -> None:
        if workflow_id in repo.workflows:
            repo.workflows[workflow_id] = repo.workflows[workflow_id].model_copy(
                update={"workflow_status": status, "failure_reason": failure_reason}
            )

    async def save_event(event: WorkflowEvent) -> None:
        repo.events.append(event)

    async def get_max_event_sequence(workflow_id: str) -> int:
        return cast(int, repo.event_sequence.get(workflow_id, 0))

    repo.create = create
    repo.get = get
    repo.set_status = set_status
    repo.save_event = save_event
    repo.get_max_event_sequence = get_max_event_sequence

    return repo


@pytest.fixture
def mock_profile_repo() -> AsyncMock:
    """Create mock ProfileRepository that returns test profile.

    Note: ProfileRepository methods return Profile objects, not ProfileRecord.
    """
    from amelia.server.database.profile_repository import ProfileRepository  # noqa: PLC0415

    repo = AsyncMock(spec=ProfileRepository)
    # ProfileRepository returns Profile objects, not ProfileRecord
    profile = Profile(
        name="test",
        tracker="noop",
        working_dir="/tmp/test",
        agents={
            "architect": AgentConfig(driver="cli", model="sonnet"),
            "developer": AgentConfig(driver="cli", model="sonnet"),
            "reviewer": AgentConfig(driver="cli", model="sonnet"),
            "plan_validator": AgentConfig(driver="cli", model="haiku"),
        },
    )
    repo.get_profile.return_value = profile
    repo.get_active_profile.return_value = profile
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
    """Create an EventBus with ConnectionManager attached.

    Note: This overrides the root conftest event_bus fixture to provide
    the connection_manager integration required by stream propagation tests.
    """
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
    return create_implementation_graph(
        checkpointer=MemorySaver(),
        interrupt_before=["human_approval_node"],
    )
