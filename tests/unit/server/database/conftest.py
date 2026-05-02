"""Shared fixtures for database tests."""

import os
import uuid
from collections.abc import AsyncGenerator, Coroutine
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

import pytest

from amelia.server.database.connection import Database
from amelia.server.database.repository import WorkflowRepository
from amelia.server.models.state import ServerExecutionState, WorkflowStatus
from amelia.server.models.tokens import TokenUsage


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://amelia:amelia@localhost:5434/amelia_test",
)


class WorkflowFactory(Protocol):
    """Factory that creates and persists a ServerExecutionState row."""

    def __call__(
        self,
        *,
        issue_id: str,
        worktree_path: str,
        started_at: datetime,
        workflow_id: uuid.UUID | None = ...,
        workflow_status: WorkflowStatus | str = ...,
        completed_at: datetime | None = ...,
        failure_reason: str | None = ...,
    ) -> Coroutine[None, None, ServerExecutionState]:
        ...


class TokenUsageFactory(Protocol):
    """Factory that creates and persists a TokenUsage row."""

    def __call__(
        self,
        *,
        workflow_id: uuid.UUID,
        timestamp: datetime,
        cost_usd: float,
        input_tokens: int,
        output_tokens: int,
        agent: str = ...,
        model: str = ...,
        cache_read_tokens: int = ...,
        duration_ms: int = ...,
        num_turns: int = ...,
    ) -> Coroutine[None, None, TokenUsage]:
        ...


@pytest.fixture
async def connected_db() -> AsyncGenerator[Database, None]:
    """Create a connected Database instance for testing.

    Yields:
        Database: Connected database instance.
    """
    async with Database(DATABASE_URL) as db:
        yield db


@pytest.fixture
async def db_with_schema() -> AsyncGenerator[Database, None]:
    """Create a database with schema initialized.

    Connects to database and runs migrations to create all tables.
    Truncates all data tables before each test for isolation.

    Yields:
        Database: Connected database instance with schema initialized.
    """
    async with Database(DATABASE_URL) as db:
        from amelia.server.database.migrator import Migrator

        migrator = Migrator(db)
        await migrator.run()
        # Truncate all data tables to ensure test isolation
        await db.execute("""
            TRUNCATE TABLE
                workflow_prompt_versions, prompt_versions, prompts,
                brainstorm_artifacts, brainstorm_messages, brainstorm_sessions,
                token_usage, workflow_log, workflows,
                profiles, server_settings, model_cache
            CASCADE
        """)
        yield db


@pytest.fixture
async def repository(db_with_schema: Database) -> WorkflowRepository:
    """Create WorkflowRepository with initialized schema.

    Args:
        db_with_schema: Database with schema initialized.

    Returns:
        WorkflowRepository: Repository instance.
    """
    return WorkflowRepository(db_with_schema)


@pytest.fixture
async def workflow(repository: WorkflowRepository) -> ServerExecutionState:
    """Create and save a test workflow.

    Args:
        repository: WorkflowRepository instance.

    Returns:
        ServerExecutionState: Created workflow.
    """
    wf = ServerExecutionState(
        id=uuid4(),
        issue_id="ISSUE-1",
        worktree_path="/tmp/test",
        workflow_status="pending",
        started_at=datetime.now(UTC),
    )
    await repository.create(wf)
    return wf


@pytest.fixture
def make_workflow(repository: WorkflowRepository) -> WorkflowFactory:
    """Factory fixture that builds and persists a ServerExecutionState.

    Use this to seed workflow rows with only the fields a test cares about;
    everything else gets sensible defaults. Returns the persisted model so
    callers can grab `.id` for foreign-key references.
    """

    async def _make(
        *,
        issue_id: str,
        worktree_path: str,
        started_at: datetime,
        workflow_id: uuid.UUID | None = None,
        workflow_status: WorkflowStatus | str = WorkflowStatus.COMPLETED,
        completed_at: datetime | None = None,
        failure_reason: str | None = None,
    ) -> ServerExecutionState:
        wf = ServerExecutionState(
            id=workflow_id if workflow_id is not None else uuid4(),
            issue_id=issue_id,
            worktree_path=worktree_path,
            workflow_status=workflow_status,
            started_at=started_at,
            completed_at=completed_at,
            failure_reason=failure_reason,
        )
        await repository.create(wf)
        return wf

    return _make


@pytest.fixture
def make_token_usage(repository: WorkflowRepository) -> TokenUsageFactory:
    """Factory fixture that builds and persists a TokenUsage record.

    Mirrors the inline construction the usage repository tests repeat. Only
    truly-required fields (workflow_id, timestamp, cost_usd, token counts)
    have no default; everything else mirrors a typical architect call.
    """

    async def _make(
        *,
        workflow_id: uuid.UUID,
        timestamp: datetime,
        cost_usd: float,
        input_tokens: int,
        output_tokens: int,
        agent: str = "architect",
        model: str = "claude-sonnet-4-20250514",
        cache_read_tokens: int = 0,
        duration_ms: int = 5000,
        num_turns: int = 3,
    ) -> TokenUsage:
        usage = TokenUsage(
            workflow_id=workflow_id,
            agent=agent,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            num_turns=num_turns,
            timestamp=timestamp,
        )
        await repository.save_token_usage(usage)
        return usage

    return _make
