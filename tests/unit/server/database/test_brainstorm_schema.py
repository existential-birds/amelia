# tests/unit/server/database/test_brainstorm_schema.py
"""Tests for brainstorming database schema."""
from uuid import uuid4

import asyncpg
import pytest

from amelia.server.database.connection import Database


pytestmark = pytest.mark.integration


async def _get_columns(db: Database, table: str) -> list[str]:
    """Get column names for a table."""
    rows = await db.fetch_all(
        "SELECT column_name FROM information_schema.columns WHERE table_name = $1 ORDER BY ordinal_position",
        table,
    )
    return [row["column_name"] for row in rows]


async def _get_indexes(db: Database, table: str) -> list[str]:
    """Get index names for a table."""
    rows = await db.fetch_all(
        "SELECT indexname FROM pg_indexes WHERE tablename = $1",
        table,
    )
    return [row["indexname"] for row in rows]


async def _table_exists(db: Database, table: str) -> bool:
    """Check if a table exists."""
    row = await db.fetch_one(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)",
        table,
    )
    return row[0] if row else False


# --- Parametrized schema checks across all brainstorm tables ---

_TABLE_COLUMNS = {
    "brainstorm_sessions": ["id", "profile_id", "driver_session_id", "driver_type", "status", "topic", "created_at", "updated_at"],
    "brainstorm_messages": ["id", "session_id", "sequence", "role", "content", "parts", "created_at"],
    "brainstorm_artifacts": ["id", "session_id", "type", "path", "title", "created_at"],
}

_TABLE_INDEXES = {
    "brainstorm_sessions": [
        "idx_brainstorm_sessions_profile",
        "idx_brainstorm_sessions_status",
    ],
    "brainstorm_messages": ["idx_brainstorm_messages_session"],
    "brainstorm_artifacts": ["idx_brainstorm_artifacts_session"],
}


class TestBrainstormTables:
    """Tests for brainstorm table schemas."""

    @pytest.mark.parametrize("table", list(_TABLE_COLUMNS))
    async def test_table_exists(self, db_with_schema: Database, table: str) -> None:
        """Brainstorm table exists after migration."""
        assert await _table_exists(db_with_schema, table) is True

    @pytest.mark.parametrize(
        "table,expected_columns",
        list(_TABLE_COLUMNS.items()),
    )
    async def test_has_expected_columns(
        self, db_with_schema: Database, table: str, expected_columns: list[str]
    ) -> None:
        """Brainstorm table has all expected columns."""
        columns = await _get_columns(db_with_schema, table)
        for col in expected_columns:
            assert col in columns, f"Missing column {col!r} in {table}"

    @pytest.mark.parametrize(
        "table,expected_index",
        [
            (table, index)
            for table, indexes in _TABLE_INDEXES.items()
            for index in indexes
        ],
    )
    async def test_index_exists(
        self, db_with_schema: Database, table: str, expected_index: str
    ) -> None:
        """Brainstorm table has expected index."""
        indexes = await _get_indexes(db_with_schema, table)
        assert expected_index in indexes


class TestBrainstormConstraints:
    """Tests for brainstorm table constraints."""

    async def test_unique_constraint_on_session_sequence(self, db_with_schema: Database) -> None:
        """(session_id, sequence) is unique in brainstorm_messages."""
        session_id = uuid4()
        msg_1_id = uuid4()
        msg_2_id = uuid4()
        await db_with_schema.execute(
            """
            INSERT INTO brainstorm_sessions (id, profile_id, status, created_at, updated_at)
            VALUES ($1, 'profile-1', 'active', NOW(), NOW())
            """,
            session_id,
        )
        await db_with_schema.execute(
            """
            INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
            VALUES ($1, $2, 1, 'user', 'Hello', NOW())
            """,
            msg_1_id,
            session_id,
        )
        with pytest.raises(asyncpg.exceptions.UniqueViolationError):
            await db_with_schema.execute(
                """
                INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
                VALUES ($1, $2, 1, 'assistant', 'Hi there', NOW())
                """,
                msg_2_id,
                session_id,
            )


def _message_inserts(session_id: object) -> list[tuple[str, list[object]]]:
    """Build parametrized inserts for two brainstorm messages."""
    return [
        (
            "INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at) VALUES ($1, $2, 1, 'user', 'Hello', NOW())",
            [uuid4(), session_id],
        ),
        (
            "INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at) VALUES ($1, $2, 2, 'assistant', 'Hi', NOW())",
            [uuid4(), session_id],
        ),
    ]


def _artifact_inserts(session_id: object) -> list[tuple[str, list[object]]]:
    """Build parametrized inserts for a brainstorm artifact."""
    return [
        (
            "INSERT INTO brainstorm_artifacts (id, session_id, type, path, title, created_at) VALUES ($1, $2, 'spec', '/path/to/spec.md', 'Feature Spec', NOW())",
            [uuid4(), session_id],
        ),
    ]


_CASCADE_DELETE_CASES = [
    pytest.param("brainstorm_messages", _message_inserts, 2, id="messages"),
    pytest.param("brainstorm_artifacts", _artifact_inserts, 1, id="artifacts"),
]


class TestBrainstormCascadeDeletes:
    """Tests for cascade delete behavior."""

    async def _insert_session(self, db: Database, session_id: object) -> None:
        """Insert a brainstorm session for cascade tests."""
        await db.execute(
            """
            INSERT INTO brainstorm_sessions (id, profile_id, status, created_at, updated_at)
            VALUES ($1, 'profile-1', 'active', NOW(), NOW())
            """,
            session_id,
        )

    @pytest.mark.parametrize("child_table,build_inserts,expected_count", _CASCADE_DELETE_CASES)
    async def test_deleting_session_cascades_to_children(
        self,
        db_with_schema: Database,
        child_table: str,
        build_inserts: object,
        expected_count: int,
    ) -> None:
        """Deleting a session cascades to delete its child rows."""
        session_id = uuid4()
        await self._insert_session(db_with_schema, session_id)
        for stmt, params in build_inserts(session_id):  # type: ignore[operator]
            await db_with_schema.execute(stmt, *params)
        rows = await db_with_schema.fetch_all(
            f"SELECT id FROM {child_table} WHERE session_id = $1",
            session_id,
        )
        assert len(rows) == expected_count
        await db_with_schema.execute(
            "DELETE FROM brainstorm_sessions WHERE id = $1",
            session_id,
        )
        rows = await db_with_schema.fetch_all(
            f"SELECT id FROM {child_table} WHERE session_id = $1",
            session_id,
        )
        assert len(rows) == 0
