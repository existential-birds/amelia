"""Unit tests for LogRetentionService."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
from pydantic import BaseModel

from amelia.server.lifecycle.retention import LogRetentionService


class MockConfig(BaseModel):
    """Mock server config."""

    log_retention_days: int = 30
    log_retention_max_events: int = 100_000
    checkpoint_retention_days: int = 0  # Default: immediate cleanup
    trace_retention_days: int = 7  # Default: 7 days for trace events


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create mock database."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=0)
    db.fetch_all = AsyncMock(return_value=[])
    return db


@pytest.fixture
def config() -> MockConfig:
    """Create config."""
    return MockConfig()


@pytest.fixture
def retention_service(mock_db: AsyncMock, config: MockConfig) -> LogRetentionService:
    """Create retention service without checkpoint path."""
    return LogRetentionService(db=mock_db, config=config)


async def test_cleanup_on_shutdown(
    retention_service: LogRetentionService,
    mock_db: AsyncMock,
) -> None:
    """Should delete old events and workflows."""
    # events deleted, workflows deleted, trace events deleted
    mock_db.execute.side_effect = [50, 5, 10]

    result = await retention_service.cleanup_on_shutdown()

    assert result.events_deleted == 50
    assert result.workflows_deleted == 5
    assert result.checkpoints_deleted == 0  # No checkpoint path configured
    assert result.trace_events_deleted == 10
    assert mock_db.execute.call_count == 3


async def test_cleanup_checkpoints_no_path_configured(
    mock_db: AsyncMock,
    config: MockConfig,
) -> None:
    """Should skip checkpoint cleanup when no path configured."""
    service = LogRetentionService(db=mock_db, config=config, checkpoint_path=None)
    # events deleted, workflows deleted, trace events deleted
    mock_db.execute.side_effect = [10, 2, 3]

    result = await service.cleanup_on_shutdown()

    assert result.checkpoints_deleted == 0


async def test_cleanup_checkpoints_path_does_not_exist(
    mock_db: AsyncMock,
    config: MockConfig,
    tmp_path: Path,
) -> None:
    """Should skip checkpoint cleanup when database file doesn't exist."""
    nonexistent = tmp_path / "nonexistent.db"
    service = LogRetentionService(
        db=mock_db, config=config, checkpoint_path=str(nonexistent)
    )
    # events deleted, workflows deleted, trace events deleted
    mock_db.execute.side_effect = [10, 2, 3]

    result = await service.cleanup_on_shutdown()

    assert result.checkpoints_deleted == 0


async def test_cleanup_checkpoints_no_finished_workflows(
    mock_db: AsyncMock,
    config: MockConfig,
    tmp_path: Path,
) -> None:
    """Should return 0 when no finished workflows exist."""
    # Create a checkpoint database
    checkpoint_db = tmp_path / "checkpoints.db"
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        await conn.execute("""
            CREATE TABLE checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            )
        """)
        await conn.commit()

    service = LogRetentionService(
        db=mock_db, config=config, checkpoint_path=str(checkpoint_db)
    )
    # events deleted, workflows deleted, trace events deleted
    mock_db.execute.side_effect = [0, 0, 0]
    mock_db.fetch_all.return_value = []  # No finished workflows

    result = await service.cleanup_on_shutdown()

    assert result.checkpoints_deleted == 0


