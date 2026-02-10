"""Shared fixtures and helpers for integration tests.

This module provides:
- Factory functions for creating test data (make_issue, make_profile, etc.)
- Fixtures for common test dependencies
"""

import os
import socket
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from amelia.core.types import AgentConfig, DriverType, Issue, Profile, TrackerType
from amelia.drivers.base import AgenticMessage, AgenticMessageType
from amelia.pipelines.implementation import create_implementation_graph
from amelia.pipelines.implementation.state import ImplementationState, rebuild_implementation_state
from amelia.server.database.connection import Database
from amelia.server.database.profile_repository import ProfileRepository
from amelia.server.database.repository import WorkflowRepository
from amelia.server.events.bus import EventBus
from amelia.server.events.connection_manager import ConnectionManager
from amelia.server.models.events import WorkflowEvent
from amelia.server.models.state import ServerExecutionState
from amelia.server.orchestrator.service import OrchestratorService
from tests.conftest import AsyncIteratorMock


# Rebuild ImplementationState to resolve forward references (e.g., EvaluationResult)
rebuild_implementation_state()


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
        "major": "Major",
        "minor": "Minor",
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


# ---------------------------------------------------------------------------
# Shared LangGraph planning mocks
# ---------------------------------------------------------------------------


def create_planning_graph_mock(
    goal: str = "Test goal from architect",
    plan_markdown: str = "## Plan\n\n### Task 1: First task\n- Do something",
    extra_stream_items: list[tuple[str, dict[str, Any]]] | None = None,
) -> MagicMock:
    """Create a mock LangGraph graph that simulates planning with interrupt.

    The mock graph yields architect output chunks, optional extra items
    (e.g. plan_validator_node), and a final interrupt chunk.

    Args:
        goal: The goal value to include in checkpoint and stream output.
        plan_markdown: The plan markdown for checkpoint and stream output.
        extra_stream_items: Additional (mode, data) tuples to yield between
            the architect output and the interrupt chunk.
    """
    mock_graph = MagicMock()

    # Mock aget_state to return checkpoint with plan data
    checkpoint_values = {
        "goal": goal,
        "plan_markdown": plan_markdown,
        "profile_id": "test",
    }
    mock_checkpoint = MagicMock()
    mock_checkpoint.values = checkpoint_values
    mock_checkpoint.next = []
    mock_graph.aget_state = AsyncMock(return_value=mock_checkpoint)

    # Mock astream to yield chunks including interrupt
    astream_items: list[tuple[str, dict[str, Any]]] = [
        ("updates", {"architect_node": {"goal": goal, "plan_markdown": plan_markdown}}),
    ]
    if extra_stream_items:
        astream_items.extend(extra_stream_items)
    astream_items.append(("updates", {"__interrupt__": ("Paused for approval",)}))

    mock_graph.astream = lambda *args, **kwargs: AsyncIteratorMock(astream_items)

    # Mock aupdate_state for approve_workflow
    mock_graph.aupdate_state = AsyncMock()

    return mock_graph


@asynccontextmanager
async def mock_langgraph_for_planning(
    goal: str = "Test goal from architect",
    plan_markdown: str = "## Plan\n\n### Task 1: First task\n- Do something",
    extra_stream_items: list[tuple[str, dict[str, Any]]] | None = None,
) -> AsyncGenerator[MagicMock, None]:
    """Context manager that mocks LangGraph for planning tests.

    Patches _create_server_graph so that the OrchestratorService runs
    against a mock graph instead of a real LangGraph instance.

    Args:
        goal: Forwarded to create_planning_graph_mock.
        plan_markdown: Forwarded to create_planning_graph_mock.
        extra_stream_items: Forwarded to create_planning_graph_mock.
    """
    mock_graph = create_planning_graph_mock(
        goal=goal,
        plan_markdown=plan_markdown,
        extra_stream_items=extra_stream_items,
    )

    with patch.object(
        OrchestratorService, "_create_server_graph", return_value=mock_graph
    ):
        yield mock_graph


# ---------------------------------------------------------------------------
# Shared database & service fixtures for orchestrator integration tests
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://amelia:amelia@localhost:5432/amelia_test",
)


@pytest.fixture
async def test_db() -> AsyncGenerator[Database, None]:
    """Create and initialize test database with PostgreSQL."""
    from amelia.server.database.migrator import Migrator  # noqa: PLC0415

    async with Database(DATABASE_URL) as db:
        migrator = Migrator(db)
        await migrator.run()
        # Truncate all data tables to ensure test isolation
        await db.execute("""
            TRUNCATE TABLE
                workflow_prompt_versions, prompt_versions, prompts,
                brainstorm_artifacts, brainstorm_messages, brainstorm_sessions,
                token_usage, workflow_log, workflows,
                profiles, server_settings
            CASCADE
        """)
        yield db


@pytest.fixture
def test_repository(test_db: Database) -> WorkflowRepository:
    """Create repository backed by test database."""
    return WorkflowRepository(test_db)


@pytest.fixture
def test_profile_repository(test_db: Database) -> ProfileRepository:
    """Create profile repository backed by test database."""
    return ProfileRepository(test_db)


@pytest.fixture
def test_event_bus() -> EventBus:
    """Create event bus for testing."""
    return EventBus()


@pytest.fixture
def test_orchestrator(
    test_event_bus: EventBus,
    test_repository: WorkflowRepository,
    test_profile_repository: ProfileRepository,
) -> OrchestratorService:
    """Create real OrchestratorService with test dependencies.

    Includes profile_repo so that replan and other profile-dependent
    operations work correctly.
    """
    return OrchestratorService(
        event_bus=test_event_bus,
        repository=test_repository,
        profile_repo=test_profile_repository,
        checkpointer=AsyncMock(),
    )


@pytest.fixture
def valid_worktree(tmp_path: Path) -> str:
    """Create a valid git worktree directory with required settings file."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    # Create fake .git directory - production code only checks .git exists
    (worktree / ".git").mkdir()

    # Worktree settings are required (no fallback to server settings)
    settings_content = """
active_profile: test
profiles:
  test:
    name: test
    driver: cli
    model: sonnet
    validator_model: sonnet
    tracker: noop
    strategy: single
"""
    (worktree / "settings.amelia.yaml").write_text(settings_content)
    return str(worktree)


@pytest.fixture
async def active_test_profile(
    test_profile_repository: ProfileRepository,
    valid_worktree: str,
) -> Profile:
    """Create and activate a test profile in the database."""
    agent_config = AgentConfig(driver="cli", model="sonnet")
    profile = Profile(
        name="test",
        tracker="noop",
        working_dir=valid_worktree,
        agents={
            "architect": agent_config,
            "developer": agent_config,
            "reviewer": agent_config,
            "plan_validator": agent_config,
            "evaluator": agent_config,
            "task_reviewer": agent_config,
        },
    )
    await test_profile_repository.create_profile(profile)
    await test_profile_repository.set_active("test")
    return profile
