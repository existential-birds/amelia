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


class TestBrainstormSessionsTable:
    """Tests for brainstorm_sessions table schema."""

    async def test_table_exists(self, db_with_schema: Database) -> None:
        """brainstorm_sessions table exists."""
        assert await _table_exists(db_with_schema, "brainstorm_sessions") is True

    async def test_has_expected_columns(self, db_with_schema: Database) -> None:
        """brainstorm_sessions table has all expected columns."""
        columns = await _get_columns(db_with_schema, "brainstorm_sessions")
        expected = ["id", "profile_id", "driver_session_id", "driver_type", "status", "topic", "created_at", "updated_at"]
        for col in expected:
            assert col in columns, f"Missing column: {col}"

    async def test_profile_id_index_exists(self, db_with_schema: Database) -> None:
        """brainstorm_sessions has index on profile_id."""
        indexes = await _get_indexes(db_with_schema, "brainstorm_sessions")
        assert "idx_brainstorm_sessions_profile" in indexes

    async def test_status_index_exists(self, db_with_schema: Database) -> None:
        """brainstorm_sessions has index on status."""
        indexes = await _get_indexes(db_with_schema, "brainstorm_sessions")
        assert "idx_brainstorm_sessions_status" in indexes


class TestBrainstormMessagesTable:
    """Tests for brainstorm_messages table schema."""

    async def test_table_exists(self, db_with_schema: Database) -> None:
        """brainstorm_messages table exists."""
        assert await _table_exists(db_with_schema, "brainstorm_messages") is True

    async def test_has_expected_columns(self, db_with_schema: Database) -> None:
        """brainstorm_messages table has all expected columns."""
        columns = await _get_columns(db_with_schema, "brainstorm_messages")
        expected = ["id", "session_id", "sequence", "role", "content", "parts", "created_at"]
        for col in expected:
            assert col in columns, f"Missing column: {col}"

    async def test_session_sequence_index_exists(self, db_with_schema: Database) -> None:
        """brainstorm_messages has composite index on session_id and sequence."""
        indexes = await _get_indexes(db_with_schema, "brainstorm_messages")
        assert "idx_brainstorm_messages_session" in indexes

    async def test_unique_constraint_on_session_sequence(self, db_with_schema: Database) -> None:
        """(session_id, sequence) is unique in brainstorm_messages."""
        await db_with_schema.execute("""
            INSERT INTO brainstorm_sessions (id, profile_id, status, created_at, updated_at)
            VALUES ('session-1', 'profile-1', 'active', NOW(), NOW())
        """)
        await db_with_schema.execute("""
            INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
            VALUES ('msg-1', 'session-1', 1, 'user', 'Hello', NOW())
        """)
        with pytest.raises(asyncpg.exceptions.UniqueViolationError):
            await db_with_schema.execute("""
                INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
                VALUES ('msg-2', 'session-1', 1, 'assistant', 'Hi there', NOW())
            """)


class TestBrainstormArtifactsTable:
    """Tests for brainstorm_artifacts table schema."""

    async def test_table_exists(self, db_with_schema: Database) -> None:
        """brainstorm_artifacts table exists."""
        assert await _table_exists(db_with_schema, "brainstorm_artifacts") is True

    async def test_has_expected_columns(self, db_with_schema: Database) -> None:
        """brainstorm_artifacts table has all expected columns."""
        columns = await _get_columns(db_with_schema, "brainstorm_artifacts")
        expected = ["id", "session_id", "type", "path", "title", "created_at"]
        for col in expected:
            assert col in columns, f"Missing column: {col}"

    async def test_session_index_exists(self, db_with_schema: Database) -> None:
        """brainstorm_artifacts has index on session_id."""
        indexes = await _get_indexes(db_with_schema, "brainstorm_artifacts")
        assert "idx_brainstorm_artifacts_session" in indexes


class TestBrainstormCascadeDeletes:
    """Tests for cascade delete behavior."""

    async def test_deleting_session_deletes_messages(self, db_with_schema: Database) -> None:
        """Deleting a session cascades to delete its messages."""
        await db_with_schema.execute("""
            INSERT INTO brainstorm_sessions (id, profile_id, status, created_at, updated_at)
            VALUES ('session-1', 'profile-1', 'active', NOW(), NOW())
        """)
        await db_with_schema.execute("""
            INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
            VALUES ('msg-1', 'session-1', 1, 'user', 'Hello', NOW())
        """)
        await db_with_schema.execute("""
            INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
            VALUES ('msg-2', 'session-1', 2, 'assistant', 'Hi', NOW())
        """)
        messages = await db_with_schema.fetch_all(
            "SELECT id FROM brainstorm_messages WHERE session_id = 'session-1'"
        )
        assert len(messages) == 2
        await db_with_schema.execute("DELETE FROM brainstorm_sessions WHERE id = 'session-1'")
        messages = await db_with_schema.fetch_all(
            "SELECT id FROM brainstorm_messages WHERE session_id = 'session-1'"
        )
        assert len(messages) == 0

    async def test_deleting_session_deletes_artifacts(self, db_with_schema: Database) -> None:
        """Deleting a session cascades to delete its artifacts."""
        await db_with_schema.execute("""
            INSERT INTO brainstorm_sessions (id, profile_id, status, created_at, updated_at)
            VALUES ('session-1', 'profile-1', 'active', NOW(), NOW())
        """)
        await db_with_schema.execute("""
            INSERT INTO brainstorm_artifacts (id, session_id, type, path, title, created_at)
            VALUES ('art-1', 'session-1', 'spec', '/path/to/spec.md', 'Feature Spec', NOW())
        """)
        artifacts = await db_with_schema.fetch_all(
            "SELECT id FROM brainstorm_artifacts WHERE session_id = 'session-1'"
        )
        assert len(artifacts) == 1
        await db_with_schema.execute("DELETE FROM brainstorm_sessions WHERE id = 'session-1'")
        artifacts = await db_with_schema.fetch_all(
            "SELECT id FROM brainstorm_artifacts WHERE session_id = 'session-1'"
        )
        assert len(artifacts) == 0