async def test_cleanup_checkpoints_deletes_finished_workflows(
    mock_db: AsyncMock,
    config: MockConfig,
    tmp_path: Path,
) -> None:
    """Should delete checkpoints for finished workflows."""
    # Create a checkpoint database with test data
    checkpoint_db = tmp_path / "checkpoints.db"
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        await conn.execute("""
            CREATE TABLE checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            )
        """)
        # Insert checkpoints for completed and in-progress workflows
        await conn.execute(
            "INSERT INTO checkpoints VALUES (?, '', 'cp1', NULL, NULL, NULL, NULL)",
            ("completed-workflow-1",),
        )
        await conn.execute(
            "INSERT INTO checkpoints VALUES (?, '', 'cp2', NULL, NULL, NULL, NULL)",
            ("completed-workflow-2",),
        )
        await conn.execute(
            "INSERT INTO checkpoints VALUES (?, '', 'cp3', NULL, NULL, NULL, NULL)",
            ("active-workflow",),  # Should NOT be deleted
        )
        # Insert writes
        await conn.execute(
            "INSERT INTO writes VALUES (?, '', 'cp1', 'task1', 0, 'ch1', NULL, NULL)",
            ("completed-workflow-1",),
        )
        await conn.commit()

    service = LogRetentionService(
        db=mock_db, config=config, checkpoint_path=str(checkpoint_db)
    )
    # events deleted, workflows deleted, trace events deleted
    mock_db.execute.side_effect = [0, 0, 0]
    mock_db.fetch_all.return_value = [
        {"id": "completed-workflow-1"},
        {"id": "completed-workflow-2"},
    ]

    result = await service.cleanup_on_shutdown()

    # 2 checkpoints + 1 write deleted = 3 total
    assert result.checkpoints_deleted == 3

    # Verify active workflow checkpoint remains
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        cursor = await conn.execute("SELECT thread_id FROM checkpoints")
        rows = list(await cursor.fetchall())
        assert len(rows) == 1
        assert rows[0][0] == "active-workflow"


async def test_cleanup_checkpoints_disabled_with_negative_retention(
    mock_db: AsyncMock,
    tmp_path: Path,
) -> None:
    """Should skip checkpoint cleanup when retention_days is -1."""
    # Create a checkpoint database with test data
    checkpoint_db = tmp_path / "checkpoints.db"
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        await conn.execute("""
            CREATE TABLE checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            )
        """)
        await conn.execute(
            "INSERT INTO checkpoints VALUES (?, '', 'cp1', NULL, NULL, NULL, NULL)",
            ("completed-workflow",),
        )
        await conn.commit()

    # Config with -1 disables cleanup
    config = MockConfig(checkpoint_retention_days=-1)
    service = LogRetentionService(
        db=mock_db, config=config, checkpoint_path=str(checkpoint_db)
    )
    # events deleted, workflows deleted, trace events deleted
    mock_db.execute.side_effect = [0, 0, 0]

    result = await service.cleanup_on_shutdown()

    # No checkpoints deleted because cleanup is disabled
    assert result.checkpoints_deleted == 0

    # Verify checkpoint still exists
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM checkpoints")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 1


async def test_cleanup_checkpoints_respects_retention_days(
    mock_db: AsyncMock,
    tmp_path: Path,
) -> None:
    """Should only delete checkpoints for workflows older than retention_days."""
    # Create a checkpoint database with test data
    checkpoint_db = tmp_path / "checkpoints.db"
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        await conn.execute("""
            CREATE TABLE checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            )
        """)
        # Old workflow checkpoint (should be deleted)
        await conn.execute(
            "INSERT INTO checkpoints VALUES (?, '', 'cp1', NULL, NULL, NULL, NULL)",
            ("old-workflow",),
        )
        # Recent workflow checkpoint (should remain)
        await conn.execute(
            "INSERT INTO checkpoints VALUES (?, '', 'cp2', NULL, NULL, NULL, NULL)",
            ("recent-workflow",),
        )
        await conn.commit()

    # Config with 7 day retention
    config = MockConfig(checkpoint_retention_days=7)
    service = LogRetentionService(
        db=mock_db, config=config, checkpoint_path=str(checkpoint_db)
    )
    # events deleted, workflows deleted, trace events deleted
    mock_db.execute.side_effect = [0, 0, 0]

    # Mock fetch_all to return only old workflow (completed > 7 days ago)
    # The query includes a date filter, so only old workflows are returned
    mock_db.fetch_all.return_value = [{"id": "old-workflow"}]

    result = await service.cleanup_on_shutdown()

    # Only the old workflow's checkpoint deleted
    assert result.checkpoints_deleted == 1

    # Verify recent workflow checkpoint remains
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        cursor = await conn.execute("SELECT thread_id FROM checkpoints")
        rows = list(await cursor.fetchall())
        assert len(rows) == 1
        assert rows[0][0] == "recent-workflow"


