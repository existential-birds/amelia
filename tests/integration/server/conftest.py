"""Shared fixtures for server integration tests.

Provides common test utilities for FastAPI async client testing,
reducing duplication across test_brainstorm_*.py files.
"""

import re
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from amelia.drivers.base import AgenticMessage, AgenticMessageType, DriverInterface
from amelia.server.database.brainstorm_repository import BrainstormRepository
from amelia.server.database.connection import Database
from amelia.server.dependencies import get_orchestrator, get_profile_repository
from amelia.server.events.bus import EventBus
from amelia.server.main import create_app
from amelia.server.routes.brainstorm import (
    get_brainstorm_service,
    get_cwd,
    get_driver,
)
from amelia.server.services.brainstorm import BrainstormService
from tests.conftest import create_mock_execute_agentic


# Type alias for the async client factory
AsyncClientFactory = Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]]


@asynccontextmanager
async def noop_lifespan(_app: Any) -> AsyncGenerator[None, None]:
    """No-op lifespan that skips database/orchestrator initialization.

    Use this when testing routes with dependency overrides that don't
    require the full application lifespan.
    """
    yield


@pytest.fixture
def async_client_factory() -> AsyncClientFactory:
    """Factory for creating httpx.AsyncClient with ASGITransport.

    Use this fixture when you need an async test client that runs in the
    same event loop as the asyncpg pool (unlike TestClient which creates
    a separate thread with its own event loop).

    Example:
        @pytest.fixture
        async def test_client(
            async_client_factory,
            test_brainstorm_service: BrainstormService,
        ) -> AsyncGenerator[httpx.AsyncClient, None]:
            app = create_app()
            app.router.lifespan_context = noop_lifespan
            app.dependency_overrides[get_brainstorm_service] = lambda: test_brainstorm_service
            async with async_client_factory(app) as client:
                yield client
    """

    @asynccontextmanager
    async def _create_client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client

    return _create_client


@pytest.fixture
def test_brainstorm_repository(test_db: Database) -> BrainstormRepository:
    """Create repository backed by test database."""
    return BrainstormRepository(test_db)


@pytest.fixture
def test_brainstorm_service(
    test_brainstorm_repository: BrainstormRepository,
    test_event_bus: EventBus,
) -> BrainstormService:
    """Create real BrainstormService with test dependencies."""
    return BrainstormService(test_brainstorm_repository, test_event_bus)


def _create_app_with_overrides(
    brainstorm_service: BrainstormService,
    driver_dep: Any,
    cwd: str,
) -> FastAPI:
    """Create FastAPI app with noop lifespan and dependency overrides."""
    app = create_app()

    app.router.lifespan_context = noop_lifespan
    app.dependency_overrides[get_brainstorm_service] = lambda: brainstorm_service
    app.dependency_overrides[get_driver] = driver_dep
    app.dependency_overrides[get_cwd] = lambda: cwd

    # Override dependencies that would otherwise require the database lifespan
    mock_profile_repo = AsyncMock()
    mock_profile_repo.get_profile = AsyncMock(return_value=None)
    app.dependency_overrides[get_profile_repository] = lambda: mock_profile_repo

    mock_orch = MagicMock()
    mock_orch.queue_workflow = AsyncMock(
        return_value="00000000-0000-4000-8000-000000000001"
    )
    app.dependency_overrides[get_orchestrator] = lambda: mock_orch

    return app


# =============================================================================
# Shared brainstorm test helpers
# =============================================================================


def create_realistic_driver_messages(
    *,
    thinking_content: str = "Let me analyze this request...",
    tool_name: str = "read_file",
    tool_input: dict[str, Any] | None = None,
    tool_output: str = "File contents here",
    result_content: str = "Based on my analysis, here's the answer.",
    session_id: str = "driver-session-123",
) -> list[AgenticMessage]:
    """Create a realistic sequence of driver messages.

    Returns:
        List of AgenticMessage objects simulating THINKING -> TOOL_CALL -> TOOL_RESULT -> RESULT.
    """
    if tool_input is None:
        tool_input = {"path": "README.md"}

    return [
        AgenticMessage(
            type=AgenticMessageType.THINKING,
            content=thinking_content,
        ),
        AgenticMessage(
            type=AgenticMessageType.TOOL_CALL,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_call_id="call-1",
        ),
        AgenticMessage(
            type=AgenticMessageType.TOOL_RESULT,
            tool_name=tool_name,
            tool_output=tool_output,
            tool_call_id="call-1",
            is_error=False,
        ),
        AgenticMessage(
            type=AgenticMessageType.RESULT,
            content=result_content,
            session_id=session_id,
        ),
    ]


def _create_mock_execute_agentic_with_plan_file(
    messages: list[AgenticMessage],
) -> Any:
    """Create a mock execute_agentic that also creates the plan file on disk.

    The service detects artifacts by checking if the plan file exists after
    driver execution. This wrapper creates that file based on the cwd kwarg
    passed by the service, so the filesystem check succeeds.
    """

    async def mock_execute_agentic(
        *args: Any, **kwargs: Any
    ) -> AsyncGenerator[AgenticMessage, None]:
        cwd = kwargs.get("cwd", "")
        if cwd:
            instructions = kwargs.get("instructions", "")
            match = re.search(r"Write the validated design to `([^`]+)`", instructions)
            if match:
                plan_path = match.group(1)
                abs_path = Path(cwd) / plan_path
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text("# Design\n\nOverview...")

        for msg in messages:
            yield msg

    return mock_execute_agentic


@pytest.fixture
def mock_driver() -> MagicMock:
    """Create a mock driver with realistic message flow."""
    driver = MagicMock(spec=DriverInterface)
    messages = create_realistic_driver_messages()
    driver.execute_agentic = create_mock_execute_agentic(messages)
    return driver


@pytest.fixture
def mock_driver_with_write_file() -> MagicMock:
    """Create a mock driver that creates the plan file on disk.

    The service detects artifacts by checking if the plan file exists
    after driver execution, so the mock must actually create the file.
    """
    driver = MagicMock(spec=DriverInterface)
    messages = [
        AgenticMessage(
            type=AgenticMessageType.THINKING,
            content="I'll create a design document...",
        ),
        AgenticMessage(
            type=AgenticMessageType.RESULT,
            content="I've created the design document.",
            session_id="driver-session-artifact",
        ),
    ]
    driver.execute_agentic = _create_mock_execute_agentic_with_plan_file(messages)
    return driver
