# tests/unit/server/database/test_brainstorm_schema.py
"""Tests for brainstorming database schema."""
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


_SESSION_UUID = "11111111-1111-1111-1111-111111111111"
_MSG1_UUID = "22222222-2222-2222-2222-222222222221"
_MSG2_UUID = "22222222-2222-2222-2222-222222222222"
_ART1_UUID = "33333333-3333-3333-3333-333333333331"


class TestBrainstormConstraints:
    """Tests for brainstorm table constraints."""

    async def test_unique_constraint_on_session_sequence(self, db_with_schema: Database) -> None:
        """(session_id, sequence) is unique in brainstorm_messages."""
        await db_with_schema.execute(f"""
            INSERT INTO brainstorm_sessions (id, profile_id, status, created_at, updated_at)
            VALUES ('{_SESSION_UUID}', 'profile-1', 'active', NOW(), NOW())
        """)
        await db_with_schema.execute(f"""
            INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
            VALUES ('{_MSG1_UUID}', '{_SESSION_UUID}', 1, 'user', 'Hello', NOW())
        """)
        with pytest.raises(asyncpg.exceptions.UniqueViolationError):
            await db_with_schema.execute(f"""
                INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
                VALUES ('{_MSG2_UUID}', '{_SESSION_UUID}', 1, 'assistant', 'Hi there', NOW())
            """)


_CASCADE_DELETE_CASES = [
    pytest.param(
        "brainstorm_messages",
        [
            f"INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at) VALUES ('{_MSG1_UUID}', '{_SESSION_UUID}', 1, 'user', 'Hello', NOW())",
            f"INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at) VALUES ('{_MSG2_UUID}', '{_SESSION_UUID}', 2, 'assistant', 'Hi', NOW())",
        ],
        2,
        id="messages",
    ),
    pytest.param(
        "brainstorm_artifacts",
        [
            f"INSERT INTO brainstorm_artifacts (id, session_id, type, path, title, created_at) VALUES ('{_ART1_UUID}', '{_SESSION_UUID}', 'spec', '/path/to/spec.md', 'Feature Spec', NOW())",
        ],
        1,
        id="artifacts",
    ),
]


class TestBrainstormCascadeDeletes:
    """Tests for cascade delete behavior."""

    async def _insert_session(self, db: Database, session_id: str = _SESSION_UUID) -> None:
        """Insert a brainstorm session for cascade tests."""
        await db.execute(f"""
            INSERT INTO brainstorm_sessions (id, profile_id, status, created_at, updated_at)
            VALUES ('{session_id}', 'profile-1', 'active', NOW(), NOW())
        """)

    @pytest.mark.parametrize("child_table,inserts,expected_count", _CASCADE_DELETE_CASES)
    async def test_deleting_session_cascades_to_children(
        self,
        db_with_schema: Database,
        child_table: str,
        inserts: list[str],
        expected_count: int,
    ) -> None:
        """Deleting a session cascades to delete its child rows."""
        await self._insert_session(db_with_schema)
        for stmt in inserts:
            await db_with_schema.execute(stmt)
        rows = await db_with_schema.fetch_all(
            f"SELECT id FROM {child_table} WHERE session_id = '{_SESSION_UUID}'"
        )
        assert len(rows) == expected_count
        await db_with_schema.execute(
            f"DELETE FROM brainstorm_sessions WHERE id = '{_SESSION_UUID}'"
        )
        rows = await db_with_schema.fetch_all(
            f"SELECT id FROM {child_table} WHERE session_id = '{_SESSION_UUID}'"
        )
        assert len(rows) == 0
