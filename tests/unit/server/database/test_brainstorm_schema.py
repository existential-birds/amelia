# tests/unit/server/database/test_brainstorm_schema.py
"""Tests for brainstorming database schema."""
import aiosqlite
import pytest

from amelia.server.database.connection import Database


class TestBrainstormSessionsTable:
    """Tests for brainstorm_sessions table schema."""

    async def test_table_exists(self, db_with_schema: Database) -> None:
        """brainstorm_sessions table exists."""
        tables = await db_with_schema.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='brainstorm_sessions'"
        )
        assert len(tables) == 1

    async def test_has_expected_columns(self, db_with_schema: Database) -> None:
        """brainstorm_sessions table has all expected columns."""
        columns = await db_with_schema.fetch_all("PRAGMA table_info(brainstorm_sessions)")
        column_names = [col["name"] for col in columns]

        expected_columns = [
            "id",
            "profile_id",
            "driver_session_id",
            "status",
            "topic",
            "created_at",
            "updated_at",
        ]
        for col in expected_columns:
            assert col in column_names, f"Missing column: {col}"

    async def test_profile_id_index_exists(self, db_with_schema: Database) -> None:
        """brainstorm_sessions has index on profile_id."""
        indexes = await db_with_schema.fetch_all("PRAGMA index_list(brainstorm_sessions)")
        index_names = [idx["name"] for idx in indexes]
        assert "idx_brainstorm_sessions_profile" in index_names

    async def test_status_index_exists(self, db_with_schema: Database) -> None:
        """brainstorm_sessions has index on status."""
        indexes = await db_with_schema.fetch_all("PRAGMA index_list(brainstorm_sessions)")
        index_names = [idx["name"] for idx in indexes]
        assert "idx_brainstorm_sessions_status" in index_names


class TestBrainstormMessagesTable:
    """Tests for brainstorm_messages table schema."""

    async def test_table_exists(self, db_with_schema: Database) -> None:
        """brainstorm_messages table exists."""
        tables = await db_with_schema.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='brainstorm_messages'"
        )
        assert len(tables) == 1

    async def test_has_expected_columns(self, db_with_schema: Database) -> None:
        """brainstorm_messages table has all expected columns."""
        columns = await db_with_schema.fetch_all("PRAGMA table_info(brainstorm_messages)")
        column_names = [col["name"] for col in columns]

        expected_columns = [
            "id",
            "session_id",
            "sequence",
            "role",
            "content",
            "parts_json",
            "created_at",
        ]
        for col in expected_columns:
            assert col in column_names, f"Missing column: {col}"

    async def test_session_sequence_index_exists(self, db_with_schema: Database) -> None:
        """brainstorm_messages has composite index on session_id and sequence."""
        indexes = await db_with_schema.fetch_all("PRAGMA index_list(brainstorm_messages)")
        index_names = [idx["name"] for idx in indexes]
        assert "idx_brainstorm_messages_session" in index_names

    async def test_unique_constraint_on_session_sequence(
        self, db_with_schema: Database
    ) -> None:
        """(session_id, sequence) is unique in brainstorm_messages."""
        # Create a session first
        await db_with_schema.execute("""
            INSERT INTO brainstorm_sessions (id, profile_id, status, created_at, updated_at)
            VALUES ('session-1', 'profile-1', 'active', datetime('now'), datetime('now'))
        """)

        # Insert first message
        await db_with_schema.execute("""
            INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
            VALUES ('msg-1', 'session-1', 1, 'user', 'Hello', datetime('now'))
        """)

        # Duplicate (session_id, sequence) should fail
        with pytest.raises(aiosqlite.IntegrityError):
            await db_with_schema.execute("""
                INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
                VALUES ('msg-2', 'session-1', 1, 'assistant', 'Hi there', datetime('now'))
            """)


class TestBrainstormArtifactsTable:
    """Tests for brainstorm_artifacts table schema."""

    async def test_table_exists(self, db_with_schema: Database) -> None:
        """brainstorm_artifacts table exists."""
        tables = await db_with_schema.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='brainstorm_artifacts'"
        )
        assert len(tables) == 1

    async def test_has_expected_columns(self, db_with_schema: Database) -> None:
        """brainstorm_artifacts table has all expected columns."""
        columns = await db_with_schema.fetch_all("PRAGMA table_info(brainstorm_artifacts)")
        column_names = [col["name"] for col in columns]

        expected_columns = [
            "id",
            "session_id",
            "type",
            "path",
            "title",
            "created_at",
        ]
        for col in expected_columns:
            assert col in column_names, f"Missing column: {col}"

    async def test_session_index_exists(self, db_with_schema: Database) -> None:
        """brainstorm_artifacts has index on session_id."""
        indexes = await db_with_schema.fetch_all("PRAGMA index_list(brainstorm_artifacts)")
        index_names = [idx["name"] for idx in indexes]
        assert "idx_brainstorm_artifacts_session" in index_names


class TestBrainstormCascadeDeletes:
    """Tests for cascade delete behavior."""

    async def test_deleting_session_deletes_messages(
        self, db_with_schema: Database
    ) -> None:
        """Deleting a session cascades to delete its messages."""
        # Create session
        await db_with_schema.execute("""
            INSERT INTO brainstorm_sessions (id, profile_id, status, created_at, updated_at)
            VALUES ('session-1', 'profile-1', 'active', datetime('now'), datetime('now'))
        """)

        # Create messages
        await db_with_schema.execute("""
            INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
            VALUES ('msg-1', 'session-1', 1, 'user', 'Hello', datetime('now'))
        """)
        await db_with_schema.execute("""
            INSERT INTO brainstorm_messages (id, session_id, sequence, role, content, created_at)
            VALUES ('msg-2', 'session-1', 2, 'assistant', 'Hi', datetime('now'))
        """)

        # Verify messages exist
        messages = await db_with_schema.fetch_all(
            "SELECT id FROM brainstorm_messages WHERE session_id = 'session-1'"
        )
        assert len(messages) == 2

        # Delete session
        await db_with_schema.execute("DELETE FROM brainstorm_sessions WHERE id = 'session-1'")

        # Messages should be gone
        messages = await db_with_schema.fetch_all(
            "SELECT id FROM brainstorm_messages WHERE session_id = 'session-1'"
        )
        assert len(messages) == 0

    async def test_deleting_session_deletes_artifacts(
        self, db_with_schema: Database
    ) -> None:
        """Deleting a session cascades to delete its artifacts."""
        # Create session
        await db_with_schema.execute("""
            INSERT INTO brainstorm_sessions (id, profile_id, status, created_at, updated_at)
            VALUES ('session-1', 'profile-1', 'active', datetime('now'), datetime('now'))
        """)

        # Create artifact
        await db_with_schema.execute("""
            INSERT INTO brainstorm_artifacts (id, session_id, type, path, title, created_at)
            VALUES ('art-1', 'session-1', 'spec', '/path/to/spec.md', 'Feature Spec', datetime('now'))
        """)

        # Verify artifact exists
        artifacts = await db_with_schema.fetch_all(
            "SELECT id FROM brainstorm_artifacts WHERE session_id = 'session-1'"
        )
        assert len(artifacts) == 1

        # Delete session
        await db_with_schema.execute("DELETE FROM brainstorm_sessions WHERE id = 'session-1'")

        # Artifact should be gone
        artifacts = await db_with_schema.fetch_all(
            "SELECT id FROM brainstorm_artifacts WHERE session_id = 'session-1'"
        )
        assert len(artifacts) == 0