async def test_cleanup_checkpoints_retention_query_includes_date(
    mock_db: AsyncMock,
    tmp_path: Path,
) -> None:
    """Should include date filter in query when retention_days > 0."""
    checkpoint_db = tmp_path / "checkpoints.db"
    async with aiosqlite.connect(str(checkpoint_db)) as conn:
        await conn.execute("""
            CREATE TABLE checkpoints (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                parent_checkpoint_id TEXT,
                type TEXT,
                checkpoint BLOB,
                metadata BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE writes (
                thread_id TEXT NOT NULL,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                checkpoint_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                type TEXT,
                value BLOB,
                PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
            )
        """)
        await conn.commit()

    config = MockConfig(checkpoint_retention_days=7)
    service = LogRetentionService(
        db=mock_db, config=config, checkpoint_path=str(checkpoint_db)
    )
    # events deleted, workflows deleted, trace events deleted
    mock_db.execute.side_effect = [0, 0, 0]
    mock_db.fetch_all.return_value = []

    await service.cleanup_on_shutdown()

    # Verify fetch_all was called with a date parameter
    fetch_call = mock_db.fetch_all.call_args
    assert fetch_call is not None
    query, params = fetch_call.args
    assert "completed_at < ?" in query
    assert len(params) == 1
    # Verify the date is approximately 7 days ago
    cutoff = datetime.fromisoformat(params[0])
    expected_cutoff = datetime.now(UTC) - timedelta(days=7)
    # Allow 1 minute tolerance for test execution time
    assert abs((cutoff - expected_cutoff).total_seconds()) < 60


class TestTraceRetention:
    """Tests for trace event retention."""

    @pytest.fixture
    async def db_with_schema(self, tmp_path: Path) -> aiosqlite.Connection:
        """Create a database with schema for trace retention tests."""
        db_path = tmp_path / "retention_test.db"
        async with aiosqlite.connect(str(db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            # Create workflows table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    issue_id TEXT NOT NULL,
                    worktree_path TEXT,
                    workflow_status TEXT NOT NULL DEFAULT 'pending',
                    status TEXT NOT NULL DEFAULT 'pending',
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    profile_id TEXT,
                    branch_name TEXT
                )
            """)
            # Create events table with level column
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    agent TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'debug',
                    message TEXT NOT NULL,
                    data_json TEXT,
                    correlation_id TEXT,
                    tool_name TEXT,
                    tool_input_json TEXT,
                    is_error INTEGER NOT NULL DEFAULT 0,
                    trace_id TEXT,
                    parent_id TEXT
                )
            """)
            await conn.commit()
            yield conn

    @pytest.fixture
    async def sample_workflow(self, db_with_schema: aiosqlite.Connection) -> MagicMock:
        """Create a sample completed workflow for testing."""
        workflow_id = "wf-trace-test"
        old_completed_at = (datetime.now(UTC) - timedelta(days=15)).isoformat()
        await db_with_schema.execute(
            """
            INSERT INTO workflows (id, issue_id, workflow_status, status, started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workflow_id, "ISSUE-1", "completed", "completed",
             datetime.now(UTC).isoformat(), old_completed_at),
        )
        await db_with_schema.commit()
        workflow = MagicMock()
        workflow.id = workflow_id
        return workflow

    @pytest.fixture
    def db(self, db_with_schema: aiosqlite.Connection) -> Any:
        """Create a database adapter that matches DatabaseProtocol."""
        class DatabaseAdapter:
            """Adapter to match DatabaseProtocol interface."""

            def __init__(self, conn: aiosqlite.Connection) -> None:
                self._conn = conn

            async def execute(self, query: str, params: tuple = ()) -> int:
                """Execute a query and return affected row count."""
                cursor = await self._conn.execute(query, params)
                await self._conn.commit()
                return cursor.rowcount

            async def fetch_all(
                self, query: str, params: tuple = ()
            ) -> list[aiosqlite.Row]:
                """Execute a query and return all rows."""
                cursor = await self._conn.execute(query, params)
                return list(await cursor.fetchall())

            async def fetch_one(
                self, query: str, params: tuple = ()
            ) -> aiosqlite.Row | None:
                """Execute a query and return one row."""
                cursor = await self._conn.execute(query, params)
                return await cursor.fetchone()

        return DatabaseAdapter(db_with_schema)

    @pytest.fixture
    def retention_service(self, db: Any) -> LogRetentionService:
        """Create retention service with trace retention config."""
        config = MockConfig(
            log_retention_days=30,
            trace_retention_days=7,
            checkpoint_retention_days=-1,  # Disable checkpoint cleanup
        )
        return LogRetentionService(db=db, config=config)

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_trace_events(
        self, retention_service: LogRetentionService, db: Any, sample_workflow: MagicMock
    ) -> None:
        """cleanup_on_shutdown deletes trace events older than retention."""
        old_timestamp = datetime.now(UTC) - timedelta(days=10)

        # Insert old trace event
        await db.execute(
            """
            INSERT INTO events (id, workflow_id, sequence, timestamp, agent, event_type, level, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("old-trace", sample_workflow.id, 1, old_timestamp.isoformat(),
             "developer", "claude_tool_call", "trace", "Old tool call"),
        )

        # Insert recent trace event
        await db.execute(
            """
            INSERT INTO events (id, workflow_id, sequence, timestamp, agent, event_type, level, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("new-trace", sample_workflow.id, 2, datetime.now(UTC).isoformat(),
             "developer", "claude_tool_call", "trace", "New tool call"),
        )

        result = await retention_service.cleanup_on_shutdown()

        # Old trace should be deleted, new trace should remain
        rows = await db.fetch_all("SELECT id FROM events WHERE level = 'trace'")
        event_ids = [r["id"] for r in rows]
        assert "old-trace" not in event_ids
        assert "new-trace" in event_ids
        assert result.trace_events_deleted >= 1

    @pytest.mark.asyncio
    async def test_cleanup_respects_trace_retention_days(
        self, db: Any, sample_workflow: MagicMock
    ) -> None:
        """Trace retention uses trace_retention_days, not log_retention_days."""
        # Config with different retention periods
        config = MockConfig(
            log_retention_days=30,
            trace_retention_days=3,
            checkpoint_retention_days=-1,
        )

        service = LogRetentionService(db=db, config=config)

        # Insert trace event 5 days old (older than trace retention, newer than log retention)
        old_timestamp = datetime.now(UTC) - timedelta(days=5)
        await db.execute(
            """
            INSERT INTO events (id, workflow_id, sequence, timestamp, agent, event_type, level, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("medium-age-trace", sample_workflow.id, 1, old_timestamp.isoformat(),
             "developer", "claude_tool_call", "trace", "Medium age"),
        )

        await service.cleanup_on_shutdown()

        # Should be deleted (older than 3 days trace retention)
        row = await db.fetch_one("SELECT id FROM events WHERE id = ?", ("medium-age-trace",))
        assert row is None

    @pytest.mark.asyncio
    async def test_cleanup_preserves_non_trace_events(
        self, retention_service: LogRetentionService, db: Any, sample_workflow: MagicMock
    ) -> None:
        """Trace cleanup should not affect non-trace events."""
        old_timestamp = datetime.now(UTC) - timedelta(days=10)

        # Insert old debug event (should NOT be deleted by trace cleanup)
        await db.execute(
            """
            INSERT INTO events (id, workflow_id, sequence, timestamp, agent, event_type, level, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("old-debug", sample_workflow.id, 1, old_timestamp.isoformat(),
             "developer", "status_update", "debug", "Old debug event"),
        )

        # Insert old trace event (should be deleted)
        await db.execute(
            """
            INSERT INTO events (id, workflow_id, sequence, timestamp, agent, event_type, level, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("old-trace", sample_workflow.id, 2, old_timestamp.isoformat(),
             "developer", "claude_tool_call", "trace", "Old trace event"),
        )

        result = await retention_service.cleanup_on_shutdown()

        # Debug event should remain, trace event should be deleted
        rows = await db.fetch_all("SELECT id, level FROM events")
        event_ids = [r["id"] for r in rows]
        assert "old-debug" in event_ids
        assert "old-trace" not in event_ids
        assert result.trace_events_deleted >= 1
